"""F3 exact live-composite versus frozen P3.3 walk-forward comparison.

Read-only with respect to application state: market history is downloaded and
one JSON artifact is written under data/backtests/.  This runner never connects
to the database and never creates advice or orders.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "portfolio_engine"), str(ROOT / "ops")]

import signals as S  # noqa: E402
import walkforward as wf  # noqa: E402
from backtest_gate import gate  # noqa: E402
from market_history import download_ohlc  # noqa: E402
from p3_backtest import P33_UNIVERSES, p33_composite_weights  # noqa: E402
from signal_score import cross_section_scores  # noqa: E402


ALLOWED = {"momentum", "low_vol", "technical"}


def _history_frames(tickers: list[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load adjusted Close+Volume through the repository's volume-capable helper."""
    bars = download_ohlc(tickers, period="10y", ttl=3600)
    closes = {ticker: frame["Close"] for ticker, frame in bars.items() if "Close" in frame}
    volumes = {ticker: frame["Volume"] for ticker, frame in bars.items() if "Volume" in frame}
    if not closes:
        raise RuntimeError("market_history.download_ohlc returned no close history")
    close_frame = pd.concat(closes, axis=1).sort_index()
    volume_frame = pd.concat(volumes, axis=1).sort_index() if volumes else pd.DataFrame(index=close_frame.index)
    return close_frame, volume_frame


def _monthly_returns(daily: pd.Series) -> pd.Series:
    clean = daily.dropna()
    if clean.empty:
        return pd.Series(dtype=float)
    return (1 + clean).groupby(clean.index.to_period("M")).prod() - 1


def _folds(daily: pd.Series, benchmark: pd.Series) -> Dict[str, Dict[str, Optional[float]]]:
    """Yearly OOS folds: skill=net excess total return; hit=positive-month rate."""
    output: Dict[str, Dict[str, Optional[float]]] = {}
    for year in sorted(set(daily.index.year)):
        strategy_days = daily[daily.index.year == year].dropna()
        if strategy_days.empty:
            continue
        benchmark_days = benchmark.reindex(strategy_days.index).fillna(0.0)
        monthly = _monthly_returns(strategy_days)
        strategy_return = float((1 + strategy_days).prod() - 1)
        benchmark_return = float((1 + benchmark_days).prod() - 1)
        output[str(year)] = {
            "skill": strategy_return - benchmark_return,
            "hit": float((monthly > 0).mean()) if len(monthly) else None,
            "return": strategy_return,
            "benchmark_return": benchmark_return,
            "n_months": int(len(monthly)),
        }
    return output


def _summary(simulation: Dict[str, Any], start: pd.Timestamp, benchmark: pd.Series) -> Dict[str, Any]:
    daily = simulation["daily"].loc[start:]
    benchmark_oos = benchmark.reindex(daily.index).fillna(0.0)
    result = wf.metrics(daily, benchmark_oos)
    monthly = _monthly_returns(daily)
    result.update({
        "hit_rate": round(float((monthly > 0).mean()), 4) if len(monthly) else None,
        "n_months": int(len(monthly)),
        "oos_from": str(daily.index[0].date()) if len(daily) else None,
        "oos_to": str(daily.index[-1].date()) if len(daily) else None,
        "folds": _folds(daily, benchmark_oos),
    })
    return result


def _run_universe(
    name: str,
    close_all: pd.DataFrame,
    volume_all: pd.DataFrame,
    regime_closes: pd.DataFrame,
) -> Dict[str, Any]:
    spec = P33_UNIVERSES[name]
    benchmark_ticker = spec["benchmark"]
    requested = list(dict.fromkeys(spec["tickers"] + [benchmark_ticker]))
    present = [ticker for ticker in requested if ticker in close_all.columns]
    if benchmark_ticker not in present:
        raise RuntimeError("missing benchmark history for %s" % benchmark_ticker)
    full = close_all[present].dropna(how="all")
    tickers = [ticker for ticker in spec["tickers"] if ticker != benchmark_ticker and ticker in full.columns]
    if not tickers:
        raise RuntimeError("no investable history for %s" % name)
    simulation_prices = full[tickers]
    universe_volumes = volume_all.reindex(index=full.index, columns=tickers)
    benchmark = full[benchmark_ticker].ffill(limit=5).pct_change(fill_method=None).fillna(0.0)

    baseline_fn = lambda h, _param: p33_composite_weights(full.loc[: h.index[-1]], benchmark_ticker)  # noqa: E731
    baseline_sim = wf.simulate(simulation_prices, baseline_fn, None)

    regime_seen: Dict[pd.Timestamp, Dict[str, Any]] = {}

    def candidate_fn(h: pd.DataFrame, _param: Any) -> pd.Series:
        asof = h.index[-1]
        regime_history = regime_closes.loc[:asof].iloc[-260:]
        regime_info = S.regime_from_closes(regime_history)
        regime_seen[pd.Timestamp(asof)] = regime_info
        # Live downloads a two-calendar-year OHLC window.  Preserve that input
        # window because the RSI/MACD EWMs otherwise retain older history.
        price_start = pd.Timestamp(asof) - pd.DateOffset(years=2)
        scores = cross_section_scores(
            simulation_prices.loc[price_start:asof],
            universe_volumes.loc[price_start:asof],
            full[benchmark_ticker].loc[price_start:asof],
            asof,
            regime_info["regime"],
            ALLOWED,
        )
        return wf._top(scores.dropna())

    candidate_sim = wf.simulate(simulation_prices, candidate_fn, None)
    start = full.index[0] + pd.DateOffset(months=12 + wf.TRAIN_M)
    baseline = _summary(baseline_sim, start, benchmark)
    candidate = _summary(candidate_sim, start, benchmark)
    verdict = gate(baseline["folds"], candidate["folds"])
    input_counts = [int(value.get("n_inputs", 0)) for value in regime_seen.values()]
    labels: Dict[str, int] = {}
    for value in regime_seen.values():
        label = str(value.get("regime", "neutral"))
        labels[label] = labels.get(label, 0) + 1
    return {
        "benchmark": benchmark_ticker,
        "tickers": tickers,
        "data_from": str(full.index[0].date()),
        "data_to": str(full.index[-1].date()),
        "baseline": baseline,
        "candidate": candidate,
        "regime_diagnostics": {
            "rebalance_dates": len(regime_seen),
            "labels": labels,
            "min_available_inputs": min(input_counts) if input_counts else 0,
            "max_available_inputs": max(input_counts) if input_counts else 0,
        },
        "verdict": verdict,
    }


def run() -> Dict[str, Any]:
    requested = set(S.REGIME_TICKERS)
    for spec in P33_UNIVERSES.values():
        requested.update(spec["tickers"])
        requested.add(spec["benchmark"])
    close_all, volume_all = _history_frames(sorted(requested))
    regime_columns = [ticker for ticker in S.REGIME_TICKERS if ticker in close_all.columns]
    regime_closes = close_all[regime_columns]
    universes: Dict[str, Any] = {}
    for name in ("global", "thai"):
        universes[name] = _run_universe(name, close_all, volume_all, regime_closes)
    all_pass = all(bool(result["verdict"].get("pass")) for result in universes.values())
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": {
            "baseline": "frozen p33 composite from ops/p3_backtest.py",
            "candidate": "portfolio_engine.signal_score exact live price composite",
            "components_allowed": sorted(ALLOWED),
            "rebalance": "monthly signal at month-end close; execute next trading close",
            "top_k": wf.TOP_K,
            "costs": "walkforward.simulate conventions",
            "oos_start": "first data date + 12-month warm-up + %d training months" % wf.TRAIN_M,
            "gate_folds": "calendar-year OOS; skill=net portfolio total return minus benchmark total return; hit=share of positive net portfolio months",
            "regime": "signals.regime_from_closes using only data <= rebalance date; missing series are omitted by regime_points, and neutral is used if no points exist; historical SET foreign flow is unavailable",
            "volume": "market_history.download_ohlc; missing ticker volume leaves volume_confirm missing and shared live missing-data normalization applies",
            "scope": "research scores only; no database writes, advice, owner-hold sell/trim output, or orders",
        },
        "universes": universes,
        "pass": all_pass,
    }


def main() -> int:
    result = run()
    output_dir = ROOT / "data" / "backtests"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / ("f3_%s.json" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    print("saved", output)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
