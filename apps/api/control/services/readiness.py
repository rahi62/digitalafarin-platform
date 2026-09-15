def summarize_readiness(checks: list[dict]) -> str:
    statuses = {item.get("status") for item in checks}
    if "blocked" in statuses:
        return "blocked"
    if "warning" in statuses:
        return "warning"
    return "ready"
