## Implementation summary

1. **F1 — Owner-hold policy**
   - Added `apply_owner_hold_policy()` in [advice_policy.py](/Users/admin/Projects/investment_advisor/portfolio_engine/advice_policy.py:31).
   - Applied to exit signals, news advisory candidates, and `save_recommendation()` as a final guard.
   - Supports bare and `.BK` ticker forms.

2. **F2 — Backtest gate**
   - Added `gate()` and failing CLI in [backtest_gate.py](/Users/admin/Projects/investment_advisor/ops/backtest_gate.py:19).
   - Added `core_gate_verdict` to [p3_backtest.py](/Users/admin/Projects/investment_advisor/ops/p3_backtest.py:304) without changing existing results.

3. **F7 — Forecast freshness**
   - [predictions.py](/Users/admin/Projects/investment_advisor/portfolio_engine/predictions.py:386) now skips live forecasts unless the underlying close is newer for that subject/horizon.
   - [portfolio_construction.py](/Users/admin/Projects/investment_advisor/portfolio_engine/portfolio_construction.py:127) excludes 1-year views older than seven days and reports them under `stale_views`.

4. **F8 — Mark freshness**
   - [risk_engine.py](/Users/admin/Projects/investment_advisor/portfolio_engine/risk_engine.py:156) adds `price_as_of_by_ticker`, `price_as_of_min`, and `stale_price_tickers`.
   - [rebalancer.py](/Users/admin/Projects/investment_advisor/portfolio_engine/rebalancer.py:78) suppresses sizing from stale/unknown marks and adds `stale_marks`.

5. **F9 — VaR coverage**
   - Added `risk_coverage_weight` and `var_coverage_incomplete` in [risk_engine.py](/Users/admin/Projects/investment_advisor/portfolio_engine/risk_engine.py:320).
   - Existing VaR values remain unchanged.

6. **F10 — Unknown macro inputs**
   - Removed Brent, Fed, BOJ, gold, FX, and gold-weight numeric fallbacks from [brief_generator.py](/Users/admin/Projects/investment_advisor/portfolio_engine/brief_generator.py:847).
   - Dependent analysis is skipped and represented as unknown.
   - Added disclosure-only `unknown_exposure_weight` fields in [fx_risk.py](/Users/admin/Projects/investment_advisor/portfolio_engine/fx_risk.py:208) and [currency_exposure.py](/Users/admin/Projects/investment_advisor/portfolio_engine/currency_exposure.py:290), without changing calculations.

7. **F11 — Trade-plan approval**
   - [trade_plans.py](/Users/admin/Projects/investment_advisor/portfolio_engine/trade_plans.py:483) now recomputes the checklist before approval.
   - Rejects non-viable, stale-price, or failed-checklist plans unless `override_reason` is supplied.
   - Added lazy `override_reason TEXT`; overrides are stored and logged.

8. **F12 — Recommendation evaluation**
   - [backtesting.py](/Users/admin/Projects/investment_advisor/portfolio_engine/backtesting.py:11) selects the first valid close on/after the target calendar date.
   - `watch` outcomes are marked neutral/excluded rather than directional buys.

9. **F13 — Unknown news mood**
   - [macro_aggregator.py](/Users/admin/Projects/investment_advisor/ai_engine/macro_aggregator.py:56) records zero articles and `unknown` mood when no qualifying news exists, using nullable `overall_score` where supported.
   - Readers in [market_context.py](/Users/admin/Projects/investment_advisor/portfolio_engine/market_context.py:45) and [api.py](/Users/admin/Projects/investment_advisor/portfolio_engine/api.py:964) render zero-article tone as unknown.
   - Missing board dates are marked `UNVERIFIED DATE`.

10. **F6 — Scanner shadow storage**
    - [opportunity_scanner.py](/Users/admin/Projects/investment_advisor/portfolio_engine/opportunity_scanner.py:173) no longer writes scanner/news candidates to `recommendations`.
    - Added lazy `scanner_shadow_log`, nullable prices, and `shadow: true` API fields.

11. **F5 — Global-equity no-trade invariant**
    - Added `_core_proxy_target_value()` in [portfolio_construction.py](/Users/admin/Projects/investment_advisor/portfolio_engine/portfolio_construction.py:179).
    - In-band global equity now preserves its current core-proxy value.

12. **F4 — Shadow zero-beta fix**
    - Added default-off `ZERO_BETA_FIX` switches in [predictions.py](/Users/admin/Projects/investment_advisor/portfolio_engine/predictions.py:60) and `macro_trends.py`.
    - Explicit `0.0` remains zero only when enabled; `None` becomes `1.0`.
    - Added read-only comparison runner [codex_gate_backtest.py](/Users/admin/Projects/investment_advisor/ops/codex_gate_backtest.py), using the new gate.

## Validation

- All changed files passed Python 3.9 `py_compile`.
- `pytest` was unavailable in the venv, so the requested fallback was used.
- `unittest`: **7 tests passed** in [test_codex_fixes.py](/Users/admin/Projects/investment_advisor/tests/test_codex_fixes.py).
- The F4 comparison runner was not executed because it requires market-history access and writes to `data/backtests/`, both prohibited during this run.
- No services, git commands, database migrations, or network calls were run.