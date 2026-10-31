You are reviewing a personal investment-analysis system (Python 3.9, FastAPI, asyncpg/Postgres) for a Thai swing/position investor (NOT intraday). This is a READ-ONLY review: do not modify any file, do not run network calls, do not run the services, do not read secrets (.env, auth/token files).

Scope (read the code):
- portfolio_engine/signals.py, momentum_base.py, walkforward.py, backtesting.py (composite signals, regime)
- portfolio_engine/predictions.py, macro_trends.py (multi-horizon forecasts, model blending, learning weights, backfill)
- portfolio_engine/risk_engine.py, fx_risk.py, currency_exposure.py, proxy_tracking.py, ai_engine/risk_scorer.py (VaR, beta, drawdown, FX layer)
- portfolio_engine/portfolio_construction.py, rebalancer.py (Black-Litterman / construction, rebalance advice)
- portfolio_engine/trade_plans.py, opportunity_scanner.py (trade plans, gates)
- portfolio_engine/market_context.py, crypto_events.py, brief_generator.py, ai_engine/macro_aggregator.py (macro/news context usage)
- ops/p3_backtest.py (the walk-forward gate used to approve changes)

Owner constraints the system must respect: never place orders; never recommend selling or trimming PTTEP or SCB (owner_holds); swing/position horizon only; no invented values (show unknown); prices/NAVs older than 7 days are stale; anything that changes signals/forecasts/weights/rebalance advice must pass a walk-forward backtest (mean OOS skill up, mean hit rate not down by more than 1 percentage point).

Deliverable: a prioritized findings list. For each finding give: id (F1..), severity (critical/high/medium/low), category (bug | lookahead/leakage | overfitting/statistics | risk-model weakness | advice-logic | context-usage), file:line(s), what is wrong in plain language, evidence (quote the code), concrete fix, and whether the fix is "correctness-only" (does not change signal/forecast/weight/advice numbers under correct data) or "changes-model-output" (must be backtested). Also list the top 5 concrete improvements to analysis and portfolio-adjustment advice with expected benefit. Be specific and verify each claim against the code; do not speculate about code you did not read. Write the final answer in English markdown.
