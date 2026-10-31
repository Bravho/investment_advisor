"""Shadow comparison of macro forecasts with the zero-beta fix OFF vs ON.

Read-only with respect to the database.  It downloads/loads market history,
regenerates forecasts in memory, writes one JSON artifact under
``data/backtests/``, and exits non-zero when the candidate fails the gate.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "portfolio_engine"), str(ROOT / "ops")]

import macro_trends as MT  # noqa: E402
import predictions as P  # noqa: E402
from backtest_gate import gate  # noqa: E402
from market_history import download_closes  # noqa: E402


def _score(records: List[Dict[str, Any]], closes: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[tuple]] = {}
    for record in records:
        series = MT._series(record["subject"], closes)
        if series is None:
            continue
        future = series.loc[pd.Timestamp(record["target_date"]):].dropna()
        if future.empty or float(record["base_price"]) <= 0:
            continue
        actual = math.log(float(future.iloc[0]) / float(record["base_price"]))
        grouped.setdefault(record["horizon"], []).append(
            (actual, float(record["exp_return"]), float(record["sigma"]))
        )
    result: Dict[str, Dict[str, Any]] = {}
    for horizon, rows in grouped.items():
        error = sum(((actual - forecast) / (sigma or 1e-9)) ** 2 for actual, forecast, sigma in rows)
        baseline_error = sum((actual / (sigma or 1e-9)) ** 2 for actual, _, sigma in rows)
        directional = [(forecast > 0) == (actual > 0) for actual, forecast, _ in rows if abs(forecast) > 1e-9]
        result[horizon] = {
            "n": len(rows),
            "skill": (1 - error / baseline_error) if baseline_error else None,
            "hit": sum(directional) / len(directional) if directional else None,
        }
    return result


def _generate(closes: pd.DataFrame, enabled: bool) -> List[Dict[str, Any]]:
    P.ZERO_BETA_FIX = enabled
    MT.ZERO_BETA_FIX = enabled
    MT.SHADOW_LIVE_REGIME_BACKFILL = True
    return MT._backfill_sync(closes, list(MT.MACRO_SUBJECTS), years=6)


def main() -> int:
    tickers = MT._price_tickers(MT.MACRO_SUBJECTS)
    closes = download_closes(tickers, None, "10y", 3600)
    original_p = P.ZERO_BETA_FIX
    original_m = MT.ZERO_BETA_FIX
    original_regime = MT.SHADOW_LIVE_REGIME_BACKFILL
    try:
        baseline_records = _generate(closes, False)
        candidate_records = _generate(closes, True)
    finally:
        P.ZERO_BETA_FIX = original_p
        MT.ZERO_BETA_FIX = original_m
        MT.SHADOW_LIVE_REGIME_BACKFILL = original_regime
    baseline = _score(baseline_records, closes)
    candidate = _score(candidate_records, closes)
    verdict = gate(baseline, candidate)
    artifact = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": str(date.today()),
        "family": "macro_trends",
        "design": "in-memory six-year macro backfill; live SPY regime on all subjects; zero-beta fix off vs on",
        "baseline_zero_beta_fix": False,
        "candidate_zero_beta_fix": True,
        "baseline": baseline,
        "candidate": candidate,
        "verdict": verdict,
    }
    output = ROOT / "data" / "backtests" / f"codex_zero_beta_{datetime.now():%Y%m%d_%H%M}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(artifact, indent=2, sort_keys=True))
    print("saved", output)
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
