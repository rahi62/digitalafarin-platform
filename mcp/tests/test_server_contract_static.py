import ast
from pathlib import Path


EXPECTED = {
    "vps_list_servers",
    "vps_get_server",
    "vps_get_metrics",
    "vps_list_services",
    "vps_get_service",
    "vps_get_recent_audit_events",
    "vps_create_service_operation",
    "vps_create_service_logs_operation",
    "vps_list_operations",
    "vps_get_operation",
    "vps_list_projects",
    "vps_get_project",
    "vps_create_bootstrap_operation",
    "vps_create_project",
    "vps_adopt_service",
    "vps_configure_service_deployment",
    "vps_prepare_service_takeover",
    "vps_get_service_takeover",
    "vps_activate_service_takeover",
    "vps_cancel_service_takeover",
    "vps_deploy_service",
    "vps_get_deployment",
    "vps_redeploy_deployment",
    "vps_rollback_deployment",
}
BANNED_FRAGMENTS = {"shell", "command", "exec", "terminal", "sql"}


def test_server_source_registers_only_inventory_and_typed_operation_tools():
    source_path = Path(__file__).parents[1] / "digitalafarin_vps_mcp" / "server.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    tool_names = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "tool"
            ):
                tool_names.add(node.name)

    assert tool_names == EXPECTED
    assert not any(
        fragment in name.lower()
        for name in tool_names
        for fragment in BANNED_FRAGMENTS
    )


def test_takeover_tool_signatures_have_no_arbitrary_execution_inputs():
    source_path = Path(__file__).parents[1] / "digitalafarin_vps_mcp" / "server.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    expected_args = {
        "vps_prepare_service_takeover": ["service_id", "commit"],
        "vps_get_service_takeover": ["takeover_id"],
        "vps_activate_service_takeover": ["takeover_id"],
        "vps_cancel_service_takeover": ["takeover_id"],
    }
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in expected_args:
            found[node.name] = [arg.arg for arg in node.args.args]

    assert found == expected_args
    forbidden = {"unit_name", "path", "command", "shell", "environment", "systemctl"}
    assert not any(arg in forbidden for args in found.values() for arg in args)
