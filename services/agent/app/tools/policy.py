"""Tool policy — the local source of truth for which tools are destructive.

Deliberately independent of any MCP `destructiveHint` annotation (defense in
depth): the agent decides HITL gating from this set, not from what the tool
server claims about itself."""

from ..config import get_settings


def is_destructive(tool_name: str) -> bool:
    return tool_name in get_settings().destructive_tools
