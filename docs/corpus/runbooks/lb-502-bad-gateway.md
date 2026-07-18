# Runbook: Load Balancer 502 Bad Gateway

**Service:** edge / ingress load balancer · **Severity when firing:** P1 · **Owning team:** API

Fires when the load balancer returns 502/504 to clients. Related alert:
`Gateway5xxRate`. A 502 means the LB reached the upstream but got an invalid or
no response; a 504 means the upstream didn't respond in time. This is distinct
from application 5xx (where the app itself returns a 500 — see the API 5xx
runbook); here the failure is at the LB↔upstream boundary.

## Triage
1. 502 vs 504: 502 = upstream returned garbage/closed the connection; 504 = upstream too slow / LB timeout. The LB access logs carry the upstream status and timing.
2. Are any healthy upstreams left? `kubectl get endpoints <svc>` — if the endpoint list is empty, every pod failed its readiness probe and the LB has nothing to route to.

## Common causes and actions
- **No ready upstreams.** A bad rollout where new pods never become ready empties the endpoint set → 502. Roll back the deploy (see the deploy-rollback runbook) to restore ready pods.
- **Upstream connection resets.** The app is crashing mid-request (OOM-kill, panic) and closing connections → 502. Check for exit code 137 (see the OOM-killer runbook) or app panics.
- **Timeout mismatch.** If the app's response time exceeds the LB's upstream timeout you get 504s. Either speed up the slow path or raise the timeout deliberately.
- **Keep-alive mismatch.** If the upstream closes idle keep-alive connections sooner than the LB expects, the LB reuses a dead connection → sporadic 502. Align idle-timeout settings.

## Verification
After mitigation, confirm the endpoint set is non-empty, `Gateway5xxRate` drops below 0.5%, and no upstream is flapping readiness.

## Escalation
If there are zero ready upstreams and a rollback doesn't restore them within 10 minutes, page API on-call — the outage is total.
