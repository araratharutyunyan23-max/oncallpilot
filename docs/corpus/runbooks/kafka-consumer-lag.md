# Runbook: Kafka Consumer Group Lag

**Service:** `events-consumer` · **Severity when firing:** P2 · **Owning team:** Data

Fires when a consumer group falls behind the tail of its topic. Related alert:
`KafkaConsumerLag` (`kafka_consumergroup_lag > 100000` for 10m). Lag means
downstream data (notifications, analytics, search indexing) is stale.

## Assess
1. Measure it: `kafka-consumer-groups --bootstrap-server $BROKER --describe --group events-consumer`. Look at `LAG` per partition — is it uniform or concentrated on a few partitions?
2. Are consumers alive? Frequent rebalances (`CURRENT-OFFSET` not advancing, members joining/leaving) point to slow processing or crashes, not throughput.

## Mitigation
- **Slow processing.** If each message does an expensive downstream call, the consumer can't keep up. Increase consumer concurrency or batch the downstream writes. Scaling consumers only helps up to the partition count.
- **Too few partitions.** Consumer parallelism is capped at the partition count. If all consumers are busy and lag still grows, the topic needs more partitions (a forward fix, not an incident action).
- **Poison message / stuck partition.** One partition not advancing while others are fine usually means a message that repeatedly fails processing. Identify the offset, fix the handler or skip the offset deliberately, and document it.
- **Rebalance storm.** If the group rebalances constantly, raise `max.poll.interval.ms` / reduce `max.poll.records` so a slow batch doesn't get the consumer evicted.

## Do not
- Do not reset offsets to `latest` to "clear" lag on a topic that drives correctness (it drops unprocessed events). Offset resets require Data on-call sign-off.

## Escalation
If lag keeps growing after scaling to the partition count, page Data on-call — the bottleneck is downstream, not the consumer.
