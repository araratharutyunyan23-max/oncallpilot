# Runbook: API 5xx Error-Rate Spike

**Service:** `api` · **Severity when firing:** P1 · **Owning team:** API

Fires when the 5xx rate on the `api` service exceeds 2% of requests over a
5-minute window. Related alert: `HighApiErrorRate`.

## Triage (first 5 minutes)
1. Scope it: is the spike on **all** endpoints or one route? `sum by (route) (rate(http_requests_total{service="api",status=~"5.."}[5m]))`.
2. Correlate with deploys: check the deploy timeline for `api` in the last 30 minutes. A spike that starts within a minute of a rollout is a bad deploy until proven otherwise — **roll back first, investigate after**.
3. Check downstream health: a 5xx spike is often a symptom. Look at `cache-redis` (see the Redis OOM runbook), the primary database (see the Postgres replication-lag runbook), and any third-party dependency dashboards.

## Common causes and actions
- **Bad deploy.** Roll back to the previous known-good revision: `deploy rollback api --to-previous`. This is the fastest mitigation; do it before deep debugging.
- **Database saturation.** Connection-pool exhaustion shows up as 5xx with `too many clients` in logs. Shed load (rate-limit the noisiest client) and check for a long-running query holding connections.
- **Cache dependency down.** If `cache-redis` is OOM or failing, the `api` falls back to origin and may overload the DB. Mitigate the cache first, then the API recovers.
- **Upstream timeout.** A slow third-party call with no circuit breaker cascades into 5xx. Trip the breaker (`flags set api.thirdparty.breaker=open`) and serve a degraded response.

## Verification
After mitigation, confirm the 5xx rate drops below 0.5% and p95 latency returns to baseline before declaring the incident resolved. File a follow-up if a rollback was used, so the bad change is fixed forward.
