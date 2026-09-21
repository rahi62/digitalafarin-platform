#!/usr/bin/python3
"""Exercise Helper validation and Agent PREPARE with real sealed permissions.

Git/build output is a tiny fixture; identity changes use real isolated systemd
workers. No production service, lifecycle record, or release is modified.
"""
import argparse
import json
import os
import stat
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from digitalafarin_agent import takeover, takeover_helper
from digitalafarin_agent.takeover_worker import run_takeover_worker


UNIT = "digitalafarin-sealed-integration.service"
COMMIT = "a" * 40


def agent_check(manifest: Path) -> None:
    data = json.loads(manifest.read_text())
    release = Path(data["prepared"]["release_path"])
    assert os.getuid() != 0
    assert not os.access(release, os.X_OK)
    try:
        (release / "apps/web/package.json").read_text()
    except PermissionError:
        pass
    else:
        raise AssertionError("Agent can read the sealed release")

    class PreparedHelper:
        def prepare_node_nextjs_release(self, params):
            return data["prepared"]

    with patch.object(takeover, "inspect_service", return_value=data["snapshot"]):
        result = takeover.prepare_service_takeover(
            data["payload"], apps_root=Path(data["apps_root"]), helper_client=PreparedHelper()
        )
    assert result["final_state"] == "prepared"
    assert result["resolved_commit"] == COMMIT
    assert result["source_snapshot"] == data["snapshot"]
    print(json.dumps({"agent_traverse": False, "agent_read": False, "prepare": "prepared"}), flush=True)


def helper_check(root: Path, user: str, group: str) -> None:
    assert os.getuid() == 0
    assert "NoNewPrivs:\t1" in Path("/proc/self/status").read_text()
    snapshot = {"unit_name": UNIT, "user": user, "group": group}
    params = {
        "project_slug": "integration", "service_name": "web", "unit_name": UNIT,
        "repository": "https://example.com/integration.git", "exact_commit": COMMIT,
        "root_directory": "apps/web", "install_configuration": {},
        "build_configuration": {}, "user": user, "group": group,
    }
    apps_root = root / "apps"

    def build_fixture(*args, **kwargs):
        release = kwargs["destination"]
        (release / ".git").mkdir()
        (release / ".git/HEAD").write_text(COMMIT + "\n")
        cwd = release / "apps/web"
        (cwd / ".next").mkdir(parents=True)
        (cwd / "package.json").write_text("{}")
        (cwd / "package-lock.json").write_text("{}")
        return release

    with (
        patch.object(takeover_helper, "inspect_service", return_value=snapshot),
        patch.object(takeover_helper, "_trusted_local_source_repository", return_value=root),
        patch.object(takeover_helper, "prepare_release", side_effect=build_fixture),
        patch.object(takeover_helper, "_run_as_worker"),
    ):
        prepared = takeover_helper.prepare_node_nextjs_release(
            params, allowed_bindings={("integration", "web", UNIT)}, apps_root=apps_root
        )
    release = Path(prepared["release_path"])
    info = release.stat()
    assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (0, 0, 0o550)
    payload = {key: value for key, value in params.items() if key not in {"user", "group"}}
    payload.update({
        "takeover_id": "11111111-1111-1111-1111-111111111111",
        "service_id": "22222222-2222-2222-2222-222222222222",
        "runtime": "node-nextjs", "service_port": 9751, "health_check": {},
    })
    manifest = root / "prepared.json"
    manifest.write_text(json.dumps({
        "prepared": prepared, "snapshot": snapshot, "payload": payload, "apps_root": str(apps_root),
    }))
    manifest.chmod(0o644)
    output = run_takeover_worker(
        phase="integration_sealed_agent", user="digitalafarin-agent", group="digitalafarin-agent",
        argv=[sys.executable, str(Path(__file__).resolve()), "--agent-check", str(manifest)],
        timeout=30,
    )
    assert json.loads(output) == {"agent_traverse": False, "agent_read": False, "prepare": "prepared"}
    assert not (release.parent.parent / "current").exists()
    assert not takeover.managed_dropin_path(UNIT).exists()
    assert (release.stat().st_uid, release.stat().st_gid, stat.S_IMODE(release.stat().st_mode)) == (0, 0, 0o550)
    print(output, flush=True)
    print("SEALED RELEASE SYSTEMD INTEGRATION: PASS", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-check", type=Path)
    parser.add_argument("--allocation-root", type=Path)
    parser.add_argument("--user", default="deploy")
    parser.add_argument("--group", default="www-data")
    args = parser.parse_args()
    if args.agent_check:
        agent_check(args.agent_check)
    else:
        helper_check(args.allocation_root, args.user, args.group)
