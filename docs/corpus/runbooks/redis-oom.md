# Runbook: Redis Out-Of-Memory (OOM)

**Service:** `cache-redis` · **Severity when firing:** P2 · **Owning team:** Platform

Fires when Redis `used_memory` crosses `maxmemory` and the eviction policy starts
dropping keys, or when `OOM command not allowed` errors appear in client logs.
Related alert: `RedisMemoryHigh` (see the alert catalog).

## Symptoms
- Clients see `OOM command not allowed when used_memory > maxmemory`.
- Elevated cache-miss rate on `api` and `checkout` services.
- `redis_memory_used_bytes / redis_memory_max_bytes > 0.90` for 5+ minutes.

## Immediate mitigation
1. Confirm the pressure: `redis-cli INFO memory | grep -E 'used_memory_human|maxmemory_human|mem_fragmentation_ratio'`.
2. Check the eviction policy: `redis-cli CONFIG GET maxmemory-policy`. For a cache it should be `allkeys-lru`; if it is `noeviction`, that is the bug — switch it: `redis-cli CONFIG SET maxmemory-policy allkeys-lru`.
3. Identify the biggest keyspaces: `redis-cli --bigkeys`. A single runaway key (an unbounded list or set) is the most common root cause.
4. If a specific key pattern is the culprit and safe to drop, expire it: `redis-cli --scan --pattern 'session:*' | head -n 10000 | xargs redis-cli DEL`.
5. If memory is still pinned, fail the affected reads over to the origin (feature flag `cache.bypass=true`) to shed load while you resize.

## Root-cause fixes
- **Missing TTLs.** Keys written without `EX`/`PX` never expire. Audit the writer; every cache write must set a TTL.
- **Fragmentation.** `mem_fragmentation_ratio > 1.5` wastes memory. Schedule `MEMORY PURGE` (jemalloc) during a low-traffic window, or restart the replica then fail over.
- **Undersized instance.** If working-set legitimately exceeds `maxmemory`, resize the instance and raise `maxmemory` to ~75% of the box.

## Escalation
If mitigation does not recover within 15 minutes, page the Platform on-call and open a P2 incident. Do not `FLUSHALL` on a shared cache — it will stampede every dependent service against its origin.
