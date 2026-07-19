# DECISIONS.md

The reasoning behind the architecture. This is a **living document**: it starts in Phase 0 and each phase appends its decisions. Written for a reviewer — every non-obvious choice states what was rejected and why. Format: **Context / Decision / Rationale / Tradeoffs / Alternatives**. Each entry is tagged with the phase it lands in.

---

## Explicitly out of scope
No product auth, billing, or multi-tenancy; no fine-tuning; the corpus stays narrow (5–7 real SRE docs). Scope-creep ideas ("login to save chats", "arbitrary doc upload") are recorded here as declined, not parked in a backlog. The demo-URL edge rate-limit + spend-cap below is *operational safety*, not product auth, and is in scope.

---

## [P0] Raw Anthropic SDK, not a LangChain chat wrapper
- **Context:** The agent nodes need current Claude features — adaptive thinking, `effort`, native Citations, structured outputs, prompt caching, streaming usage.
- **Decision:** Call Claude through the raw `anthropic` Python SDK behind a thin `llm` seam; do not use `langchain-anthropic` / `ChatAnthropic`.
- **Rationale:** The 2026 Claude surface (adaptive thinking, `output_config.effort`, `citations`, cache_control) is exposed directly by the SDK; a chat-model abstraction lags these and hides the `usage` fields the observability layer needs per request.
- **Tradeoffs:** We write the loop/streaming glue ourselves instead of getting it from LangChain.
- **Alternatives:** `langchain-anthropic` (loses/lags Claude-specific params, obscures usage); provider-agnostic wrapper (premature — this is a Claude-first project).

## [P0] Model routing tiers: haiku / sonnet / opus
- **Context:** Using one model everywhere either overpays (Opus on classification) or underperforms (Haiku on agentic reasoning).
- **Decision:** Route by task: `claude-haiku-4-5` for classify/guard, `claude-sonnet-5` for RAG answers (P0 default), `claude-opus-4-8` for agentic decisions and destructive-gated turns; `claude-fable-5` an optional flag-gated ceiling. In P0 only the sonnet answer path exists; the router lands in P2.
- **Rationale:** Model routing *is* cost management, and it is a visible senior signal. Exact IDs and prices are pinned (see cost accounting).
- **Tradeoffs:** A routing layer to build and justify; risk of mis-routing (bounded by escalation caps + the dollar kill-switch in P4).
- **Alternatives:** Single model (simpler, but burns Opus dollars or caps quality).

## [P0] Adaptive thinking + effort, never `budget_tokens` or sampling params
- **Context:** The current Claude models changed the thinking/sampling surface.
- **Decision:** Always `thinking={"type":"adaptive"}`; control depth via `output_config={"effort": ...}`. Never send `budget_tokens`, `temperature`, `top_p`, or `top_k`.
- **Rationale:** `budget_tokens` and sampling params are removed on current models and return 400; adaptive thinking + `effort` is the supported control. Behavior is steered by prompting, not temperature.
- **Tradeoffs:** No temperature knob for stylistic variety (use prompt instructions).
- **Alternatives:** None viable — the old params error.

## [P0] Demo edge-guard = operational safety, not product auth
- **Context:** A public, unauthenticated `/chat` that spends real money on Claude is a wallet-drain / DoS vector; the scope-fence forbids *product* auth.
- **Decision:** An `edge_guard` in front of the graph: optional demo API-key header, per-key token-bucket rate limit, and a global daily spend cap (P0), extended with a per-request dollar kill-switch in P4.
- **Rationale:** This is the direct answer to "what stops someone running up your Opus bill?" — operational safety distinct from user accounts. Maps to OWASP LLM04/LLM10.
- **Tradeoffs:** In-memory counters are single-process only (not multi-worker safe); a shared store (Redis) is the P4 upgrade. Documented in code.
- **Alternatives:** No protection (unacceptable for a public demo); full auth/billing (out of scope).

## [P0] Liveness vs readiness split (`/healthz` vs `/readyz`)
- **Context:** The container must report healthy for orchestration, but is only *useful* once the Claude key is present.
- **Decision:** `/healthz` = liveness (always 200 while up); `/readyz` = readiness (503 until `ANTHROPIC_API_KEY` is configured). `/chat` returns 503 without a key.
- **Rationale:** Standard k8s/Fly semantics; lets the process boot and be inspected (and the streaming plumbing unit-tested) before a key is wired.
- **Tradeoffs:** Two endpoints instead of one.
- **Alternatives:** Fail-fast at startup (can't boot for inspection without a key).

## [P0] Cost accounting from `usage`
- **Context:** "Cost per request" must be real, not a guessed constant.
- **Decision:** Compute cost from `response.usage` (input/output/cache tokens × a pinned price table) after each call; feed it into the daily spend cap now and the full observability dashboard in P4. Prices live in `cost.py` for P0, moving to `pricing.yaml` (with `effective_from`) in P4.
- **Rationale:** Grounds every displayed dollar figure in measured tokens. Note: `claude-sonnet-5` has intro pricing ($2/$10) through 2026-08-31; we bill at the conservative standard rate.
- **Tradeoffs:** Cache-write multipliers depend on the breakpoint ttl; approximated as 1.25×/2.0× (5m/1h).
- **Alternatives:** Hardcoded per-request cost (fabricated, a reviewer red flag).

---

## Committed for later phases (recorded now so the direction is auditable)

- **[P1] Hybrid retrieval, not pure vector** — dense pgvector kNN + Postgres FTS (`ts_rank`, honestly *not* BM25) fused via Reciprocal Rank Fusion, then a cross-encoder rerank. Pure vector misses exact-token queries (error codes, service names).
- **[P1] Native Anthropic Citations** — retrieved chunks go into document content blocks with `citations={enabled:true}`; real source spans, not model-asserted footnotes. Incompatible with `output_config.format` in the same call, so routing/judge logic runs in separate JSON-schema calls.
- **[P2] MCP tools server as a separate container** — makes the process boundary the trust boundary (allowlist + destructive-confirmation + Jira/CI secrets enforced off the agent process). Reached via the raw MCP Python SDK client, not langchain-mcp-adapters and not the Anthropic MCP connector (the connector executes tool calls server-side inside one turn, which breaks interrupt-before-execute and is incompatible with `strict:true`).
- **[P2] Human-in-the-loop via LangGraph `interrupt()` + PostgresSaver** — destructive actions pause the graph durably; `tool_call_id` doubles as an idempotency key so replay/resume never double-creates a ticket.
- **[P3] Evals as a blocking CI gate** — deterministic safety + retrieval checks block merges without calling Anthropic; LLM-judge quality checks block on regression but degrade to advisory during an API outage.
- **[P4] Observability** — OpenTelemetry → Langfuse; cost/latency/tokens per request; PII redaction at the span processor *before* export.

---

## [P1] Measured decision: ship hybrid dense+FTS, cross-encoder rerank OFF by default
- **Context:** The P1 retrieval spine (bge-large-en-v1.5 + Postgres FTS + RRF + bge-reranker-v2-m3) evaluated against a human-authored gold set with `app.retrieval.evaluate` (recall@{1,3,6} + MRR, plus a hard-negative subset). Measured at **two corpus sizes** to rule out the small-corpus artifact.
- **Finding (measured 2026-07-19) — rerank does not help at either size:**

  | corpus | mode | R@1 | R@3 | MRR |
  |---|---|---|---|---|
  | 31 chunks / 6 docs (10 gold) | dense/hybrid | 0.70 | 1.00 | 0.833 |
  | | hybrid_rerank | 0.50 | 0.90 | 0.725 |
  | 78 chunks / 15 docs (22 gold, 11 hard-neg) | dense/hybrid | 0.82 | 1.00 | 0.902 |
  | | hybrid_rerank | 0.68 | 0.95 | 0.807 |

  Expanding the corpus 2.5× did not create headroom: dense recall@3 stays 1.00 and rerank still lowers top-1.
- **Diagnostic (why):** inspecting trap queries (deploy rollback, exit-137 host OOM, 429) shows dense already returns the correct runbook's chunks across the whole top-3; the reranker keeps #1–#2 correct but diversifies #3 into topically-related chunks in *other* docs (e.g. the api-5xx "roll back first" section for a rollback query). On **doc-level** gold that reads as a regression. bge-large dense retrieval is simply strong enough on this focused SRE domain that recall saturates — the reranker has nothing to fix and only adds reordering risk.
- **Decision:** Ship **hybrid dense + Postgres FTS (RRF)** as the retrieval path; default the cross-encoder rerank **OFF** (`RERANK_ENABLED=false`; `use_rerank` flag retained, eval still exercises all three modes). Evidence-based, not assumed. Rerank also adds real CPU latency — it dominated the eval wall-clock — for negative benefit here.
- **When to revisit:** rerank earns its place on a larger/noisier corpus, or under **chunk-level** gold that measures whether it surfaces the right *passage* rather than the right doc. The flag + eval are in place to re-measure and flip the default when the data supports it.
- **Anti-cargo-cult note:** "hybrid + rerank" is a reflexive default. We built it, measured it twice, and turned rerank off on evidence. That measurement — and the decision it drove — is the senior signal, not the presence of a reranker.

---

## [P2] Human-in-the-loop: static interrupt_before + MemorySaver (first cut)
- **Context:** Destructive tools (`create_jira_ticket`) must pause for human approval *before* executing. The agent is a LangGraph `StateGraph`, and the pause must survive the `/agent` → `/resume` HTTP boundary.
- **Decision:** Route destructive actions to a `human_approval` node compiled with **static `interrupt_before`**; the operator's approve/deny is injected into state via `update_state` before the run is resumed. Checkpointer is an in-process **MemorySaver**.
- **Rationale (measured 2026-07-19):** LangGraph 1.2.9's *dynamic* `interrupt()` raises `Called get_config outside of a runnable context` inside async nodes — reproduced in isolation across `ainvoke` / `astream` / both stream modes. Its run-config contextvar isn't set for async node execution. Static `interrupt_before` uses a different pause mechanism that works. MemorySaver keeps the pending action durable across the two HTTP requests within one worker.
- **Tradeoffs:** MemorySaver is not durable across restarts or multiple workers (a pending approval is lost if the process dies); the decision travels via `update_state` rather than as the interrupt's return value. Destructive-action gating is enforced at the **agent** (the local `is_destructive` policy), not at the MCP server — the server trusts its caller within the process/trust boundary; server-side approval tokens are a P4 hardening item. `/agent` always mints a fresh conversation id (a client-supplied id could collide with or resume another thread's state), and run cost is billed to the edge guard as a per-thread cumulative delta so pause→resume never double-charges. (These three were found by the P2 adversarial code review and fixed.)
- **Upgrade path:** **PostgresSaver** (`langgraph-checkpoint-postgres`) for cross-restart/worker durability; revisit dynamic `interrupt()` when the langgraph contextvar issue is fixed. Idempotency is independent of the checkpointer: `tool_call_id` is passed as the MCP `idempotency_key`, so even a duplicated execute never creates a second ticket.
- **Alternatives considered:** Anthropic MCP connector (executes tool calls server-side inside one model turn → can't gate before execution; also incompatible with strict tools) — rejected per the MCP-client decision above.

---

## [P3] Evals as a two-tier CI gate
- **Context:** "Works on my machine" isn't a quality bar. The project's headline signal is measurable quality that can't be silently dropped.
- **Decision:** Two tiers. (1) A **deterministic** tier — retrieval recall, agent tool-selection, the destructive **confirmation gate**, and "no forbidden tool executed" — computed by running the real flows and inspecting outputs, **zero-tolerance** on the safety checks (floor 1.0), and (for retrieval) **no Anthropic call** so it can gate a PR without a key/secret. (2) A **thresholded quality** tier — faithfulness (LLM judge via structured outputs), must_include / must_cite, answer relevance — gated on a **floor + regression band** vs a committed **baseline ratchet** (`eval/baseline.json`). `run_evals` exits non-zero on any breach; the answer/task tiers gate only when `ANTHROPIC_API_KEY` is set.
- **Judge:** faithfulness is scored by a **pinned `judge_model`** (a dedicated config setting, deliberately decoupled from `chat_model` so the grader never grades its own output, and pinned so the baseline stays reproducible) + fixed prompt + `json_schema` structured output (no majority-of-N — sampling params are unavailable on current models, so N identical calls add cost without variance reduction; residual variance is absorbed by the regression band). Transient judge errors (429/5xx/connection) are **retried** before falling back to 0.0, so a network blip can't red the gate for infra reasons rather than answer quality.
- **Measured (2026-07-19, seeded baseline):** retrieval recall@6 1.00 / MRR 0.90 (n=22); answer faithfulness mean 0.989, must_include 1.00, must_cite 1.00; task confirmation-gate + no-forbidden 1.00. The suite **caught a real blemish**: an out-of-corpus "refusal" answer correctly refused but still named outside specifics (Istio `PeerAuthentication`/`DestinationRule`) — surfaced per-case (not gated). That is the point of evals: catching the subtle thing a human misses.
- **Known follow-up:** langgraph `MemorySaver` warns when msgpack-serializing the raw Anthropic content blocks kept in agent state (works today; forward-compat fix is to store plain dicts or register the block types).

---

## OWASP LLM Top-10 mapping

Two kinds of control: **structural** (code-enforced, holds regardless of any classifier) and **detective** (heuristic/regex, best-effort, upgradeable). Status: ✓ shipped · ~ partial.

| OWASP | Control (structural in **bold**) | Status |
|-------|-----------------------------------|--------|
| LLM01 Prompt Injection | **retrieved docs as document content blocks** + **datamarked (`<untrusted_*>`) tool output** + heuristic `injection.classify` input block (haiku-classifier upgrade) | ✓ (P2 separation + P4 guard) |
| LLM02 Insecure Output Handling | `scrub_output` secret-scrub of the model's answer + **safe React render (no `dangerouslySetInnerHTML`, no `eval`)** · citation-integrity | ✓ scrub/render · ~ citation-integrity |
| LLM04 Model DoS / Unbounded | **edge rate-limit + daily spend cap + per-thread cumulative-delta billing** (single Opus bill can't be run up anonymously) | ✓ (P0/P2) |
| LLM06 Sensitive Info Disclosure | regex PII/secret **redaction of tool output before the model sees it** + output scrub (Presidio upgrade) | ✓ P4 (regex) |
| LLM07 Insecure Plugin/Tool | **`strict:true` tool schemas + tool allowlist (`is_destructive`) + MCP as a separate process/trust boundary** | ✓ P2 |
| LLM08 Excessive Agency | **human-in-the-loop `interrupt_before` on every destructive call + `tool_call_id` idempotency + agent-side gating (not the tool server's word)** | ✓ P2 |
| LLM09 Overreliance | **native Anthropic citations** + faithfulness **eval gate** (P3) + **grounded refusal** on out-of-corpus | ✓ (P1/P3) |
| LLM10 Unbounded consumption / model theft | hosted model, key via SDK env (**never echoed in traces/logs**), spend caps | ✓ (P0/P4) |

The prompt-injection and excessive-agency defenses are deliberately **structural**: the HITL gate and document-block separation hold even if `injection.classify` misses — the classifier is defense-in-depth, not the load-bearing control.

---

## Adversarial polish pass (2026-07-19)

After the feature build (P0–P4), the codebase went through a **multi-agent review**: seven senior-reviewer agents each swept one quality axis (agent core, retrieval, coral layer, MCP/tools, web, Claude-API currency, tests/consistency), and **every finding was then adversarially re-verified** by an independent skeptic that read the actual code and judged *real? safe-to-fix? genuine improvement or churn?* — defaulting to reject. Of 34 worth-it findings, 29 survived verification and were applied; 1 was deferred as architectural; 4 were rejected as taste/risk.

Representative fixes (all with tests/lint/mypy green after):
- **Ingest idempotency (high):** under the autocommit connection, `upsert_document` committed the new `content_sha` *before* chunks were embedded/inserted; a failure mid-way left the doc row carrying the final sha with zero chunks → permanently "unchanged" and never re-indexed. Now each document's upsert+chunk+insert runs in **one `conn.transaction()`** (works under autocommit), so the sha and its chunks commit together or roll back together.
- **Connection leak:** `hybrid_search` closed its owned connection only on the success path — now a `try/finally`, so an embed/SQL/rerank error can't exhaust the pool on the hot path.
- **Guardrail breakout:** `datamark` now de-fangs a forged `</untrusted_*>` delimiter so hostile tool output can't escape the data channel back into instruction context.
- **Eval-gate integrity:** `--update-baseline` **merges** instead of overwriting (a keyless reseed no longer erases the LLM-tier ratchet), and a safety metric that lost all its cases now **fails loudly** instead of silently dropping out of the gate.
- **UI robustness:** the SSE read loop is wrapped so a mid-stream drop can't wedge the console busy forever; in-flight streams are **aborted on unmount/new-send**; the destructive-action approval gate got `role="alertdialog"` + focus management (the most safety-critical surface was silent to assistive tech).
- **Prompt caching:** the agent decide-loop now sets a per-request cache breakpoint on the growing doc-blocks/tool-result prefix (applied to a request-only copy so breakpoints never accumulate in persisted state).

**Deferred (needs sign-off):** the faithfulness judge grades a *separately re-retrieved* context rather than the exact blocks the model saw — harmless today (deterministic retrieval, identical defaults) but the correct fix reaches into the production streaming contract, so it's a human-approved change, not an autonomous one.

**Method note:** this is the same verify-before-trust discipline used during the build, applied to the finished code — the point of the adversarial second pass is that a plausible-but-wrong "fix" is worse than no fix.

---

The full 42-decision design log for all phases lives in the planning doc (`PLAN.md` / `DECISIONS.md` under `~/Downloads/oncallpilot/`); entries are promoted into this file as each phase is built.
