# Runbook: Deploy Rollback

**Service:** any · **Severity:** matches the incident it mitigates · **Owning team:** owning service team

The fastest mitigation for a bad deploy is almost always to roll back first and
debug after. Many other runbooks (API 5xx, LB 502) point here. Rollback restores
the previous known-good revision; it does not fix the bug — that is a follow-up
forward fix.

## When to roll back
- An incident (5xx spike, latency, 502, crash-loop) starts within minutes of a
  rollout. Correlation with a deploy is strong enough evidence — do not wait to
  root-cause before rolling back.
- New pods never become ready (empty endpoint set → 502).

## Procedure
1. Identify the current and previous revisions: `deploy history <service>` (or `kubectl rollout history deployment/<service>`).
2. Roll back: `deploy rollback <service> --to-previous` (or `kubectl rollout undo deployment/<service>`). Watch pods become ready.
3. Confirm recovery: error rate and latency return to baseline; endpoint set is healthy.
4. **Lock the bad revision** so CI/CD doesn't immediately redeploy it, and open a ticket to fix forward.

## Gotchas
- **Database migrations.** If the bad release ran a non-backward-compatible schema migration, a code rollback alone can break against the new schema. Roll back only if the migration is backward-compatible; otherwise you need a forward fix or a down-migration — get Data on-call involved. This is why migrations must be backward-compatible by policy.
- **Config vs code.** If the bad change was a config/flag flip rather than a deploy, "rollback" means reverting the flag, not the image.

## After rollback
File a follow-up: the change is only reverted, not fixed. A rollback used during an incident should always produce a fix-forward ticket.
