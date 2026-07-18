"""Per-request cost accounting from Claude `usage`.

Prices are per-million-tokens (USD). Note: claude-sonnet-5 has intro pricing
($2/$10) through 2026-08-31; we bill at the conservative standard rate here and
move the price table (with `effective_from`) into config in P4. See DECISIONS.md
"Cost accounting".
"""

from dataclasses import dataclass

PRICING: dict[str, tuple[float, float]] = {
    # model: (input_per_mtok, output_per_mtok)
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-fable-5": (10.0, 50.0),
}

# cache-write multiplier by ttl (reads are always ~0.1x input)
_WRITE_MULT = {"5m": 1.25, "1h": 2.0}
_PER_MTOK = 1_000_000.0


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


def cost_usd(model: str, usage: Usage, cache_ttl: str = "1h") -> float:
    p_in, p_out = PRICING.get(model, (0.0, 0.0))
    write_mult = _WRITE_MULT.get(cache_ttl, 2.0)
    return (
        usage.input_tokens * p_in
        + usage.output_tokens * p_out
        + usage.cache_read_input_tokens * p_in * 0.1
        + usage.cache_creation_input_tokens * p_in * write_mult
    ) / _PER_MTOK
