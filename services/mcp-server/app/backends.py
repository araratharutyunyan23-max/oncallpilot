"""Mock backends for the tool server (seed-driven, deterministic).

`create_ticket` deduplicates by idempotency_key so a replayed/retried
destructive call never creates a second ticket — the invariant the agent's
human-in-the-loop + idempotency design relies on. A real backend (Jira REST,
GitHub Actions, Alertmanager) would slot in behind the same interface.
"""

import json
import threading
from pathlib import Path

_SEED = Path(__file__).parent / "seed"


class MockBackend:
    def __init__(self) -> None:
        self._ci: dict = json.loads((_SEED / "ci_pipelines.json").read_text())
        self._alerts: list = json.loads((_SEED / "alerts.json").read_text())
        self._tickets: dict[str, dict] = {}  # idempotency_key -> ticket
        self._counter = 4200
        self._lock = threading.Lock()

    def ci_status(self, pipeline: str, branch: str | None, limit: int) -> dict:
        runs = list(self._ci.get(pipeline, []))
        if branch:
            runs = [r for r in runs if r["branch"] == branch]
        return {"pipeline": pipeline, "count": len(runs), "runs": runs[: max(1, limit)]}

    def alerts(
        self, state: str, service: str | None, severity: str | None, limit: int
    ) -> dict:
        rows = [a for a in self._alerts if a["state"] == state]
        if service:
            rows = [a for a in rows if a["service"] == service]
        if severity:
            rows = [a for a in rows if a["severity"] == severity]
        return {"count": len(rows), "alerts": rows[: max(1, limit)]}

    def create_ticket(
        self,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str,
        priority: str,
        labels: list[str],
        idempotency_key: str,
    ) -> dict:
        with self._lock:
            if idempotency_key in self._tickets:
                return {**self._tickets[idempotency_key], "status": "deduped"}
            self._counter += 1
            key = f"{project_key}-{self._counter}"
            ticket = {
                "ticket_key": key,
                "url": f"https://jira.example.com/browse/{key}",
                "project_key": project_key,
                "summary": summary,
                "description": description,
                "issue_type": issue_type,
                "priority": priority,
                "labels": labels,
                "status": "created",
            }
            self._tickets[idempotency_key] = ticket
            return ticket


_backend: MockBackend | None = None


def get_backend() -> MockBackend:
    global _backend
    if _backend is None:
        _backend = MockBackend()
    return _backend
