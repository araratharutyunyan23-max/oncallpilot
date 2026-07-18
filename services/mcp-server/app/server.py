"""OncallPilot MCP tools server (FastMCP, Streamable HTTP on :9000/mcp).

A separate process so the tool boundary is a real network/trust boundary: the
allowlist and destructive-action gating are enforced where the agent can't reach
around them, and (in a real deployment) Jira/CI/monitoring secrets live here, off
the agent process. Three tools: two read-only, one destructive + idempotent.
"""

from typing import Literal

from mcp.server.fastmcp import FastMCP

from .backends import get_backend

mcp = FastMCP("oncallpilot-tools", host="0.0.0.0", port=9000)
_backend = get_backend()


@mcp.tool()
def get_ci_status(
    pipeline: Literal["api-deploy", "web-deploy", "batch-etl", "infra-plan"],
    branch: str | None = None,
    limit: int = 10,
) -> dict:
    """Get recent CI runs for a pipeline (status, branch, commit, duration). Read-only."""
    return _backend.ci_status(pipeline, branch, min(limit, 20))


@mcp.tool()
def query_monitoring_alerts(
    state: Literal["firing", "resolved"] = "firing",
    service: str | None = None,
    severity: Literal["P1", "P2", "P3", "P4"] | None = None,
    limit: int = 20,
) -> dict:
    """Query monitoring alerts by state/service/severity (with runbook links). Read-only."""
    return _backend.alerts(state, service, severity, min(limit, 50))


@mcp.tool()
def create_jira_ticket(
    project_key: Literal["SRE", "PLATFORM", "NETOPS"],
    summary: str,
    description: str,
    idempotency_key: str,
    issue_type: Literal["Incident", "Bug", "Task"] = "Incident",
    priority: Literal["P1", "P2", "P3", "P4"] = "P2",
    labels: list[str] | None = None,
) -> dict:
    """Create a Jira ticket. DESTRUCTIVE — the agent must get human approval first.

    Idempotent: passing the same idempotency_key returns the existing ticket with
    status "deduped" instead of creating a second one. `summary` max 255 chars.
    """
    return _backend.create_ticket(
        project_key=project_key,
        summary=summary[:255],
        description=description,
        issue_type=issue_type,
        priority=priority,
        labels=labels or [],
        idempotency_key=idempotency_key,
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
