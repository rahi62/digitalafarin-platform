import os
import shutil
import subprocess
import sys
import tempfile
import types
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
if "psutil" not in sys.modules:
    sys.modules["psutil"] = types.SimpleNamespace(virtual_memory=lambda: None)

from control.models import (
    AgentCredential,
    DatabaseResource,
    Deployment,
    EnrollmentToken,
    EnvironmentVariable,
    Operation,
    Project,
    Server,
    Service,
    ServiceCredential,
    ServicePrincipal,
    Volume,
)
from control.security import issue_secret
from control.services.deployments import DeploymentAdmissionError, deployment_admission
from digitalafarin_agent.bootstrap import bootstrap_server
from digitalafarin_agent.deployment import deploy_release, rollback_release
from digitalafarin_agent.operations import execute_operation
from digitalafarin_agent.postgres import restore_database
from digitalafarin_agent.volumes import create_volume


class FixtureExecutor:
    def __init__(self):
        self.restarts = []

    def recipe_commands(self, runtime, install_configuration, build_configuration, root_directory):
        return [["node", "build.mjs"]]

    def run_commands(self, commands, cwd, environment, known_secrets):
        for command in commands:
            subprocess.run(
                command,
                cwd=cwd,
                env={**os.environ, **environment},
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
                shell=False,
            )

    def restart(self, unit_name):
        self.restarts.append(unit_name)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        shell=False,
    ).stdout.strip()


class MigrationReadinessAcceptance(TestCase):
    def setUp(self):
        self.old_keys = os.environ.get("PLATFORM_SECRET_KEYS")
        os.environ["PLATFORM_SECRET_KEYS"] = Fernet.generate_key().decode()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()
        if self.old_keys is None:
            os.environ.pop("PLATFORM_SECRET_KEYS", None)
        else:
            os.environ["PLATFORM_SECRET_KEYS"] = self.old_keys

    def test_complete_safe_migration_fixture(self):
        # 1. Enroll a fresh outbound-only server and 2. heartbeat/readiness.
        enrollment = issue_secret("enroll")
        EnrollmentToken.objects.create(
            token_prefix=enrollment.prefix,
            secret_hash=enrollment.digest,
            expires_at=timezone.now() + timedelta(minutes=5),
            created_by="acceptance",
        )
        agent_api = APIClient()
        enrolled = agent_api.post(
            "/api/agent/v1/enroll",
            {"name": "Fixture VPS", "hostname": "fixture", "agent_version": "0.3.0", "capabilities": ["typed_operations"]},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {enrollment.cleartext}",
        )
        self.assertEqual(enrolled.status_code, 201)
        server = Server.objects.get(public_id=enrolled.json()["server_id"])
        heartbeat = agent_api.post(
            "/api/agent/v1/heartbeat",
            {
                "agent_version": "0.3.0", "hostname": "fixture", "capabilities": ["typed_operations"],
                "metrics": {"cpu_percent": 5, "memory_percent": 10, "disk_percent": 20, "uptime_seconds": 100},
                "services": [],
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {enrolled.json()['agent_token']}",
        )
        self.assertEqual(heartbeat.status_code, 204)
        with patch("digitalafarin_agent.bootstrap.platform.freedesktop_os_release", return_value={"ID": "ubuntu", "VERSION_ID": "24.04"}), patch(
            "digitalafarin_agent.bootstrap.shutil.which", return_value="/usr/bin/tool"
        ), patch("digitalafarin_agent.bootstrap.psutil.virtual_memory") as memory, patch(
            "digitalafarin_agent.bootstrap.shutil.disk_usage"
        ) as disk:
            memory.return_value.total = 4 * 1024**3
            disk.return_value = type("Disk", (), {"total": 100, "used": 20, "free": 80})()
            self.assertEqual(bootstrap_server({}, srv_root=self.root / "srv")["overall"], "ready")
            self.assertEqual(bootstrap_server({}, srv_root=self.root / "srv")["overall"], "ready")

        # Create an operator and 3. project, 4. service, 5/6. plain+secret variables.
        principal = ServicePrincipal.objects.create(
            name="acceptance-ui", scopes=["operations:read", "operations:create", "logs:read"]
        )
        service_secret = issue_secret("service")
        ServiceCredential.objects.create(principal=principal, token_prefix=service_secret.prefix, token_hash=service_secret.digest)
        control = APIClient()
        control.credentials(HTTP_AUTHORIZATION=f"Bearer {service_secret.cleartext}")
        project_response = control.post("/api/control/v1/projects/", {"name": "Oily", "slug": "oily"}, format="json")
        project_id = project_response.json()["id"]
        service_response = control.post(
            f"/api/control/v1/projects/{project_id}/services/",
            {
                "name": "web", "executor": "systemd", "repository": "https://github.com/example/fixture.git",
                "branch": "master", "root_directory": ".", "runtime": "node-nextjs",
                "install_configuration": {"package_manager": "npm", "lockfile": False},
                "build_configuration": {"build_script": "build"}, "service_port": 3000,
                "target_server_id": str(server.public_id),
            },
            format="json",
        )
        self.assertEqual(service_response.status_code, 201)
        service = Service.objects.get(public_id=service_response.json()["id"])
        for key, value, value_type in (("APP_MODE", "production", "plain"), ("APP_SECRET", "acceptance-sentinel", "secret")):
            response = control.post(
                f"/api/control/v1/projects/{project_id}/variables/",
                {"key": key, "value": value, "value_type": value_type, "scope": "service", "service_id": str(service.public_id)},
                format="json",
            )
            self.assertEqual(response.status_code, 201)
            self.assertNotIn("acceptance-sentinel", str(response.json()))

        # 7/14. Create a persistent volume and sentinel outside releases.
        volume_response = control.post(
            f"/api/control/v1/projects/{project_id}/volumes/",
            {"name": "media", "service_id": str(service.public_id), "mount_path": "/data", "owner": "deploy", "group": "deploy", "mode": "0750", "backup_policy": "daily"},
            format="json",
        )
        volume_root = self.root / "srv" / "digitalafarin" / "volumes"
        with patch("digitalafarin_agent.volumes.shutil.chown"):
            created_volume = create_volume(
                {"project_slug": "oily", "name": "media", "owner": "deploy", "group": "deploy", "mode": "0750"},
                base_path=volume_root,
            )
        volume_path = Path(created_volume["host_path"])
        (volume_path / "persistent.txt").write_text("survives", encoding="utf-8")
        volume = Volume.objects.get(public_id=volume_response.json()["id"])
        volume.host_path = str(volume_path)
        volume.save(update_fields=["host_path"])

        # 15. Create database resource and exercise managed restore path.
        database_response = control.post(
            f"/api/control/v1/projects/{project_id}/databases/",
            {"service_id": str(service.public_id), "database_name": "oily", "username": "oily_app"},
            format="json",
        )
        self.assertEqual(database_response.status_code, 201)
        backup_root = self.root / "srv" / "digitalafarin" / "backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        (backup_root / "oily.dump").write_bytes(b"safe fixture")
        with patch("digitalafarin_agent.postgres.subprocess.run") as database_run:
            database_run.return_value = type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            self.assertTrue(restore_database({"database_name": "oily", "username": "oily_app", "backup_name": "oily.dump"}, backup_root=backup_root)["restored"])

        # Build a real Git repository for 8-13 deploy/redeploy/health/activate/rollback.
        repository = self.root / "repository"
        shutil.copytree(ROOT / "acceptance" / "fixtures" / "sample-node", repository)
        git(repository, "init")
        git(repository, "config", "user.name", "Acceptance Fixture")
        git(repository, "config", "user.email", "fixture@example.invalid")
        git(repository, "add", ".")
        git(repository, "commit", "-m", "fixture")
        commit = git(repository, "rev-parse", "HEAD")
        service.repository = str(repository)
        service.save(update_fields=["repository"])
        apps_root = self.root / "srv" / "digitalafarin" / "apps"
        executor = FixtureExecutor()
        payload = {
            "deployment_id": "fixture-deployment", "project_slug": "oily", "service_name": "web",
            "repository": str(repository), "requested_ref": "master", "exact_commit": commit,
            "runtime": "node-nextjs", "install_configuration": {}, "build_configuration": {},
            "root_directory": ".", "unit_name": "oily-web.service",
            "environment": {"APP_SECRET": "acceptance-sentinel"},
            "volumes": [{"host_path": str(volume_path), "mount_path": "/data"}],
            "health_check": {"url": "http://127.0.0.1:3000/health", "expected_status": 200},
        }
        with patch("digitalafarin_agent.deployment.check_http_health", return_value={"attempts": 1, "status": 200}):
            first = deploy_release(payload, apps_root=apps_root, executor=executor)
            first_path = apps_root / "oily" / "web" / "releases" / first["release_name"]
            second = deploy_release(payload, apps_root=apps_root, executor=executor)
            rollback_release(
                {
                    "deployment_id": "rollback", "service_root": str(apps_root / "oily" / "web"),
                    "release_path": str(first_path), "exact_commit": commit,
                    "unit_name": "oily-web.service", "health_check": payload["health_check"],
                },
                executor=executor,
            )
        self.assertEqual(first["final_state"], "succeeded")
        self.assertEqual(second["final_state"], "succeeded")
        self.assertEqual((apps_root / "oily" / "web" / "current").resolve(), first_path.resolve())
        self.assertEqual((volume_path / "persistent.txt").read_text(encoding="utf-8"), "survives")

        # 16/17. Bounded logs are returned with secret redaction.
        with patch("digitalafarin_agent.operations.subprocess.run") as journal:
            journal.return_value = type("Result", (), {"returncode": 0, "stdout": "Authorization: Bearer acceptance-sentinel\n", "stderr": ""})()
            logs = execute_operation("service.logs", {"unit_name": "oily-web.service", "lines": 50, "since_seconds": 3600})
        self.assertNotIn("acceptance-sentinel", logs["logs"])

        # 18. Both disk thresholds are enforced from fresh telemetry.
        server.refresh_from_db()
        server.disk_percent = 80
        server.save(update_fields=["disk_percent"])
        self.assertTrue(deployment_admission(server)["warning"])
        server.disk_percent = 90
        server.save(update_fields=["disk_percent"])
        with self.assertRaises(DeploymentAdmissionError):
            deployment_admission(server)

        project_view = control.get(f"/api/control/v1/projects/{project_id}/")
        self.assertEqual(project_view.status_code, 200)
        self.assertNotIn("acceptance-sentinel", str(project_view.json()))
