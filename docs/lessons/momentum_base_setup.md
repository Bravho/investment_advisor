# Lesson: momentum + base setup → `momentum_base_swing`

Source: trading lesson shared by Tho on LINE, 30 Oct 2026 (Thai, parts 1–3 of 4; **part 4 not received yet**).
Tho's instruction: learn from it, adapt it to this project, don't follow it blindly.
Tho's constraints: he is a **swing/position investor, not a day trader**, and he places every order himself.

## What the lesson says (summary of the original)

| Part | Original lesson |
|---|---|
| 1/4 Strong stocks + base | Screener sorted by 1, 3, 6-month return; focus on names up >30% and in the top 20–30%; drop illiquid names; weekly chart first, then daily. Look for higher lows, tightening swings, price back above EMA 9/21 that are flattening or turning up. |
| 2/4 Support then trigger | On the daily chart combine EMA 9/21/50, AVWAP, prior highs/lows and gaps as support. Then on 1/5/15-min charts wait for a pullback and bounce; buy on a break of the prior candle's high. Prefer the first retest of support after a breakout of a key level (example: AMPX zone $7.45–7.50). |
| 3/4 Stop first, then size | Stop at the intraday low or the signal candle's low. Example: $10,000 account, 0.5% risk = $50; buy $20, stop $19.50 → 100 shares = $2,000 (20% of the account). Enter on the signal and set the stop at once; price can gap through a stop. |
| 4/4 | *Not received yet. Add it here and adjust the setup when it arrives.* |

## How it was adapted (and why)

| Lesson element | Adaptation in this project | Why |
|---|---|---|
| 1/3/6m return screener | Relative-strength score = weighted percentile (20% 1m, 40% 3m, 40% 6m) inside each market (SET and US ranked separately). Pass = RS percentile ≥ 70 (top 30%) **and** 3m or 6m return ≥ 30% (US) / 20% (SET). | SET large caps rarely move 30% in 3–6 months; the top-30% percentile rule still applies. Thresholds live in `config/setups.json`. |
| "Remove low-volume names" | 20-day average traded value ≥ 50M THB (SET) / $20M (US); price ≥ 1 THB / $5. The trade-plan checklist also requires ADV ≥ 20× the position. | Turnover, not share count, is what matters for slippage. |
| Weekly chart first | Weekly close > EMA10w > EMA30w, EMA10w rising, weekly higher lows (completed weekly bars only). | This is the trend filter for a swing/position horizon. |
| Base: higher lows, tighter swings, EMA 9/21 reclaim | Daily: 10-day low above the prior 20-day low; ATR10/ATR50 ≤ 1.0 or 10-day range ≤ 60% of the 30-day range; close above EMA9 and EMA21; EMA21 5-day slope ≥ −0.2%. A base score from 0 to 100 is shown on /desk. | This is a VCP-style volatility contraction, measured objectively. |
| Breakout of a key level, then first retest | Breakout = close above the prior 50-session high (pivot). Within 25 sessions, the **first** pullback that touches EMA9/EMA21/the breakout level (±0.5 ATR) is the retest. If it fails to trigger within 5 sessions, the setup is void: there is no second retest. | This is the lesson's "first retest" rule, applied mechanically. |
| Support confluence (EMA 9/21/50, AVWAP, pivots, gaps) | Levels: EMA9/21/50 daily, EMA10 weekly, AVWAP anchored at the breakout day and at the 6-month swing low, the breakout level, prior swing highs (old resistance), recent swing lows, and unfilled up-gaps. Levels within 0.5 ATR are clustered. The zone is the nearest cluster below price with ≥ 2 kinds of evidence, within 3 ATR. | The zone feeds the trade-plan entry zone and stop. |
| **1/5/15-minute trigger** | **Dropped.** Daily trigger only: a buy-stop 1 tick above the prior day's high after the retest (or the close-confirm variant: a daily close above the prior high, entering at the next open). Walk-forward picks the variant. | Tho does not day trade, and no free, reliable intraday SET data exists. |
| Stop at the signal-bar low | Stop = min(pullback low, signal-bar low, zone low) − k × ATR14, with k ∈ {0.5, 1.0} chosen by walk-forward. Trades are skipped if the stop is more than 10% below entry. | This gives room for normal daily volatility on a weeks-to-months hold. |
| Size = risk ÷ per-share risk | Same formula, using the per-trade risk % (default = `risk_limits.json` 1.0%; the lesson's 0.5% is recorded as `lesson_risk_pct`). The per-share risk is increased by the typical bad overnight gap (5th percentile of open/prev-close over 1 year), then the **25% per-stock and 40% per-sector caps** apply, plus SET 100-share lots. | The lesson itself warns that price can gap through a stop. Tho's limits are unchanged. |
| (no exit rule in parts 1–3) | Sell half at +3R and move the stop to breakeven. Trail the rest on a daily close < EMA21 (once +1R), a daily close < EMA50, or a weekly close < EMA10w; walk-forward picks the rule. Time stop 252 sessions. A gap through the stop exits at the open. | Fits the swing/position horizon. |
| Intraday entry "set the stop immediately" | The plan lists the stop. Tho places both orders himself at his broker. | **No order or broker code exists in this project.** |

## Where it lives

- Code: `portfolio_engine/momentum_base.py`. Config: `config/setups.json`. API (8996):
  - `GET /setups/momentum-base`: latest screen plus a backtest summary
  - `POST /setups/momentum-base/run`
  - `GET|POST /setups/momentum-base/backtest[/run]`
  - `GET /setups/momentum-base/advisor-context?tickers=`
- Schedule: screen at 17:45 ICT Mon–Fri (after the SET close) and 06:47 ICT (before the brief, once the US close is in); walk-forward backtest Sunday 05:30 ICT.
- Trade plans: `trade_plans.source='setup'` and `trade_plans.setup='momentum_base_swing'`. Status is always `proposed`. Approval on /desk only logs Tho's decision and copies the levels to the watch list for alerts.
- /desk: a "Momentum + base (swing)" panel shows the screen, states, zone, trigger, stop, target, backtest vs existing signals, and the live parameters. Plans carry an "MB swing" tag.
- LINE secretary → 8991 advisor: the advisor context includes the setup screen, per-ticker levels and the backtest evidence.
- DB (local `investor_db`, additive only): tables `setup_screens` and `setup_backtests`, and the column `trade_plans.setup`. Backup taken first: `~/backups/investor_db/investor_db.full.20261030-115243.dump`.

## Backtest (walk-forward, out-of-sample 2019-10-31 → 2026-10-29)

Rules: parameters (trigger variant, ATR buffer, exit rule) are chosen on a trailing 24-month train window by expectancy and applied to the next 6 months; only OOS trades are reported. One position per ticker at a time. Costs: SET 0.157% + VAT + 0.10% slippage per side; offshore 0.15% + 0.25% FX + 0.10% per side. Portfolio sim: 1% risk per trade with the gap haircut, 25% cap per position, max 6 open, no leverage.

| Universe | Variant | Trades | Hit | Expectancy | PF | CAGR | Sharpe | Max DD | Avg exposure |
|---|---|---|---|---|---|---|---|---|---|
| Thai core (12) | full setup | 48 | 46% | +0.24R | 1.43 | 1.1% | 0.29 | −6.5% | 12% |
| Thai core | no base filter | 65 | 45% | +0.16R | 1.28 | 1.4% | 0.31 | −8.5% | 14% |
| Thai core | RS breakout only | 74 | 38% | +0.05R | 1.07 | 0.3% | 0.09 | −13.4% | 14% |
| Global core (15) | full setup | 64 | 47% | +0.52R | 1.89 | 3.3% | 0.63 | −12.5% | 11% |
| US extended (57) | full setup | 383 | 37% | +0.32R | 1.43 | 6.7% | 0.58 | −13.6% | 44% |
| US extended | no base filter | 427 | 36% | +0.11R | 1.15 | 3.6% | 0.34 | −20.0% | 45% |
| Thai extended (60) | full setup | 212 | 30% | −0.02R | 0.97 | −1.9% | −0.18 | −34.2% | 34% |

Existing signal strategies over the same OOS window (monthly top-3 rotation): Thai `combined` CAGR 12.9%, Sharpe 0.81; global `momentum` CAGR 37.7%, Sharpe 1.08; global `combined` Sharpe 1.12.

**Verdict:** the setup has a positive per-trade edge in US names (+0.3 to +0.5R), and the base/VCP filter clearly adds value there. On the broad SET list it has **no out-of-sample edge**. At 1% risk per trade it uses little capital, so its portfolio CAGR and Sharpe are well below the existing rotation signals. Under the pre-set blending rule (≥ 30 OOS trades, expectancy > 0.15R, Sharpe above the best existing strategy, excess CAGR > 0) it is **NOT blended** into the composite signal or the forecasts. It stays a separate, labelled entry-timing setup, and SET plans carry a low-conviction warning.

Caveats: survivorship bias (today's liquid names; the extended US list is hindsight-heavy); daily bars only; the sector cap is not modelled in the sim; US results are in USD (no FX P&L); RS ranks are inside the screen universe.

## To do when part 4 arrives
Add it to the table above, map each element to code or config, and re-run `POST /setups/momentum-base/backtest/run`. Only change the defaults if out-of-sample results improve.
