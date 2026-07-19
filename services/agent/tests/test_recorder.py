from app.obs.recorder import Recorder, RequestTrace


def _t(**kw):
    base = dict(
        ts=0.0, endpoint="rag", model="claude-sonnet-5", tokens_in=0, tokens_out=0,
        cache_read=0, cost_usd=0.0, latency_ms=0, tools=[], paused=False, ok=True,
    )
    base.update(kw)
    return RequestTrace(**base)


def test_summary_percentiles_and_mix():
    r = Recorder()
    for i in range(1, 6):
        r.record(
            _t(
                cost_usd=0.01 * i,
                latency_ms=100 * i,
                tools=(["get_ci_status"] if i == 3 else []),
                ok=(i != 5),
            )
        )
    s = r.summary()
    assert s["count"] == 5
    assert s["total_cost_usd"] == round(0.01 * 15, 6)
    assert s["p50_latency_ms"] == 300
    assert s["p95_latency_ms"] == 500
    assert s["models"]["claude-sonnet-5"] == 5
    assert s["tool_calls"] == 1
    assert s["error_rate"] == 0.2


def test_recent_is_newest_first_and_limited():
    r = Recorder()
    for i in range(3):
        r.record(_t(ts=float(i), endpoint="agent"))
    rec = r.recent(2)
    assert len(rec) == 2
    assert rec[0]["ts"] == 2.0  # newest first


def test_empty_summary():
    assert Recorder().summary() == {"count": 0}
