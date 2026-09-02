from pathlib import Path

from digitalafarin_agent.identity import AgentIdentityStore


def test_token_file_is_written_and_read_with_owner_only_mode(tmp_path: Path):
    path = tmp_path / "state" / "agent.token"
    store = AgentIdentityStore(path)

    store.write("da_agent_prefix.secret")

    assert store.read() == "da_agent_prefix.secret"
    assert (path.stat().st_mode & 0o777) == 0o600
    assert (path.parent.stat().st_mode & 0o777) == 0o700
