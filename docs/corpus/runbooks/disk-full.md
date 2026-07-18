# Runbook: Disk Space Exhaustion

**Service:** any host / volume · **Severity when firing:** P2 · **Owning team:** Platform

Fires when a filesystem crosses 90% used. Related alert: `DiskSpaceLow`
(`node_filesystem_avail_bytes / node_filesystem_size_bytes < 0.10`). A full disk
causes writes to fail — databases go read-only, logs stop, apps crash.

## Find what filled it
1. Which mount: `df -h`. Note the specific filesystem, not just "/".
2. Biggest directories on that mount: `du -xh --max-depth=1 /var | sort -h | tail`.
3. Common culprits: runaway application logs, un-rotated log files, a stuck job writing temp files, container image/layer bloat, or Postgres WAL that can't archive.

## Immediate mitigation
1. **Logs.** Truncate (don't `rm` an open file — the space isn't freed until the writer closes it): `truncate -s 0 /var/log/app/huge.log`, then fix log rotation.
2. **Deleted-but-open files.** `lsof +L1` lists files deleted while still held open — restart the holding process to release the space.
3. **Docker.** `docker system df` then `docker system prune -f` reclaims dangling images/layers/volumes (be careful with named volumes).
4. **Postgres WAL not archiving.** If `pg_wal` is growing, the archiver is failing or a replication slot is stuck. A stuck slot is the classic cause — see the Postgres replication-lag runbook; do not delete WAL files by hand.

## Do not
- Do not `rm -rf` inside a data directory to free space — you can corrupt a database or lose the very data that matters. Truncate logs and reclaim caches only.

## Escalation
If you cannot free space within 15 minutes and writes are failing, page Platform on-call and grow the volume.
