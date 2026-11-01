# INTC −28.6% on 30 Oct 2026: what happened, what we knew, what changed (Tho t39u, written 2026-11-01 ICT)

## 1. The move (from real price data: Yahoo Finance daily bars via yfinance, retrieved 2026-11-01)
| | value |
|---|---|
| Close on 29 Oct → close on 30 Oct (US) | 92.07 → 65.76 = **−28.58%** (Tho's "27%" is close, but the measured figure is −28.6%) |
| Open on 30 Oct | 68.36 = **−25.75% gap**; open→close −3.80%; high 68.77, low ~63.20 |
| Volume | 454.2M = **4.53× the 50-day average** (100.3M) |
| After-hours, 29 Oct (results were out) | fell to ~70.9 (low 70.16); pre-market on 30 Oct 71.0 → 65.3 |
| Size of the move | −5.8σ against the 1-year daily vol of 5.25%; 1 month −45.2%; still about +67% YTD (39.38 at the start of 2026; 1-year high 140.94 on 22 Jun 2026) |
Reuters described it as Intel's worst day since 1974.

## 2. Root cause
**Primary trigger: a guidance cut, not a bad quarter.** Q3 results came out after the close on Thu 29 Oct.
- **Q3 beat:** revenue $16.5B (+21% YoY), non-GAAP EPS $0.52.
- **Q4 guidance:** revenue $15–16B vs ~$17.1B consensus (LSEG; FactSet $17.3B), and EPS $0.25 vs ~$0.43.
- **PC slowdown:** client-computing (PC chip) revenue fell more than 20% from the prior quarter. Intel now expects PC units to fall about 12% in 2026 and about 10% in 2027, because memory is short and expensive.
- **Fab 28 (Israel) explosion:** about a $300M revenue hit in Q4 and about 200 bp off gross margin.
- **Cash flow:** negative this year.
- Sources: [Intel press release](https://www.intc.com/news-events/press-releases/detail/1786/intel-reports-third-quarter-2026-financial-results), [call transcript (Motley Fool)](https://www.fool.com/earnings/call-transcripts/2026/10/30/intel-intc-q3-2026-earnings-call-transcript/), [Reuters after-hours](https://www.investing.com/news/stock-market-news/intel-signals-slower-growth-as-pc-market-remains-under-pressure-4984967), [Reuters "chip rout"](https://www.investing.com/news/stock-market-news/intel-warning-sparks-chip-rout-pc-weakness-clouds-turnaround-4987123).

**Amplifiers:**
1. **Expectations and positioning:** the stock had rallied about 150% YTD on the turnaround story and traded on a rich multiple, so a guidance cut left little cushion.
2. **Credit and analysts:** D.A. Davidson downgraded to neutral ("Not fixed yet"). The cost of insuring Intel debt against default (5-year credit default swaps) rose to a record 124.75, the biggest one-day jump since 2022.
3. **AI-capex doubts on the same night:** Amazon also reported ([CNBC](https://www.cnbc.com/2026/10/30/amazon-intel-earnings-big-tech-ai-spending-concerns.html), [NBC](https://www.nbcnews.com/business/markets/tech-stocks-nasdaq-ai-boom-fears-deepen-rcna606512), [AP](https://apnews.com/article/stock-markets-ai-alphabet-oil-16c266731fdf64178f38070af2b42497)).
4. **Sector read-through:** PC and memory-cost exposure, with AMD reporting on 3 Nov ([Investing on AMD](https://www.investing.com/news/stock-market-news/why-is-advanced-micro-devices-stock-sliding-today-93CH-4988108), [etf.net](https://etf.net/news/intel-outlook-sparks-chip-selloff-2026-10-30)).

**Peers on 30 Oct (Yahoo closes):**
- Semiconductor index and ETFs: ^SOX −7.20%, SOXX −8.24%, SMH −6.98%.
- Single chips: AMD −10.88%, TSM −5.95%, AVGO −5.48%, MU −5.30%, NVDA −4.22%.
- Broad market: QQQ −3.47%, SPY −1.77%.

**Spillover into Tho's watch list:** the 1-day ≥5% alerts fired for AVGO, MU, TSM and GDX. GOOGL had already fallen **−12.64% on 29 Oct** on its own earnings (324.89 → 283.82).

## 3. What our system knew beforehand
- **INTC itself:** not on the DB watch list, so it had no signal score, forecast, setup screen or trade plan. It appeared only in the legacy `data/watchlist.json` note and the old tech-screener name map.
- **News:** ingested only after the event. The first Intel-result headline in `news_articles` was at 08:55 ICT on 30 Oct, after the US after-hours drop.
- **Earnings-date awareness:**
  - Trade plans: proposed plans already carried a Yahoo-calendar "event inside plan window" warning (not required).
  - Thai holdings: `earnings_tracker` covers them in the morning brief.
  - Gaps: there was **no** earnings-date awareness on the watch list, the desk, the advisor context or the forecasts, and no awareness of bellwethers (INTC/AMD/AMZN) whose reports move our names.
- **Forecast bands:** the 3d forecasts were frozen at 00:49 ICT on 30 Oct, before Intel's report, from the 29 Oct closes. On the very first day (30 Oct close), several names were already below the 80% band low, though all stayed inside the 95% band:
  - AVGO 326.08 (80% low 327.88)
  - TSM 406.13 (412.51)
  - QQQ 690.49 (696.08)
  - SPY 755.72 (756.56)
  - NVDA 204.64 was just inside (204.36); MU 884.74 was inside (858.64).
  - The forecasts had no earnings or event input.

## 4. Lessons tested (walk-forward, `ops/backtest_gate.py`: mean skill must improve, mean hit may drop ≤1 pt)
### A. Earnings-aware forecast bands → **PASS → LIVE**
- **Problem it targets:** across 12 US mega/large caps over 10 years, vol-based 80% bands covered only **48%** of 3-day outcomes when an earnings reaction day fell inside the window (84% otherwise), and 72% of 1-month outcomes (84% otherwise).
- **Test design (`ops/earnings_band_gate.py`):**
  - The live forecast models were re-run point-in-time for NVDA, MSFT, GOOGL, TSM, AVGO and MU.
  - Sigma multiplier fitted only on data before 2022: **×2.156 for 3d, ×1.204 for 1m**. Everything from 2022 on is out-of-sample.
- **Results (OOS 2022–2026):**
  - Mean skill 0.00373 → **0.00389**; mean hit 0.534 → 0.534 (unchanged).
  - 80% coverage in earnings windows: 3d 48.9% → **75.0%**, 1m 69.2% → **77.6%**; normal windows unchanged.
  - Artifact: `data/backtests/earnings_band_gate_20261101_162126.json`.
- **What changes live (`predictions.EARNINGS_SIGMA_MULT`):** only the bands, P(up) magnitude and confidence move. The median forecast and direction stay the same.
  - Scope: US single stocks with a company-published earnings date inside (as-of, target].
  - Recorded in `method.earnings_event` plus an assumption line.
  - The global learned sigma_scale still applies on top.
- A dry run (no inserts) widened the NVDA 1m band for the 18 Nov report.

### B. Signal overlays on the live P3.3 score (`ops/earnings_gate.py`, global universe, monthly top-3, OOS from 2019-10)
| variant | mean skill (base 0.1618) | mean hit (base 0.6708) | gate |
|---|---|---|---|
| skip names reporting within 10 trading days | 0.1208 | 0.6375 | FAIL |
| skip names reporting within the coming month | 0.0073 | 0.5833 | FAIL |
| half-size names reporting within the month | 0.0790 | 0.6479 | FAIL |
| skip names ≤20 trading days after a ≤−7% earnings gap | 0.1755 | 0.6708 | PASS* |

- \*The post-gap PASS comes from **one** affected rebalance in 7 years (GOOGL, Jul 2026). It holds at −5%/−7% thresholds and vanishes at −10%. That is too thin, so it ships in **SHADOW**: `data/shadow/earnings_post_gap_shadow.jsonl` logs once per day which US top-3 names it would skip.
- No reliable drift after big earnings drops in this basket: after ≤−7% earnings gaps over 5 years (n=44), the median next-20-day return was −0.16%, lower in 50% of cases. So there is no "post-earnings-gap drift" trade to add.
- Avoiding earnings altogether costs too much: momentum leaders keep reporting, so skipping or half-sizing them cuts returns. **The lesson is about sizing and bands, not avoidance.**

### C. Display / context (live, no scoring)
- **/desk card "ความเสี่ยงช่วงประกาศงบ"** (earnings-gap risk) covers the US watch list plus bellwethers INTC, AMD, ASML, AMZN, META, AAPL. It shows:
  - next report date (ICT), trading days left and level (≤5 imminent, ≤15 soon);
  - historical earnings-day moves (median / p90 / worst of the last 12 reports);
  - post-gap flag and read-through names.
- **Pre-trade checklist** (`earnings_gap_risk`, `post_earnings_gap`; informational, not required): flags when earnings fall inside the plan window and a p90 earnings gap is larger than the stop distance.
- **Advisor context** gets a new `=== EARNINGS EVENT RISK ===` block (`/earnings/advisor-context`).
- **Event registry:** `config/event_categories.json` adds an `earnings_guidance_shock` category for the planned news-event impact model, labelled with INTC (30 Oct) and GOOGL (29 Oct).
  - `crypto_events.py` and the Binance-hack watch routine (to 7 Nov) are untouched.
  - Any scoring use must pass the gate after 7 Nov.

## 5. Generalisable lesson
1. **Guidance beats the quarter:** a "beat and cut" can gap a stock 25%+. Earnings-day moves for these names are 2–5× a normal day (INTC: median ±8.9%, p90 ±25.8% over the last 12 reports).
2. **Stops don't protect across a report:** an overnight gap jumps the stop. For swing trades, size for the gap or enter after the report.
3. **Watch the bellwethers:** a stock we don't own (INTC) moved five of our names by 4–6% in one day. Their report dates now sit on /desk.
4. **Holdings:** no sell/trim advice for PTTEP/SCB follows from this.
