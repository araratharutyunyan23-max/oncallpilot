"""Pure-function tests for the agent graph (routing, approval payload, policy) —
no network / graph execution needed."""

from app.graph.build import _preview, _route_after_decide, pending_payload
from app.tools.policy import is_destructive


def test_route_after_decide():
    assert _route_after_decide({"route": "respond"}) == "respond"
    assert _route_after_decide({"route": "approve"}) == "human_approval"
    assert _route_after_decide({"route": "act"}) == "tool_exec"
    assert _route_after_decide({}) == "tool_exec"  # default -> execute read-only


def test_pending_payload_only_destructive():
    vals = {
        "pending_calls": [
            {
                "id": "t1",
                "name": "get_ci_status",
                "input": {"pipeline": "api-deploy"},
                "destructive": False,
            },
            {
                "id": "t2",
                "name": "create_jira_ticket",
                "input": {"project_key": "SRE", "summary": "x", "priority": "P1"},
                "destructive": True,
            },
        ]
    }
    payload = pending_payload(vals)
    assert len(payload["pending_actions"]) == 1  # only the destructive one is gated
    action = payload["pending_actions"][0]
    assert action["tool_call_id"] == "t2"
    assert action["name"] == "create_jira_ticket"
    assert "SRE" in action["preview"]


def test_preview_jira():
    call = {
        "name": "create_jira_ticket",
        "input": {"project_key": "SRE", "priority": "P1", "summary": "api-deploy red"},
    }
    p = _preview(call)
    assert "SRE" in p and "P1" in p and "api-deploy red" in p


def test_is_destructive_default():
    assert is_destructive("create_jira_ticket")
    assert not is_destructive("get_ci_status")
    assert not is_destructive("query_monitoring_alerts")
