#!/usr/bin/python3
import argparse
import grp
import json
import os
import pwd
import stat
import sys
from pathlib import Path

from digitalafarin_agent.takeover_worker import run_takeover_worker


def _status_value(name: str) -> str:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError(f"missing /proc status field: {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--user", default="deploy")
    parser.add_argument("--group", default="www-data")
    parser.add_argument("--allocation-root", required=True, type=Path)
    args = parser.parse_args()

    if _status_value("NoNewPrivs") != "1":
        raise RuntimeError("helper probe is not running with NoNewPrivileges")

    head = run_takeover_worker(
        phase="integration_source_verify",
        user=args.user,
        group=args.group,
        argv=["git", "-C", str(args.repo.resolve(strict=True)), "rev-parse", "HEAD"],
        timeout=30,
    )
    identity_program = (
        "import json,os,pathlib;"
        "s=dict(line.split(':',1) for line in "
        "pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line);"
        "print(json.dumps({'uid':os.getuid(),'gid':os.getgid(),"
        "'groups':os.getgroups(),'no_new_privs':s['NoNewPrivs'].strip(),"
        "'cap_eff':s['CapEff'].strip()}))"
    )
    identity = json.loads(
        run_takeover_worker(
            phase="integration_identity",
            user=args.user,
            group=args.group,
            argv=[sys.executable, "-c", identity_program],
            timeout=30,
        )
    )
    expected_user = pwd.getpwnam(args.user)
    expected_group = grp.getgrnam(args.group)
    sudo_gid = grp.getgrnam("sudo").gr_gid
    print(json.dumps({"head": head, "identity": identity}, sort_keys=True), flush=True)
    assert identity["uid"] == expected_user.pw_uid
    assert identity["gid"] == expected_group.gr_gid
    assert sudo_gid not in identity["groups"]
    assert set(identity["groups"]).issubset({expected_group.gr_gid, 65534})
    assert identity["no_new_privs"] == "1"
    assert int(identity["cap_eff"], 16) == 0

    releases = args.allocation_root.resolve(strict=True) / "releases"
    releases.mkdir(mode=0o755)
    release = releases / "preallocated-release"
    release.mkdir(mode=0o750)
    os.chown(release, expected_user.pw_uid, expected_group.gr_gid)
    release.chmod(0o750)
    assert list(release.iterdir()) == []
    assert stat.S_IMODE(releases.stat().st_mode) == 0o755
    assert stat.S_IMODE(releases.stat().st_mode) & 0o022 == 0

    run_takeover_worker(
        phase="integration_release_git",
        user=args.user,
        group=args.group,
        argv=[
            "git",
            "clone",
            "--no-checkout",
            "--",
            str(args.repo.resolve(strict=True)),
            str(release),
        ],
        writable_path=release,
        timeout=60,
    )
    assert (release / ".git").is_dir()
    assert stat.S_IMODE(releases.stat().st_mode) == 0o755
    print(
        json.dumps(
            {
                "preallocated_release": str(release),
                "release_owner": release.stat().st_uid,
                "release_group": release.stat().st_gid,
                "release_mode": oct(stat.S_IMODE(release.stat().st_mode)),
                "parent_mode": oct(stat.S_IMODE(releases.stat().st_mode)),
                "clone_succeeded": True,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
