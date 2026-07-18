# Runbook: Postgres Replication Lag

**Service:** `postgres-primary` / `postgres-replica` · **Severity when firing:** P2 · **Owning team:** Data

Fires when a read replica falls behind the primary. Related alert:
`PostgresReplicationLag` (threshold: `pg_replication_lag_seconds > 60` for 10m).
Stale reads from a lagging replica cause user-visible inconsistency (e.g. a
just-created ticket "not found" on the next read).

## Assess the lag
1. On the primary: `SELECT client_addr, state, replay_lag FROM pg_stat_replication;`.
2. On the replica: `SELECT now() - pg_last_xact_replay_timestamp() AS lag;`.
3. Distinguish **network/apply lag** (replica can't keep up applying WAL) from **a stuck query** on the replica blocking replay: `SELECT pid, state, wait_event_type, query FROM pg_stat_activity WHERE state <> 'idle' ORDER BY xact_start;`.

## Mitigation
- **Long query blocking replay.** A long-running analytics query on the replica can pause WAL apply (`max_standby_streaming_delay`). Cancel it: `SELECT pg_cancel_backend(<pid>);`. This is the single most common cause.
- **Route reads to primary temporarily.** If lag is user-visible, flip `db.reads=primary` to stop serving stale data while the replica catches up. Watch primary load — do not leave it there.
- **WAL apply can't keep up.** If the replica is CPU/IO-bound applying WAL under heavy write load, the fix is capacity: faster disks or a larger replica. Short term, reduce write volume upstream.

## Do not
- Do not promote the replica to primary to "fix" lag — promotion is for primary failure, not lag, and it splits the cluster. Promotion is a separate, higher-severity procedure that requires Data on-call sign-off.

## Escalation
If lag keeps growing after cancelling blocking queries, page Data on-call and consider routing all reads to the primary while investigating disk/IO on the replica.
