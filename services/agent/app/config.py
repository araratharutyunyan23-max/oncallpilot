"""Typed configuration (pydantic-settings). Single source of env truth.

Phase 0 scope: only the settings the skeleton actually uses. Phase 1+ knobs
(embeddings, pgvector, MCP) live in .env.example as commented stubs until the
code that consumes them exists — see DECISIONS.md "Explicitly out of scope".
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> str:
    """Resolve the repo-root .env regardless of CWD (local dev runs from
    services/agent). In a container no file is found and OS env vars are used."""
    for parent in Path(__file__).resolve().parents:
        if (parent / ".env").exists() or (parent / ".git").exists():
            return str(parent / ".env")
    return ".env"

DEFAULT_SYSTEM_PROMPT = (
    "You are OncallPilot, an assistant for SRE / on-call engineers. "
    "Answer clearly and concisely, grounded strictly in the information you are given. "
    "If you are unsure, or the information is not available, say so plainly rather than "
    "guessing. Never fabricate runbook steps, ticket IDs, alert names, or metrics."
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_find_env_file(), env_file_encoding="utf-8", extra="ignore"
    )

    # --- Claude (the single required secret in Phase 0) ---
    anthropic_api_key: str | None = None
    chat_model: str = "claude-sonnet-5"
    chat_effort: str = "medium"  # low | medium | high | xhigh | max
    chat_max_tokens: int = 4096
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    cache_ttl: str = "1h"  # ephemeral cache ttl for the frozen system prefix

    # --- HTTP / CORS ---
    cors_allow_origins: str = "http://localhost:3000"
    log_level: str = "INFO"

    # --- Edge guard (operational safety — NOT product auth; see DECISIONS.md) ---
    demo_api_key: str | None = None  # if set, /chat requires a matching x-demo-key header
    rate_limit_per_min: int = 30
    rate_limit_burst: int = 10
    daily_spend_cap_usd: float = 5.0
    max_request_usd: float = 0.50

    # --- Retrieval (Phase 1) ---
    database_url: str = "postgresql://oncallpilot:oncallpilot@localhost:55432/oncallpilot"
    embed_model: str = "BAAI/bge-large-en-v1.5"
    embed_dim: int = 1024
    chunk_tokens: int = 512
    chunk_overlap: int = 64
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_topn: int = 6
    rerank_enabled: bool = False  # measured off — see DECISIONS.md "[P1] Measured decision"
    retrieve_fetch_k: int = 30  # candidates per arm before fusion
    rrf_k: int = 60
    hnsw_ef_search: int = 80

    # --- Agent (Phase 2) ---
    mcp_url: str = "http://localhost:9000/mcp"
    agent_model: str = "claude-sonnet-5"  # prod tier is opus-4-8; sonnet keeps demo cheap
    agent_effort: str = "high"
    max_agent_steps: int = 6
    mcp_destructive_tools: str = "create_jira_ticket"  # local source of truth (not MCP annotation)

    @property
    def destructive_tools(self) -> set[str]:
        return {t.strip() for t in self.mcp_destructive_tools.split(",") if t.strip()}

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
