# Agency Admin port reservation

Production preflight on 2026-09-05 found `127.0.0.1:3060` already owned by `digitalafarin-platform-mcp.service`.

Agency Control Center Admin therefore reserves `127.0.0.1:3061`. The existing DigitalAfarin Platform MCP service must not be moved as part of this change.
