"""Gate logic tests — floor, regression band, safety metrics — deterministic and
free (no flows run)."""

from app.eval.run import _rate, gate


def test_gate_passes_at_baseline():
    m = {
        "retrieval.recall_at_6": 1.0,
        "answer.faithfulness_mean": 0.99,
        "tasks.confirmation_pass_rate": 1.0,
    }
    assert gate(m, dict(m)) == []


def test_gate_fails_below_safety_floor():
    fails = gate({"tasks.confirmation_pass_rate": 0.83}, {})  # safety floor is 1.0
    assert any("confirmation_pass_rate" in f and "floor" in f for f in fails)


def test_gate_fails_on_regression_past_band():
    # dropped 0.14, band is 0.05 -> regression
    fails = gate({"answer.faithfulness_mean": 0.85}, {"answer.faithfulness_mean": 0.99})
    assert any("regression" in f for f in fails)


def test_gate_allows_within_band():
    # dropped 0.03, band is 0.05 -> allowed
    assert gate({"answer.faithfulness_mean": 0.96}, {"answer.faithfulness_mean": 0.99}) == []


def test_rate_computes_fraction_and_none():
    graded = [{"checks": {"x": True}}, {"checks": {"x": False}}, {"checks": {}}]
    assert _rate(graded, "x") == 0.5
    assert _rate(graded, "missing") is None
