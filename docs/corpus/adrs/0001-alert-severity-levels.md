# ADR 0001: Alert Severity Levels (P1–P4)

**Status:** Accepted · **Date:** 2026-02-10 · **Deciders:** SRE guild

## Context
Alerts were firing at inconsistent urgencies — some paged at 3am for
non-urgent issues, some user-facing outages only sent a Slack message. We need
a single severity scale that maps cleanly to response expectations and to the
`priority` field on incident tickets.

## Decision
Four severities, defined by **user impact**, not by which system is unhealthy:

- **P1 — critical.** Active, broad user-facing outage or data loss. Pages
  on-call immediately, 24/7. Target acknowledgement: 5 minutes. Example:
  `HighApiErrorRate` above 2%.
- **P2 — high.** Degraded service or imminent risk of P1 if unaddressed. Pages
  on-call during business hours; after hours it waits unless it is escalating.
  Example: `RedisMemoryHigh`, `PostgresReplicationLag`.
- **P3 — medium.** Localized or non-urgent degradation with a workaround.
  Slack notification, handled next business day.
- **P4 — low.** Informational / capacity-planning signal. No notification;
  visible on dashboards only.

Ticket `priority` mirrors the alert severity one-to-one (P1 alert → P1 ticket).

## Rationale
Severity by user impact keeps the pager meaningful — engineers trust a page
because a page always means real impact. Mapping severity to ticket priority
removes a manual judgement call during an incident.

## Consequences
- Every alert definition must declare a severity and link a runbook.
- The destructive action `create_jira_ticket` derives ticket `priority` from the
  triggering alert's severity by default; an operator may override it on the
  confirmation step.
