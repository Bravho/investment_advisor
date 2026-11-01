# กองทุนพันธบัตรสหรัฐฯ แบบไม่ป้องกันค่าเงิน (Thai THB feeder funds) — 1 พ.ย. 2569

Research for Tho (t36u). Watch/advisory only — FinBot never places orders. No invented numbers; "unknown" = not in a free source.
Companion to `us_bond_hedged_funds_20261101.md`.

**Sources** (retrieved 1 Nov 2026, 11:57–12:20 ICT): Finnomena public fund API (NAV 29 Oct 2026, returns as of 29 Oct 2026, fee tables);
SEC factsheets: TUSFIX M0029_2559 (30 Sep 2026), TLUSGOV M0853_2569 (30 Sep 2026), TLUSGOVRMF M0880_2569 (30 Sep 2026), MUBONDUH M0630_2566 (30 Sep 2026);
Talis one-page TLUSGOV (7 Oct 2026; SGOV YTM 3.95% as of 31 Aug 2026); SEC prospectus TLUSGOV (unhedged policy);
USD/THB closes from local `market_prices` (USDTHB=X, yfinance); FX book from `/fx/risk` (generated 1 Nov 2026 10:10 ICT).

## TLUSGOV TER check (the odd 2.26%)
Finnomena fee table shows "ค่าธรรมเนียมและค่าใช้จ่ายรวมทั้งหมด" actual **2.26%**. The SEC factsheet (30 Sep 2026) shows **รวมค่าใช้จ่าย เก็บจริง 0.2568%*** (mgmt 0.0963%; "*ยังไม่รวมค่าใช้จ่ายอื่น"). 2.26 looks like a mis-keyed 0.2568 (or an annualised first-month estimate) — FinBot now stores the factsheet value 0.2568% and keeps the Finnomena figure as `ter_actual_finnomena`. Confirm with Talis if it matters.

## How much of the return is FX (USD/THB, local data)
USD/THB 29 Oct 2025 32.34 → 29 Oct 2026 33.687 = **+4.17%** (baht weaker = gain for unhedged). 6m (29 Apr 2026 32.49): **+3.68%**. 4 Sep 2026 (32.89) → 29 Oct: **+2.42%**. 3Y: local FX history starts 6 Jun 2024 (36.57 → 33.69 = −7.9%), so over 3Y the baht's strength was a large drag; exact 3Y FX = unknown.
- TUSFIX 1Y +7.61% ≈ FX +4.17pp + ~3.3pp T-bill yield after fees (assumes ~0% hedge all year; the hedge ratio before 30 Sep 2026 is unknown).
- MUBONDUH-A 1Y +2.12% ≈ FX +4.17pp, so the bonds themselves lost ~2% in USD (rates up). 6m +1.37% vs FX +3.68pp.
- TLUSGOV since 4 Sep 2026: NAV 10.00 → 10.2791 (+2.79%) vs FX +2.42pp → ~0.4pp from T-bills in ~8 weeks.

## Ranked shortlist (Tho: already ~104k THB unhedged USD via SCBGOLDE; war risk high; Fed leaning hike; USD/THB 33.72 at 96% of its 1-year range)
1. **TLUSGOV** — cheapest clean way to hold US T-bills unhedged: TER 0.2568% (factsheet), no front/back fee, 0–3 month SGOV (no rate risk), T+2. Young fund (since 4 Sep 2026).
2. **TLUSGOVRMF** — same SGOV exposure with RMF deduction (TER 0.4494%, no fees); only US-Treasury RMF found. Locked to RMF rules (≥5y and age 55).
3. **TUSFIX** — T-bills via BIL with a 10-year record; TER 0.53% + 0.50% front fee; policy is *dynamic* — 0% hedged on 30 Sep 2026 but the manager may re-hedge.
4. **MUBONDUH-A** — only if he wants duration/credit too: US Aggregate, rate-sensitive (hurts if the Fed hikes), TER 0.944% + 1.07% front. Not a pure buffer.

## Trade-off vs the hedged shortlist
- Unhedged keeps the full US T-bill yield (SGOV master YTM 3.95% on 31 Aug 2026; TUSFIX YTM 3.98% on 30 Sep 2026) instead of losing ~2.75–3%/yr to hedging (Fed 3.75–4.00% vs BOT 1.00%, 28 Oct 2026). Hedged T-bills ≈ Thai money-market returns (~1%).
- Break-even: unhedged beats hedged unless the baht strengthens by more than ~2.8–3% over a year. A move like Dec 2022 (−8.79% in a month) would wipe ~3 years of yield edge.
- In a war/risk-off shock the baht has tended to weaken → unhedged USD rises in THB → acts as a buffer (that's why it fits the geo-risk view). In a "risk-on + weak dollar" world it hurts.
- USD/THB is near the top of its 1-year range (33.83 high / 30.91 low): less room to gain from further baht weakness, more room for a pull-back.

## Impact on Tho's FX exposure (`/fx/risk`, book 848,611 THB)
Now: net direct unhedged FX **104,111 THB (12.3%)** (SCBGOLDE); portfolio FX beta **+0.029** (Thai equities offset PTTEP/gold); baht +10% stronger ⇒ economic −2,416 THB, direct-only −10,411 THB; FX VaR95 1m ≈ 840 THB.
Adding an unhedged US T-bill fund (beta 1, funded from new THB cash):

| Added | Direct USD exposure | Portfolio FX beta | FX VaR95 1m | Baht 10% stronger (economic / direct-only) | Dec-2022-type month (−8.79%) on the new fund |
|---|---|---|---|---|---|
| 50,000 | 154,111 (17.1%) | +0.083 | ~2,590 | −7,416 / −15,411 | −4,395 |
| 100,000 | 204,111 (21.5%) | +0.131 | ~4,320 | −12,416 / −20,411 | −8,790 |
| 150,000 | 254,111 (25.4%) | +0.175 | ~6,050 | −17,416 / −25,411 | −13,185 |

(Method as `/fx/risk`: parametric VaR = 1.645 × 0.46% daily vol × √21 × |beta| × value; scenarios move USD/THB alone.) A split (e.g., part hedged DAOL-USTBILL/TUSTREASURY, part unhedged TLUSGOV) keeps the war buffer without doubling FX risk.

## Full table

| Fund | AMC | Master | Hedge now / policy | TER actual | Mgmt | Front / back | NAV (date) | 6m | 1Y (FX part) | 3Y p.a. | Duration / maturity | Risk | Min | Dividend | Tax |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TLUSGOV | Talis | iShares 0-3 Month Treasury Bond ETF (SGOV) | 0% / **unhedged by policy** | 0.2568% (FS); Finnomena 2.26% (doubtful) | 0.0963% | waived / waived | 10.2791 (29 Oct 26) | n/a | n/a (since 4 Sep 26: +2.79%, FX +2.42pp) | n/a | 0–3 months; master YTM 3.95% (31 Aug 26) | 3 | 1,000 | none | none |
| TLUSGOVRMF | Talis | SGOV | 0% / **unhedged by policy** | 0.4494% (FS) / 0.45% (Finnomena) | 0.2889% | waived / waived | 10.2679 (29 Oct 26) | n/a | n/a (FS since launch +1.83% to 30 Sep) | n/a | 0–3 months | 3 | 1,000 | none | **RMF** |
| TUSFIX | TISCO | SPDR Bloomberg 1-3 Month T-Bill ETF (BIL) | **0.00%** (30 Sep 26) / dynamic | 0.53% | 0.27% | 0.50% / none | 11.2838 (29 Oct 26) | +4.48% | +7.61% (FX ≈ +4.17pp) | +1.21% | avg 1m 29d; YTM 3.98% | 3 | 1,000 | none | none |
| MUBONDUH-A | MFC | JPMorgan Funds – US Aggregate Bond I (acc) USD (MBS 32.1%, corp 31.9%, UST 23.0%, 31 Aug 26) | **0.00%** (30 Sep 26) / unhedged | 0.9439% | 0.8025% | 1.07% / none | 10.9125 (29 Oct 26) | +1.37% | +2.12% (FX ≈ +4.17pp → bonds ≈ −2% in USD) | +2.95% (since Oct 2023) | duration unknown (FS) | 4 (Finnomena) | 1,000 (next 500) | none (-D class pays) | none (SSF class MUBONDUH-SSF: no deduction for buys from 2025) |
| DAOL-USTBILL (ref.) | DAOL | direct US T-bills ≤1y | 62.82% (19 Oct 26) / dynamic — partly unhedged | 0.587% | 0.2675% | 0.2675% / waived | 9.8404 (29 Oct 26) | +1.61% | +1.33% | n/a | 49 days | 3 | 500 | none | none (kept in hedged group) |

Excluded: USD-denominated money-market feeders (SCBUSDYIELD, ASP-USDL USD class, KF-SINCOME-USD, etc.) and BCAP-USL (Pictet USD money market, not Treasury-specific); global unhedged bond funds (K-GSF(UH), K-GDBONDUH, KKP SIB-UH, TLWORLDBOND-UH-X) — not US-Treasury focused. M-USTBILL liquidated 14 Aug 2025.

## Wiring
`fund_watchlist` group `usbond_uh`: TLUSGOV, TLUSGOVRMF (moved from `usbond`), TUSFIX, MUBONDUH-A — refreshed by the existing 08:30/21:30 job; dashboard tab "พันธบัตรสหรัฐ (ไม่ป้องกันค่าเงิน)". Not in signals/forecasts (fund_watchlist never feeds them).

## Update 1 Nov 2026 14:10 ICT (t38u)
Tho: keep only **TUSFIX**, for trend assessment — he expects not to invest. Changes:
- TUSFIX: `fund_watchlist.status = 'trend'` → no watch score, badge "ติดตามแนวโน้มเท่านั้น · ไม่ลงทุน", advisor context tags it "TREND-WATCH ONLY - NOT an investment candidate". fund_watchlist never feeds P3.3 signals, forecasts or trade plans.
- TLUSGOV, TLUSGOVRMF, MUBONDUH-A: removed from the registry and set `status='dropped'` in the DB (rows and NAV history kept, hidden from the dashboard/advisor; no NAV refresh).
- Hedged group (DAOL-USTBILL, TUSTREASURY, TUSBOND-A, MUBOND-A) and the US bond ETFs (SGOV, SHY, IEF, TIP) unchanged.
