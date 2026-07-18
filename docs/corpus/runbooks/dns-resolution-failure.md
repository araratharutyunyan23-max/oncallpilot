# Runbook: DNS Resolution Failure

**Service:** cluster DNS / any service · **Severity when firing:** P1 · **Owning team:** Platform

Fires when services can't resolve hostnames — internal (`service.namespace.svc`)
or external. Related alert: `DNSErrorRate`. Symptoms cascade widely: connection
timeouts, `Name or service not known`, intermittent 5xx that look like the
downstream is down when really the name won't resolve.

## Triage
1. Reproduce from an affected pod: `nslookup api.internal` and `nslookup example.com`. Distinguish **internal-only** failure (CoreDNS problem) from **external-only** (upstream resolver / egress) from **total**.
2. Is it partial? `DNSErrorRate` spiking on some nodes but not others points at one unhealthy DNS pod or one node's `resolv.conf`.

## Mitigation
- **CoreDNS pods unhealthy.** `kubectl -n kube-system get pods -l k8s-app=kube-dns`. If pods are crash-looping or OOM (see the OOM-killer runbook), restart/scale them. CoreDNS OOM under high query volume is common — raise its memory limit.
- **Upstream resolver down.** If external names fail but internal resolve, the upstream forwarder is the problem — fail over to a secondary resolver in the CoreDNS `forward` config.
- **NDOTS / search-domain amplification.** A high `ndots` makes every external lookup try several search domains first, multiplying query load and latency. Lower `ndots` or use fully-qualified names for hot external calls.
- **Negative-cache too short.** Under a dependency outage, repeated failed lookups hammer DNS. A sane negative TTL absorbs the storm.

## Escalation
DNS failure is rarely localized — if error rate is climbing cluster-wide, page Platform on-call immediately; treat as P1 because it presents as many unrelated service outages at once.
