from typing import Any, Awaitable

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from digitalafarin_telegram_mcp.config import get_settings
from digitalafarin_telegram_mcp.control_plane import ControlPlaneClient
from digitalafarin_telegram_mcp.errors import MCPDomainError


async def _safe(call: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    try:
        return await call
    except MCPDomainError as exc:
        return exc.as_dict()


def create_mcp(control_plane: ControlPlaneClient | Any | None = None) -> MCPServer:
    settings = get_settings() if control_plane is None else None
    client = control_plane or ControlPlaneClient(
        settings.control_plane_url,
        settings.control_plane_token,
    )

    mcp = MCPServer(
        "DigitalAfarin Telegram Publisher",
        instructions=(
            "Publish text to Telegram channels configured by alias in DigitalAfarin Platform. "
            "Use telegram_list_channels before publishing when the intended alias is unclear. "
            "telegram_test_channel and telegram_publish_message create real Telegram messages. "
            "Never invent channel aliases and never claim a publish succeeded unless the tool returns ok=true."
        ),
    )

    @mcp.tool(
        title="List Telegram channels",
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    async def telegram_list_channels() -> dict[str, Any]:
        """List active Telegram channel aliases available for publishing."""
        return await _safe(client.list_channels())

    @mcp.tool(
        title="Test Telegram channel",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=True,
        ),
    )
    async def telegram_test_channel(channel: str) -> dict[str, Any]:
        """Send a real diagnostic message to one configured Telegram channel alias."""
        return await _safe(client.test_channel(channel))

    @mcp.tool(
        title="Publish Telegram message",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=True,
        ),
    )
    async def telegram_publish_message(
        channel: str,
        text: str,
        disable_web_page_preview: bool = False,
    ) -> dict[str, Any]:
        """Publish text to one configured Telegram channel alias. This creates real messages."""
        return await _safe(
            client.publish_message(
                channel,
                text,
                disable_web_page_preview=disable_web_page_preview,
            )
        )

    return mcp


def main() -> None:
    settings = get_settings()
    mcp = create_mcp()
    mcp.run(
        transport="streamable-http",
        host=settings.telegram_mcp_host,
        port=settings.telegram_mcp_port,
        streamable_http_path=settings.telegram_mcp_path,
    )


if __name__ == "__main__":
    main()
