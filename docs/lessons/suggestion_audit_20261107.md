# Suggestion audit, 7 Nov 2026: did past suggestions beat the market?

Short answer: **not proven.** The data shows no statistically reliable edge yet, and the
live scoring had bugs that made the reported accuracy wrong. Both are now documented and
the scoring bugs have a tested fix (not yet switched on live).

## 1. What was measured

- Source: `recommendations` (2,548 raw rows, 6 Jun to 1 Nov 2026), `paper_trades` (252).
- Benchmark: TDEX.BK (SET50 ETF), the project's SET proxy. Free yfinance download.
- Window: 7 days after each suggestion.
- Script: `ops/suggestion_audit.py` (read-only). Scoring rules: `portfolio_engine/suggestion_scoring.py`.

## 2. Data problems found (fix these first)

| Problem | Size | Effect |
|---|---|---|
| Repeated identical suggestions (same ticker, action, day) | 2,548 raw rows, about 190 unique ticker-day-action rows | Inflates counts about 13x |
| `review_buy` / `review_reduce` missing from the scoring sets | 38 + 7 rows | Every one marked wrong, a labeling bug, not a real signal |
| Missing price stored as `0.0` and scored as a 0% return | 12 review_buy, 2 review_reduce | Fake wrong results |
| Price taken up to 23 days late, not 7 | Several rows (`days_held` 23) | Stale window scored as if on time |
| Scoring ignores the market (raw return sign only) | All rows | A +1% stock in a +3% market counts as a win |
| `watch` rows scored under an older rule | 146 rows in the live table | Mixed rules in one table |

## 3. Results after cleaning

Usable, deduplicated, valid-price rows: **90** (of 190 unique). Benchmark TDEX.BK moved +0.84% on average over the same windows.

| Action | Scored n | Hit rate (beat market) | Mean excess return | t-stat |
|---|---|---|---|---|
| accumulate | 29 | 58.6% | +0.40% | 0.52 |
| watch (no position, tracked only) | 61 | not scored | +0.35% | 0.82 |
| review_buy / review_reduce | 0 usable | n/a | n/a | n/a |

- A t-stat around 2 or more is needed for confidence. Both results are well below that.
- `watch` picks beat the market on average by +0.35%, but only 5 of 61 moved more than +5%.
- Split at 15 Sep 2026: too few rows after the split (2 watch) to compare.

## 4. Existing backtests: what they actually prove

Files: `data/backtests/*.json`.

- **p33 live composite, global universe:** CAGR 23.8% vs SPY 15.6% (excess about +8.3% a year), Sharpe 0.90, max drawdown -31.5%. **But** the universe was picked with hindsight (NVDA, MU, TSM, AVGO, which were winners). Survivorship and selection bias are likely, so treat this as optimistic.
- **p33 live composite, Thai universe:** CAGR 1.9% vs TDEX.BK 4.7% (excess about **-2.75% a year**), Sharpe 0.20, max drawdown **-43.9%**. The gate still shows `pass_thai: true`.
- **Lesson:** the gate flags check improvement over the *old formula*, not over the *market*. A design can "pass" and still lose to a cheap index fund.
- **codex_zero_beta:** failed (mean skill -0.3%). Correctly rejected.
- **earnings_band_gate:** passed with skill 0.37% to 0.39%, a tiny change, on only 6 tickers. Multipliers were fit before 2022 and tested after, which is good, but the effect is too small to trust.
- **earnings_gate:** only `post_gap_block` passed, with skill 0.162 to 0.176 and hit rate unchanged. Other variants lowered hit rate. Weak evidence.
- **f3:** failed (`pass: false`).
- **P3 family:** core and macro_trends, 3-year OOS window. Results summarized, not re-checked in this audit.

## 5. Paper trades

- 4 closed trades, all stopped out, net -6,094 THB total (avg R-multiple -1.24). Small sample, but every closed trade lost.
- 224 of 252 paper trades are `plan_superseded` with no P&L, so they never produced a result. This hides the real trade record.

## 6. Lessons

1. **Measure against the market, not against zero.** A win is an excess return over TDEX.BK (or SPY for US names).
2. **Never score missing data.** A missing price must be "not scored", never 0%.
3. **Keep the window honest.** Only score prices from the target window (7 days, max 3 days late).
4. **Dedupe before counting.** One idea, one row.
5. **Make gates test the market, not just the old formula.** The Thai universe shows the current design can lose to the index while passing its own gate.
6. **Do not trust small samples.** Under about 100 scored rows per action cannot show an edge.
7. **Avoid hindsight universes.** Choose tickers by a rule fixed before the test, not after seeing winners.

## 7. What changed in code (proposed, not switched on)

- `portfolio_engine/suggestion_scoring.py`: benchmark-relative scoring with the fixes above.
- `tests/test_suggestion_scoring.py`: 10 unit tests, all passing.
- The live evaluator in `portfolio_engine/backtesting.py` still uses the old rules. Switching it on changes how past results are reported, so it needs the user's approval.

## 8. Open items

- Need more scored history before any conclusion. The window ends 30 Oct, so recent suggestions are not yet due.
- Thai universe: propose a market-relative gate and review the Thai signal before using it for sizing.
- Paper trades: investigate why 224 were superseded without a result.
