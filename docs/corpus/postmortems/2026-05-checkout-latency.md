# Postmortem: Checkout Latency Incident (2026-05-14)

**Severity:** P1 · **Duration:** 42 minutes · **Author:** Checkout on-call

## Summary
On 2026-05-14 the `checkout` service p95 latency rose from 240ms to 3.1s for 42
minutes, and the `api` 5xx rate crossed 2% (alert `HighApiErrorRate` fired).
Root cause was cache pressure on `cache-redis` cascading into database
saturation. No orders were lost; ~8% of checkout attempts timed out and were
retried by clients.

## Timeline (UTC)
- **14:02** `RedisMemoryHigh` fires (P2). On-call acknowledges but does not yet act.
- **14:09** `HighApiErrorRate` fires (P1). Checkout p95 climbs past 1s.
- **14:12** On-call follows the API 5xx runbook, sees `cache-redis` at 96% memory.
- **14:18** Root cause identified: a deploy 20 minutes earlier began writing
  `cart:*` keys **without a TTL**, so the working set grew unbounded until
  eviction thrashed.
- **14:26** Mitigation: set `maxmemory-policy allkeys-lru` (it had drifted to
  `noeviction`) and expired the untagged `cart:*` keys per the Redis OOM runbook.
- **14:31** Cache memory recovers; 5xx rate falls below 0.5%.
- **14:44** Latency back to baseline; incident resolved.

## Root cause
A code change added a cart-caching path that wrote keys without an expiry. Under
normal traffic the cache filled within ~20 minutes and, because the eviction
policy had earlier been changed to `noeviction` during unrelated debugging and
never reverted, Redis started rejecting writes with OOM instead of evicting.

## What went well
- The Redis OOM and API 5xx runbooks were accurate and led straight to the fix.

## What went wrong
- The P2 `RedisMemoryHigh` at 14:02 was the early warning and was not acted on
  until it became a P1. Acting on the P2 would have prevented the outage.
- `maxmemory-policy` had been left at `noeviction` from an earlier session —
  config drift with no guardrail.

## Action items
- Enforce a TTL on all cache writes via a lint check in CI. (owner: Checkout)
- Alert on `maxmemory-policy != allkeys-lru` for cache instances. (owner: Platform)
- Treat `RedisMemoryHigh` as act-now during business hours, per ADR 0001. (owner: SRE)
