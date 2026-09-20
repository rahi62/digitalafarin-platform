from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from control.models import Deployment, Project, Release, Server, Service, ServiceTakeover


class TakeoverModelTests(TestCase):
    def setUp(self):
        self.server = Server.objects.create(
            name="Target",
            last_seen_at=timezone.now(),
            disk_percent=25,
        )
        self.project = Project.objects.create(name="Platform", slug="platform")
        self.service = Service.objects.create(
            project=self.project,
            name="web",
            executor=Service.EXECUTOR_SYSTEMD,
            unit_name="digitalafarin-platform-web.service",
            lifecycle_state=Service.LIFECYCLE_CONFIGURED,
            repository="https://github.com/example/platform.git",
            branch="main",
            root_directory="apps/web",
            runtime=Service.RUNTIME_NODE,
            install_configuration={"package_manager": "npm", "lockfile": "package-lock.json"},
            build_configuration={"build_script": "build"},
            service_port=9751,
            target_server=self.server,
        )

    def takeover(self, *, state=ServiceTakeover.STATE_QUEUED, commit="a" * 40):
        return ServiceTakeover.objects.create(
            service=self.service,
            state=state,
            requested_commit=commit,
            requested_by="operator",
            health_check_snapshot={
                "url": "http://127.0.0.1:9751/",
                "expected_status": 200,
                "attempts": 6,
                "timeout_seconds": 10,
                "interval_seconds": 5,
            },
        )

    def test_only_one_active_takeover_is_allowed_per_service(self):
        self.takeover()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.takeover(commit="b" * 40)

    def test_terminal_takeover_allows_a_new_takeover(self):
        self.takeover(state=ServiceTakeover.STATE_FAILED)
        second = self.takeover(commit="b" * 40)
        self.assertEqual(second.state, ServiceTakeover.STATE_QUEUED)

    def test_release_requires_exactly_one_provenance_source(self):
        takeover = self.takeover(state=ServiceTakeover.STATE_SUCCEEDED)
        deployment = Deployment.objects.create(
            service=self.service,
            requested_ref="main",
            resolved_commit="b" * 40,
            requested_by="operator",
            state="succeeded",
        )

        takeover_release = Release.objects.create(
            service=self.service,
            takeover=takeover,
            name="20260920-120000-aaaaaaa",
            exact_commit="a" * 40,
            path="/srv/digitalafarin/apps/platform/web/releases/20260920-120000-aaaaaaa",
        )
        self.assertIsNone(takeover_release.deployment_id)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Release.objects.create(
                    service=self.service,
                    deployment=deployment,
                    takeover=takeover,
                    name="invalid-both",
                    exact_commit="c" * 40,
                    path="/srv/digitalafarin/apps/platform/web/releases/invalid-both",
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Release.objects.create(
                    service=self.service,
                    name="invalid-neither",
                    exact_commit="d" * 40,
                    path="/srv/digitalafarin/apps/platform/web/releases/invalid-neither",
                )
