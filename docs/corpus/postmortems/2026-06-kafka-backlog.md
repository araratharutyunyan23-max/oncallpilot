# Postmortem: Notification Backlog from Kafka Consumer Lag (2026-06-03)

**Severity:** P2 · **Duration:** 3h 10m · **Author:** Data on-call

## Summary
On 2026-06-03 the `events-consumer` group fell hours behind on the
`notifications` topic (alert `KafkaConsumerLag` fired), so users received order
and incident notifications up to two hours late. No data was lost — Kafka
retained the events and the consumer caught up after the fix. Root cause was a
slow downstream call amplified by a memory leak in the consumer.

## Timeline (UTC)
- **09:14** `KafkaConsumerLag` fires (P2). Lag climbing on all partitions uniformly.
- **09:20** On-call follows the Kafka consumer-lag runbook; consumers are alive, no rebalance storm — this is a throughput problem, not a crash.
- **09:35** Downstream: each notification made a synchronous call to a provider that had slowed from 40ms to 900ms after their own incident. The consumer processed one message at a time, so throughput collapsed.
- **09:52** Second signal: `HostMemoryPressure` on two consumer nodes; `dmesg` shows the OOM-killer terminated a consumer (exit 137) — a slow-growing leak in the consumer had been building for days and the backpressure tipped it over.
- **10:10** Mitigation part 1: batched the downstream calls and raised consumer concurrency up to the partition count, per the runbook.
- **10:40** Mitigation part 2: restarted the leaking consumers on nodes with headroom (see the OOM-killer runbook) to stop the exit-137 restarts.
- **12:24** Lag drained to zero; notifications real-time again. Resolved.

## Root cause
A downstream provider slowdown exposed two latent problems: the consumer had no
batching (so it was throughput-bound on a synchronous call) and it had a memory
leak that, under the extended backlog, grew RSS until the host OOM-killer stepped
in and restarted it repeatedly — each restart re-reading from the last committed
offset and losing in-flight progress.

## What went well
- The Kafka consumer-lag and OOM-killer runbooks correctly separated the two
  failure modes (throughput vs host memory) so the fixes didn't get conflated.

## What went wrong
- The consumer memory leak had been visible in dashboards for days at P4 and was
  never actioned.
- No batching on a downstream call that could obviously slow down.

## Action items
- Batch the notification downstream calls; add a circuit breaker. (owner: Data)
- Fix the consumer memory leak (heap profile attached). (owner: Data)
- Add a per-consumer memory limit so a leak is contained, not an OOM-kill. (owner: Platform)
