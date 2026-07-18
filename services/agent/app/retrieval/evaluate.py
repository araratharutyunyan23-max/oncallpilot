"""Offline retrieval eval — no ANTHROPIC_API_KEY needed. Compares dense-only vs
hybrid vs hybrid+rerank on a human-authored gold set, printing recall@k, MRR,
and the rerank-lift on the hard-negative subset. Run: `python -m app.retrieval.evaluate`."""

from pathlib import Path

import yaml

from .db import connect
from .retrieve import hybrid_search

REPO_ROOT = Path(__file__).resolve().parents[4]
GOLD = REPO_ROOT / "eval" / "datasets" / "retrieval.yaml"

MODES = {
    "dense_only": dict(use_sparse=False, use_rerank=False),
    "hybrid": dict(use_sparse=True, use_rerank=False),
    "hybrid_rerank": dict(use_sparse=True, use_rerank=True),
}


def _first_hit_rank(slugs: list[str], gold: set[str]) -> int | None:
    for i, slug in enumerate(slugs):
        if slug in gold:
            return i + 1
    return None


KS = (1, 3, 6)


def run_eval(gold_path: Path | None = None) -> dict:
    cases = yaml.safe_load(Path(gold_path or GOLD).read_text())["cases"]
    conn = connect()
    n = len(cases)
    nh = sum(1 for c in cases if c.get("hard_negative"))
    counts = conn.execute(
        "SELECT (SELECT count(*) FROM documents), (SELECT count(*) FROM chunks)"
    ).fetchone()
    docs, chunks = counts if counts else (0, 0)

    stats: dict[str, dict] = {
        m: {"r": dict.fromkeys(KS, 0.0), "mrr": 0.0, "hmrr": 0.0} for m in MODES
    }
    for mode, flags in MODES.items():
        for case in cases:
            gold = set(case["gold"])
            results, _ = hybrid_search(case["query"], conn=conn, **flags)
            slugs = [r["slug"] for r in results]
            rank = _first_hit_rank(slugs, gold)
            mrr = (1.0 / rank) if rank else 0.0
            stats[mode]["mrr"] += mrr
            if case.get("hard_negative"):
                stats[mode]["hmrr"] += mrr
            for k in KS:
                if any(sl in gold for sl in slugs[:k]):
                    stats[mode]["r"][k] += 1.0
    conn.close()

    print(f"gold: {n} cases ({nh} hard-negative) · corpus: {chunks} chunks / {docs} docs\n")
    header = f"{'mode':14s}" + "".join(f"{'R@' + str(k):>7s}" for k in KS)
    print(header + f"{'MRR':>8s}{'hMRR':>8s}")
    for mode in MODES:
        st = stats[mode]
        print(
            f"{mode:14s}"
            + "".join(f"{st['r'][k] / n:>7.2f}" for k in KS)
            + f"{st['mrr'] / n:>8.3f}{st['hmrr'] / max(1, nh):>8.3f}"
        )

    d, hr = stats["dense_only"], stats["hybrid_rerank"]
    print("\nrerank-lift (hybrid_rerank − dense_only):")
    for k in KS:
        print(f"  R@{k}: {(hr['r'][k] - d['r'][k]) / n:+.2f}", end="")
    print(f"   MRR: {(hr['mrr'] - d['mrr']) / n:+.3f}")
    return stats


if __name__ == "__main__":
    run_eval()
