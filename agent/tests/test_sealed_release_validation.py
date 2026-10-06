import os
import stat
from pathlib import Path

import pytest

from digitalafarin_agent import takeover_helper as helper
from test_takeover_helper import ALLOWED_BINDINGS, _prepare_params
from test_takeover import snapshot


@pytest.fixture
def prepared_tree(tmp_path, monkeypatch):
    """Use real files and sealing; emulate chown for unprivileged unit tests."""
    owners = {}
    real_stat = Path.stat

    def chown(path, uid, gid, **kwargs):
        owners[Path(path)] = (uid, gid)

    def owned_stat(path, **kwargs):
        result = real_stat(path, **kwargs)
        if path in owners:
            fields = list(result)
            fields[4:6] = owners[path]
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(helper.os, "chown", chown)
    monkeypatch.setattr(Path, "stat", owned_stat)
    monkeypatch.setattr(helper, "_account", lambda _u: type("Account", (), {"pw_uid": 1000, "pw_gid": 33})())
    monkeypatch.setattr(helper, "_group_id", lambda *_a: 33)
    monkeypatch.setattr(helper, "inspect_service", lambda _u: snapshot())
    monkeypatch.setattr(helper, "_trusted_local_source_repository", lambda *_a: tmp_path / "source")
    monkeypatch.setattr(helper, "_run_as_worker", lambda *_a, **_k: None)
    allocated = []

    def prepare(*args, **kwargs):
        release = kwargs["destination"]
        allocated.append(release)
        (release / ".git").mkdir()
        (release / ".git/HEAD").write_text("a" * 40 + "\n")
        cwd = release / "apps/web"
        (cwd / ".next" / "standalone").mkdir(parents=True)
        (cwd / ".next" / "static").mkdir(parents=True)
        (cwd / ".next" / "standalone" / "server.js").write_text("server")
        (cwd / "package.json").write_text("{}")
        (cwd / "package-lock.json").write_text("{}")
        return release

    monkeypatch.setattr(helper, "prepare_release", prepare)
    yield tmp_path / "apps", allocated
    for release in allocated:
        if release.exists():
            for root, dirs, files in os.walk(release):
                Path(root).chmod(0o750)


def test_helper_returns_verified_sealed_release_metadata(prepared_tree):
    apps_root, allocated = prepared_tree
    result = helper.prepare_node_nextjs_release(
        _prepare_params(), allowed_bindings=ALLOWED_BINDINGS, apps_root=apps_root
    )
    release = allocated[0]
    assert result == {
        "release_name": release.name,
        "release_path": str(release),
        "resolved_commit": "a" * 40,
        "source_snapshot": snapshot(),
        "source_fingerprint": helper.fingerprint_snapshot(snapshot()),
    }
    assert (release.stat().st_uid, release.stat().st_gid) == (0, 33)
    assert stat.S_IMODE(release.stat().st_mode) == 0o550
    assert not (release.parent.parent / "current").exists()


@pytest.mark.parametrize("artifact", ["package.json", "package-lock.json", ".next"])
def test_helper_rejects_missing_build_artifact(prepared_tree, monkeypatch, artifact):
    apps_root, allocated = prepared_tree
    def build(*args, **kwargs):
        path = allocated[0] / "apps/web" / artifact
        if path.is_dir():
            path.rmdir()
        elif path.exists():
            path.unlink()
    monkeypatch.setattr(helper, "_run_as_worker", build)
    with pytest.raises(helper.TakeoverHelperDomainError) as exc:
        helper.prepare_node_nextjs_release(_prepare_params(), allowed_bindings=ALLOWED_BINDINGS, apps_root=apps_root)
    assert exc.value.code == "release_validation_failed"
    assert not allocated[0].exists()


@pytest.mark.parametrize("kind", ["commit", "package_symlink", "root_symlink", "tree_symlink", "release_symlink", "unsealed", "head_fifo", "head_oversized", "head_uppercase"])
def test_helper_rejects_invalid_built_release(prepared_tree, monkeypatch, kind, tmp_path):
    apps_root, allocated = prepared_tree
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "package.json").write_text("{}")

    real_open = Path.open
    def safe_open(path, *args, **kwargs):
        if path.name == "HEAD" and path.exists() and stat.S_ISFIFO(path.lstat().st_mode):
            raise AssertionError("Helper attempted to read a FIFO")
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", safe_open)

    def build(*args, **kwargs):
        release = allocated[0]
        if kind == "head_fifo":
            head = release / ".git/HEAD"
            if not stat.S_ISFIFO(head.lstat().st_mode):
                head.unlink()
                os.mkfifo(head)
        elif kind == "head_oversized":
            (release / ".git/HEAD").write_text("a" * 40 + " " * 1000)
        elif kind == "head_uppercase":
            (release / ".git/HEAD").write_text("A" * 40 + "\n")
        elif kind == "commit":
            (release / ".git/HEAD").write_text("b" * 40 + "\n")
        elif kind == "package_symlink":
            path = release / "apps/web/package.json"
            if not path.is_symlink():
                path.unlink()
                path.symlink_to(outside / "package.json")
        elif kind == "root_symlink":
            path = release / "apps/web"
            if not path.is_symlink():
                path.rename(release / "original-web")
                path.symlink_to(outside, target_is_directory=True)
        elif kind == "tree_symlink":
            path = release / "escape"
            if not path.is_symlink():
                path.symlink_to(outside, target_is_directory=True)
        elif kind == "release_symlink":
            if not release.is_symlink():
                release.rename(release.parent / "moved")
                release.symlink_to(release.parent / "moved", target_is_directory=True)

    monkeypatch.setattr(helper, "_run_as_worker", build)
    if kind == "unsealed":
        monkeypatch.setattr(helper, "_seal_release", lambda *_a, **_k: None)
    with pytest.raises(helper.TakeoverHelperDomainError) as exc:
        helper.prepare_node_nextjs_release(_prepare_params(), allowed_bindings=ALLOWED_BINDINGS, apps_root=apps_root)
    assert exc.value.code == "release_validation_failed"
