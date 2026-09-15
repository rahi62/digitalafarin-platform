import subprocess
from pathlib import Path

from digitalafarin_agent.releases import atomic_activate, cleanup_releases, prepare_release, resolve_exact_commit, rollback


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def make_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "source"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "user.name", "Fixture")
    (repo / "version.txt").write_text("one", encoding="utf-8")
    git(repo, "add", "version.txt")
    git(repo, "commit", "-m", "one")
    first = git(repo, "rev-parse", "HEAD")
    (repo / "version.txt").write_text("two", encoding="utf-8")
    git(repo, "commit", "-am", "two")
    return repo, first, git(repo, "rev-parse", "HEAD")


def test_prepare_release_checks_out_exact_commit_before_activation(tmp_path):
    repo, first, _second = make_repo(tmp_path)
    apps = tmp_path / "apps"

    release = prepare_release("oily", "web", str(repo), first, apps_root=apps, timestamp="20260915-183015")

    assert (release / "version.txt").read_text(encoding="utf-8") == "one"
    assert release.name == f"20260915-183015-{first[:7]}"
    assert not (apps / "oily" / "web" / "current").exists()


def test_resolve_exact_commit_resolves_branch_once(tmp_path):
    repo, _first, second = make_repo(tmp_path)

    resolved = resolve_exact_commit(str(repo), "master")

    assert resolved == second


def test_atomic_activation_and_rollback_only_switch_symlink(tmp_path):
    root = tmp_path / "apps" / "oily" / "web"
    first = root / "releases" / "first"
    second = root / "releases" / "second"
    first.mkdir(parents=True)
    second.mkdir()
    (first / "build.txt").write_text("first-build", encoding="utf-8")

    assert atomic_activate(root, first) is None
    previous = atomic_activate(root, second)
    rollback(root, previous)

    assert (root / "current").resolve() == first.resolve()
    assert (first / "build.txt").read_text(encoding="utf-8") == "first-build"


def test_cleanup_retains_five_and_never_follows_symlinks(tmp_path):
    root = tmp_path / "apps" / "oily" / "web"
    releases = root / "releases"
    volume = tmp_path / "volumes" / "oily" / "media"
    volume.mkdir(parents=True)
    (volume / "sentinel").write_text("keep", encoding="utf-8")
    for number in range(7):
        release = releases / f"release-{number}"
        release.mkdir(parents=True)
        (release / "media").symlink_to(volume, target_is_directory=True)

    cleanup_releases(root, keep=5, protected=set())

    assert len(list(releases.iterdir())) == 5
    assert (volume / "sentinel").read_text(encoding="utf-8") == "keep"
