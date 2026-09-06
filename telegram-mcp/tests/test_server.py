import pytest
from mcp import Client

from digitalafarin_telegram_mcp.server import create_mcp


class FakeControlPlane:
    async def list_channels(self):
        return {
            "items": [
                {"id": "11111111-1111-1111-1111-111111111111", "alias": "seo", "name": "SEO"}
            ]
        }

    async def test_channel(self, channel):
        return {"ok": True, "channel": channel, "message_ids": [10]}

    async def publish_message(self, channel, text, disable_web_page_preview=False):
        return {
            "ok": True,
            "channel": channel,
            "message_ids": [11],
            "disable_web_page_preview": disable_web_page_preview,
            "text": text,
        }


@pytest.mark.asyncio
async def test_server_exposes_only_three_telegram_tools():
    server = create_mcp(FakeControlPlane())
    async with Client(server, raise_exceptions=True) as client:
        result = await client.list_tools()
        names = {tool.name for tool in result.tools}

    assert names == {
        "telegram_list_channels",
        "telegram_test_channel",
        "telegram_publish_message",
    }


@pytest.mark.asyncio
async def test_publish_tool_forwards_alias_text_and_preview_option():
    server = create_mcp(FakeControlPlane())
    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool(
            "telegram_publish_message",
            {
                "channel": "seo",
                "text": "Hello Telegram",
                "disable_web_page_preview": True,
            },
        )

    assert result.structuredContent["channel"] == "seo"
    assert result.structuredContent["message_ids"] == [11]
    assert result.structuredContent["disable_web_page_preview"] is True


@pytest.mark.asyncio
async def test_test_channel_tool_forwards_alias():
    server = create_mcp(FakeControlPlane())
    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool("telegram_test_channel", {"channel": "seo"})

    assert result.structuredContent["ok"] is True
    assert result.structuredContent["channel"] == "seo"
