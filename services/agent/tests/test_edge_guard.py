from app.config import Settings
from app.edge_guard import EdgeGuard


def test_rate_limit_blocks_after_burst():
    s = Settings(rate_limit_per_min=60, rate_limit_burst=3)
    g = EdgeGuard(s)
    assert g.allow("ip1")
    assert g.allow("ip1")
    assert g.allow("ip1")
    assert not g.allow("ip1")  # burst exhausted
    assert g.allow("ip2")  # a different key is unaffected


def test_daily_spend_cap():
    s = Settings(daily_spend_cap_usd=0.10)
    g = EdgeGuard(s)
    assert g.spend_ok()
    g.add_spend(0.09)
    assert g.spend_ok()
    g.add_spend(0.02)
    assert not g.spend_ok()
    assert g.spend_remaining() == 0.0
