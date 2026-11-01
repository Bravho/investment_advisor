# กองทุนพันธบัตรสหรัฐฯ แบบป้องกันค่าเงิน (Thai feeder funds) — 1 พ.ย. 2569

Research for Tho (t35u). Watch/advisory only — FinBot never places orders. No numbers invented; "unknown" = not found in a free source.

**Sources** (retrieved 1 Nov 2026, 11:40–12:30 ICT):
- Finnomena public fund API (`/fn3/api/fund/v2/public/funds/...`, republishes SEC/AIMC data) — NAV, returns, fee table, risk level. NAV date 29 Oct 2026.
- SEC factsheets (`secdocumentstorage.blob.core.windows.net/fundfactsheet/<proj>.pdf`): TUSTREASURY M0406_2565, TUSFIX M0029_2559, TUSBOND M0716_2565, DAOL-USTBILL M0696_2566, MUBOND M0768_2565, TLUSGOV M0853_2569, TLUSGOVRMF M0880_2569, M-USTBILL M0908_2566. Factsheet dates: 30 Sep 2026 (TISCO, MFC, Talis), 19 Oct 2026 (DAOL).
- Krungsri product page for TUSTREASURY ("โดยปกติป้องกันประมาณ 90%"); Talis TLUSGOVRMF page + SEC prospectus (unhedged by policy); infoquest IPO list (TLUSGOV IPO 28 Aug–3 Sep 2026).
- Rates: FOMC statement 28 Oct 2026 (3.75–4.00%, 2 dissents for a hike); BOT MPC 5/2026, 28 Oct 2026 (1.00%).
- ETF expense ratios: iShares product pages (SGOV 0.09%, SHY 0.15%, IEF 0.15%, TIP 0.18%).

## Hedging cost (read this first)
Hedging USD→THB costs roughly the short-rate gap: Fed 3.75–4.00% vs BOT 1.00% ≈ **2.75–3.0 % per year** (approximation; actual forward points vary). So:
- A fully hedged **T-bill** fund earns ≈ US T-bill yield − ~2.9% − fees ≈ about Thai money-market level (compare K-CASH-A: 1Y +0.80%, TER 0.27%). The hedge removes FX risk but also removes most of the US yield pick-up.
- A hedged **intermediate** Treasury fund earns the term/price effect on top: gains if US yields fall (growth scare, flight to safety), loses if the Fed hikes (TUSTREASURY 1Y −3.56%).
- If the gap narrows (Fed cuts or BOT hikes) hedging gets cheaper; if the Fed hikes it gets dearer.
- Unhedged funds (TLUSGOV/RMF, TUSFIX right now) instead carry USD/THB: in a war/risk-off THB usually weakens, so unhedged USD exposure can itself act as a buffer — but it also adds FX swings (TUSFIX 1Y +7.61% was mostly FX).

## Ranked shortlist (cost + fit: no fixed income yet, Fed leaning to hike, high geopolitical risk, wants a buffer)
1. **DAOL-USTBILL** — shortest duration (avg 49 days) so a Fed hike barely hurts; TER 0.587%, front 0.2675%, min 500 THB. Caveat: only 62.82% hedged on 19 Oct 2026 (dynamic) → ~37% moves with USD/THB; 3Y record n/a (since 19 Dec 2023, −0.75% p.a.).
2. **TUSTREASURY** — the only pure-Treasury hedged fund (GOVT, ~5y avg maturity), cheapest TER of the hedged long funds (0.497%), 91.24% hedged. Best "crisis" diversifier if a shock pushes US yields down; loses if the Fed hikes, so stage entries.
3. **TUSBOND-A** — US Aggregate (JPM), 95.17% hedged, TER 0.781%; only ~23% Treasuries (rest agency MBS + corporates) so less of a pure safe haven. Cheaper than MUBOND on the same master.
4. **MUBOND-A / MUBOND-D** — same JPM US Aggregate master, 98% hedged, but TER 0.944% and front 1.07% → dominated by TUSBOND-A on cost. D class pays dividends (taxable 10% WHT).
- RMF: **no FX-hedged US-Treasury RMF found** (searched all 7,424 funds in the Finnomena list). Closest: TLUSGOVRMF (SGOV, TER 0.45%, **unhedged by policy**) or the Thai-bond RMF already watched (KFLTGOVRMF, TER 0.42%, 1Y −0.63%, 3Y +3.43% p.a.).

## Full table

| Fund | AMC | Master / holdings | Hedge policy (factsheet) | TER actual | Mgmt fee | Front / back | NAV (date) | 1Y | 3Y p.a. | Duration / maturity | YTM (FS) | Risk | Min | Dividend | Tax type |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TUSTREASURY | TISCO | iShares U.S. Treasury Bond ETF (GOVT; ICE US Treasury Core) | Dynamic; **91.24% hedged** (30 Sep 26); "normally ~90%" (Krungsri) | 0.497% | 0.2675% | 0.50% / none | 8.8466 (29 Oct 26) | −3.56% | +0.38% | avg maturity 5y 4m 5d (duration unknown) | 5.03% | 3 | 1,000 | none | none |
| DAOL-USTBILL | DAOL | Direct US T-bills/notes ≤1y (≥80% NAV) | Dynamic; **62.82% hedged** (19 Oct 26) | 0.587% | 0.2675% | 0.2675% / waived | 9.8404 (29 Oct 26) | +1.33% (FS 1Y +0.51%) | n/a (launched 19 Dec 23) | avg 49 days | 1.94% | 3 | 500 | none | none |
| TUSBOND-A | TISCO | JPMorgan Funds – US Aggregate Bond C (acc) USD | Dynamic; **95.17% hedged** (30 Sep 26) | 0.781% | 0.535% | 0.75% / none | 9.8021 (29 Oct 26) | −4.99% | +1.08% | avg maturity 6y 4d | 5.30% | FS text "ปานกลางค่อนข้างต่ำ"; Finnomena 4 — verify | none stated (FS) | none | none (SSF class TUSBOND-SSF exists; SSF deduction ended for buys from 2025) |
| MUBOND-A (-D) | MFC | JPMorgan Funds – US Aggregate Bond I (acc) USD; master: agency MBS 32.1%, corp 31.9%, UST 23.0% (31 Aug 26) | Dynamic; **98.00% hedged** (30 Sep 26) | 0.944% | 0.8025% | 1.07% (<100 MB) / none | 9.4420 (29 Oct 26) | −4.85% | +0.17% | unknown (FS shows YTM 0.00% — treat as unknown) | unknown | FS "ปานกลางค่อนข้างต่ำ"; Finnomena 4 — verify | 1,000 (next 500) | A none / D pays | none (SSF class exists) |
| TLUSGOVRMF | Talis | iShares 0-3 Month Treasury Bond ETF (SGOV) | **Unhedged by policy** | 0.45% | 0.2889% | waived / waived | 10.2679 (29 Oct 26) | n/a (launched 4 Sep 26) | n/a | 0–3 months (master) | master 3.95% (31 Aug 26) | 3 | 1,000 | none | **RMF** |
| TLUSGOV | Talis | SGOV | **Unhedged by policy** | unknown (Finnomena shows 2.26% — looks wrong for a new fund; check prospectus) | 0.0963% | waived / waived | 10.2791 (29 Oct 26) | n/a | n/a | 0–3 months | master 3.95% | 3 | 1,000 | none | none |
| TUSFIX | TISCO | SPDR Bloomberg 1-3 Month T-Bill ETF (BIL) | Dynamic; **0.00% hedged now** (30 Sep 26) → effectively unhedged | 0.53% | 0.27% | 0.50% / none | 11.2838 (29 Oct 26) | +7.61% (mostly FX) | +1.21% | avg 1m 29d | 3.98% | 3 | 1,000 | none | none |
| M-USTBILL | MFC | US T-bills | — | — | — | — | last 10.2455 (8 Aug 25) | — | — | — | — | — | — | — | **liquidated** (SEC status LI, 14 Aug 2025) |

Excluded: SCBUSDYIELD, ASP-USDL, BCAP-USL (USD money-market feeders; USD-denominated or unhedged vs THB, not Treasury-specific); global/multi-sector hedged bond funds (not US-Treasury focused).

## What was wired in
- `fund_watchlist`: new group `usbond` = TUSTREASURY, DAOL-USTBILL, TUSBOND-A, MUBOND-A, TLUSGOVRMF (NAV refresh with the existing 08:30/21:30 job; dashboard tab "พันธบัตรสหรัฐ (ป้องกันค่าเงิน)").
- `investment_watchlist`: SGOV, SHY, IEF, TIP (sector `us_bond`, bond-sized triggers: 1-day move ≥1.5%, 52-week low). TLT left out on purpose (very long duration while the Fed leans to hike) — add later if wanted.
- `us_bond` rows are **excluded from signals, forecasts, momentum screen, opportunity scanner and trade-plan generation** (they would distort the P3.3 cross-section). Display, prices and alerts only.
