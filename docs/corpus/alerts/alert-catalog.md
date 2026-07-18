# Alert Catalog

Every alert declares a severity (per ADR 0001) and links its runbook. The agent
uses `runbook` to fetch mitigation steps and `severity` to set ticket priority.

## HighApiErrorRate
- **Service:** `api` · **Severity:** P1
- **Expression:** `sum(rate(http_requests_total{service="api",status=~"5.."}[5m])) / sum(rate(http_requests_total{service="api"}[5m])) > 0.02`
- **For:** 5m
- **Runbook:** `runbooks/api-5xx.md`
- **Summary:** API 5xx error rate above 2% — likely a bad deploy or a saturated downstream dependency.

## RedisMemoryHigh
- **Service:** `cache-redis` · **Severity:** P2
- **Expression:** `redis_memory_used_bytes / redis_memory_max_bytes > 0.90`
- **For:** 5m
- **Runbook:** `runbooks/redis-oom.md`
- **Summary:** Redis is above 90% of maxmemory and close to OOM/eviction thrash. Act now during business hours (see the checkout-latency postmortem for why).

## PostgresReplicationLag
- **Service:** `postgres-replica` · **Severity:** P2
- **Expression:** `pg_replication_lag_seconds > 60`
- **For:** 10m
- **Runbook:** `runbooks/postgres-replication-lag.md`
- **Summary:** A read replica is more than 60s behind the primary — reads may be stale. Usually a long query on the replica blocking WAL apply.

## CheckoutLatencyHigh
- **Service:** `checkout` · **Severity:** P2
- **Expression:** `histogram_quantile(0.95, sum by (le) (rate(checkout_request_duration_seconds_bucket[5m]))) > 1`
- **For:** 5m
- **Runbook:** `runbooks/api-5xx.md`
- **Summary:** Checkout p95 latency above 1s. Frequently a downstream cache or database symptom rather than a checkout bug.
