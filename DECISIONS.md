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

## [P1] Measured: hybrid + rerank does not lift on a 31-chunk corpus
- **Context:** The P1 retrieval spine (bge-large-en-v1.5 + Postgres FTS + RRF + bge-reranker-v2-m3) is built. The corpus is 6 real SRE docs → 31 chunks. The offline eval (`app.retrieval.evaluate`, 10 gold cases, 4 hard-negative) reports recall@{1,3,6} and MRR for dense-only / hybrid / hybrid+rerank.
- **Finding (measured 2026-07-19):**

  | mode | R@1 | R@3 | R@6 | MRR |
  |---|---|---|---|---|
  | dense_only | 0.70 | 1.00 | 1.00 | 0.833 |
  | hybrid | 0.70 | 1.00 | 1.00 | 0.833 |
  | hybrid_rerank | 0.50 | 0.90 | 1.00 | 0.725 |

  Rerank-lift is **negative** (R@1 −0.20, MRR −0.108).
- **Decision:** Keep rerank behind the `use_rerank` flag and **do not claim it as a win** until it earns one on a realistic corpus. The eval is committed as the honest baseline. No faked lift.
- **Why:** 31 chunks over 6 heavily cross-linked docs leaves no headroom — top-6 almost always contains a gold chunk regardless of method, so a general multilingual cross-encoder mostly reshuffles near-duplicates. Exactly the risk flagged in *"Narrow corpus vs demonstrate rerank lift"*.
- **Path to a real lift (next):** modestly expand the corpus with more real per-service runbooks to create distractor headroom, and add chunk-level gold so the eval measures whether rerank surfaces the *right step*, not just the right doc. Re-baseline; if rerank still doesn't help at a realistic size, default it **off** with the evidence recorded here rather than shipping a reranker that hurts.

---

## OWASP LLM Top-10 mapping (skeleton — filled in as controls land)

| OWASP | Control | Phase |
|-------|---------|-------|
| LLM01 Prompt Injection | jailbreak classifier + document-block channel separation + indirect-scan (docs + tool output) + operator channel | P4 (input guard seed) |
| LLM02 Insecure Output Handling | citation integrity, leak scan, safe markdown render, no `eval` | P4 |
| LLM04 Model DoS / Unbounded consumption | **edge rate-limit + daily spend cap** (P0) + per-request dollar kill-switch + task budgets | **P0** / P4 |
| LLM06 Sensitive Info Disclosure | Presidio redaction (in/docs/tool/out) + span-mask before Langfuse | P4 |
| LLM07 Insecure Plugin/Tool Design | `strict:true` schemas + tool allowlist + scoped creds + MCP trust boundary | P2 |
| LLM08 Excessive Agency | human-in-the-loop on destructive actions + allowlist + budgets | P2 |
| LLM09 Overreliance | native citations + RAGAS faithfulness gate + grounded refusal | P1 / P3 |
| LLM10 Unbounded / Model Theft | hosted model, key via SDK env, no key echo in traces | P0 / P4 |

The full 42-decision design log for all phases lives in the planning doc (`PLAN.md` / `DECISIONS.md` under `~/Downloads/oncallpilot/`); entries are promoted into this file as each phase is built.
