import re
import subprocess
from pathlib import Path

from .redaction import redact


IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
BACKUP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")


class DatabaseError(RuntimeError):
    pass


def _identity(value: object) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise DatabaseError("invalid database identifier")
    return value


def _run(argv: list[str], **kwargs):
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
            shell=False,
            **kwargs,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DatabaseError(type(exc).__name__) from exc
    if result.returncode != 0:
        raise DatabaseError(redact(result.stderr or "database operation failed")[:500])
    return result


def create_database(payload: dict) -> dict:
    if set(payload) != {"database_name", "username", "password"}:
        raise DatabaseError("invalid database create payload")
    database = _identity(payload["database_name"])
    username = _identity(payload["username"])
    password = payload["password"]
    if not isinstance(password, str) or not password:
        raise DatabaseError("invalid database credential")
    literal = password.replace("'", "''")
    sql = (
        f'DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = \'{username}\') '
        f'THEN CREATE ROLE "{username}" LOGIN PASSWORD \'{literal}\'; END IF; END $$;\n'
        f'SELECT format(\'CREATE DATABASE %I OWNER %I\', \'{database}\', \'{username}\') '
        "WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '"
        f"{database}')\\gexec\n"
    )
    _run(
        ["psql", "--no-psqlrc", "--set=ON_ERROR_STOP=1", "--dbname=postgres"],
        input=sql,
    )
    return {"created": True}


def restore_database(
    payload: dict, *, backup_root: Path = Path("/srv/digitalafarin/backups")
) -> dict:
    if set(payload) != {"database_name", "username", "backup_name"}:
        raise DatabaseError("invalid database restore payload")
    database = _identity(payload["database_name"])
    username = _identity(payload["username"])
    backup_name = payload["backup_name"]
    if not isinstance(backup_name, str) or not BACKUP_NAME.fullmatch(backup_name):
        raise DatabaseError("invalid backup name")
    root = backup_root.resolve()
    backup = (root / backup_name).resolve()
    if not backup.is_relative_to(root) or not backup.is_file():
        raise DatabaseError("managed backup not found")
    _run(
        [
            "pg_restore",
            "--exit-on-error",
            "--no-owner",
            "--role",
            username,
            "--dbname",
            database,
            str(backup),
        ]
    )
    return {"restored": True, "backup_name": backup_name}
