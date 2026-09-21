import pwd
import re
import uuid
from pathlib import Path

from .health import HealthCheckError, check_http_health_stable
from .releases import COMMIT, SLUG
from .takeover_helper_client import TakeoverHelperClient, TakeoverHelperError
from .takeover_systemd import (
    fingerprint_snapshot,
    inspect_service,
    managed_dropin_path,
)


SAFE_ROOT = re.compile(r"^(?:\.|[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)$")


def _is_safe_root_directory(value: object) -> bool:
    if not isinstance(value, str) or not SAFE_ROOT.fullmatch(value):
        return False
    if value == ".":
        return True
    return all(part not in {".", ".."} for part in value.split("/"))
_PREPARE_KEYS = {
    "takeover_id",
    "service_id",
    "project_slug",
    "service_name",
    "unit_name",
    "repository",
    "exact_commit",
    "runtime",
    "root_directory",
    "install_configuration",
    "build_configuration",
    "service_port",
    "health_check",
}

_ACTIVATE_KEYS = {
    "takeover_id",
    "service_id",
    "project_slug",
    "service_name",
    "unit_name",
    "exact_commit",
    "root_directory",
    "source_fingerprint",
    "release_name",
    "release_path",
    "health_check",
}


def _managed_dropin_path(unit_name: str) -> Path:
    return managed_dropin_path(unit_name)


class TakeoverExecutionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _account(user: str):
    if not user or user == "root":
        raise TakeoverExecutionError(
            "source_user_unsafe",
            "Takeover build requires a non-root source service user.",
        )
    try:
        return pwd.getpwnam(user)
    except KeyError as exc:
        raise TakeoverExecutionError(
            "source_user_unsafe",
            "Source service user does not exist.",
        ) from exc


def _validate_prepare_payload(payload: dict) -> None:
    if set(payload) != _PREPARE_KEYS:
        raise TakeoverExecutionError("invalid_payload", "Invalid takeover prepare payload.")
    for field in ("takeover_id", "service_id"):
        try:
            uuid.UUID(str(payload[field]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise TakeoverExecutionError("invalid_payload", f"Invalid {field}.") from exc
    if not SLUG.fullmatch(str(payload["project_slug"])) or not SLUG.fullmatch(
        str(payload["service_name"])
    ):
        raise TakeoverExecutionError("invalid_payload", "Invalid takeover identity.")
    if not COMMIT.fullmatch(str(payload["exact_commit"])):
        raise TakeoverExecutionError(
            "invalid_exact_commit", "Takeover requires an exact lowercase commit."
        )
    if payload.get("runtime") != "node-nextjs":
        raise TakeoverExecutionError(
            "unsupported_takeover_runtime", "Stage B3 supports node-nextjs only."
        )
    root_directory = payload.get("root_directory")
    if not _is_safe_root_directory(root_directory):
        raise TakeoverExecutionError(
            "release_validation_failed", "Invalid release root directory."
        )


def prepare_service_takeover(
    payload: dict,
    *,
    apps_root: Path = Path("/srv/digitalafarin/apps"),
    helper_client: TakeoverHelperClient | None = None,
) -> dict:
    _validate_prepare_payload(payload)
    try:
        source_snapshot = inspect_service(payload["unit_name"])
    except Exception as exc:
        if isinstance(exc, TakeoverExecutionError):
            raise
        raise TakeoverExecutionError(
            "release_prepare_failed", "Unable to inspect source service."
        ) from exc
    if source_snapshot.get("unit_name") != payload["unit_name"]:
        raise TakeoverExecutionError(
            "release_validation_failed", "Inspected source unit does not match takeover."
        )
    source_user = source_snapshot.get("user", "")
    account = _account(source_user)
    dropin = _managed_dropin_path(payload["unit_name"])
    if dropin.exists() or dropin.is_symlink():
        raise TakeoverExecutionError(
            "managed_dropin_conflict", "Reserved managed systemd drop-in already exists."
        )

    # Resolve only the managed parent before the privileged Helper seals the release.
    releases_root = (
        apps_root.resolve() / payload["project_slug"] / payload["service_name"] / "releases"
    )
    helper = helper_client or TakeoverHelperClient()
    try:
        prepared = helper.prepare_node_nextjs_release(
            {
                "project_slug": payload["project_slug"],
                "unit_name": payload["unit_name"],
                "service_name": payload["service_name"],
                "repository": payload["repository"],
                "exact_commit": payload["exact_commit"],
                "root_directory": payload["root_directory"],
                "install_configuration": payload.get("install_configuration", {}),
                "build_configuration": payload.get("build_configuration", {}),
                "user": source_user,
                "group": source_snapshot.get("group", ""),
            }
        )
    except TakeoverHelperError as exc:
        raise TakeoverExecutionError(exc.code, str(exc)) from exc

    # Helper success attests filesystem validation. Only inspect metadata here:
    # the sealed root:root release is intentionally inaccessible to the Agent.
    release_name = prepared.get("release_name")
    release_path = prepared.get("release_path")
    resolved_commit = prepared.get("resolved_commit")
    if (
        not isinstance(release_name, str)
        or not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{7}(?:-[0-9]+)?", release_name)
        or release_path != str(releases_root / release_name)
        or resolved_commit != payload["exact_commit"]
        or release_name.split("-")[2] != resolved_commit[:7]
        or prepared.get("source_snapshot") != source_snapshot
        or prepared.get("source_fingerprint") != fingerprint_snapshot(source_snapshot)
    ):
        raise TakeoverExecutionError(
            "release_validation_failed", "Privileged helper returned invalid release metadata."
        )

    # account is intentionally resolved before clone/build. Keep the access here
    # so tests can prove the non-root identity path was exercised.
    _ = account
    return {
        "takeover_id": payload["takeover_id"],
        "final_state": "prepared",
        "resolved_commit": resolved_commit,
        "source_snapshot": source_snapshot,
        "source_fingerprint": fingerprint_snapshot(source_snapshot),
        "release_name": release_name,
        "release_path": release_path,
        "events": [
            {"state": "inspecting", "message": ""},
            {"state": "preparing", "message": ""},
            {"state": "prepared", "message": ""},
        ],
    }



def _validate_activate_payload(payload: dict) -> None:
    if set(payload) != _ACTIVATE_KEYS:
        raise TakeoverExecutionError("invalid_payload", "Invalid takeover activation payload.")
    for field in ("takeover_id", "service_id"):
        try:
            uuid.UUID(str(payload[field]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise TakeoverExecutionError("invalid_payload", f"Invalid {field}.") from exc
    if not SLUG.fullmatch(str(payload["project_slug"])) or not SLUG.fullmatch(
        str(payload["service_name"])
    ):
        raise TakeoverExecutionError("invalid_payload", "Invalid takeover identity.")
    if not COMMIT.fullmatch(str(payload["exact_commit"])):
        raise TakeoverExecutionError("invalid_exact_commit", "Invalid exact commit.")
    if not re.fullmatch(r"[0-9a-f]{64}", str(payload["source_fingerprint"])):
        raise TakeoverExecutionError("invalid_payload", "Invalid source fingerprint.")
    if not re.fullmatch(
        r"[0-9]{8}-[0-9]{6}-[0-9a-f]{7}(?:-[0-9]+)?",
        str(payload["release_name"]),
    ):
        raise TakeoverExecutionError("release_validation_failed", "Invalid release name.")
    root_directory = payload.get("root_directory")
    if not _is_safe_root_directory(root_directory):
        raise TakeoverExecutionError("release_validation_failed", "Invalid release root directory.")


def _expected_release_path(payload: dict, apps_root: Path) -> Path:
    """Derive the prepared release path without touching the sealed filesystem."""
    root = Path(apps_root)
    if not root.is_absolute() or ".." in root.parts:
        raise TakeoverExecutionError(
            "release_validation_failed", "Invalid managed apps root."
        )
    return (
        root
        / payload["project_slug"]
        / payload["service_name"]
        / "releases"
        / payload["release_name"]
    )


def activate_service_takeover(
    payload: dict,
    *,
    apps_root: Path = Path("/srv/digitalafarin/apps"),
    helper_client: TakeoverHelperClient | None = None,
) -> dict:
    _validate_activate_payload(payload)

    # Activation stays metadata-only in the unprivileged Agent. The prepared
    # release is intentionally sealed root:root 0550, so filesystem validation
    # beneath it belongs to the privileged Helper.
    expected_release = _expected_release_path(payload, apps_root)
    if payload.get("release_path") != str(expected_release):
        raise TakeoverExecutionError(
            "release_validation_failed", "Prepared release path mismatch."
        )

    # Keep the cheap source configuration drift check in the Agent. The Helper
    # repeats it immediately before mutation.
    try:
        snapshot_now = inspect_service(payload["unit_name"])
    except Exception as exc:
        raise TakeoverExecutionError(
            "takeover_activation_failed", "Unable to re-inspect source service."
        ) from exc
    if fingerprint_snapshot(snapshot_now) != payload["source_fingerprint"]:
        raise TakeoverExecutionError(
            "service_configuration_changed",
            "Source service configuration changed after prepare.",
        )

    helper = helper_client or TakeoverHelperClient()
    try:
        activation = helper.activate_release(
            {
                "project_slug": payload["project_slug"],
                "service_name": payload["service_name"],
                "unit_name": payload["unit_name"],
                "release_name": payload["release_name"],
                "root_directory": payload["root_directory"],
                "source_fingerprint": payload["source_fingerprint"],
                "exact_commit": payload["exact_commit"],
            }
        )
    except TakeoverHelperError as exc:
        raise TakeoverExecutionError(exc.code, str(exc)) from exc

    previous_release_name = activation.get("previous_release_name")
    if previous_release_name is not None and not re.fullmatch(
        r"[0-9]{8}-[0-9]{6}-[0-9a-f]{7}(?:-[0-9]+)?",
        str(previous_release_name),
    ):
        raise TakeoverExecutionError(
            "takeover_activation_failed",
            "Privileged helper returned invalid activation metadata.",
        )

    try:
        check_http_health_stable(payload["health_check"])
    except HealthCheckError:
        try:
            helper.rollback_activation(
                {
                    "project_slug": payload["project_slug"],
                    "service_name": payload["service_name"],
                    "unit_name": payload["unit_name"],
                    "previous_release_name": previous_release_name,
                }
            )
            check_http_health_stable(payload["health_check"])
            helper.cleanup_release(
                {
                    "project_slug": payload["project_slug"],
                    "service_name": payload["service_name"],
                    "unit_name": payload["unit_name"],
                    "release_name": payload["release_name"],
                }
            )
        except (TakeoverHelperError, HealthCheckError) as rollback_exc:
            raise TakeoverExecutionError(
                "takeover_rollback_failed",
                "Controlled takeover rollback did not restore healthy service.",
            ) from rollback_exc
        return {
            "takeover_id": payload["takeover_id"],
            "final_state": "rolled_back",
            "resolved_commit": payload["exact_commit"],
            "release_name": payload["release_name"],
            "previous_current_path": activation.get("previous_current_path"),
            "managed_dropin_path": activation.get("managed_dropin_path"),
            "events": [
                {"state": "activating", "message": ""},
                {"state": "verifying", "message": ""},
                {
                    "state": "rolled_back",
                    "message": "New release failed health verification; original service restored.",
                },
            ],
        }

    return {
        "takeover_id": payload["takeover_id"],
        "final_state": "succeeded",
        "resolved_commit": payload["exact_commit"],
        "release_name": payload["release_name"],
        "previous_current_path": activation.get("previous_current_path"),
        "managed_dropin_path": activation.get("managed_dropin_path"),
        "events": [
            {"state": "activating", "message": ""},
            {"state": "verifying", "message": ""},
            {"state": "succeeded", "message": ""},
        ],
    }
