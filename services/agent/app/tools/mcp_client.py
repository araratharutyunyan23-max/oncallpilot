"""Raw MCP client (Streamable HTTP) — the agent reaches the tools server through
the official `mcp` SDK, NOT the Anthropic MCP connector and NOT langchain
adapters (see DECISIONS.md): the connector executes tool calls server-side
inside one model turn, which would defeat interrupt-before-execute for
destructive actions.

Tool definitions are static, so they're fetched once and cached (guarded by a
lock against a cold-start race). Each tool call opens a short-lived session
(simple + stateless; a persistent session is a later optimization)."""

import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from ..config import get_settings

_tool_defs: list[dict] | None = None
_tool_defs_lock = asyncio.Lock()


async def list_tool_defs() -> list[dict]:
    """MCP tools as Anthropic tool definitions (name/description/input_schema)."""
    global _tool_defs
    if _tool_defs is not None:
        return _tool_defs
    async with _tool_defs_lock:
        if _tool_defs is not None:  # another task populated it while we waited
            return _tool_defs
        async with streamablehttp_client(get_settings().mcp_url) as (r, w, _):
            async with ClientSession(r, w) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                _tool_defs = [
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "input_schema": t.inputSchema,
                    }
                    for t in tools
                ]
    return _tool_defs


async def call_tool(name: str, args: dict) -> str:
    """Call an MCP tool; return its result as a JSON string (for tool_result).

    A tool-level failure (isError) is returned as `{"error": ...}` so the model
    sees it and can recover, rather than being masked as a successful result."""
    async with streamablehttp_client(get_settings().mcp_url) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            res = await session.call_tool(name, args)
            text = (
                res.content[0].text
                if res.content and hasattr(res.content[0], "text")
                else ""
            )
            if getattr(res, "isError", False):
                return json.dumps({"error": text or "tool call failed"})
            sc = getattr(res, "structuredContent", None)
            if sc is not None:
                return json.dumps(sc)
            return text or "{}"
