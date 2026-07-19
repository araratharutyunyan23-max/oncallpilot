import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    conversation_id: str
    query: str
    # raw Anthropic messages (assistant tool_use / user tool_result), managed manually
    anthropic_messages: list[Any]
    doc_blocks: list[Any]          # retrieved context as document blocks (no citations here)
    sources: list[dict]            # retrieved chunks (for the UI/trace)
    pending_calls: list[dict]      # [{id, name, input, destructive}]
    approvals: dict                # {tool_call_id: "approved" | "denied"}
    step: int
    route: str | None           # "respond" | "act" | "approve"
    final_answer: str | None
    # accumulated across nodes
    trace: Annotated[list, operator.add]
    cost_usd: Annotated[float, operator.add]
    tokens_in: Annotated[int, operator.add]
    tokens_out: Annotated[int, operator.add]
