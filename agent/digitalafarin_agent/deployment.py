import re
from pathlib import PurePosixPath

from .health import check_http_health



class DeploymentFailure(RuntimeError):
    pass


def _event(events: list[dict], state: str, message: str = "") -> None:
    events.append({"state": state, "message": message})


def deploy_release(payload: dict, *, helper=None) -> dict:
    """Compatibility entry point; all deployments use the privileged helper."""
    return deploy_managed_release(payload, helper=helper)


def rollback_release(payload: dict, *, helper=None) -> dict:
    """Compatibility entry point; rollback never runs agent-side mutations."""
    return rollback_managed_release(payload, helper=helper)


def deploy_managed_release(payload: dict, *, helper=None) -> dict:
    """Coordinate managed deployment without opening or mutating release files."""
    from .takeover_helper_client import TakeoverHelperClient, TakeoverHelperError

    helper = helper or TakeoverHelperClient()
    events = []
    release_name = None
    exact_commit = payload.get("exact_commit")
    result = {"deployment_id": payload["deployment_id"], "exact_commit": exact_commit, "events": events}
    identity = {key: payload[key] for key in ("project_slug", "service_name", "unit_name")}
    root = payload.get("root_directory", ".")
    _event(events, "preparing")
    try:
        for key, empty, code in (
            ("environment", {}, "managed_environment_unsupported"),
            ("volumes", [], "managed_volumes_unsupported"),
        ):
            if payload.get(key, empty) != empty:
                raise TakeoverHelperError(code, f"Managed {key} updates are not supported.")
        if payload.get("runtime") != "node-nextjs":
            raise TakeoverHelperError("managed_runtime_unsupported", "Only node-nextjs is supported.")
        if not isinstance(exact_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", exact_commit):
            raise TakeoverHelperError("invalid_exact_commit", "An exact lowercase commit is required.")
        _event(events, "cloning")
        _event(events, "building")
        prepare_request = {
            **identity, "repository": payload["repository"], "exact_commit": exact_commit,
            "runtime": payload["runtime"], "root_directory": root,
            "install_configuration": payload.get("install_configuration", {}),
            "build_configuration": payload.get("build_configuration", {}),
            "environment": payload.get("environment", {}), "volumes": payload.get("volumes", []),
        }
        if payload.get("source_id"):
            prepare_request["source_id"] = payload["source_id"]
        prepared = helper.prepare_managed_node_nextjs_release(prepare_request)
        release_name = prepared["release_name"]
        result["release_name"] = release_name
        if prepared["resolved_commit"] != exact_commit:
            raise TakeoverHelperError("invalid_exact_commit", "Prepared commit does not match request.")
        _event(events, "releasing")
        _event(events, "health_check")
        _event(events, "activating")
        activation = helper.activate_managed_release({
            **identity, "release_name": release_name, "root_directory": root,
            "exact_commit": exact_commit,
        })
        _event(events, "verifying")
        try:
            check_http_health(payload["health_check"])
        except Exception:
            helper.rollback_managed_activation({
                **identity, "release_name": release_name, "root_directory": root,
                "previous_release_name": activation["previous_release_name"],
            })
            check_http_health(payload["health_check"])
            helper.cleanup_release({**identity, "release_name": release_name})
            _event(events, "rolled_back", "New release failed health verification")
            return {**result, "final_state": "rolled_back"}
        helper.prune_managed_releases({
            **identity, "root_directory": root, "release_name": release_name,
            "previous_release_name": activation["previous_release_name"],
        })
        _event(events, "succeeded")
        return {**result, "final_state": "succeeded"}
    except Exception as exc:
        if release_name is not None:
            try:
                helper.cleanup_release({**identity, "release_name": release_name})
            except Exception:
                # The helper refuses to delete an active release, including when
                # an activation response was lost or rollback failed.
                result["cleanup_error_code"] = "managed_cleanup_failed"
        code = exc.code if isinstance(exc, TakeoverHelperError) else "managed_deployment_failed"
        message = str(exc) if isinstance(exc, TakeoverHelperError) else "Managed deployment failed."
        _event(events, "failed", code)
        return {**result, "final_state": "failed", "error_code": code, "error_message": message[:500]}


def rollback_managed_release(payload: dict, *, helper=None) -> dict:
    """Accept the existing control-plane payload without accessing release files."""
    from .takeover_helper_client import TakeoverHelperClient, TakeoverHelperError

    helper = helper or TakeoverHelperClient()
    events = []
    result = {"deployment_id": payload["deployment_id"], "exact_commit": payload["exact_commit"], "events": events}
    _event(events, "preparing")
    try:
        # Pure lexical parsing only. The helper independently binds names to paths.
        root = PurePosixPath(payload["service_root"])
        release = PurePosixPath(payload["release_path"])
        base = PurePosixPath("/srv/digitalafarin/apps")
        relative = root.relative_to(base)
        if (
            len(relative.parts) != 2 or ".." in root.parts or ".." in release.parts
            or str(root) != payload["service_root"] or str(release) != payload["release_path"]
            or release.parent != root / "releases"
        ):
            raise ValueError("Invalid managed rollback path")
        identity = {"project_slug": relative.parts[0], "service_name": relative.parts[1], "unit_name": payload["unit_name"]}
        for state in ("cloning", "building", "releasing", "health_check", "activating"):
            _event(events, state, "Retained release rollback")
        activation = helper.rollback_managed_release({
            **identity, "release_name": release.name, "exact_commit": payload["exact_commit"],
        })
        result["release_name"] = release.name
        root_directory = activation["root_directory"]
        _event(events, "verifying")
        try:
            check_http_health(payload["health_check"])
        except Exception:
            helper.rollback_managed_activation({
                **identity, "root_directory": root_directory, "release_name": release.name,
                "previous_release_name": activation["previous_release_name"],
            })
            check_http_health(payload["health_check"])
            _event(events, "rolled_back", "Rollback target failed health verification")
            return {**result, "final_state": "rolled_back"}
        helper.prune_managed_releases({
            **identity, "root_directory": root_directory, "release_name": release.name,
            "previous_release_name": activation["previous_release_name"],
        })
        _event(events, "succeeded")
        return {**result, "final_state": "succeeded"}
    except Exception as exc:
        code = exc.code if isinstance(exc, TakeoverHelperError) else "managed_rollback_failed"
        _event(events, "failed", code)
        return {**result, "final_state": "failed", "error_code": code}
