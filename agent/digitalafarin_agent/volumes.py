import os
import re
import shutil
from pathlib import Path


SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
IDENTITY = re.compile(r"^[a-z_][a-z0-9_-]{0,63}$")


class VolumeError(RuntimeError):
    pass


def create_volume(payload: dict, *, base_path: Path = Path("/srv/digitalafarin/volumes")) -> dict:
    if set(payload) != {"project_slug", "name", "owner", "group", "mode"}:
        raise VolumeError("invalid volume payload")
    project = payload["project_slug"]
    name = payload["name"]
    owner = payload["owner"]
    group = payload["group"]
    mode = payload["mode"]
    if not SLUG.fullmatch(project) or not SLUG.fullmatch(name):
        raise VolumeError("invalid volume path component")
    if not IDENTITY.fullmatch(owner) or not IDENTITY.fullmatch(group):
        raise VolumeError("invalid volume ownership")
    if not re.fullmatch(r"0[0-7]{3}", mode):
        raise VolumeError("invalid volume mode")
    root = base_path.resolve()
    target = (root / project / name).resolve()
    if not target.is_relative_to(root):
        raise VolumeError("volume path escapes base")
    target.mkdir(parents=True, exist_ok=True)
    os.chmod(target, int(mode, 8))
    shutil.chown(target, user=owner, group=group)
    return {"host_path": str(target), "created": True}
