import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "portfolio_engine"))
from country_flows import confirmation_label, lead_score  # noqa: E402


def test_observed_flow_does_not_enter_lead_score():
    base = {"relative_equity_momentum": 50, "global_risk_appetite": 20,
            "fx_trend": 10, "rate_carry": -10}
    assert lead_score(base) == lead_score({**base, "observed_flow": -100})


def test_sparse_score_is_not_actionable():
    result = lead_score({"fx_trend": 100})
    assert result["label"] == "insufficient_data"
    assert result["coverage"] == 0.15


def test_weights_renormalize_over_available_features():
    result = lead_score({"relative_equity_momentum": 100, "global_risk_appetite": -100,
                         "fx_trend": 100, "rate_carry": -100})
    assert result["coverage"] == 0.75
    assert round(result["score"], 2) == 6.67


def test_flow_confirmation_uses_day_or_five_day_threshold():
    assert confirmation_label(1.2, 0.0) == "observed_net_buying"
    assert confirmation_label(0.0, -3.2) == "observed_net_selling"
    assert confirmation_label(0.2, 0.4) == "mixed_or_small"
