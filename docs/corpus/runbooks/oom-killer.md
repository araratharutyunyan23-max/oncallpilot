# Runbook: Host OOM-Killer Terminating Processes

**Service:** any host / node · **Severity when firing:** P2 · **Owning team:** Platform

Fires when the Linux kernel OOM-killer terminates a process because the **host**
ran out of physical memory (not a Redis maxmemory limit — for that see the Redis
OOM runbook). Related alert: `HostMemoryPressure`. Signature: `Out of memory:
Killed process <pid> (<name>)` in `dmesg` / kernel log, and a service that
"restarted" with exit code 137 (128 + SIGKILL).

## Symptoms
- A container or process disappears and restarts; exit code **137**.
- `dmesg -T | grep -i 'killed process'` shows the OOM-killer entry.
- Node `node_memory_MemAvailable_bytes` near zero; heavy swap-in.

## Immediate mitigation
1. Confirm it was the kernel, not the app: `dmesg -T | grep -iE 'out of memory|killed process'`. The `oom_score_adj` of the victim tells you why that process was chosen.
2. Find the memory hog: `ps aux --sort=-%mem | head`. A single leaking process (see the memory-leak follow-up in the Kafka backlog postmortem) is the usual cause.
3. Relieve pressure: restart the offending service on a node with headroom, or cordon the node and reschedule.
4. If the whole node is oversubscribed, reduce the pod/container memory requests colocated on it, or scale the node pool.

## Root-cause fixes
- **Missing memory limits.** Containers without a memory limit can consume the whole node. Set requests/limits so one workload can't starve the host.
- **Real leak.** If RSS grows unbounded over hours, it is an application leak — capture a heap profile and fix forward; a restart only defers it.
- **Undersized nodes.** If aggregate working-set legitimately exceeds node memory, add capacity.

## Not this runbook
If the killed process is Redis and the error is `OOM command not allowed when
used_memory > maxmemory`, that is a Redis-level eviction problem, **not** the
kernel OOM-killer — use the Redis OOM runbook instead.

## Escalation
If OOM-kills recur across multiple nodes within 15 minutes, page Platform on-call — it is likely a fleet-wide leak or a bad rollout, not a single bad node.
