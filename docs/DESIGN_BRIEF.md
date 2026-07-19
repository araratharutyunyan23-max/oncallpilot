# OncallPilot — UI Design Brief

_A brief you can hand to a designer or studio. There is already a working reference
build (a dark "operator console") and a rendered preview — treat it as **v0**: elevate
it, or propose a stronger distinct direction._

## Product in one line
An AI on-call assistant for SRE / DevOps engineers. It answers questions from internal
runbooks **with cited sources**, and it **takes actions** (check CI status, query
monitoring alerts, file an incident ticket) — pausing for **human approval** before
anything destructive.

## Who it's for
On-call / SRE engineers, often mid-incident: high-stress, time-critical, working at odd
hours in dark tools (terminals, Grafana, PagerDuty). They value **density,
scannability, and trust signals** over decoration. Secondary audience: hiring managers
reviewing this as a portfolio piece — so it must look like a real production tool.

## The one job of the UI
Let an engineer type an incident or question and either:
1. **Ask** — get a fast, grounded answer with clickable citations to the source runbook; or
2. **Act** — watch the agent gather facts and propose an action, then **approve/deny** it —
   with total clarity on what the agent did, what it's about to do, and what it cost.

## Chosen visual direction — "Operator console" (dark)
Technical, dense, dark-first. Reads like an incident tool (Grafana / Datadog / Linear /
Warp / Raycast), **not** a chatbot and **not** a marketing SaaS page. One restrained
accent; machine data in monospace; severity encoded in color and shape (pills/stripes),
separate from the accent. Committed to dark by design (the on-call context); a light
theme is optional, not required.

## Palette (starting tokens — refine, don't feel bound)
| Role | Hex |
|---|---|
| Base (page) | `#0B0E14` |
| Surface / inset | `#131722` / `#0F1420` |
| Border | `#1F2733` |
| Text / muted / faint | `#E5E9F0` / `#8B93A7` / `#5A6377` |
| Accent (single) | teal `#2DD4BF` |
| Severity P1 / P2 / P3 | `#F43F5E` / `#F59E0B` / `#38BDF8` |
| Success | `#34D399` |

Neutrals are cool / slightly blue-biased — chosen, not default grey. Semantic colors
(P1–P4, success) are **not** the accent.

## Typography
- **Sans** (system-UI / Inter-like) for prose and labels.
- **Monospace** (JetBrains Mono-like) for IDs, tool names, arguments, doc slugs, costs, timestamps.
- Small **uppercase, letter-spaced** labels for section headers (`AGENT TRACE`, `CITATIONS`).
- Tabular numerals wherever figures align (cost, tokens, latency).

## Screens & states to design
1. **Console** — single focused column: header (brand + live status + **Ask / Act** toggle) + input row.
2. **Ask result** — streamed grounded answer, inline **citation chips** (footnote → source), a sources list, and a **cost / token badge**.
3. **Act — agent trace** — a live timeline of steps (retrieve → decide → tool call → result), each status-coded.
4. **Human-approval gate (signature moment)** — a card surfacing the proposed **destructive** action (tool, human-readable preview, raw args) with **Approve / Deny**; the agent is visibly paused here.
5. **Empty / streaming / error** states.
6. **(Phase 4) Evals & observability dashboard** — cost-per-request, p50/p95 latency, faithfulness trend, token mix, tool-call log, guardrail feed. Give charts real data-viz care (area fills, faint grid, emphasized endpoints).

## Interaction & motion
Restrained. Streaming text should feel live but not jittery. The approval card should
**draw the eye as a decision point** without being alarmist. Tasteful hover / button
micro-interactions. Respect `prefers-reduced-motion`.

## Copy tone
Operator-grade: terse, active voice, says exactly what happens ("Approve" → toast/line
"Ticket created SRE-4201"). Errors state what went wrong and how to fix it. No cutesy AI
persona, no apologies.

## Deliverables (suggested)
- Hi-fi mockups of states 1–5 (desktop-first + a narrow/responsive variant).
- A **design-token set** (colors, type scale, spacing, radii) as CSS variables / Figma
  tokens, so it maps 1:1 onto the build.
- Optional: light theme; a logo/wordmark treatment for "OncallPilot".

## Build constraints (so the design lands cleanly)
- Implemented in **Next.js 15 + Tailwind**; tokens should map to Tailwind theme values.
- Self-contained assets (no external font CDNs at runtime).
- Domain vocabulary to use correctly: runbook, ADR, postmortem, alert (P1–P4), CI
  pipeline / run, Jira incident ticket, human-in-the-loop approval, citation.

## References
Grafana, Datadog, Linear, Vercel dashboard, Warp, Raycast.
**Avoid:** chatbot bubbles, purple→blue marketing gradients, cream + serif editorial, emoji as section markers.

---
_Reference build: `apps/web` (dark operator console, working). Rendered preview available
as an artifact. The designer may elevate v0 or pitch a distinct direction that still fits
the brief above._
