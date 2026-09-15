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
