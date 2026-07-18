# Runbook: API Rate-Limit Exhaustion (429s)

**Service:** `api` gateway · **Severity when firing:** P2 · **Owning team:** API

Fires when clients receive a high rate of `429 Too Many Requests`. Related alert:
`RateLimit429Rate`. This is the gateway **rejecting** traffic on purpose — very
different from a 5xx (server failure) or a 502 (bad upstream). The question is
whether the limiter is protecting you correctly or misconfigured.

## Triage
1. Who is being limited: `sum by (client_id) (rate(http_requests_total{status="429"}[5m]))`. One noisy client vs broad 429s across many clients tells you which case you're in.
2. Is it legitimate protection (a client actually flooding) or a misconfiguration (limit set too low after a change)?

## Actions
- **One abusive client.** If a single client_id is hammering the API, the limiter is doing its job. Confirm with the client's owner; consider a per-client quota bump only if the traffic is legitimate.
- **Limit too low.** If broad 429s started right after a config change to the limiter, the new limit is wrong — revert the limiter config (a config rollback, see the deploy-rollback runbook's config note), not the app.
- **Retry storm.** Clients retrying 429s without backoff amplify the problem. The fix is client-side exponential backoff + jitter; server-side, return a `Retry-After` header so well-behaved clients wait.
- **Shared limiter counter drift.** If the limiter's backing store (often Redis) is under memory pressure and evicting counters, limits behave erratically — check the Redis OOM runbook.

## Do not
- Do not simply disable the rate limiter to make 429s go away — that removes the protection and can turn a contained problem into a full overload / DoS.

## Escalation
If 429s are hitting legitimate traffic broadly and a config revert doesn't help within 15 minutes, page API on-call.
