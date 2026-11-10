# Investment Advisor — Development Log

---

## Nightly Run — 2026-07-29 02:30 ICT

### Market Intelligence Summary
The two-sided oil stand-off **broke to the DOWNSIDE**. On **Jul-27 the US paused lethal strikes** (ending a 13-day campaign) and **Iran halted retaliation**; on **Jul-28 Iran was reported discussing Hormuz shipping with BOTH Oman AND Saudi Arabia** — the Saudi/Gulf leg that had been the missing precondition is now actively in negotiation. **Brent crashed ~7% on Jul-27** and settled **~$84–86 (Jul-28)**, WTI back below $80, draining the geopolitical premium (Goldman: ~$80 year-end if Hormuz fully reopens). Domestically **SET ~1,624** (above the 1,600 breakout), **gold ~$4,042** (below $4,100, Fed-capped into the **Jul-29 FOMC**), **USD/THB ~33.64**.

### Thai Holdings Update
- **BAFS**: jet-fuel-cost **HEADWIND now EASING** on the oil crash (net positive vs the ~$100 peak); stable tourism. Last print **9.25 THB (−4.15%, Jul-28)** on general SET softness. H1 est ~Aug-14.
- **PTTEP**: realised-price **TAILWIND now ERODING** — the premium is draining; **do not add**. **Q2 results release Aug-02** (analyst meeting Aug-03) — independently corroborated (public.com/MSN); the earnings seed was refined **Aug-03 → Aug-02**. Note the Brent spike was mostly July/Q3, so the Q2 (Apr–Jun) realised print may be more moderate than the late-July peak.
- **SCB**: **155.00 THB** (Jul-24 close, confirmed; 52w 123–160). Q2 read holds (THB 11,117m; NPL 3.17%; CAR 18.6%; no div). **Interim-dividend watch Aug–Sep** (~THB 2.00 base). Yield ~7.3%.
- **Gold Fund (SCBGOLDE)**: gold ~$4,042 × USD/THB 33.64 → est NAV **~4.23 THB/unit**; weak-baht cushion intact. House band $4,000–4,900.

### Technology Sector Highlight
Big-Tech earnings week: **MSFT & META report Jul-29, AAPL & AMZN Jul-30**, with the market focused on **AI-capex vs ROI** (hyperscaler 2026 capex >$650–725B; Meta guided FY26 $125–145B, Amazon ~$200B, Microsoft ~$119B) — described as "in revolt over AI spending." **FOMC Jul-29** hold ~66% priced (hike odds risen to ~36%). Vietnam **VN-Index 1,680.62 (+0.70%)**, 2nd up day; FTSE EM upgrade still Sep-21. No direct Tho exposure — a global risk gauge.

### Improvements Implemented Tonight
1. **`portfolio_engine/oil_scenario.py`** *(re-ranked — DECISIVE DE-ESCALATION)* — Added a `2026-07-29` re-rank block for the Jul-27 US-Iran mutual pause + the broadening of Hormuz talks to Saudi Arabia and the ~7% Brent crash. Shifted mass onto the de-escalation paths and re-anchored the base DOWN: **deal_signed 8→12**, **deal_partial 16→30** (mid-$80s is now the realised path), **status_quo anchor 97→86 / weight 32→28**, **lebanon_spillover_reclosure 23→17** (trimmed but live — Yanbu/Jizan damage unrepaired), **nuclear_track_breakdown 21→13**. Rewrote all five narratives + `probability_qualitative`, the `probability_weighted_outlook()` note, and the `run_oil_scenario_report()` default (**96.8→85.0**). Additive; every change carries a `2026-07-29` marker. Sum = 12+30+28+17+13 = 100.
2. **`portfolio_engine/earnings_tracker.py`** *(refined — PTTEP date)* — Independent corroboration (public.com/MSN earnings pages) of the **Q2-2026 results release on Aug-02** (analyst meeting Aug-03). Since the actuals-capture and pre-earnings brief key off the results filing (not the meeting), the seed was moved **2026-08-03 → 2026-08-02** (`confirmed=True`, after-close); Aug-03 analyst meeting retained in the notes; alert window now opens **Jul-30**. Note updated: watch the Q2 (Apr–Jun) AVG realised oil (the spike was mostly Q3; Brent has since crashed to ~$85). `2026-07-29` marker.
3. **`data/watchlist.json`** *(refresh)* — `last_updated`→2026-07-29, `usd_thb_rate` 33.55→**33.64**; PTTEP note (eroding) + `next_earnings` Aug-04-era→**2026-08-02** + `pttep_calendar_jul29`; BAFS note (headwind easing) + price 9.25; SCB interim-div watch; SCBGOLDE NAV **4.23** (gold $4,042); 3 catalysts (Jul-29 FOMC/MSFT/META, Jul-30 AAPL/AMZN, Aug-02 PTTEP); **13 dated `jul29_` macro keys**. macro_context now **395 keys**; duplicate-key scan → NONE.
4. **`data/market_intel/2026-07-29.md`** *(new file)* — 6-section report + re-rank table + 5 risk flags: de-escalation headline, holdings (PTTEP eroding / BAFS easing / SCB interim watch / gold Fed-capped), gold & currency, US/Fed (FOMC + Big-Tech week), regional, oil re-rank; ≥2 outlets per major item.

### Verification
`ast.parse` clean on `oil_scenario.py` and `earnings_tracker.py`. `oil_scenario` scenario block scanned: `probability_pct` = **[12,30,28,17,13] sum=100**; isolated weighted-Brent check → **$91.20** (above the ~$85 spot — the two escalation tails correctly price the unrepaired Yanbu/Jizan physical damage + pause-break risk). `watchlist.json` re-loaded via `object_pairs_hook` **duplicate-key scan → NONE** (395 macro keys; usd_thb 33.64; PTTEP Aug-02; SCBGOLDE NAV 4.23). News cross-checked ≥2 outlets per item (oil/pause: CNBC + CNN + Fortune + Al Jazeera + Trading Economics; gold/Fed: Yahoo + CNBC + FXLeaders + goldsilver.com; SET/SCB/BAFS: Investing.com + SET; FX: Trading Economics + Wise; PTTEP date: PTTEP IR calendar + public.com/MSN; US tech: Benzinga + Fortune + Fast Company; Vietnam: Vietstock). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `run_oil_scenario_report()` / `generate_daily_brief()` weren't exercised end-to-end — edits are additive and the math/loaders were verified in isolation; (b) **FOMC decision lands Jul-29 ~1am ICT Jul-30** — this run precedes it; digest the outcome next run; (c) one search returned a PTTEP price of ~162 THB, inconsistent with the 141 close and a falling-oil tape — treated as stale/erroneous and NOT written (kept 141, flagged to re-verify on a clean SET close); (d) `data/snapshots/` still holds only `2026-06-21.json` (the live macOS archive cron can't run here); (e) MS/UBS gold targets in `gold_institutional_targets` still carried from Jun-2026 — re-verify.

### Next Priority (for next run)
**Digest the Jul-29 FOMC** (gold/real-yield/SCBGOLDE read) and the **MSFT/META (Jul-29) + AAPL/AMZN (Jul-30) capex prints** (AI-trade risk gauge). **Capture the PTTEP Q2/H1 result (Aug-02)** into `data/earnings/pttep_q22026_actual.json` (loader wiring done — brief auto-surfaces it): realised Brent, ~560kboe/d volume, capex guidance, any interim dividend + reconciliation vs preview. **Watch the SCB interim-dividend declaration (Aug–Sep)** — set the Sep interim event `confirmed=True` with actual size/ex-date. **Track the oil de-escalation**: if Hormuz fully reopens (→Goldman ~$80), shift more mass to deal_signed and mark status_quo toward the low-$80s + flag further PTTEP erosion / BAFS tailwind; if the pause breaks or the Red Sea (Yanbu) flares, snap the tails back toward $105–120 and flag PTTEP operational risk. Lower priority: **re-verify the MS/UBS gold targets** and **reconcile a clean Jul-28/29 SET close** for SCB/PTTEP/BAFS prices.

---

## Nightly Run — 2026-07-28 02:30 ICT

### Market Intelligence Summary
The oil tape turned **two-sided**. The US-Iran **bilateral pause held** (Iran halted retaliation; Oman-mediated Hormuz safe-passage talks ongoing) — but over the weekend the **Red Sea front RE-escalated**: on **Jul-25 the Houthis struck Saudi Aramco**, setting the **Jizan refinery burning** and hitting **Yanbu**, Saudi Arabia's main Red Sea oil port and the primary workaround for barrels skirting blockaded Hormuz (two Yanbu missiles intercepted by a Patriot battery). The two effects roughly offset — **Brent held ~$96.78** — so the fear premium is no longer draining one-way. Domestically the tape is constructive: **SET ~1,633, holding above the 1,600 breakout**. Gold **~$4,050** into the **Jul-29 FOMC** (hold ~66% priced), **USD/THB firmed to ~33.55**.

### Thai Holdings Update
- **BAFS**: jet-fuel-cost **HEADWIND, capped** at ~$97 Brent; stable tourism offsets. H1 est ~Aug-14.
- **PTTEP**: realised-price **TAILWIND, now TWO-SIDED** — the bilateral pause argues for premium erosion, but the Red Sea re-escalation keeps barrels off the market. Closed **141.00 THB**. **Q2 date RECONCILED: analyst meeting Aug-3 per PTTEP's official IR calendar**, SET filing ~Aug-2/3 — **1 day earlier than the seeded Aug-4**; `earnings_tracker.py` seed corrected tonight. Hold core; do not add into a still-elevated premium.
- **SCB**: **price flag RESOLVED** — reset **158.5 → 155.00 THB** (Jul-24 close per Investing.com/Yahoo; prev 152.50; 52w **123.00–160.00**). The 158.5 carried since the Jul-26 log was an over-carry. Q2 read holds (THB 11,117m; NPL 3.17%; CAR 18.6%; no div). **Interim watch Aug-Sep** (~THB 2.00 base). Yield ~7.3% at 155.
- **Gold Fund (SCBGOLDE)**: gold ~$4,050 × USD/THB 33.55 → est NAV **~4.23 THB/unit**. Year-end house band **$4,000–4,900** (GS $4,900 / JPM ~$4,500); stale "$6,300" back-corrected in watchlist tonight.

### Technology Sector Highlight
Jul-27 **mixed** — Dow +0.5% (51,947), **Nasdaq red on an Nvidia drop + AI-capex worry** (XLK −1.4%). Busiest week of the quarter: **MSFT & META (Wed), AAPL & AMZN (Thu)** earnings, with the market focused on capex-vs-ROI on the AI trade, plus **FOMC Jul-29**. Vietnam FTSE EM upgrade still Sep-21. No direct Tho exposure — a global risk gauge.

### Improvements Implemented Tonight
1. **`portfolio_engine/earnings_tracker.py`** *(corrected — resolves the open PTTEP-date flag)* — Updated the PTTEP Q2-2026 seed **2026-08-04 → 2026-08-03** (`confirmed=True`), anchored to the **official PTTEP IR calendar analyst-meeting date (Aug-3, 10:30–12:00 GMT+7)**; SET results filing expected ~Aug-2/3. This supersedes the Jul-25 SET-sourced "Aug-04" (a day late vs the IR calendar) and still vindicates the earlier rejection of Yahoo's Jul-23 auto-estimate. Alert window opens **Jul-31**. Notes rewritten; `2026-07-28` marker.
2. **`portfolio_engine/oil_scenario.py`** *(re-ranked — TWO-SIDED: bilateral pause holds, Red Sea re-opens)* — Added a `2026-07-28` re-rank block for the Jul-25 Yanbu/Jizan Aramco strike vs the continuing bilateral pause: **deal_partial 18→16** (clean near-term throughput restoration is harder with Saudi's main workaround port under fire), **lebanon_spillover_reclosure 21→23** (Red Sea second front actively re-escalated). Held: deal_signed 8, status_quo 32 (anchor $97 — Brent unchanged), nuclear 21. Rewrote both affected narratives + qualitatives. Additive; every change carries a `2026-07-28` marker. Sum = 8+16+32+23+21 = 100.
3. **`data/watchlist.json`** *(refresh + two reconciliations + back-correction)* — `last_updated`→2026-07-28, `usd_thb_rate` 33.70→**33.55**; **PTTEP** `next_earnings` Aug-04→**Aug-03** + `pttep_calendar_jul28` (flag resolved) + Jul-28 two-sided note; **SCB** `last_price_thb` 158.5→**155.0** + `52w_range` 123–160 + `price_reconciliation_jul28` (flag resolved); **SCBGOLDE** NAV→**4.23** (gold $4,050); **gold_institutional_targets back-corrected** (GS 5400→4900, JPM 6000→4500) + note; catalysts for **Jul-28 / Jul-29 FOMC / Aug-03 PTTEP** (Aug-04 marked superseded); **12 dated `jul28_` macro keys**. macro_context now **382 keys**; duplicate-key scan → NONE.
4. **`data/market_intel/2026-07-28.md`** *(new file)* — 6-section report + 5 risk flags: two-sided-oil headline, holdings (PTTEP date reconciled / SCB price reconciled / BAFS / gold target corrected), gold & currency, US/Fed (FOMC Jul-29), regional, oil re-rank; ≥2 outlets per major item.

### Verification
`ast.parse` clean on `oil_scenario.py` and `earnings_tracker.py`. `oil_scenario` `probability_pct` scan → **[8,16,32,23,21] sum=100**; isolated weighted-Brent check → **$98.9** (above the ~$96.78 spot — the tails correctly price the persistent physical Red Sea + Hormuz disruption). `watchlist.json` re-loaded via `object_pairs_hook` **duplicate-key scan → NONE** (382 macro keys; usd_thb 33.55; PTTEP Aug-03; SCB 155.0; SCBGOLDE NAV 4.23; GS/JPM 4900/4500). News cross-checked ≥2 outlets per item (pause/Red Sea: Fortune + Washington Post + Al Jazeera + Reuters; Brent/FX: Trading Economics + Wise + Investing.com; gold/Fed: goldsilver.com + FXLeaders + allegiancegold; SET: Investing.com; SCB: Investing.com + Yahoo/stockanalysis; PTTEP date: PTTEP IR calendar; US/tech: Yahoo Finance + Motley Fool). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `run_oil_scenario_report()` / `generate_daily_brief()` weren't exercised end-to-end — edits are additive and the math/loaders were verified in isolation; (b) SCB 155.0 is the Jul-24 close (a clean Jul-27/28 SET close would refine it further); (c) PTTEP Aug-3 is the confirmed IR analyst-meeting date — the exact SET results-filing timestamp (Aug-2 after-close vs Aug-3) still to confirm on the day; (d) `data/snapshots/` still holds only `2026-06-21.json` (the live macOS archive cron can't run here); (e) MS/UBS gold targets in `gold_institutional_targets` are carried from Jun-2026 and flagged to re-verify.

### Next Priority (for next run)
**Capture the PTTEP Q2/H1 result (~Aug-2/3)** into `data/earnings/pttep_q22026_actual.json` (loader wiring done — the brief auto-surfaces it): realised Brent, ~560kboe/d volume, capex guidance, any interim dividend + reconciliation vs preview. **Watch the SCB interim-dividend declaration (Aug-Sep)** — set the Sep interim event `confirmed=True` with the actual size/ex-date. **Digest the Jul-29 FOMC** (gold/real-yield read) and the **MSFT/META/AAPL/AMZN capex prints** (AI-trade risk gauge). **Track the oil two-sider**: if Yanbu throughput is materially degraded, lift the tails toward $105–115 and flag PTTEP operational risk; if the bilateral pause converts to a Saudi/Gulf ceasefire, shift mass to deal_partial/deal_signed and mark status_quo toward the mid-$80s.

---

## Nightly Run — 2026-07-27 02:30 ICT

### Market Intelligence Summary
The Jul-26 de-escalation **tell hardened into action**: the **US and Iran paused attacks for a SECOND straight day**, snapping a **13-day nightly-airstrike streak**, while **Iran continued Hormuz safe-passage talks with Oman** ("progress" reported). It's a de-escalation *step*, not a resolution — Pakistan's precondition (a halt to Saudi/Gulf attacks) is unmet and all three physical disruptions (Hormuz, Red Sea, Kazakhstan's CPC terminal) persist — so **Brent held ~$96.78** (WTI $89.31): the fear premium keeps eroding off the ~$101 peak but barrels stay off the market. Gold held **~$4,075** (Fed-capped into Jul-29), **USD/THB ~33.70**. US equities fell Jul-23 (S&P −1.21%, Nasdaq −2.15%) on the oil surge + weak Big Tech FCF (Alphabet −7%, Tesla −14%).

### Thai Holdings Update
- **BAFS**: Jet-fuel-cost **HEADWIND, easing** at ~$97 as the pause caps oil; stable tourism offsets. H1 est ~Aug-14.
- **PTTEP**: Realised-price **TAILWIND, premium now ACTIVELY ERODING** — the two-day mutual pause + Oman Hormuz talks make a premium-draining truce the live downside path. Closed **141.00 THB (−2.36%/7d)**. **Q2 results now expected ~Aug-2/3** per PTTEP's IR calendar (earnings release ~Aug-2, analyst meeting Aug-3) — **1 day earlier than the seeded Aug-4; flagged to re-verify** on the official SET calendar. Hold core; do not add into an eroding premium.
- **SCB**: **~152–158 THB** (Jul-24) — an alternate SET quote shows **~152.00** vs the 158.5 carried from the Jul-26 log (~4% gap, flagged for reconciliation). Q2 reconciled read holds (THB 11,117m; NPL 3.17%, CAR 18.6%; no div). **Interim watch Aug-Sep**; history (THB 2.00 paid 2025-09-19) supports a ~THB 2.00 base case. Yield thesis holds (~6.5–7%).
- **Gold Fund (SCBGOLDE)**: gold ~$4,075 × USD/THB 33.70 → est NAV **~4.27 THB/unit**. **House-target correction**: GS cut year-end to **$4,900** (from $5,400), JPM ~**$4,500** Q4 — the "**$6,300 JPM**" in prior logs is **superseded**; now using the $4,000–4,900 consensus band.

### Technology Sector Highlight
Jul-23 US selloff on oil + AI-capex worry: **Alphabet −7%** (negative Q2 FCF), **Tesla −14%** (first negative FCF in 2+ years); **Super Micro +~20%** on >$60bn orders. **FOMC Jul-29** hold still base case, but **CME hike odds rose to ~46.5%** (from 34% Sunday) on the oil-inflation impulse. Vietnam FTSE EM upgrade still Sep-21. No direct Tho exposure — a global risk gauge.

### Improvements Implemented Tonight
1. **`portfolio_engine/oil_scenario.py`** *(re-ranked — DE-ESCALATION FIRMS)* — Continued the Jul-26 tell into the Jul-26 two-day mutual pause + Oman Hormuz talks. Added a `2026-07-27` re-rank block; shifted a modest sliver from the escalation tails onto the de-escalation paths: **deal_signed 6→8**, **deal_partial 14→18**, **status_quo 34→32** (anchor HELD at 97 — Brent unchanged ~$96.78), **lebanon_spillover_reclosure 23→21**, **nuclear_track_breakdown 23→21**. Rewrote all five narratives + `probability_qualitative`, the `probability_weighted_outlook()` note, and the `advisory_note` (premium now actively eroding; do not add into it; PTTEP Q2 date noted as ~Aug-2/3). Additive; every change carries a `2026-07-27` marker. Sum = 8+18+32+21+21 = 100.
2. **`data/market_intel/2026-07-27.md`** *(new file)* — 6-section report + macro table + 5 risk flags: de-escalation-firms headline, holdings (PTTEP premium eroding / SCB price reconciliation + interim history / BAFS relief / gold house-target correction), gold & currency, US/Fed (hike odds 46.5%), regional; ≥2 outlets per major item.
3. **`data/watchlist.json`** *(refresh + reconciliation + correction)* — `last_updated`→2026-07-27 (usd_thb held 33.70); PTTEP note (premium eroding) + `pttep_calendar_jul27` (Aug-2/3); BAFS `oil_regime_jul27`; SCB `price_reconciliation_jul27` (~152 vs 158.5) + `interim_div_history_note` (THB 2.00 Sep-19 2025); **SCBGOLDE gold-house-target correction** (GS $4,900 / JPM $4,500; NAV→4.27, gold $4,075); **12 dated `jul27_` macro keys**; new `2026-07-27` catalyst. macro_context now **368 keys**; duplicate-key scan → NONE.

### Verification
`ast.parse` clean on `oil_scenario.py`; `probability_pct` regex scan → **[8,18,32,21,21] sum=100**; isolated weighted-Brent check → **$98.4** (above the ~$96.78 spot — the tails still price the persistent three-front physical disruption). `watchlist.json` re-loaded via `object_pairs_hook` **duplicate-key scan → NONE** (368 macro keys; usd_thb 33.70; SCBGOLDE NAV 4.27). News cross-checked ≥2 outlets per item (pause/talks: Fortune + Fox + Al Jazeera + CNN; Brent: Trading Economics + Fortune; gold + targets: Yahoo + goldsilver.com; FX: Trading Economics + Wise; US/Fed: CBS + Forbes + CNBC + TheStreet). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `run_oil_scenario_report()` / `generate_daily_brief()` weren't exercised end-to-end — edits are additive and the math/loaders were verified in isolation; (b) **SCB price conflict** (~152 vs 158.5 Jul-24) is unresolved — carried as an approximate band pending a clean Jul-27 close; (c) **PTTEP Q2 date** now looks like ~Aug-2/3 (IR calendar) vs the seeded Aug-4 — flagged to re-verify, not yet changed in `earnings_tracker.py`; (d) the **gold "$6,300"** in prior logs was corrected to the $4,000–4,900 consensus — worth a one-time back-check of older entries; (e) `data/snapshots/` still holds only `2026-06-21.json` (the live macOS archive cron can't run here).

### Next Priority (for next run)
**Verify the PTTEP Q2 date** on the official SET/PTTEP corporate calendar (~Aug-2/3 vs seeded Aug-4) and, if it moves, update the `earnings_tracker.py` seed + alert window; then **capture the PTTEP Q2/H1 result** into `data/earnings/pttep_q22026_actual.json` (loader wiring already done, so the brief auto-surfaces it). **Reconcile the SCB price** (~152 vs 158.5) and **watch the interim-dividend declaration (Aug-Sep)** — set the Sep interim event `confirmed=True` with the actual size/ex-date. **Track the oil pause**: if it converts to a durable truce (Saudi/Gulf ceasefire), shift more mass to deal_partial/deal_signed and mark status_quo toward the mid-$80s; if it breaks, lift the tails toward $115–120 and flag PTTEP operational risk. Lower priority: **back-correct the stale gold "$6,300" references** in earlier DEVLOG/watchlist notes to the $4,000–4,900 consensus.

---

## Nightly Run — 2026-07-26 02:30 ICT

### Market Intelligence Summary
The one-way oil escalation **broke** on Jul-24: **Brent settled DOWN 3.9% at ~$96.78** (WTI $89.31) — the first down session after four straight weekly gains — on reports that **China is pushing, with Pakistan mediating, a resumption of US-Iran talks** centred on Hormuz (China/Pakistan FMs jointly urged a ceasefire Jul-17). This is a **de-escalation tell, not a resolution**: US strikes continue, Pakistan set a **precondition not yet met** (a halt to Saudi/Gulf attacks), and all three physical disruptions persist (Hormuz constrained, Houthi Red Sea/Saudi-port blockade, Kazakhstan's **CPC Black Sea terminal offline** with output cut — ~1% of global supply). So the **fear premium eased off the top while the barrels stay off the market**. Gold held **~$4,053** (Fed-capped into Jul-29), **USD/THB weakened to ~33.70** (from 33.37), and US indices recovered from the Jul-23 selloff (S&P +0.05%, Dow +0.46%, Nasdaq −0.64%).

### Thai Holdings Update
- **BAFS**: Jet-fuel-cost **HEADWIND, easing slightly** at ~$97 vs the ~$101 peak; stable tourism offsets. H1 est ~Aug-14.
- **PTTEP**: Realised-price **TAILWIND, easing** — closed **141.00 THB (−2.36%/7d)** tracking the oil pullback. **Q2 results officially confirmed Aug-04**; PTTEP pre-registered in the actuals loader tonight so the brief auto-switches post-print. Two-sided — premium can unwind fast on a truce; hold core, don't add into the spike.
- **SCB**: Closed **158.50 THB (+0.38%/7d)** — banking strength offsetting the oil-driven SET churn. Q2 reconciled read holds (THB 11,117m, ~2% Q2 beat / H1 soft; NPL 3.17%, CAR 18.6%; no div declared). **Interim-dividend watch Aug-Sep**; yield thesis holds on a ~THB 10–11 DPS base (~6.5–7%).
- **Gold Fund (SCBGOLDE)**: gold ~$4,053 × USD/THB 33.70 → est NAV **~4.25 THB/unit**; weak-baht cushion intact. JPM year-end $6,300.

### Technology Sector Highlight
US recovered from the Jul-23 oil-driven selloff — Nasdaq 24,975.82 (−0.64%), S&P 7,411.98 (+0.05%), Dow 51,947.25 (+0.46%). **FOMC Jul-29** hold expected (3.50–3.75%, 5th straight); Sep-hike odds stay elevated on the oil-inflation impulse but the de-escalation tell could ease them at the margin. Nikkei still the YTD leader; Vietnam FTSE EM upgrade still Sep-21. No direct Tho exposure — a global risk gauge.

### Improvements Implemented Tonight
1. **`portfolio_engine/oil_scenario.py`** *(re-ranked — FIRST DE-ESCALATION TELL)* — Corrected the Jul-25 three-front-escalation read against the Jul-24 reversal. Added a `2026-07-26` re-rank block: **status_quo** anchor **100→97** (marked to the Jul-24 realised settle; weight held at 34 — supply is still physically disrupted), **deal_partial 10→14** (the diplomatic channel reopened and oil fell 3.9%, re-activating the primary downside path), **lebanon_spillover_reclosure 25→23** and **nuclear_track_breakdown 25→23** (talks-exploration trims the total-closure / sustained-campaign tails); **deal_signed held at 6**. Rewrote all four affected narratives + `probability_qualitative`, the `probability_weighted_outlook()` note, and the `run_oil_scenario_report()` default (**101.0→96.8**). Additive; every change carries a `2026-07-26` marker. Sum = 6+14+34+23+23 = 100.
2. **`portfolio_engine/earnings_tracker.py`** *(prep — resolves the Jul-25 queued next-priority)* — Pre-registered **`PTTEP.BK → pttep_q22026_actual.json`** in the `load_earnings_actual()` map ahead of the confirmed **Aug-04** print. The file doesn't exist yet, so the loader returns `None` gracefully (the `.exists()` guard) until the actuals are captured on/after Aug-04 — at which point `_load_reported_actuals()` (already iterating PTTEP.BK) surfaces PTTEP in the brief automatically with **no further code change**. `2026-07-26` marker.
3. **`data/market_intel/2026-07-26.md`** *(new file)* — 6-section report + macro table + 5 risk flags: de-escalation-tell headline, holdings (PTTEP Aug-04 / SCB interim watch / BAFS headwind easing), gold & currency (baht 33.70), US/Fed (Jul-29 hold), regional; ≥2 outlets per major item.
4. **`data/watchlist.json`** *(refresh + reconciliation)* — `_meta.usd_thb_rate` 33.37→**33.70**, `last_updated`→2026-07-26; PTTEP note/price (141.0) + `next_earnings` Aug-04; SCB price (158.5) + interim-div watch; BAFS `oil_regime_jul26`; SCBGOLDE NAV→**4.25** (gold $4,053); **12 dated `jul26_` macro keys** (de-escalation tell, Brent $96.78, US-Iran talks, supply-still-offline, oil re-rank, gold, USD/THB, US markets, FOMC, PTTEP prep, SCB div watch, regional). Enriched the Jul-24 catalyst with the Friday reversal + added a 2026-07-26 catalyst. macro_context now **356 keys**.

### Verification
`ast.parse` clean on `oil_scenario.py`, `earnings_tracker.py`, and `brief_generator.py`. `oil_scenario` `probability_pct` regex scan → **[6,14,34,23,23] sum=100**; isolated weighted-Brent check → **$99.9** (above the $96.78 spot — the tails correctly price the persistent physical-supply risk). `earnings_tracker` imported live (after `pip install httpx`): `load_earnings_actual('SCB.BK')` returns the reconciled actual; **`load_earnings_actual('PTTEP.BK')` returns `None` and logs the pending file** (correct — auto-surfaces once the Aug-04 file lands); `load_earnings_actual('BAFS.BK')` → None. `watchlist.json` re-loaded via `object_pairs_hook` **duplicate-key scan → NONE** (356 macro keys; usd_thb 33.70; NAV 4.25). News cross-checked ≥2 outlets per item (oil/talks: CNBC + Reuters/Internazionale + IBTimes + Bloomberg; CPC: Euronews + Moscow Times + Kpler; gold: goldrate24 + Trading Economics; FX: Trading Economics + Wise; US/Fed: CBS + Forbes + Yahoo/CNBC). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `run_oil_scenario_report()` and `generate_daily_brief()` weren't exercised end-to-end against the live DB — edits are additive and the math/loaders were verified in isolation; (b) the Jul-24 −3.9% daily settle coexists with the "+14.6% week" (the week ran up early, Friday reversed) — not a contradiction; (c) `data/snapshots/` still holds only `2026-06-21.json` (the live macOS archive cron can't run here).

### Next Priority (for next run)
**Capture the PTTEP Q2/H1 result on Aug-04** into `data/earnings/pttep_q22026_actual.json` (mirroring the SCB pattern) — realised Brent, ~560kboe/d volume, capex guidance, any interim dividend + reconciliation vs preview; the loader wiring is already done, so the brief will surface it automatically. **Track the oil de-escalation**: if the US-Iran talks convert to a durable truce (Saudi/Gulf attacks halt), shift oil_scenario mass toward deal_partial/deal_signed and mark status_quo back toward the mid-$80s; if talks break down, lift the tails toward $115–120 and flag PTTEP operational risk. **Watch the SCB interim-dividend declaration (Aug-Sep)** and set the Sep interim event `confirmed=True` with the actual size/ex-date.

---

## Nightly Run — 2026-07-25 02:30 ICT

### Market Intelligence Summary
The oil regime **escalated further** since Jul-24: Brent settled **~$101.06** (4th straight weekly gain, **+14.6% on the week**, highest since May) as the disruption broadened to a **THIRD supply route** — Kazakhstan cut output after suspected **Ukrainian drone strikes closed the CPC Black Sea export terminal**, on top of Hormuz (crossings down to a **single tanker** Thursday, lowest since May-7) and the Houthi Red Sea blockade. Analysts still flag **$120 next**. Offsetting risk-off hit Asia (Nikkei −2.73%, Hang Seng −0.98%, Sensex −0.79%, VN-Index −0.78%) and the US (Nasdaq −2.15% Jul-23). Gold held **~$4,102** (Fed-capped despite oil), **USD/THB eased to ~33.37** (baht firmed from 33.79). The queued PTTEP calendar question resolved: **PTTEP officially set Q2-2026 results for Aug-04.**

### Thai Holdings Update
- **BAFS**: Jet-fuel-cost **HEADWIND** deepens at ~$101 oil; stable tourism a partial offset. H1 est ~Aug-14.
- **PTTEP**: Large realised-price **TAILWIND**; closed 151.00 THB (−0.33%) Jul-24, well above the 129.5 (Jun-26) print. **Q2 results OFFICIALLY CONFIRMED Aug-04** (was internal Aug-11; Yahoo Jul-23 vindicated as rejected). Two-sided — premium can unwind fast on a truce + Middle East transit risk. Hold core; don't add into the spike.
- **SCB**: Closed 154.50 THB (+1.31%) Jul-24 — banking-sector buying offset the oil-driven SET rout. Q2 reconciled read holds (THB 11,117m, ~2% Q2 beat / H1 modestly soft; NPL 3.17%, CAR 18.6%; no div declared, interim Aug-Sep). **Yield thesis holds on a lower ~THB 10–11 DPS base (~6.5–7%).**
- **Gold Fund (SCBGOLDE)**: gold ~$4,102 × USD/THB 33.37 → est NAV **~4.26 THB/unit**; weak-baht cushion intact. JPM year-end $6,300.

### Technology Sector Highlight
Global risk-off led by oil: US Jul-23 selloff (Dow −0.97%, S&P −1.21%, Nasdaq −2.15%) and Asia lower. **FOMC Jul-29** hold expected (3.50–3.75%), but the oil-inflation impulse keeps **Sep-hike odds ~82%** (July ~1-in-3). Nikkei still the YTD leader despite the −2.73% day; Vietnam FTSE EM upgrade still Sep-21. No direct Tho exposure — a global risk gauge.

### Improvements Implemented Tonight
1. **`portfolio_engine/earnings_tracker.py`** *(corrected — resolves the long-standing PTTEP calendar conflict)* — Updated the PTTEP `add_earnings_event` seed to the **officially confirmed 2026-08-04** date (`confirmed=True`), superseding the internal Aug-11 estimate. Aug-04 is 35 days after the Jun-30 quarter-end (inside the 30–45d SET large-cap band) and vindicates the 2026-06-30 rejection of Yahoo's Jul-23 auto-estimate. Notes rewritten for the Brent-$100 regime (watch realised oil price, ~560kboe/d volume, capex, interim dividend); pre-earnings alert window now opens Aug-01. `2026-07-25` marker.
2. **`portfolio_engine/oil_scenario.py`** *(re-ranked — escalation broadens to a third route)* — Incremental tightening on the Jul-24 major re-rank for the CPC Black Sea terminal closure + Hormuz-to-1-tanker + 4th weekly gain: **deal_partial 12→10**, **lebanon 24→25**, **nuclear 24→25**, **status_quo anchor 98→100** (weight held 34). Rewrote all four affected narratives + `run_oil_scenario_report()` default (**100.0→101.0**). Additive; `2026-07-25` markers.
3. **`portfolio_engine/brief_generator.py`** *(enhanced — resolves the Jul-24 queued next-priority)* — Wired **`load_earnings_actual()`** into the brief. Added import + a new **`_load_reported_actuals()`** helper (loads SCB/PTTEP/BAFS actuals, filters to prints within 45 days, returns a compact reconciled read: verdict, dividend_status, thesis_holds/read, advisory). Injected into the LLM context as `reported_earnings_actuals` and extended Section 5 so a "✅ Reported" line surfaces the confirmed SCB Q2 read (not the stale preview). Additive; `2026-07-25` markers.
4. **`data/market_intel/2026-07-25.md`** *(new file)* — 6-section report + macro table + 5 risk flags: oil three-front escalation, holdings (PTTEP Aug-04 confirmed / SCB reconciled / BAFS headwind), gold & currency, US/Fed (Sep-odds 82%), regional; ≥2 outlets per major item.
5. **`data/watchlist.json`** *(refresh + reconciliation)* — `_meta.usd_thb_rate` 33.79→**33.37**, `last_updated`→2026-07-25; PTTEP note/price (151.0) + `next_earnings` **2026-08-04 CONFIRMED**; SCB price 154.5 + `earnings_actual_file`; SCBGOLDE NAV→**4.26**; **15 dated `jul25_` macro keys** (Brent $101.06, third route/CPC, Hormuz-1-tanker, oil re-rank, PTTEP Aug-04, prices, brief-wiring, gold $4,102, USD/THB 33.37, FOMC/Sep-82%, US/regional). 2 catalyst dates (Jul-24 Brent $101, Aug-04 PTTEP). macro_context now **344 keys**.

### Verification
`ast.parse` clean on all three edited modules. oil_scenario `probability_pct` regex scan → **[6,10,34,25,25] sum=100**; isolated weighted-Brent check → **$101.96** (matches the realised ~$101). `earnings_tracker` imported live (after `pip install httpx`): **`load_earnings_actual('SCB.BK')` returns the reconciled actual** (verdict `inline_to_slightly_soft`), `load_earnings_actual('PTTEP.BK')` → None; `validate_earnings_dates()` flags **0 PTTEP issues** (the confirmed Aug-04 date clears the prior Yahoo-Jul-23 conflict); the `_load_reported_actuals` recency filter confirms the SCB print is 8 days old (≤45d, included). `watchlist.json` re-loaded via `object_pairs_hook` **duplicate-key scan → NONE** (344 macro keys; usd_thb 33.37). News cross-checked ≥2 outlets per item (oil: CNBC + Business Standard + NBC + Trading Economics; PTTEP date: Kaohoon; SCB/SET: Kaohoon; gold/FX: goldrate24 + exchange-rates.org + Trading Economics; Fed: CBS + Forbes + CNBC; regional: HDFCSky + Armenpress + Trading Economics). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `run_oil_scenario_report()` and `generate_daily_brief()` weren't exercised end-to-end against the live DB — edits are additive and the math/loaders were verified in isolation; (b) PTTEP Aug-04 is now confirmed but re-verify on the official SET corporate calendar; (c) `data/snapshots/` still holds only `2026-06-21.json` (the live macOS archive cron can't run here).

### Next Priority (for next run)
**Capture the PTTEP Q2/H1 result on Aug-04** — realised Brent, ~560kboe/d volume, capex guidance, any interim dividend — into the earnings calendar + a `data/earnings/pttep_q22026_actual.json` actuals file (mirroring the SCB pattern), and add `PTTEP.BK` to the `load_earnings_actual` map so `_load_reported_actuals` surfaces it. **Watch the SCB interim-dividend declaration (Aug-Sep)** and set the Sep interim event `confirmed=True` with the actual size/ex-date. **Re-check the oil regime**: if Hormuz/Red Sea/CPC de-escalate, shift status_quo/tails back toward the mid-$80s; a total Hormuz closure lifts the tails toward $115–120 and warrants flagging PTTEP operational risk in the brief.

---

## Nightly Run — 2026-07-24 02:30 ICT

*Catch-up run — no runs Jul 17–23.*

### Market Intelligence Summary
Two developments dominate the gap since Jul-16. First, a **major oil re-escalation**: the Jul-16 partial walk-back reversed hard — US airstrikes on Iran ran a **ninth consecutive night**, Houthis struck **two Saudi tankers in the Red Sea** and declared a **Saudi-port blockade** (a second disrupted trade route alongside Hormuz), and **Brent broke $100** (~$100.7 on Jul-23, +7% d/d, +36% m/m, highest since May), with analysts flagging **$120 next**. Second, the top queued item landed: **SCB reported Q2-2026 on Jul-17** — net profit **THB 11,117m (+9.0% QoQ, −13.1% YoY)** — reconciled below. Gold slipped ~2% to **~$4,044** (hawkish-Fed/firm-USD cap despite the oil spike; JPM raised its year-end target to $6,300), **USD/THB reached ~33.79** (baht weakest; BOT held 1.00%), and the **SET holds near multi-year highs** (~1,635–1,649).

### Thai Holdings Update
- **BAFS**: Read flips to a **jet-fuel-cost HEADWIND** at $100 oil (reverses the recent low-oil tailwind); stable tourism offsets. H1 est ~Aug-14.
- **PTTEP**: Large realised-price **TAILWIND** — Brent through $100 on top of the record ~560kboe/d Q2 volume setup; H1 est ~Aug-11. Two-sided: the fear-premium can unwind fast on a truce, and the Middle East footprint adds operational/transit risk. Hold core; don't add into the spike.
- **SCB**: **Q2-2026 REPORTED & RECONCILED** — THB 11,117m (+9% QoQ, −13.1% YoY); NII −10.2% YoY (NIM pressure); fee/wealth +14.8% YoY; trading income +349% QoQ; **NPL 3.17%** (improved, beat the 3.3% est); CAR 18.6%; cost/income 41.3%. **No dividend declared** (interim expected Aug–Sep). H1 ~THB 21.3bn is modestly below the 22–25bn preview → the ~12.79bn Smartkarma Q2 preview was too high (echoed FY2025). Verdict inline-to-soft; **yield thesis holds** on a lower base (~THB 10–11 FY DPS, ~6.5–7%).
- **Gold Fund (SCBGOLDE)**: gold ~$4,044 × USD/THB 33.79 → est NAV **~4.25 THB/unit** (weak-baht cushion offsets the gold dip). JPM year-end target raised to $6,300.

### Technology Sector Highlight
Jul-23 US selloff on the oil surge + Alphabet AI-capex concerns: **Dow −0.97%, S&P −1.21%, Nasdaq −2.15%**. **FOMC Jul-29** hold expected, but **Sep-hike odds jumped to ~82%** (from <53% a week ago) on the oil-inflation impulse. **Nikkei +27.4% YTD** still leads; **Hang Seng −4.3%**, **India SENSEX −8.8%** lag; **Vietnam VN-Index ~1,686** (−9.5% m/m), FTSE EM upgrade still Sep-21. No direct Tho exposure — a global risk gauge.

### Improvements Implemented Tonight
1. **`portfolio_engine/oil_scenario.py`** *(re-ranked — MAJOR RE-ESCALATION)* — Corrected the stale Jul-16 "blockade-without-toll ~$85" base against the realised Brent-$100 print. Added a `2026-07-24` re-rank block + docstring update: status_quo re-anchored **$85→$98** and weight **28→34** (two-front realised base); escalation tails raised (**lebanon 18→24**; **nuclear 20→24**, anchor **$105→$115** toward the $120 warning); de-escalation paths cut (**deal_partial 26→12**, **deal_signed 8→6**). Rewrote all five narratives + `probability_qualitative`, `run_oil_scenario_report()` default (**85.0→100.0**), and the advisory note (large PTTEP tailwind + amplified two-sided risk + BAFS mirror headwind). Additive only; every change carries a `2026-07-24` marker.
2. **`portfolio_engine/earnings_tracker.py`** *(enhanced — SCB reconciliation)* — Added **`load_earnings_actual(ticker)`** (counterpart to `load_earnings_preview`; loads `data/earnings/<slug>_actual.json`) so the brief can switch from preview to reported+reconciled. Updated the SCB Jul-17 `quarterly_results` seed note with the actual print and the preview reconciliation, and the SCB `interim_dividend_announcement` seed note (no div declared Jul-17; interim ~Aug-Sep, likely ~THB 2.00 not 5.5–6.0). Additive; `2026-07-24` markers.
3. **`data/earnings/scb_q22026_actual.json`** *(new file)* — Full reported actuals (P&L, NII/fee/trading split, NPL/CAR/coverage, cost/income), dividend outcome, reconciliation vs preview (verdict: inline-to-slightly-soft), and a yield-thesis assessment (holds, medium-high confidence). Sourced to Kaohoon/ThaiPR/SCB.
4. **`data/market_intel/2026-07-24.md`** *(new file)* — 6-section catch-up report + macro table + 5 risk flags: oil >$100 headline, holdings (SCB reconciled / PTTEP tailwind / BAFS headwind), gold & currency, US/Fed (Sep-hike odds 82%), regional; ≥2 outlets per major item.
5. **`data/watchlist.json`** *(refresh + reconciliation)* — `_meta.usd_thb_rate` 33.59→**33.79**, `last_updated`→2026-07-24; PTTEP/SCB/BAFS/SCBGOLDE notes rewritten to the new regime; SCBGOLDE NAV→**4.25**; SCB `q2_2026_actual` + `earnings_actual_file` added; **23 dated `jul24_` macro keys** (Brent $100.7, oil re-rank, Red Sea front, gold $4,044/JPM $6,300, USD/THB 33.79, SCB actual+reconciliation, KBANK peer, US markets, FOMC/Sep-odds 82%, regional, PTTEP/BAFS oil reads); 3 catalyst dates (Jul-17 SCB, Jul-23 Brent $100, Jul-29 FOMC). macro_context now 329 keys.

### Verification
`ast.parse` clean on `oil_scenario.py` and `earnings_tracker.py`. `probability_pct` regex scan → **[6,12,34,24,24] sum=100**; isolated weighted-Brent check → **~$100.76** (matches the realised ~$100). `scb_q22026_actual.json` and `watchlist.json` re-loaded via `json.load` with an `object_pairs_hook` **duplicate-key scan → NONE** (watchlist 329 macro keys; usd_thb 33.79; NAV 4.25). News cross-checked ≥2 outlets per item (Brent/oil: Trading Economics + CNBC + NBC; SCB: Kaohoon + ThaiPR; gold: Trading Economics + Forbes + JPMorgan/AOL; FX: Trading Economics + Wise; US/Fed: CNBC + Yahoo/CME; regional: Advisor Perspectives + Trading Economics). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `run_oil_scenario_report()` and `load_earnings_actual()` weren't exercised end-to-end against the live DB — edits are additive and the model math/JSON were verified in isolation; (b) SCB H1 ~THB 21.3bn is derived (Q1 ~10.2 + Q2 11.117), not a separately restated H1 figure; (c) the SCB interim dividend is NOT yet declared — the Sep-15 seed stays `confirmed=False`; (d) PTTEP Aug-11 remains an estimate until the SET calendar posts.

### Next Priority (for next run)
**Capture the PTTEP H1/Q2 result (~Aug-11)** — realised Brent, production volume, capex guidance, any interim dividend — into the earnings calendar; the $100 oil regime makes this a high-signal print. **Watch for the SCB interim-dividend declaration (Aug–Sep)** and set the Sep interim event `confirmed=True` with the actual size/ex-date once the board declares. **Re-check the oil regime**: if Hormuz/Red Sea de-escalates, shift status_quo/tails back toward the mid-$80s; if it moves to a total Hormuz closure, lift the tails toward $115–120 and flag PTTEP operational risk in the brief. Lower priority: wire `load_earnings_actual()` into `brief_generator` so the reported+reconciled SCB read reaches the morning brief.

---

## Nightly Run — 2026-07-16 02:30 ICT

### Market Intelligence Summary
The key change since Jul-15 is a **partial walk-back, not a de-escalation**: **Trump abandoned the 20% Strait of Hormuz cargo toll** (CNBC, Jul-14), removing the economic-friction leg of the Jul-13 measures — but **US airstrikes and the naval blockade continue** and Hormuz crossings remain down >50% w/w. **Brent eased to ~$84.7** (Jul-14 settle; Sep future ~$85.9) vs the ~$86–88 the Jul-15 model assumed. Meanwhile **June US CPI cooled to 3.5%** (Fed held 3.50–3.75%, next FOMC Jul-29, ~25–30% hike odds), **gold slipped to ~$4,060** (JPM cut its Q4 target to $4,500 from $6,000), and **USD/THB reached 33.59** — the weakest baht since May 2025, above the 33.5 trigger. Thai equities are strong: SET ~1,608, SET50 at a multi-year high, IMF revised Thai GDP up, and the Constitutional Court cleared the THB 400bn loan decree.

### Thai Holdings Update
- **BAFS**: No material news; ~$85 oil is a mild jet-fuel-cost headwind offset by stable tourism. SCB's Jul-17 print may be a peer catalyst.
- **PTTEP**: Still a **net tailwind**, marginally softer than Jul-15 (toll gone, Brent ~$85 vs ~$86–88). Q1 sales 553k boe/d (+14% YoY), FY2026 target 556k (+8%), record ~560k Q2 volume flagged; ~8% 2026e yield. Two-sided: Middle East operational/transit risk persists. Hold core; add on a de-escalation dip that keeps yield >4.5%.
- **SCB**: **⏰ Q2/H1-2026 results Fri Jul-17 (after close) — imminent.** Preview (Smartkarma, UNCONFIRMED) ~THB 12.79bn vs ~10.89bn consensus — flagged that this figure closely echoes the FY2025 Q2 print, so treat as indicative until the official filing.
- **Gold Fund (SCBGOLDE)**: gold ~$4,060 × USD/THB 33.59 → est NAV **~4.24 THB/unit** (was 4.29). JPM Q4 target cut to $4,500 (still above spot); weak-baht cushion intact.

### Technology Sector Highlight
June CPI 3.5% (core 2.9%) supported a chip-led bounce in US indices; Fed on hold into Jul-29. **Nikkei +33.6% YTD** stays the global leader; **Hang Seng −5.5% YTD** and **India SENSEX −8.9% YTD** lag; **Vietnam VN-Index ~1,791** (+21% YoY) with the FTSE EM upgrade effective Sep-21. No direct Tho exposure — global risk gauge.

### Improvements Implemented Tonight
1. **`portfolio_engine/oil_scenario.py`** *(re-ranked — PARTIAL WALK-BACK)* — Corrected the Jul-15 read for the abandoned Hormuz toll. Added a `2026-07-16` re-rank block; trimmed **status_quo** anchor **87.5 → 85.0** and weight **30 → 28** (toll removed = less friction, Brent eased to ~$84.7 settle), nudged **deal_partial 24 → 26** (toll drop is a mild de-escalation tell), left the active-conflict tails unchanged (18 / 20) and deal_signed at 8 (sum = 100, `ast.parse` clean). Rewrote the status_quo/deal_partial narratives, module docstring update block, the `run_oil_scenario_report()` default (86.0 → 85.0), and the advisory note. Additive only; every change carries a `2026-07-16` marker.
2. **`data/market_intel/2026-07-16.md`** *(new file)* — 6-section report + macro table + 5 risk flags: Hormuz toll-drop headline, holdings (PTTEP softer tailwind / SCB Jul-17 imminent), gold & currency (baht 33.59), US/Fed (CPI 3.5%, FOMC Jul-29), regional (Nikkei leads, India/HK lag), Thai macro/SET multi-year high. ≥2 outlets per major item.
3. **`data/watchlist.json`** *(refresh + reconciliation)* — `_meta.usd_thb_rate` 33.5 → **33.59**, `last_updated` → 2026-07-16; PTTEP note → toll-dropped/Brent-$85 + `oil_regime_jul16`; SCB note → Jul-17 imminent with the preview-figure caveat + `q2_2026_results_date`; SCBGOLDE NAV → **4.24** (gold ~$4,060); **19 dated `jul16_` macro keys** added (toll abandoned, Brent $84.7, oil re-rank, USD/THB 33.59, gold $4,060 + JPM $4,500, SET/SET50, SCB Jul-17, FOMC Jul-29, CPI 3.5%, regional, PTTEP Q1 sales). macro_context now 304 keys.

### Verification
`ast.parse` clean on `oil_scenario.py`; scenario `probability_pct` values [8, 26, 28, 18, 20] confirmed summing to 100. `watchlist.json` re-loaded and re-serialized via `json.load`/`json.dump` (valid JSON, no duplicate keys).

### Next Priority (for next run)
**Post-SCB-earnings reconciliation:** after the Jul-17 (after-close) filing, verify the actual Q2/H1 net income and DPS against the Smartkarma preview (flagged as possibly echoing the FY2025 print), update the SCB watchlist note and dividend_tracker with the confirmed interim-dividend ex-date, and record whether the ~6.75% yield thesis holds. Also confirm whether the Hormuz toll abandonment marks the start of a genuine de-escalation (would shift oil_scenario mass back toward deal_partial/deal_signed).

---

## Nightly Run — 2026-07-15 02:30 ICT

### Market Intelligence Summary
🚨 **The dominant story is a regime FLIP in the opposite direction from Jul-13/14: the US-Iran interim truce has COLLAPSED into active conflict.** The truce broke ~Jul 8 (Iran struck ships in Hormuz), US forces bombed **80+ targets inside Iran** over Jul 12-13, Iran's IRGC **re-closed the Strait of Hormuz**, and on Jul-13 the US reimposed a **naval blockade + 20% cargo toll** (effective Jul-14). **Brent surged ~+10% w/w to ~$86**; ~230 tankers are stranded and crossings fell >50% (though ~8M bbl still transited under US escort — a blockade-and-toll, not yet a total cutoff). Offsetting: **June US CPI cooled to +3.5%** (vs 3.8% exp), but the Fed (Chair Warsh) held 3.50-3.75% and still signals a 2026 hike (CME ~33% Jul / ~69% Sep). **Gold ~$4,119** stayed flat despite the oil-inflation impulse (hawkish Fed + firm USD cap it), and **USD/THB reached ~33.50 — AT the 33.5 HIGH FX trigger.**

### Thai Holdings Update
- **BAFS**: ~9.75 THB. Higher oil (~$86) is now a mild jet-fuel-cost headwind (reversing the recent low-oil tailwind); tourism stable. H1 est ~Aug-14.
- **PTTEP**: **Oil regime flipped to a TAILWIND.** On top of the already-bullish Q2 setup (record ~560kboe/d volume; CLSA ~THB 27.3bn, +131% QoQ; ~8% 2026e yield), the $86 Brent lifts realised prices — but the same event adds **Middle East operational/transit risk**. Breakeven ~$45 = solvency never in doubt. Skew flips downside→**upside**; hold core, don't chase the spike. H1 est Aug-11 (Yahoo Jul-23 still rejected).
- **SCB**: **⏰ Q2/H1 results Fri Jul-17 (after close) — pre-earnings window open.** PREVIEW (Smartkarma, **UNCONFIRMED**): Q2 net income **~THB 12.79bn, beat** vs ~10.89bn est. Kasikorn **upgraded BUY, TP 162**; Phillip 'Accumulate'. 2026e DPS guided ~THB 10.3 (from 11.28), yield ~6.75%.
- **Gold Fund (SCBGOLDE)**: est NAV **~4.29 THB/unit** (gold ~$4,119 × USD/THB ~33.50); gold_drawdown_monitor → fed_driven_dip → hold/add. Weak-baht cushion at the 33.5 trigger.

### Technology Sector Highlight
June CPI 3.5% (below 3.8% exp) lifted **S&P +0.4% / Nasdaq +1%** on a chip bounce; Fed hawkish-hold (Jul ~33% / Sep ~69% hike odds). **Nikkei ~69,744 (+1.47%)** remains the global YTD leader; **Hang Seng ~23,350 (+1.28%)** firm; India IT on agentic-AI momentum; Vietnam FTSE EM upgrade confirmed **Sep-21**. NVDA next earnings Aug-26. No direct Tho exposure — a global risk gauge.

### Improvements Implemented Tonight
1. **`portfolio_engine/oil_scenario.py`** *(re-ranked — REGIME FLIP)* — Inverted the Jul-13 "premium drained" framing to the realised escalation. Re-ranked `brent_scenarios()`: **deal_signed 58→8, deal_partial 26→24, status_quo (now the realised "blockade-but-flowing" ~$86-88 base) 6→30, lebanon_spillover_reclosure 6→18, nuclear_track_breakdown (deal-collapse realised) 4→20 (sum=100)**. Rewrote every narrative + `probability_qualitative`, the module docstring, the Jul-13 comment (added a Jul-15 re-rank block), `probability_weighted_outlook()` note, `run_oil_scenario_report()` default (76.0→**86.0**), and the `advisory_note` (now a two-sided tailwind + Middle East operational-risk read). Expected Brent **~$92.4**. Additive only; every change carries a `2026-07-15` marker.
2. **`portfolio_engine/brief_generator.py`** *(enhanced — resolves the Jul-14 queued item)* — Extended **`_load_calendar_integrity()`** to carry each issue's **`event_type`** and, for `interim_dividend_announcement` rows (which carry no vendor `reconciliation`), **synthesize a readable REVIEW verdict** from `status` + `days_after_results` + `reference_results_date`. Extended the brief prompt so a dividend integrity issue renders labeled as an **ex-date issue**, not an earnings-date issue. A mis-dated ex-date now reaches the morning brief with context instead of a bare status. Additive; `2026-07-15` marker.
3. **`data/market_intel/2026-07-15.md`** *(new file)* — 7-section report: Hormuz crisis, holdings (PTTEP tailwind / SCB Jul-17 preview), gold & currency (33.5 trigger), US/Fed (CPI 3.5%), regional, Thai macro/SET50 multi-year high, macro table + 5 risk flags; ≥2 outlets per item.
4. **`data/watchlist.json`** *(refresh + reconciliation, no duplicate keys)* — `_meta.usd_thb_rate` 33.35→**33.50** (at HIGH trigger); PTTEP note→oil-regime-flip + `oil_regime_jul15`; SCB note→Q2 preview beat + `q2_2026_preview`; SCBGOLDE NAV→**4.29**, gold ~$4,119; **16 dated Jul-15 macro keys** (Hormuz crisis, Brent $86, oil_scenario re-rank, US-Iran conflict, USD/THB 33.5, gold, June CPI 3.5%, Fed odds, SCB preview, PTTEP Q2, SET50, China/Japan, BOT 1.00%, brief dividend-integrity, refresh); `fed_hike_prob_next_meeting_pct`→33, `_dec`→69; catalysts +Jul-14 (blockade) & Jul-17 (SCB). Top + `_meta` `last_updated`→**2026-07-15** (285 macro keys).

### Verification
`ast.parse` clean on both `oil_scenario.py` and `brief_generator.py`. `probability_pct` regex scan → **[8,24,30,18,20] sum=100**; isolated weighted-Brent check → **~$92.4**. The new dividend-synthesis branch was **unit-tested in isolation**: implausible-before-earnings → readable "-7d after the 2026-07-17 results" REVIEW line; no-reference → "no anchoring results event" line; a quarterly row with a vendor `reconciliation` passes through **untouched**. `watchlist.json` reloaded through an `object_pairs_hook` **duplicate-key scan → NONE** (285 macro keys; usd_thb 33.50, `last_updated` 2026-07-15). News cross-checked ≥2 outlets per item (Hormuz: Axios+NPR+CNBC+TheStreet; Brent: Trading Economics+EIA; CPI/Fed: CNBC+TheStreet+Yahoo; gold: LiteFinance/JPMorgan+RoboForex; FX: Trading Economics+Xe/Wise; SCB: Smartkarma+Kaohoon; PTTEP Q2: Kaohoon+Nation). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `run_oil_scenario_report()` and `_load_calendar_integrity()` weren't exercised end-to-end against the live DB/calendar — edits are additive and the model math/synthesis logic were unit-verified; (b) the **SCB ~THB 12.79bn Q2 figure is a Smartkarma PREVIEW, UNCONFIRMED** until the official Jul-17 filing — flagged as such in the watchlist/brief; (c) PTTEP Aug-11 remains an estimate until the SET calendar posts; (d) `data/snapshots/` still holds only `2026-06-21.json` (live macOS archive cron can't run here); (e) no fresh PTTEP spot print found — prior 129.5 (Jun-26) retained.

### Next Priority (for next run)
**Capture the SCB Jul-17 official result** (NIM, NPL, H1 interim dividend) into the earnings calendar + dividend tracker and reconcile against the ~THB 12.79bn preview; set the SCB Sep-15 interim-dividend `confirmed=True` once the board declares. **Re-check the oil regime**: if Hormuz de-escalates (blockade lifted / truce), revert `status_quo`/tails back toward the Jul-13 weights; if it moves to a **total closure**, lift `lebanon`/`nuclear` toward the $105 anchor and flag PTTEP operational risk in the brief. **Watch the 33.5 baht trigger** — if USD/THB holds >33.5, confirm `currency_regime_flag` reads HIGH in the live brief. Lower priority: once ≥3 real snapshots exist, retire the static `gold_recent_high_usd`.

---

## Nightly Run — 2026-07-14 02:30 ICT

### Market Intelligence Summary
The **SET printed a fresh multi-year high** (Jul-13 intraday **1,628.65**, best since Jan-2020) after Thailand's **Constitutional Court approved the government's THB 400bn loan decree**, removing a fiscal-stimulus overhang and extending a **sixth straight session of foreign inflows**; **June CPI cooled to 2.42%** (a 3-month low, back inside the BOT 1–3% band). The Fed **held 3.50–3.75%** with only ~7% priced for Jul 28-29 after the weak June jobs print, keeping the gold/baht real-yield headwind contained: **gold consolidated ~$4,100–4,200** and **USD/THB ~33.35** (below the 33.5 HIGH trigger). **Brent re-firmed to ~$72–76** (+5% wk off the four-month low) — the PTTEP oil-premium drain has **stalled**, not re-escalated.

### Thai Holdings Update
- **BAFS**: ~9.75 THB (P/E ~28); no company news; ~$72–76 Brent keeps jet-fuel costs contained; tourism strong. H1 est ~Aug-14.
- **PTTEP**: **Bullish Q2 setup** — CLSA models Q2 net profit **~THB 27.3bn (+131% QoQ, +102% YoY)**, DBS ~THB 25.6bn; **div yield ~8.2% 2026e**. Softer forward-oil (EIA 3Q26 $74, 2027 $65) is an earnings-**growth** headwind, not solvency (breakeven ~$45). ⚠️ Calendar conflict persists: internal **Aug-11** vs Yahoo **Jul-23** (validator keeps rejecting Jul-23); statutory deadline Aug-14.
- **SCB**: **~153.0 THB (−1.3%). ⏰ Q2/H1 results Fri Jul-17 (after close) — the 3-day pre-earnings alert window OPENS TODAY.** Watch NIM, NPL, and the H1 interim dividend (est THB 5.5–6.0/share). ~7.5% yield thesis intact.
- **Gold Fund (SCBGOLDE)**: est NAV **~4.30 THB/unit** (gold ~$4,150 × USD/THB ~33.35); `gold_drawdown_monitor` → fed_driven_dip → hold/add.

### Technology Sector Highlight
NVDA anchors the AI supercycle: fiscal-Q1 FY27 record revenue **$81.6bn (+85% YoY)**, data-center $75.2bn (92%), +$80bn buyback, dividend raised to $0.25 ("demand has gone parabolic"); **next earnings Aug-26**. July semis choppy after a +80% H1 (DeepSeek own-chip report), but Micron's blowout (HBM sold out into 2028) confirms the memory cycle. **HK/China tech rallied hard** (HSCEI +3.6%, Alibaba +11%; Hang Seng's best week in 8+ months). **Nikkei +38.5% YTD** leads globally. Vietnam FTSE EM upgrade confirmed **Sep-21**. No direct Tho exposure — a global risk gauge.

### Improvements Implemented Tonight
1. **`portfolio_engine/earnings_tracker.py`** *(enhanced — resolves the queued Jul-05/Jul-13 lower-priority item)* — Extended **`validate_earnings_dates()`** to also validate **`interim_dividend_announcement`** events (previously skipped). Added **`_find_reference_results_date()`** (finds the latest quarterly-results event on/before a dividend ex-date) and **`_classify_dividend_date()`** (statuses: `implausibly_before_earnings` / `within_typical_window` (1–90d) / `unusually_late` (>90d) / `no_reference_earnings`). The validation loop now branches by `event_type` (each row now carries an explicit `event_type` key), only flags an ex-date on/before its triggering earnings as a true issue, and the `summary_text` builder handles both quarterly and dividend row shapes. The **SCB Sep-15** interim-dividend seed now validates **`within_typical_window`** (60d after the Jul-17 results). Additive only — no functions removed; every block carries a `2026-07-14` marker.
2. **`data/watchlist.json`** *(data refresh + reconciliation, no duplicate keys)* — SCB `last_price` 143.5→**153.0** (Jul-14) + earnings-alert-open note; PTTEP `q2_2026_outlook` added (CLSA +131% QoQ, 8.2% yield) + note refreshed to the re-firmed oil read; `_meta.usd_thb_rate` 33.28→**33.35**; gold ~$4,150, Brent ~$72–76, SET Jul-13 high **1,628.65**. Added **22 dated Jul-14 macro keys** (SET high + 400bn loan-decree approval, Jun CPI 2.42%, SCB alert-open, PTTEP Q2 outlook, gold/FX/Brent, NVDA Aug-26, China/Japan/India/Vietnam/EU/Fed notes, `earnings_tracker_dividend_validation_added_jul14`). Added 5 catalyst dates (Jul-13, Jul-17, Aug-11, Aug-26, Sep-21). Top + `_meta` `last_updated`→**2026-07-14** (269 macro keys).
3. **`data/market_intel/2026-07-14.md`** *(new file)* — 7-section report: SET multi-year high / 400bn decree, holdings (SCB Jul-17 alert / PTTEP Q2 outlook), gold & currency, US/tech (NVDA), regional (China rally / Nikkei lead / Vietnam Sep-21 / ECB), oil/OPEC, macro table + 5 risk flags; ≥2 outlets per item.

### Verification
`ast.parse` clean on `earnings_tracker.py`. The new dividend classifier was **unit-tested in isolation**: SCB Sep-15 → `within_typical_window` (60d); same-day → `implausibly_before_earnings`; Nov-01 → `unusually_late` (107d); a ticker with no prior quarterly → `no_reference_earnings` — all correct. `watchlist.json` reloaded through an `object_pairs_hook` **duplicate-key scan → NONE** (269 macro keys; SCB 153.0, `_meta` usd_thb 33.35, `last_updated` 2026-07-14). News cross-checked ≥2 outlets per item (SET: Trading Economics + Kaohoon; PTTEP Q2: Kaohoon + HoonVision; gold: LiteFinance/JPMorgan + CoinCodex; FX: Wise/Xe + Bloomberg; NVDA: NVIDIA newsroom/SEC + CNBC; oil: EIA + JPMorgan; rates: Fed + ECB + BOT). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `validate_earnings_dates()` wasn't exercised end-to-end against the live calendar file — the edits are additive and the new helpers were unit-verified; (b) PTTEP Aug-11 remains an *estimate* until the official SET calendar posts (late-Jul); (c) `data/snapshots/` still holds only `2026-06-21.json` (the live 17:35 macOS archive cron can't run here); (d) fresh PTTEP spot price not captured this run — no reliable Jul-14 print found, prior 129.5 (Jun-26) retained.

### Next Priority (for next run)
**Capture the SCB Jul-17 result** (NIM, NPL, H1 interim dividend) into the earnings calendar + dividend tracker, set the SCB Sep-15 interim-dividend `confirmed=True` once the board declares it, and verify the pre-earnings alert actually surfaced in the Jul-14–17 morning briefs. **Confirm the PTTEP date** on the official SET calendar once posted (clears the Yahoo-Jul-23 flag). Lower priority: wire the new dividend-validation output into `brief_generator._load_calendar_integrity()` so a mis-dated ex-date reaches the morning brief, and — once ≥3 real snapshots exist — retire the static `gold_recent_high_usd`.

---

## Nightly Run — 2026-07-13 02:30 ICT

### Market Intelligence Summary
Catch-up run (no runs Jul 6–12). The dominant shift since Jul-5 is that the **oil-premium drain has STALLED**: **Brent firmed ~5% off its ~$70–72 four-month low back to ~$76** (Jul-10) as **Hormuz transit stayed below pre-conflict normal** and renewed US-Iran headlines re-injected a modest supply premium (a record UAE production month capping the upside) — a **re-firming, not a re-escalation**, that eases the further-downside skew on PTTEP. The **SET extended its multi-year run** (Jul-11 intraday high **1,621.55**, off the Jul-3 three-year high 1,611.28; +5% m/m) on plunging bond yields and foreign big-cap inflows. **Gold consolidated ~$4,100–4,200** and **USD/THB eased to ~33.28** (still below the 33.5 HIGH trigger) under a Fed that is **holding but hawkishly split** (June SEP: 9/18 officials see ≥1 hike; PCE revised up to 3.6%; first meeting under new Chair Kevin Warsh).

### Thai Holdings Update
- **BAFS**: No company news; ~$76 Brent still a mild jet-fuel-cost positive; demand stable. H1 est ~Aug-14.
- **PTTEP**: Brent back to ~$76 firms the earnings read vs the June ~$70 trough; breakeven ~$45, dividend safe, yield >4.5% = medium-term add zone. ⚠️ **Calendar conflict persists** — Yahoo still lists next earnings **Jul-23** (10 days out) vs internal **Aug-11**; validator keeps rejecting Jul-23. Re-confirm on the official SET calendar (posts late-Jul); statutory deadline Aug-14.
- **SCB**: **Q2/H1-2026 results confirmed Jul-17** (after close); the **pre-earnings alert window opens tomorrow, Jul-14**. Watch NIM, NPL, and the H1 interim dividend (est THB 5.5–6.0/share). ~7.5% yield thesis intact in the hawkish-hold regime.
- **Gold Fund (SCBGOLDE)**: est. NAV **~4.30 THB/unit** (gold ~$4,150 × USD/THB ~33.28). `gold_drawdown_monitor` reads **fed_driven_dip → hold/add**, not a trend break. JPM ~$6,000 Q4; HSBC trimmed its 2026 avg to $4,560.

### Technology Sector Highlight
H1 index gains were strong (Nasdaq +12.8%, S&P +9.6%, Dow +8.9%) but July turned choppy (Jul-7 S&P −0.45%, Nasdaq −1.16%). **Semis sold off** after Samsung results and reports that **China's DeepSeek is building its own AI chip** — profit-taking after the PHLX chip index's ~+60% YTD run (NVDA −10.8% in June). Offsetting the US wobble, **HK/China tech rallied hard** (HSCEI +3.6%, Alibaba +11%; Hang Seng's best week in 8+ months). Japan's Nikkei leads globally (+38.5% YTD ~68,558). No direct Tho exposure — a global risk-sentiment gauge. Vietnam FTSE EM upgrade confirmed **Sep-21** (top regional catalyst).

### Improvements Implemented Tonight
1. **`portfolio_engine/oil_scenario.py`** *(enhanced — re-ranks the PTTEP oil regime for the Jul-13 re-firming)* — The module's mass sat 64% on the Jun-24 "premium gone / deal-signed strengthening" leg, which the data now contradicts (Brent +5% off the four-month low, Hormuz still sub-normal). Re-ranked `brent_scenarios()` probabilities **deal_signed 64→58, deal_partial 22→26, status_quo 6, lebanon_spillover 5→6, nuclear_track 3→4 (sum=100)**, updated each narrative + the `deal_signed` anchor 77→**76**, refreshed the module docstring, `probability_weighted_outlook()` note, `run_oil_scenario_report()` default (77→**76**), and the advisory note to a firmer **$76–88** band. Additive only — no functions removed; every change carries a `2026-07-13` marker. Effect: PTTEP's oil read in the brief shifts from "further-downside" to "premium drain stalled, firmer band."
2. **`data/watchlist.json`** *(data refresh + reconciliation, no duplicate keys)* — Brent 72→**76** (+5% wk), gold 4175→**4150**, USD/THB→**33.28**, SCBGOLDE NAV **~4.30**, `_meta.usd_thb_rate`→33.28. Added 14 dated Jul-13 keys: oil re-firming + `oil_scenario_rerank_jul13`, SET 3-yr-high extension, Fed hawkish-split SEP (Chair Warsh, PCE 3.6%), China/Japan/India/US-tech/Vietnam notes, `scb_earnings_imminent_jul13` (alert Jul-14), and `pttep_yahoo_conflict_jul13` (Yahoo Jul-23 still rejected). Top + `_meta` `last_updated`→2026-07-13 (247 macro keys).
3. **`data/market_intel/2026-07-13.md`** *(new file)* — 8-section catch-up report: oil-premium stall, SET run, holdings (SCB Jul-17 / PTTEP Jul-23 conflict), gold/currency, US-tech/DeepSeek, China rally, Japan/India, Vietnam, macro table + 5 risk flags; ≥2 outlets per item.

### Verification
`ast.parse` clean on `oil_scenario.py`; `probability_pct` values regex-scanned → **[58, 26, 6, 6, 4] sum = 100**. `watchlist.json` reloaded through an `object_pairs_hook` **duplicate-key scan → NONE** (247 macro keys; gold 4150, Brent 76, USD/THB 33.28; top + `_meta` `last_updated` 2026-07-13). News cross-checked ≥2 outlets per item (Brent: Fortune+Forbes+Trading Economics; gold: Yahoo/Forbes+JPMorgan+CoinCodex; FX: Trading Economics+Xe/Wise; SET: Trading Economics+Kaohoon; Fed: Fed SEP+Trading Economics; China: Bloomberg+SCMP; SCB Jul-17: Stock Events+market.sec.or.th). **Verified no change needed** on the SCB pre-earnings path: seed has SCB Jul-17 `confirmed=True` with "brief should flag from 2026-07-14", and `upcoming_earnings_alerts(alert_days=3)` marks days_until=1 as `imminent` — it will fire tomorrow. **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so the re-ranked `run_oil_scenario_report()` wasn't exercised end-to-end — the edits are additive and the model math is unchanged; (b) PTTEP Aug-11 remains an *estimate* until the official SET calendar posts (late-Jul); (c) `data/snapshots/` still holds only `2026-06-21.json` (the live macOS archive cron can't run here); (d) the Brent re-firming read leans on Jul-6/10 Fortune/Forbes items that emphasise residual Hormuz disruption — treated as a modest re-firming, not a confirmed re-escalation.

### Next Priority (for next run)
**Verify the SCB Jul-14 pre-earnings alert actually surfaced** in the live morning brief, and capture the Jul-17 result (NIM/NPL/H1 dividend) into the calendar + dividend tracker. **Confirm the PTTEP date** on the official SET calendar once posted and set `confirmed=True` (clears the Yahoo-Jul-23 flag). **Re-check the oil regime**: if Brent holds/extends above ~$78 on sustained Hormuz sub-normal transit, consider nudging `deal_partial` further and lifting the tails; if it slides back below $72, revert toward the Jul-5 weights. Lower priority: extend `validate_earnings_dates` to `interim_dividend_announcement` events (SCB Sep-15 seed) and, once ≥3 real snapshots exist, retire the static `gold_recent_high_usd`.

---

## Nightly Run — 2026-07-05 02:30 ICT

### Market Intelligence Summary
A **monetary regime flip** dominated the Jun-30 → Jul-5 gap (no runs Jul 1-4). The **June US jobs report (Jul-2): payrolls +57k** vs ~115k consensus, with April/May revised **down 74k combined** and unemployment 4.2% on a falling participation rate. This **crumbled Fed hike odds** — a September hike is now off the table, CME FedWatch reads ~**7%** for Jul 28-29, the base case is a prolonged hold, and the first cut is pushed to **Sept-2026** at earliest. The repricing reversed late-June's higher-for-longer narrative: **gold rebounded to ~$4,175** (Jul-4) from the ~$4,026 Jun-30 low, and the **SET hit a three-year high of 1,611.28 (+1.11%, Jul-3)** on plunging bond yields and foreign big-cap inflows. Brent held ~$72 (Hormuz recovered, OPEC+ Aug quota hike expected); USD/THB eased to ~33.19-33.43, still below the 33.5 trigger.

### Thai Holdings Update
- **BAFS**: No company news; cheaper jet fuel a mild margin positive; demand stable. H1 est ~Aug-14.
- **PTTEP**: Brent ~$72 — premium fully unwound; earnings-growth headwind, **not** solvency (breakeven ~$45, dividend safe). Yield >4.5% = medium-term add zone. H1 est **Aug-11** (official SET calendar not yet posted).
- **SCB**: Loses a little higher-for-longer shine as the hike path unwinds, but ~7.5% yield + digital/virtual-banking + Home Credit Vietnam story intact; mkt cap ~463bn THB. **Earnings Jul-17 re-confirmed** (external listings); alert Jul-14.
- **Gold Fund (SCBGOLDE)**: gold ~$4,175, USD/THB ~33.2 → est. NAV **~4.31 THB/unit** (up from ~4.18). `gold_drawdown_monitor` reads **fed_driven_dip → hold/add**, not a trend break. GS YE $4,900 / JPM ~$6,000 avg Q4.

### Technology Sector Highlight
US tech two-sided: **chips sold off** on profit-taking after a +80% H1 — Micron -10%/-7% (still +260% YTD), AMD -4.3%, Applied Materials -7.4% on valuation questions — while **Meta +9%** (new cloud/compute-resale business), MSFT +3%, AAPL +2%. H1 index gains: Nasdaq +12.8%, S&P +9.6%, Dow +8.9%. No direct Tho exposure — a global risk-sentiment gauge. Japan/BOJ ~2% terminal path (yen ~160, carry intact spot); Vietnam FTSE EM upgrade confirmed **Sep-21** (top regional catalyst).

### Improvements Implemented Tonight
1. **`portfolio_engine/brief_generator.py`** *(enhanced — resolves the Jun-30 queued #1)* — Added **`_load_calendar_integrity()`** (imports `validate_earnings_dates` from `earnings_tracker`, dual-safe, degrades to `{issue_count:0, issues:[]}`), which returns a compact `issue_count` + up to 4 flagged items (ticker, expected_date, status, reconciliation verdict). Wired into `generate_daily_brief()`'s context as `calendar_integrity`, and extended the prompt so the **Catalyst Watch header** now emits a one-line **📅 Calendar integrity** note whenever an unconfirmed quarterly date is `suspiciously_early`/`breaches_deadline` or a vendor estimate disagrees — quoting the KEEP/REVIEW/AMBIGUOUS verdict verbatim (e.g. PTTEP Aug-11 KEEP vs Yahoo Jul-23 REJECT). Any vendor/calendar date conflict now reaches Tho's morning brief instead of living only in the DEVLOG. Omitted entirely when `issue_count == 0`.
2. **`data/watchlist.json`** *(data refresh + reconciliation, no duplicate keys)* — Repriced for the regime flip: gold 4026→**4175**, USD/THB 33.29→**33.2**, Brent 70→**72**, SCBGOLDE NAV **~4.31**; **`fed_hike_prob_next_meeting_pct` 19→7** and `fed_hike_prob_dec_pct` 80→30 (feeds `fed_policy_risk_flag.hike_prob_pct` — the key scoring input). Added dated Jul-05 keys: `us_jun_payrolls_k=57` + note, `fed_hike_prob_note_jul05` (regime-flip explainer), `gold_note_jul05`, `usd_thb_note_jul05`, `brent_note_jul05`, `set_close_jul03=1611.28`/`set_change_jul03_pct=1.11`/`set_jul03_note` (3-yr high), `us_tech_note_jul05`, `scb_earnings_confirm_jul05`, `calendar_integrity_brief_integration_jul05`. `_meta.usd_thb_rate`→33.2; top + `_meta` `last_updated`→2026-07-05 (232 macro keys).
3. **`data/market_intel/2026-07-05.md`** *(new file)* — 8-section nightly report covering the Fed regime flip, SET 3-yr high, holdings, gold/currency, US-tech two-sided read, oil/OPEC, regional, and a macro table + 5 risk flags; ≥2 outlets per item.

### Verification
`ast.parse` clean on `brief_generator.py` (import + helper + context + prompt edits are additive; the LLM prompt only *adds* an optional header line gated on `calendar_integrity.issue_count > 0`). `watchlist.json` reloaded through a `object_pairs_hook` **duplicate-key scan → NONE** (232 macro keys; gold 4175, USD/THB 33.2, fed_hike_next 7, SET 1611.28; top + `_meta` `last_updated` 2026-07-05). News cross-checked ≥2 outlets per item (jobs: CNBC+BLS+Kiplinger; gold: CNBC+JPMorgan+Trading Economics; SET: Kaohoon+Trading Economics; oil: Fortune+OilPrice+Trading Economics; FX: Xe+Trading Economics). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `_load_calendar_integrity()` wasn't exercised end-to-end — the wiring is additive and the underlying `validate_earnings_dates()` was unit-verified on the Jun-30 run; (b) PTTEP Aug-11 remains an *estimate* until the official SET calendar posts (late-Jul) — `validate_earnings_dates` keeps flagging it until `confirmed=True`; (c) `data/snapshots/` still holds only `2026-06-21.json` (the live 17:35 macOS archive cron can't run here).

### Next Priority (for next run)
**Confirm the PTTEP date on the official SET calendar** once posted (late-Jul) and set `confirmed=True` — this clears the calendar-integrity flag. **SCB earnings Jul-17** enters the 3-day pre-earnings window ~Jul-14: verify `pre_earnings_brief` fires and the brief carries the alert. **Re-check `fed_policy_risk_flag` output** now that `hike_prob_pct` dropped 19→7 — confirm the gold/baht drag reads materially lower (dovish repricing) in the next live brief. Lower priority: extend `validate_earnings_dates` to `interim_dividend_announcement` events; once ≥3 real snapshots exist, retire the static `gold_recent_high_usd`.

---

## Nightly Run — 2026-06-30 02:30 ICT

### Market Intelligence Summary
The driver stayed **monetary, not geopolitical**. **Gold slid to ~$4,026** (Jun-29, -1.49%), on track for a **fourth straight monthly loss (~-10% in June)** as US-Iran de-escalation + firm Fed-hike pricing sap safe-haven demand; the Jun-30 daily band dips as low as **~$3,952**, re-testing $4,000. The **baht eased to ~33.29/USD** (from 33.39), still under the 33.5 `currency_regime_flag` HIGH trigger (week range 32.92-33.47). **Brent rebounded above $70** off a four-month low as Gulf supply ramps (Saudi loading Ras Tanura; UAE/Kuwait/Qatar boosting) — with an OPEC-cohesion wrinkle (Iraq sought a higher quota and signalled a possible exit). The **SET bounced**: Jun-29 opened 1,550.80 and reached an intraday 1,577.81, off the Jun-26 close of 1,542.34. The next Fed meeting (**Jul 28-29**) is ~80% priced for a hold (~20% hike); the hawkish path is intact further out (~80% Dec).

### Thai Holdings Update
- **BAFS**: No company news; cheaper jet fuel (Brent ~$70) a mild margin positive; demand stable. H1 est ~Aug-14 (= the statutory deadline).
- **PTTEP**: ~129.5 THB. Brent ~$70-72 — premium fully unwound; earnings-growth headwind, **not** solvency (breakeven ~$45, dividend safe). ✅ **Earnings-date conflict RESOLVED tonight**: internal Aug-11 estimate retained (in-band); Yahoo's Jul-23 auto-estimate rejected.
- **SCB**: ~143.5 THB; clearest higher-for-longer-Fed beneficiary (~7.5% yield); BOT 1.00% trims NIM at the margin. **Earnings Jul-17** (alert Jul-14).
- **Gold Fund (SCBGOLDE)**: gold ~$4,026, USD/THB ~33.29 → est. NAV **~4.18 THB/unit**. Weak-baht cushion + Fed-driven dip → `gold_drawdown_monitor` reads hold/add. GS YE target **cut to ~$4,900** (from $5,400); JPM ~$5,000 Q4.

### Technology Sector Highlight
US tech bounced to start a holiday-shortened week (US closed Fri Jul-3): Jun-29 S&P +0.55%, Nasdaq +0.98%. But the **prior week was rough** — S&P -2%, Nasdaq -4.6% on a reported **OpenAI IPO delay** (NYT: weighing a push to next year after SpaceX's weak post-debut trade) that whipsawed chip stocks. Micron's blowout (HBM sold out 2027/28) still anchors the supercycle. No direct Tho exposure — a global risk-sentiment gauge. **Japan/BOJ** on a ~2% terminal path (Tamura: hikes at "few-month intervals"), yen ~160. **Vietnam** VN-Index near a record (~1,929; FTSE EM upgrade confirmed **Sep-21**, the top regional catalyst).

### Improvements Implemented Tonight
1. **`portfolio_engine/earnings_tracker.py`** *(enhanced — resolves the Jun-29 queued PTTEP date conflict)* — Added **`validate_earnings_dates()`** plus helpers `_infer_quarter_end()`, `_set_filing_deadline()`, `_classify_report_date()`, and a `KNOWN_EXTERNAL_ESTIMATES` map. It checks every `quarterly_results` event against two ground-truth anchors — the **SET statutory 45-day filing window** (Q2 ends Jun-30 → hard deadline Aug-14) and the **empirical 30-45-day large-cap reporting band** (PTTEP's Q1-2026 filed May-06 = 36 days after Mar-31) — classifying each date as `within_typical_band` / `suspiciously_early` / `implausibly_early` / `breaches_deadline`, and reconciling vendor estimates with a KEEP/REVIEW/AMBIGUOUS verdict (never auto-mutates the calendar). **Result:** internal PTTEP **Aug-11 (42d, in-band) KEPT**; Yahoo **Jul-23 (23d, suspiciously_early) REJECTED**. Confirmed events (SCB Jul-17) are excluded from issue-flagging so banks' earlier reporting cadence doesn't false-alarm.
2. **`portfolio_engine/earnings_tracker.py` → `run_nightly_earnings_check()` + PTTEP seed note** *(wired + documented)* — The nightly result dict now carries a **`date_validation`** block, and the PTTEP `seed_known_earnings` note documents the reconciliation logic (Aug-11 retained, Jul-23 rejected, re-confirm on the official SET calendar late-Jul; statutory deadline Aug-14).
3. **`data/watchlist.json`** *(data refresh + reconciliation, no duplicate keys)* — gold 4088→**4026** (4th monthly loss, Jun-30 band 3,952-4,060), USD/THB 33.39→**33.29** (eased, still <33.5), Brent 72→**70** (rebound off the 4-mo low; OPEC/Iraq-exit watch), SCBGOLDE NAV **~4.18**, GS YE target **cut to $4,900**. Rolled the Fed next-meeting odds to the **Jul 28-29** meeting (**63→19**, prior 63 referred to Sept; Dec path 80 retained) feeding `fed_policy_risk_flag.hike_prob_pct`. Added Jun-29/30 SET/US-tech/BOJ/Vietnam notes + the earnings-validation markers. `_meta`+top `last_updated`→2026-06-30 (220 macro keys).
4. **`data/market_intel/2026-06-30.md`** *(new file)* — 8-section nightly report: gold's monthly-loss/$4k re-test, SET bounce + holdings, the gold/currency two-leg read, Fed Jul-28-29 + BOJ, oil/OPEC-cohesion, US-tech/OpenAI-IPO-delay, Vietnam, macro table + 5 risk flags; ≥2 outlets per item.

### Verification
`ast.parse` clean on `earnings_tracker.py`. `validate_earnings_dates` classification logic unit-tested standalone (project imports stubbed): **PTTEP Aug-11 → within_typical_band (42d)**; **Yahoo Jul-23 → suspiciously_early (23d)**; **BAFS Aug-14 → within_typical_band (45d, deadline edge)**; **Q1 precedent May-06 → within_typical_band (36d)** — validating the empirical anchor; **Aug-20 → breaches_deadline (51d)**; **Jun-15 → breaches_deadline**. `json.load` clean on `watchlist.json` with a **duplicate-key scan (object_pairs_hook) → NONE** (220 macro keys; gold 4026, USD/THB 33.29, Brent 70, Fed next-meeting 19/Dec 80; top `last_updated` 2026-06-30). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `run_nightly_earnings_check()` wasn't exercised end-to-end — the pure validator logic is verified standalone and the wiring is additive; (b) the Aug-11 PTTEP date remains an *estimate* pending the official SET corporate-calendar (posts late-Jul) — `validate_earnings_dates` will keep flagging it until `confirmed=True`; (c) `data/snapshots/` still holds only `2026-06-21.json` (the live 17:35 macOS archive cron can't run here).

### Next Priority (for next run)
**Confirm the PTTEP date on the official SET calendar** once posted (late-Jul) and set `confirmed=True` (this clears it from `validate_earnings_dates` issues). **Surface `date_validation` in the morning brief** — add a one-line "calendar integrity" note to `brief_generator` so any `suspiciously_early`/`breaches_deadline` vendor conflict reaches Tho. **Watch USD/THB through 33.5** (HIGH trigger) and whether gold holds the $4,000 re-test (Jun-30 band to ~$3,952). Lower priority: extend `validate_earnings_dates` to `interim_dividend_announcement` events (different SET timing rules) and, once ≥3 real snapshots exist, retire the static `gold_recent_high_usd`.

---

## Nightly Run — 2026-06-29 02:30 ICT

### Market Intelligence Summary
A quiet, weekend-flat confirming run — markets shut Jun-27/28, so all the late-June frames carried over intact. **Gold held ~$4,088** (essentially unchanged after the soft-PCE rebound to ~$4,085; Jun-29 forecast band ~$3,952–$4,060, mixed technicals, $4k reclaim holding). The **baht held ~33.39/USD**, still just under the 33.5 `currency_regime_flag` HIGH trigger (wk range 32.88–33.47). **Brent stayed ~$72–74** (lowest since Feb; Hormuz ~75% of prewar flows). The **SET's Jun-26 close of 1,542.34 (−1.04%)** carries into Monday's open. The driver remains **monetary, not geopolitical**: ~84% priced for ≥1 Fed hike in 2026, and the **BOJ on a slow ~2% terminal path** (Tamura: hike at "few-month intervals") — the latter is tonight's code focus.

### Thai Holdings Update
- **BAFS**: No company news; cheaper jet fuel (Brent ~$72–74) a mild margin positive; demand stable. H1 est ~Aug 14.
- **PTTEP**: ~129.5 THB. Brent ~$72–74 — premium fully unwound; earnings-growth headwind, **not** solvency (breakeven ~$45, dividend safe). ⚠️ Yahoo lists next earnings **Jul 23** (internal est. had Aug 11) — flagged for calendar reconciliation.
- **SCB**: ~143.5 THB; clearest higher-for-longer-Fed beneficiary (~7.5% yield); BOT 1.00% trims NIM at the margin. **Earnings Jul 17** (alert Jul 14).
- **Gold Fund (SCBGOLDE)**: gold ~$4,088, USD/THB ~33.39 → est. NAV **~4.22 THB/unit**. Weekend hold + weak-baht cushion support the sleeve; `gold_drawdown_monitor` reads fed-driven dip → hold/add. GS YE ~$4,900 / JPM ~$6,150.

### Technology Sector Highlight
US/Asia tech kept rotating, not breaking: a mid-June −1.34% Fed-driven Nasdaq down day (MSFT/META/GOOGL/AMZN red) was followed by a +1.91% recovery to ~26,518, on AI-data-center cost worries + an OpenAI-IPO-delay narrative. Micron's blowout (HBM sold out to 2027/28) still anchors the supercycle. No direct Tho exposure — a global risk-sentiment gauge. **Japan/BOJ** is tonight's regional focus (see below): rate 1.00%, ~2% terminal path, yen ~160 (carry intact spot). Vietnam VN-Index near record (~1,929; FTSE EM upgrade confirmed **Sep 21**, the top regional catalyst).

### Improvements Implemented Tonight
1. **`portfolio_engine/brief_generator.py`** *(enhanced — resolves the Jun-28 queued next-priority)* — Added **`_load_japan_policy_risk(boj_rate, usd_jpy_rate, boj_hike_prob_pct)`**, mirroring `_load_fed_policy_risk()`/`_load_currency_regime()` (dual import path, degrades to `{}`), and wired it into `generate_daily_brief()`'s context build. The brief previously had **no Japan/BOJ section at all** — Japan was bare free text. Now the `boj_hike_prob_pct` plumbing added Jun-28 reaches Tho's morning brief.
2. **`portfolio_engine/brief_generator.py` → context + Section 4 prompt** *(enhanced)* — Injected `japan_policy_risk_flag` into the LLM context dict, and rewrote the **Section 4 (Regional Markets)** instruction to require a numeric Japan line: risk_level + risk_score (e.g. *"Japan/BOJ carry risk: low (0.49)"*), the market-implied next-meeting BOJ hike odds when present (~20% late-Jul), and an explicit **medium-term framing** — weak spot yen (USD/JPY ~160) keeps carry intact *today*, but a priced BOJ tightening path is a *forward* risk to EM/Asian (incl. SET) capital flows, i.e. a watch item not a today-action. Escalates if `carry_threshold_breached` or elevated/high.
3. **`data/watchlist.json`** *(reconciled + data refresh)* — `last_updated`/`_meta.last_updated` → 2026-06-29 (both reconciled); gold 4085→**4088** (weekend-flat); refreshed `boj_hike_prob_note` with Tamura's "few-month interval" / ~2% terminal guidance; added `japan_brief_integration_jun29` marker + Jun-29 gold/USD-THB/Brent notes (206 macro keys). `boj_hike_prob_next_meeting_pct` left at **20** (no new futures-implied print).
4. **`data/market_intel/2026-06-29.md`** *(new file)* — 5-section nightly report with a dedicated **Japan/BOJ** subsection explaining tonight's brief integration, plus macro table + 5 risk flags, ≥2 outlets per item.

### Verification
`ast.parse` clean on `brief_generator.py`; `json.load` clean on `watchlist.json` (206 macro keys; top + `_meta` `last_updated` both 2026-06-29; gold 4088, NAV 4.22, boj_prob 20). `japan_policy_risk_flag` re-tested standalone via the live `risk_scorer.py` source (constants/`datetime` stubbed) to confirm the brief helper's inputs map correctly: **1.0%/USD-JPY 160, no prob → elevated 0.45** (backward compatible); **+20% → elevated 0.49** (the intended nudge, matches Jun-28 documented values); **+80% → high 0.61**; **USD-JPY 140 + 100% → severe 1.0** (clamps, `carry_threshold_breached=True`); **+0% → no bump (0.45)**. The new brief code is additive/diagnostic — no scoring or DB logic changed. **Caveats:** (a) the ~20% BOJ next-meeting odds remain a sourced estimate (no clean futures-implied print published) — revise when one exists; (b) `data/snapshots/` still holds only `2026-06-21.json` (the live macOS 17:35 archive cron + DB can't run in this sandbox), so `generate_daily_brief()` couldn't be exercised end-to-end; the wiring is verified standalone; (c) PTTEP earnings date conflict (Yahoo Jul 23 vs internal Aug 11) flagged for reconciliation.

### Next Priority (for next run)
**Confirm the Japan line lands in a live brief** once the macOS run executes — verify `japan_policy_risk_flag.boj_hike_prob_pct` appears in the brief Section 4 and reads sensibly alongside the Fed/currency flags. **Reconcile the PTTEP earnings date** (Yahoo Jul 23 vs internal Aug 11) against the SET calendar and fix `earnings_tracker`/watchlist accordingly. **Watch USD/THB through 33.5** (currency_regime HIGH trigger) and whether gold holds the $4,000 reclaim. Lower priority: still **confirm the 17:35 snapshot job writes daily files** so `derive_gold_trailing_high()` and the currency/Fed/BOJ archival go live; once ≥3 real snapshots exist, retire the static `gold_recent_high_usd`.

---

## Nightly Run — 2026-06-28 02:30 ICT

### Market Intelligence Summary
A quiet, confirming weekend run. The **May PCE printed in line/soft**, prompting a *modest* scale-back of 2026 Fed-hike bets — enough to lift **gold back to ~$4,085** (Jun 27, +~1.9% over two sessions) but **not** to dislodge the priced hiking path (**~80% Dec, ~63% Sep**). The **baht held ~33.39/USD** (weakest since May 2025, still under the 33.5 flip line), **Brent stayed ~$72** (lowest since Feb; Hormuz flows ~75% of prewar, US-Iran MOU signed), and **SET closed Jun-26 at 1,542.34 (-1.04%)** amid a global tech sell-off (Korea's Kospi tripped an 8% circuit breaker; an OpenAI IPO delay was reported). Net for the book: wash-to-positive.

### Thai Holdings Update
- **BAFS**: No company news; cheaper jet fuel (Brent ~$72) a mild margin positive; demand stable. H1 est ~Aug 14.
- **PTTEP**: ~129.5 THB. Brent ~$72 — premium fully unwound; earnings-growth headwind, **not** solvency (breakeven ~$45, dividend safe). H1 est Aug 11.
- **SCB**: ~143.5 THB; clearest higher-for-longer-Fed beneficiary (~7.5% yield); BOT 1.00% trims NIM at the margin. **Earnings Jul 17** (alert Jul 14).
- **Gold Fund (SCBGOLDE)**: gold ~$4,085, USD/THB ~33.39 → est. NAV **~4.22 THB/unit** (up from ~4.14). The rebound + weak-baht cushion support the sleeve; `gold_drawdown_monitor` reads fed-driven dip → hold/add. GS YE ~$4,900 / JPM ~$6,150.

### Technology Sector Highlight
US/Asia tech kept rotating, not breaking: Nasdaq –0.24% Jun 26 (4th down session), S&P –0.05%, on AI-data-center cost worries + a reported **OpenAI IPO delay**; **Korea's Kospi hit an 8% circuit breaker**. Micron's blowout still stands. No direct Tho exposure — global risk-sentiment gauge. Vietnam VN-Index near a record (~1,929; FTSE EM upgrade ~Sep 21 the top regional catalyst).

### Improvements Implemented Tonight
1. **`ai_engine/risk_scorer.py`** *(enhanced — resolves the Jun-27 queued next-priority)* — Extended **`japan_policy_risk_flag()`** with an optional **`boj_hike_prob_pct`** parameter, mirroring the Fed flag's market-implied treatment. A priced BOJ hike only *raises* repatriation/carry-unwind risk, so the component is purely additive (**0.0–0.20, 100% ⇒ +0.20**) and can only **sharpen** the score — surfacing *forward* tightening risk even while the spot yen is weak (USD/JPY ~160, carry intact). The cap is set **below the Fed flag's (0.40)** on purpose: Japan's rate component already runs the base near the "high" band once the BOJ sits at the 1.0% carry threshold, so a modest priced hike should nudge — not jump — the read. New output keys `boj_hike_prob_pct` + `components{rate,jpy,hike_prob}` (additive, backward compatible).
2. **`ai_engine/risk_scorer.py` → `calculate_portfolio_risk()`** *(wired)* — Now reads `macro_context.boj_hike_prob_next_meeting_pct` from `watchlist.json` and forwards it to `japan_policy_risk_flag()`. `None`/absent ⇒ prior rate/FX-only behaviour.
3. **`data/watchlist.json`** *(reconciled + data refresh)* — Added `boj_hike_prob_next_meeting_pct=20` (late-Jul, low; BOJ guided to ~few-month intervals toward ~2% terminal — Sept/Oct the likelier vehicle) + `boj_hike_prob_note`/`boj_hike_prob_integration_jun28`. Refreshed gold 4007→**4085** (+~1.9% two-session rebound on soft PCE), SCBGOLDE NAV 4.14→**4.22**, **SET Jun-26 close 1,542.34 (-1.04%)** (prior entry only had the Jun-25 close + Jun-26 open). **De-staled `currencies.USD_THB.last_rate`** (33.22/Jun-24 → 33.39/Jun-27, matching `macro_context`). Updated US-tech/Vietnam/Brent notes; `_meta`+top `last_updated`→2026-06-28 (202 macro keys).
4. **`data/market_intel/2026-06-28.md`** *(new file)* — 8-section nightly report incl. a dedicated **Japan/BOJ** section explaining tonight's flag enhancement, the gold rebound read, the baht-near-33.5 watch, oil/Hormuz, US/Asia tech rotation, macro table + 6 risk flags, sourced ≥2 outlets per item.

### Verification
`ast.parse` clean on `risk_scorer.py`. `japan_policy_risk_flag` refinement unit-tested standalone (constants stubbed): backward-compat identical without `boj_hike_prob_pct` (**1.0%/USD-JPY 160 → 0.45 "elevated"**); **+20% → 0.49** (stays elevated, the intended nudge); **+80% → 0.61** ("high"); severe yen 138 + 100% **clamps at 1.0**; 0% ⇒ no bump. `json.load` clean on `watchlist.json` after rewrite (202 macro keys; `_meta`/top `last_updated` both 2026-06-28; gold 4085, NAV 4.22, SET 1542.34, boj_prob 20). News cross-checked ≥2 outlets per item (gold: Trading Economics + JM Bullion + GoldSilver; USD/THB: Trading Economics + Wise; Brent/Hormuz: CNBC + OilPrice; US/Fed: Yahoo Finance + TheStreet; BOJ: CNBC + Bloomberg; Vietnam: Trading Economics + Vietnam Briefing). **Caveats:** (a) no clean futures-implied BOJ next-meeting probability is published, so the 20% is a sourced estimate (BOJ "few-month interval" guidance), flagged for revision when a real print exists; (b) `data/snapshots/` still holds only `2026-06-21.json` — the live macOS 17:35 archive cron hasn't produced new files in this sandbox, so `calculate_portfolio_risk()` couldn't be exercised end-to-end (DB + venv unavailable here); the new wiring is additive and verified standalone.

### Next Priority (for next run)
**Surface `japan_policy_risk_flag` in the daily brief.** Unlike the Fed and currency-regime flags, the brief currently has *no* Japan/BOJ section at all — add a `_load_japan_policy_risk()` helper (mirroring `_load_fed_policy_risk()`) and a Section-2/Regional line citing the carry-unwind risk_level + the priced BOJ hike odds, so the new `boj_hike_prob_pct` plumbing reaches Tho's morning brief. Also: **confirm `calculate_portfolio_risk()` consumes both `hike_prob_pct` (Fed) and `boj_hike_prob_pct` (BOJ)** once the live macOS run executes; **watch USD/THB through 33.5** (HIGH trigger) and whether gold holds the $4,000 reclaim. Lower priority: still **confirm the 17:35 snapshot job writes daily files** so `derive_gold_trailing_high()` and the currency/fed/BOJ archival go live.

---

## Nightly Run — 2026-06-27 02:30 ICT

### Market Intelligence Summary
The driver tonight is **monetary, not geopolitical**. The Fed's hawkish pause is now priced as an *active hiking path* — markets put **~80% on a December hike and ~63% on September**, and new Chair **Kevin Warsh's** median projection calls for **1–2 hikes in 2026** (vs *one cut* projected in March). That single repricing pulled **gold back to ~$4,007** (–~5% w/w, ~20% below the Jan $5,602 record), held the **baht at ~33.39/USD** (weakest since May 2025, but still under the 33.5 regime-flip line), and drove a **rotation out of US mega-cap tech** — Nasdaq down a 4th straight day — *despite* Micron's blowout. Brent kept falling to **~$72** on Hormuz de-escalation (tankers exiting) even as a ceasefire-violation/drone-attack headline flickered — the market dismissed it.

### Thai Holdings Update
- **BAFS**: No company news; cheaper jet fuel (Brent ~$72) a mild margin positive; demand stable. H1 est ~Aug 14.
- **PTTEP**: ~129.5 THB. Brent ~$72 (lowest since Feb) — premium fully unwound; earnings-growth headwind, **not** solvency (breakeven ~$45, dividend safe). Lebanon-Hormuz reclosure tail dormant/walked-back. H1 est Aug 11.
- **SCB**: ~143.5 THB; clearest higher-for-longer-Fed beneficiary (~7.5% yield); BOT 1.00% trims NIM at the margin. **Earnings Jul 17** (alert Jul 14).
- **Gold Fund (SCBGOLDE)**: gold ~$4,007, USD/THB ~33.39 → est. NAV **~4.14 THB/unit**. Weak baht cushions the THB NAV; `gold_drawdown_monitor` reads a Fed-driven dip → hold/add. GS YE ~$4,900 / JPM ~$6,150.

### Technology Sector Highlight
Micron's blowout (rev $41.46B, EPS $25.11, Q4 guide $50B, HBM sold out to 2027/28) confirms the AI-memory supercycle, but the **tape is rotating away from tech**: Nasdaq –4 sessions, S&P –3% MTD, on AI-cost worries (Apple/Microsoft raised iPhone/Xbox prices Jun 25), OpenAI-IPO-delay chatter, and the hawkish Fed. Not directly Tho-relevant (no US tech holdings) — a global risk-sentiment gauge. Vietnam VN-Index near a record (~1,929; ATH ~1,937 May 15), FTSE EM upgrade ~Sep 21 the top regional catalyst.

### Improvements Implemented Tonight
1. **`ai_engine/risk_scorer.py`** *(enhanced — answers tonight's Fed regime shift)* — Added an optional **`hike_prob_pct`** parameter to **`fed_policy_risk_flag()`**, grounding the hawkish bias bump in the *market-implied* next-meeting hike odds instead of free-text dot-plot guesses. The probability scales a 0.0–0.40 component (100% ⇒ +0.40) and can only **sharpen — never soften** — an already-hawkish read; a dovish-text-but-priced-hike case surfaces the repricing tension and nets it (never below the dovish floor). Fully backward compatible (`None` ⇒ prior text-only behaviour). Wired into `calculate_portfolio_risk()` (reads `macro_context.fed_hike_prob_next_meeting_pct`) and exposed in the output (`hike_prob_pct`, `components.hike_prob`).
2. **`portfolio_engine/brief_generator.py`** *(enhanced)* — `_load_fed_policy_risk()` now forwards `hike_prob_pct` (from the same watchlist macro field), and the Section 2 prompt asks the brief to cite the market-implied hike odds alongside the Fed-drag score when present (e.g. *"Fed drag: elevated (0.59); market prices ~80% Dec hike"*).
3. **`data/watchlist.json`** *(reconciled + data-integrity fix)* — **De-staled the `_meta` block** (it carried 33.22 / 2026-06-25 while `macro_context` was current — two competing `last_updated` keys; now both 2026-06-27 / 33.39). **Corrected a mislabeled SET close** (stored "Jun-25 1,548.22" was actually the Jun-24 close; Kaohoon confirms Jun-25 = 1,558.55, +0.67%). Refreshed the **stale `holdings`/`SET_indices` sub-trees** (SCBGOLDE note still said "FED HANGOVER Jun 18" / NAV 4.3; PTTEP note still said "deal virtually signed Jun 15"; SET index last_close still 1,587.07 from Jun-18). Updated gold 4040→4007, Brent 73→72, USD/THB→33.39, SCBGOLDE NAV 4.17→4.14; added `fed_hike_prob_next_meeting_pct=63` / `fed_hike_prob_dec_pct=80` + Jun-26 tech/oil/lebanon notes (193 macro keys).
4. **`data/market_intel/2026-06-27.md`** *(new file)* — 8-section nightly report: the Fed-regime headline, SET + holdings (with the SET correction), gold/currency core read, oil/Hormuz two-sided wrinkle, US-tech rotation, regional, macro table + 5 risk flags, sourced.

### Verification
`ast.parse` clean on `risk_scorer.py` and `brief_generator.py`. `fed_policy_risk_flag` unit-tested in isolation (constants stubbed): backward-compat identical without `hike_prob_pct`; **3.625% neutral + 80% → 0.5075 (elevated)** vs 0.1875 text-only (probability grounds the headwind); hawkish text + 80%/63% unchanged at 0.5875 (prob ≤ the 0.40 cap can't double-count); **dovish text + 80% → 0.3075** (repricing surfaced, netted); clamps at 0/100/150%. `json.load` clean on `watchlist.json` after the rewrite (193 macro keys; `_meta`/top `last_updated` both 2026-06-27). News cross-checked ≥2 outlets per item (USD/THB: Trading Economics + Wise; gold: Trading Economics + forecast trackers; Brent/Hormuz: CNBC + Al Jazeera + EIA; Fed/US: Yahoo Finance + CNBC + TheStreet; SET: Kaohoon; Vietnam: Trading Economics). **Snapshot note:** `data/snapshots/` still holds only `2026-06-21.json` — the 17:35 ICT archive cron has not produced new files in this sandbox (the live macOS scheduler + DB can't be exercised here), so `calculate_portfolio_risk()`/`_load_scbgolde_weight()` couldn't be run end-to-end; the new wiring is additive and the flag was verified standalone.

### Next Priority (for next run)
**Confirm `calculate_portfolio_risk()` consumes the new `hike_prob_pct`** once the live macOS run executes — verify `fed_policy_risk_flag.hike_prob_pct` appears in the snapshot/brief and that the brief Section 2 cites the priced odds. **Watch USD/THB through 33.5** (HIGH trigger) and the Hormuz ceasefire-violation headline — if Brent re-spikes toward ~$105, flip `lebanon_hormuz_status` to *threatened* and raise the oil-scenario reclosure tail; if it keeps fading, return to *dormant*. Lower priority: still **confirm the 17:35 snapshot job writes daily files** so `derive_gold_trailing_high()` and the currency/fed archival go live; once ≥3 real snapshots exist, retire the static `gold_recent_high_usd`. Consider also extending the same market-implied-probability treatment to `japan_policy_risk_flag` (BOJ hike odds).

---

## Nightly Run — 2026-06-26 02:30 ICT

### Market Intelligence Summary
Two confirmations and one regime watch. **Micron's after-close Jun-24 print was a blowout beat-and-raise** — record revenue **$41.46B** (+346% YoY, ~+16% vs consensus), non-GAAP EPS **$25.11** (+24%), 84.6% gross margin, and a **Q4 guide of $50B rev / 86% margin / >$30B FCF**, with HBM3E+HBM4 **sold out through CY2027 into 2028**; stock **+14.6%**. That answers last run's "react to MU" priority: the Jun-23 semis rout was bar-nerves, not a demand break, and the AI-memory supercycle is intact. Meanwhile the **baht broke to its weakest since May 2025** (USD/THB ~33.38, week high 33.47) on the widening US(hawkish)–Thailand(easy 1.00%) gap, pushing `currency_regime_flag` to **ELEVATED (~0.48, regime-break)** toward the 33.5 line that flips it HIGH. **Gold rebounded above $4,000 to ~$4,040** (+1.02% Jun 25) after the Jun-24 sub-$4k crack, on a softer dollar + in-line May core PCE (3.4% YoY).

### Thai Holdings Update
- **BAFS**: No company news; cheaper jet fuel (Brent ~$73) a mild margin positive; demand stable. H1 est ~Aug 14.
- **PTTEP**: ~129.5 THB. Brent ~$73 (lowest since Feb), premium fully unwound — earnings-growth headwind, **not** solvency (breakeven ~$45, dividend safe). Lebanon-Hormuz upside tail dormant. H1 est Aug 11.
- **SCB**: ~143.5 THB; clearest higher-for-longer-Fed beneficiary (~7.5% yield); BOT 1.00% trims NIM at the margin. **Earnings Jul 17** (alert Jul 14).
- **Gold Fund (SCBGOLDE)**: gold ~$4,040, USD/THB ~33.38 → est. NAV **~4.17 THB/unit**. Weak baht cushions the THB NAV vs the USD gold move; `gold_drawdown_monitor` reads Fed-driven dip → hold/add. GS YE ~$4,900 / JPM ~$6,150.

### Technology Sector Highlight
Micron's blowout (rev $41.46B, EPS $25.11, Q4 guide $50B, HBM sold out to 2027/28, +14.6%) resets AI-semis sentiment firmly positive; read-through positive for NVDA/AMD/AVGO. Offsets: narrow breadth + a hawkish Fed (May core PCE 3.4% in line, median dot 3.8%, no 2026 cuts, dollar near a 4-week high). Vietnam VN-Index at a record ~1,929 (8th straight weekly advance) on a Moody's outlook upgrade to POSITIVE.

### Improvements Implemented Tonight
1. **`portfolio_engine/brief_generator.py`** *(enhanced — resolves last run's queued #2)* — Wired **`risk_scorer.currency_regime_flag`** into the daily brief **Section 2**. Added three helpers: `_load_currency_regime()` (dual import path, degrades to {}), `_load_scbgolde_weight()` (estimates the gold-sleeve fraction from `data_collector/portfolio_snapshot.json`, falls back to 0.25 when the fund NAV price is missing), and `_parse_leading_float()` (extracts the numeric value from annotated watchlist fields like `"33.47 (Jun 24, 2026)"`). The brief now reads USD/THB + the prior 1-yr high from the watchlist and the gold weight from the live snapshot, computes the flag, injects `currency_regime_flag` into the LLM context, and the Section 2 prompt now states the **baht-regime risk_level/score and the two-sided FX trade-off** — the weak baht **cushions** SCBGOLDE's THB NAV (`scbgolde_thb_nav_cushion_pct`) while **raising** the FX entry cost of new USD buys — and flags a **33.5 crossing**. Diagnostic/advisory only; no scoring or DB logic changed. `usd_asset_weight` left 0.0 (the book holds no USD-denominated positions today).
2. **`data/market_intel/2026-06-26.md`** *(new file)* — 7-section nightly report: the Micron-confirmation + baht-regime headline, SET rebound + holdings, gold/currency (the core two-leg read), oil + the conflicting-Hormuz-headlines caveat, US tech (MU result), regional (Vietnam record + Moody's), macro table + 5 risk flags, sourced.
3. **`data/watchlist.json`** *(reconciled)* — `last_updated`→2026-06-26; gold $3,987→**$4,040** (rebound above $4k), USD/THB 33.22→**33.38** (`usd_thb_1yr_high`→33.47), Brent 76.5→**73.0** (lowest since Feb, with the de-escalation-vs-closure caveat), SET Jun-25 **1,548.22** (+0.48%), SCBGOLDE NAV 4.10→**4.17**, the **Micron beat-and-raise RESULT** (replacing the "imminent" marker) + refreshed `us_tech_note`, May core PCE 3.4%, Vietnam record/Moody's, and the `brief_currency_regime_integration_jun26` marker.

### Verification
`ast.parse` clean on `brief_generator.py`. `currency_regime_flag` logic unit-tested standalone against tonight's inputs (macOS venv + cross-package imports can't run in-sandbox): **33.38 vs prior 33.22 → elevated (0.48), regime_break=True, crossed 33.0, baht +2.71% vs neutral → SCBGOLDE cushion +0.68% at 0.25 weight**; week-high 33.47 → elevated (0.51); hypothetical 33.55 → crosses the 33.5 threshold as expected. `_parse_leading_float` verified on annotated string `"33.47 (Jun 24, 2026)"`→33.47 and plain float 33.38. `json.load` clean on `watchlist.json` (179 macro keys). News cross-checked ≥2 outlets per item (MU: Investing.com + TradingKey; gold: TradingEconomics; baht: TradingEconomics + Wise; Brent/Hormuz: Sunday Guardian + TradingEconomics + EIA; PCE/Fed: Federal Reserve + FXStreet + BEA; SET: Kaohoon; Vietnam: TradingEconomics + the-shiv). **Snapshot note:** `data/snapshots/` still holds only `2026-06-21.json` — the 17:35 ICT archive cron has not produced new files (the live macOS scheduler hasn't run in this sandbox), so `_load_scbgolde_weight()` falls back to the 0.25 default; confirm the weight self-derives once the live snapshot writer fills.

### Next Priority (for next run)
**Watch the baht through 33.5** — if USD/THB prints ≥33.5 the `currency_regime_flag` flips toward HIGH; verify the brief Section 2 states it and that the SCBGOLDE cushion scales correctly once `data_collector/portfolio_snapshot.json` carries a live gold-fund NAV (today the gold leg has no price, so the weight defaults to 0.25). **Confirm the de-escalation vs Lebanon-Hormuz-closure ambiguity resolves** — if a genuine reclosure is confirmed (Brent spiking toward ~$105), flip `lebanon_hormuz_status` and raise the oil-scenario reclosure tail; if traffic keeps normalising, leave dormant. Lower priority: still **confirm the 17:35 snapshot job writes daily files** so `_load_scbgolde_weight()` and `derive_gold_trailing_high()` go live; once ≥3 real snapshots exist, retire the static `gold_recent_high_usd`.

---

## Nightly Run — 2026-06-25 02:30 ICT

### Market Intelligence Summary
Two clean technical breaks on one Fed-driven move. **Gold tumbled ~3.07% to ~$3,987 — its first sub-$4,000 print of this drawdown** — as a stronger dollar and firm Fed-rate-hike expectations (9/18 dots now a hike, median 3.8%, PCE 3.6%) lifted real yields. Simultaneously the **baht broke past 33/USD to ~33.22, its weakest since May 2025**, on the widening US(hawkish)–Thailand(easy, 1.00%) policy gap. The two are the same USD-strength trade and partly offset for this book: the weak baht cushions SCBGOLDE's THB NAV even as gold falls in USD. Separately, **Brent fell below $77 to ~$76.5** (lowest since Feb) on rising Hormuz traffic + US-Iran peace progress (signing flagged Friday).

### Thai Holdings Update
- **BAFS**: No company news; cheaper jet fuel (~$76.5 Brent) a mild margin positive; demand stable. H1 est ~Aug 14.
- **PTTEP**: ~134 THB. Brent ~$76.5 — premium fully unwound; earnings-growth headwind, **not** solvency (breakeven ~$45, dividend safe). The Lebanon-Hormuz upside tail is now **dormant**. H1 est Aug 11.
- **SCB**: ~141 THB; clearest higher-for-longer-Fed beneficiary (~7.5% yield); BOT 1.00% trims NIM at the margin. **Earnings Jul 17** (alert Jul 14).
- **Gold Fund (SCBGOLDE)**: gold ~$3,987, USD/THB ~33.22 → est. NAV **~4.10 THB/unit**. ~−11% off the ~$4,500 early-June high → `gold_drawdown_monitor` reads Fed-driven dip → hold/add; GS YE ~$4,900 / JPM ~$6,150 intact.

### Technology Sector Highlight
**Micron (MU) reports fiscal Q3 AFTER the US close Jun 24 (~03:00 ICT Jun 25) — the result is NOT yet out at this run.** Guided record revenue ~$35.5B, HBM capacity sold out for 2026, ~17% implied move into a record ~$1,134 price; the watch item is **beat-and-raise guidance**. The tape was fragile: Jun 23 saw a heavy semis rout (MU −13%, Nasdaq −2.21%) on bar-nerves into earnings, not a demand break. MRVL joined the S&P 500 (Jun 22). HK weak (Hang Seng −1.8%); Japan/India soft; Vietnam VN-Index ~1,857 with the FTSE EM upgrade ~Sep 21 the top regional catalyst.

### Improvements Implemented Tonight
1. **`ai_engine/risk_scorer.py`** *(enhanced — resolves the oldest, least-developed currency code)* — Added **`currency_regime_flag(usd_thb_rate, prior_1yr_high, scbgolde_weight, usd_asset_weight)`**, a discrete two-sided THB-regime diagnostic that replaces the bare linear `currency_risk_score` (2026-06-08) as the project's FX-cost/risk lens. It scores baht weakness across a **threshold ladder (33.0/33.5/34.0/35.0)** plus a **regime-break bump** when the rate prints a fresh cyclical low above the prior 1-yr high, and frames the impact **both ways**: the weak baht **cushions SCBGOLDE's THB NAV** (more THB per USD-priced unit) while **raising FX entry cost** for any new USD-denominated buy and signalling imported-inflation/SET-outflow pressure. Wired into `calculate_portfolio_risk()` (reads the prior 1-yr high + SCBGOLDE/USD weights from the live position values; tonight 33.22 → **ELEVATED**, score ~0.43, regime_break=True) and into `_build_snapshot_archive_payload()` (`currency_regime_level`/`_break`/`baht_vs_neutral_pct`). Diagnostic only — the blended score is unchanged.
2. **`data/market_intel/2026-06-25.md`** *(new file)* — 6-section nightly report: the twin gold-<$4k / baht->33 break headline, SET −2.11% + holdings, gold/currency (the core read), oil + the now-dormant Lebanon tail, US tech (MU imminent), regional + macro table + 5 risk flags, sourced.
3. **`data/watchlist.json`** *(reconciled)* — `last_updated`→2026-06-25; gold $4,129→**$3,987** (sub-$4k), USD/THB 32.9→**33.22** (broke 33; `usd_thb_1yr_high`→33.22), Brent 77.2→**76.5**, SET Jun-23 **1,540.90** (−2.11%), SCBGOLDE NAV 4.21→**4.10**, **`lebanon_hormuz_status` walked_back→dormant**, Fed dot-plot bias, MU-earnings-imminent marker, USD_THB currencies block refreshed, and the currency_regime_flag-add marker.

### Verification
`ast.parse` clean on `risk_scorer.py`. `currency_regime_flag` unit-tested across the full ladder (with `utils` stubbed): 32.4→low(0.00), 32.9→low(0.128), 33.0→elevated(0.36, break), **33.22→elevated(0.43, break, crossed 33.0)**, 33.6→elevated(0.55), 34.2→high(0.74), 35.5→high(1.00); edge cases `prior_1yr_high=None`→no break and zero-weight contributions both clean; two-sided deltas verified (at 33.22: baht +2.22% vs neutral → SCBGOLDE NAV cushion scales by weight, USD entry-cost scales by USD weight). `json.load` clean on `watchlist.json` (165 macro keys). News cross-checked ≥2 outlets (gold: Trading Economics + Fortune; USD/THB: Trading Economics + Bloomberg/Wise; Brent/Hormuz: Sunday Guardian + HDFC Sky + GS; Fed: Federal Reserve + U.S. Bank + TradingKey; SET: Kaohoon). **Snapshot note:** `data/snapshots/` still holds only `2026-06-21.json` — the 17:35 ICT archive cron has not produced new files, i.e. the live scheduler hasn't run in this sandbox (the macOS-linked venv + cross-package import + DB can't be exercised here). The new flag is additive; confirm `data/snapshots/` fills with `currency_regime_level` on the next live cycle.

### Next Priority (for next run)
**React to Micron's Jun-24 after-close print** — a >14–17% move (beat-and-raise vs in-line guide) resets the AI-semis sentiment read across the watchlist; update `us_tech_note` and, if MU disappoints, re-check the chip-cycle thesis. **Watch the baht regime**: if USD/THB pushes through 33.5 the `currency_regime_flag` flips toward HIGH — consider surfacing it (and the gold-fund cushion) in `brief_generator.py` Section 2 so the brief states the FX trade-off explicitly. Lower priority: still **confirm the 17:35 snapshot job writes daily files** so `derive_gold_trailing_high()` and the new `currency_regime` archival go live; once ≥3 real snapshots exist, retire the static `gold_recent_high_usd`.

---

## Nightly Run — 2026-06-24 02:30 ICT

### Market Intelligence Summary
The oil-conflict narrative kept **de-escalating**. The US granted Iran a **60-day license to sell oil internationally**, Hormuz transit is **rising** (Iran shipped >30M bbl last week; Kuwait/UAE on alternative routes), and **Brent fell to a ~3-month low ~$77.2**. The Jun 19–20 IRGC threat to re-close Hormuz over Israeli strikes in **Lebanon is being WALKED BACK**, not executed — answering last run's "materialise or walk back?" question. Gold slid to **~$4,129** (−1.49%, below $4,150) as firm Fed-rate-hike expectations outweighed the peace optimism — a Fed/USD repricing, not a demand break.

### Thai Holdings Update
- **BAFS**: No company news; cheaper jet fuel (~$77 Brent) a mild margin positive; demand stable. H1 est ~Aug 14.
- **PTTEP**: ~134 THB. Brent ~$77, premium fully unwound — an earnings-growth headwind, **not** solvency (breakeven ~$45, dividend safe). A Lebanon-driven Hormuz reclosure would be a sharp positive (EIA ~$105). H1 est Aug 11.
- **SCB**: ~141 THB; clearest higher-for-longer-US-Fed beneficiary (~7.5% yield); BOT confirmed **1.00%** trims NIM at the margin. **Earnings Jul 17** (alert Jul 14).
- **Gold Fund (SCBGOLDE)**: gold ~$4,129, USD/THB ~32.9 → est. NAV **~4.21 THB/unit**. Drawdown reads as a Fed/USD dip (GS YE ~$4,900 / JPM ~$6,150 intact).

### Technology Sector Highlight
**AI trade cooled Jun 23** — NVDA/MU/AMD led a semis pullback into earnings. **Micron (MU) reports fiscal Q3 after the close Jun 24** — consensus ~$19.95–20.76 EPS / ~$34.7–35.8B revenue (~+280% YoY rev), options imply a **~14% move**; ~+275% YTD, 8-quarter beat streak — the week's key semis catalyst. **Marvell (MRVL) joined the S&P 500 Jun 22** (passive bid). Japan/India soft; HK weak; **Vietnam VN-Index 1,857 (+1.77%)**, FTSE EM upgrade ~Sep 21 the top regional catalyst.

### Improvements Implemented Tonight
1. **`ai_engine/risk_scorer.py`** *(enhanced — resolves the queued #1)* — Added **`lebanon_spillover_flag(status, current_brent_usd, pttep_weight)`**, which scores the **Lebanon→Hormuz reclosure tail DISCRETELY**, decoupled from the nuclear-talks status (until now this tail was merged into oil_scenario's `deal_collapses`). It scores the *opposite* tail to `oil_scenario_risk_flag` — an oil **re-spike** — via a 5-rung status ladder (dormant/walked_back/threatened/partial_disruption/reclosed → 0.05–0.95 proxy) and frames it as an **asymmetric PTTEP upside hedge** (re-spike toward the EIA ~$105 anchor lifts PTTEP earnings) while remaining a broad EM/inflation risk. Wired into `calculate_portfolio_risk()` (reads `lebanon_hormuz_status` from the watchlist; tonight = `walked_back` → LOW) and into `_build_snapshot_archive_payload()` (`lebanon_spillover_status`/`_risk_level`/`_proxy`). Diagnostic only — the blended score is unchanged.
2. **`portfolio_engine/oil_scenario.py`** *(enhanced — resolves the queued split)* — **Split the single `deal_collapses` case into two discrete tails** mirroring the new flag: `lebanon_spillover_reclosure` (regional channel, **trimmed 8→5** as the threat is walked back) and `nuclear_track_breakdown` (**3**, small given the roadmap + IAEA return). `deal_signed` raised **62→64** on the 60-day oil license + rising transit; `status_quo` 6, `deal_partial` 22 (sum **100**). Current-Brent default **80→77**; narratives and advisory note updated to the ~$77 3-month-low reality.
3. **`data/market_intel/2026-06-24.md`** *(new file)* — 7-section nightly report: the de-escalation headline, SET + confirmed BOT 1.00%, gold/currency, oil + the two discrete tails, US tech (MU earnings Jun 24, MRVL→S&P 500, AI-trade cooling), regional (Vietnam strong), macro table + risk flags, sourced.
4. **`data/watchlist.json`** *(reconciled)* — `last_updated`→2026-06-24; Brent 80.6→77.2 (3-month low + oil-license note), gold $4,190→$4,129, USD/THB→32.9, SCBGOLDE NAV 4.28→4.21, SET Jun-22 1,574.13; added the new **`lebanon_hormuz_status: "walked_back"`** field (consumed by `lebanon_spillover_flag`), the Iran 60-day-oil-license flag, MU-earnings-Jun-24 marker, and markers for tonight's flag-add + oil-scenario-split.

### Verification
`ast.parse` clean on both edited modules. `oil_scenario` probabilities re-extracted: **[64, 22, 6, 5, 3] → sum 100**. `lebanon_spillover_flag` unit-tested in isolation across the full status ladder: dormant→low(0.05), walked_back→low(0.12), threatened→elevated(0.45), partial_disruption→high(0.70), reclosed→high(0.95), and an unknown status falls back to walked_back — all with the correct re-spike gap ($105−$77=$28) and PTTEP upside scaling by weight. `json.load` clean on `watchlist.json` (150 macro keys). News cross-checked across ≥2 outlets (oil/Hormuz: Al Jazeera + Trading Economics + EIA; gold: Trading Economics + GoldPrice; SET/BOT: KAOHOON + DBS; Micron: CNBC + Benzinga + Nasdaq). **Snapshot-writer note:** `data/snapshots/` still holds only `2026-06-21.json` — the new 17:35 ICT cron job (added Jun 23) has not produced `2026-06-22/06-23.json`, i.e. the live scheduler hasn't run in this environment (and the macOS-linked venv + cross-package import + DB can't be exercised in-sandbox). The wiring is unchanged and additive; confirm `data/snapshots/` fills on the next live nightly cycle before retiring the static `gold_recent_high_usd`.

### Next Priority (for next run)
**Watch the Lebanon→Hormuz channel:** if the IRGC reclosure threat re-arms, flip `lebanon_hormuz_status` to `threatened`/`partial_disruption` and raise `lebanon_spillover_reclosure` in `oil_scenario.py` (oil re-spike → PTTEP tailwind); if it fully dissolves, set `dormant` and trim toward 3–4. **React to Micron's Jun-24 after-close print** — a >14% move would reset the AI-semis sentiment read across the watchlist. Still pending: **confirm the 17:35 snapshot job actually writes daily files** so `derive_gold_trailing_high()` goes live; once ≥3 real snapshots exist, retire the static gold trailing-high. Lower priority: surface `lebanon_spillover` in `brief_generator.py` Section 3 (oil) so the brief states the discrete tail explicitly.

---

## Nightly Run — 2026-06-23 02:30 ICT

### Market Intelligence Summary
The Iran/oil narrative turned **two-sided**. De-escalation **strengthened**: the postponed Swiss talks **resumed Jun 21–22** ("encouraging progress"), the US and Iran agreed a **roadmap for a final deal**, and **Iran invited IAEA inspectors back in** — the biggest verification milestone yet and a clear positive for keeping Hormuz open. But a **new, independent tail surfaced**: the IRGC reportedly moved to **re-close the Strait of Hormuz over Israeli strikes in Lebanon** — a regional-spillover channel decoupled from the nuclear track. Brent held ~$80.6 (Jun 19); gold firmed to **~$4,190** (+0.93% Jun 22) off the ~$4,140 low; USD/THB ~32.95. Domestically, the **BOT rate is confirmed 1.00%** (held unanimously in April) — finishing the reconciliation of last run's correction.

### Thai Holdings Update
- **BAFS**: No company news; cheaper jet fuel (~$80 Brent) a mild margin positive; demand stable. H1 est ~Aug 14.
- **PTTEP**: ~134 THB. Brent ~$80, premium unwound — an earnings-growth headwind, not solvency (breakeven ~$45, dividend safe). A Lebanon-driven Hormuz reclosure would be a sharp positive (EIA ~$105). H1 est Aug 11.
- **SCB**: ~141 THB; clearest higher-for-longer-US-Fed beneficiary (~7.5% yield); BOT 1.00% trims NIM at the margin. **Earnings Jul 17** (alert Jul 14); H1 preview seeded.
- **Gold Fund (SCBGOLDE)**: gold ~$4,190, USD/THB ~32.95 → est. NAV **~4.28 THB/unit**. Drawdown reads as a Fed/USD dip, not a demand break (JPM Q4 target $6,000).

### Technology Sector Highlight
US mixed Jun 22 (S&P +0.12%, Nasdaq −0.27%) as markets weighed the Iran progress. **Marvell (MRVL) joined the S&P 500 Jun 22** (passive-buying event); **Micron (MU) +4% ahead of earnings this week** — a near-term semis catalyst. Vietnam VN-Index **1,857 (+1.77%)**; the **FTSE EM upgrade (~Sep 21)** stays the top regional medium-term catalyst. Japan/India soft; HK weak.

### Improvements Implemented Tonight
1. **`ai_engine/engine_runner.py`** *(enhanced — resolves the long-standing queued #1)* — Wired the DB-free **`archive_daily_snapshot()`** into the nightly scheduler as a new cron job at **17:35 ICT** (5 min after `save_daily_performance` at 17:30), and registered it in `pipeline_state`. Until now only the DB-path writer was scheduled, so when Postgres was down the archive line never ran and `data/snapshots/` stayed empty (leaving `derive_gold_trailing_high()` and the multi-day drawdown trend inert). The new job fills the archive regardless of DB state; it's idempotent (writes today's dated file), so running alongside the DB path is harmless.
2. **`portfolio_engine/oil_scenario.py`** *(enhanced — resolves the queued "watch for a rescheduled US-Iran round")* — Re-ranked and **reframed** the Brent scenarios to tonight's two-sided reality. The nuclear track **re-de-risked** (talks resumed Jun 21-22, roadmap agreed, IAEA inspectors invited back), so the negotiation-execution tail shrinks: `deal_collapses` **reframed from "talks stall" to the Lebanon-spillover Hormuz-reclosure channel** and trimmed **9→8**; `deal_signed` nudged **61→62** on the roadmap + IAEA progress; `deal_partial` 23, `status_quo` 7 (sum **100**). EIA's ~$105 Hormuz-reclosure anchor retained for the collapse case.
3. **`data/market_intel/2026-06-23.md`** *(new file)* — 7-section nightly report: the two-sided Iran/oil headline, SET + confirmed BOT 1.00%, gold/currency, oil + the Lebanon channel, US tech (MRVL→S&P 500, MU earnings), regional (Vietnam strong), macro table + risk flags, sourced.
4. **`data/watchlist.json`** *(reconciled)* — `last_updated`→2026-06-23; **`bot_policy_rate_pct` corrected 1.25→1.00** (stale field finally fixed); gold $4,155→$4,190, USD/THB 32.82→32.95, SCBGOLDE NAV est 4.24→4.28; added the Iran roadmap + Lebanon-Hormuz-reclosure flags, the oil-scenario re-rank marker, US Jun-22 (MRVL/MU), Vietnam 1,857, and the snapshot-writer scheduling marker.

### Verification
`ast.parse` clean on both edited modules. `oil_scenario` probabilities re-extracted: **[62, 23, 7, 8] → sum 100**. `engine_runner.py` confirmed to import `archive_daily_snapshot`, register it in `pipeline_state`, and schedule a cron job at `minute=35`. `json.load` clean on `watchlist.json` (135 macro keys). News cross-checked across ≥2 outlets (Iran roadmap: NPR + CNBC; Hormuz/Lebanon: CNBC + the Iran-negotiations briefings; gold: LiteFinance + JPM; SET/BOT: Kaohoon + BOT). Note: a full in-sandbox run of the new scheduled job (which needs the cross-package `performance_analytics` import + a populated `portfolio_snapshot.json`) wasn't executed here — the wiring is additive and the called function is unchanged from the verified Jun-22 work, so it carries no new logic risk; confirm `data/snapshots/2026-06-23.json` appears after the first live 17:35 run.

### Next Priority (for next run)
**Confirm the new 17:35 job actually wrote `data/snapshots/2026-06-23.json`** on the next live cycle; once ≥3 real snapshots exist, verify `derive_gold_trailing_high()` self-updates correctly and consider retiring the static `gold_recent_high_usd`. Then: **add a discrete `lebanon_spillover` flag to `risk_scorer`/`oil_scenario`** so the Hormuz-reclosure tail is tracked independently of the nuclear-talks status (tonight they were merged into `deal_collapses`). Watch whether the IRGC reclosure threat **materialises or is walked back** — if it sticks, raise the collapse tail and flag an oil re-spike for PTTEP; if it dissolves alongside the roadmap, downgrade it further.

---

## Nightly Run — 2026-06-22 02:30 ICT

### Market Intelligence Summary
A quiet weekend tape but two substantive shifts. **Gold ~$4,155** (Fri Jun 19), ~8% off the early-June ~$4,500 high — a Fed/USD repricing after the hawkish June dot-plot, **not** a demand break — and notably **Goldman Sachs reportedly trimmed its year-end gold target to ~$4,900 (from $5,400)** while JPM stays ~$6,000+. **Brent ~$80.6** (week −8.5%; GS cut Q4 to $80) as the Iran ceasefire holds and Hormuz stays open despite the postponed Swiss technical talks. The **US Fed held 3.50–3.75%** (no 2026 cuts, hikes possible; new Chair Kevin Warsh; YE PCE seen 3.6%), keeping `fed_policy_risk` ELEVATED. Domestically, a **correction worth flagging: the live BOT policy rate is already 1.00%** (cut Feb 2026, held Apr 2026) — the watchlist had been implying 1.25%.

### Thai Holdings Update
- **BAFS**: No company news; cheaper jet fuel (~$80 Brent) a mild margin positive; demand stable. H1 est. ~Aug 14.
- **PTTEP**: ~134.0 THB. Brent ~$80, premium unwound — earnings-growth headwind, not solvency (breakeven ~$45, dividend safe). Dip with yield >4.5% = medium-term add zone. H1 est. ~Aug 11.
- **SCB**: ~141.0 THB; still the clearest higher-for-longer-US-Fed beneficiary (~7.5% yield), but BOT at 1.00% trims NIM. Earnings Jul 17 (alert Jul 14).
- **Gold Fund (SCBGOLDE)**: gold ~$4,155, USD/THB ~32.82 → est. NAV ~4.24 THB/unit. `gold_drawdown_monitor` → fed_driven_dip (≈ −7.7%) → hold/add.

### Technology Sector Highlight
Philadelphia Semiconductor Index **+61% QTD** vs S&P +13% — leadership intact despite the early-June Broadcom-driven air-pocket (Nasdaq −4.18% Jun 5, since recovered). **Marvell (MRVL) joins the S&P 500 today (Jun 22)** — a passive-buying event. Japan: Nikkei off its record (~66,588, −1.31%) as US tech weakness spread; BOJ at 1%. India: Nifty soft on the Accenture IT read-through; lower oil + RBI-cut hopes are medium-term tailwinds. HK/China weak on soft data.

### Improvements Implemented Tonight
1. **`ai_engine/risk_scorer.py`** *(enhanced — resolves the long-standing queued #1)* — Added **`archive_daily_snapshot()`**, a standalone nightly snapshot writer that fills `data/snapshots/YYYY-MM-DD.json` **without the Postgres path**. Previously the archive step sat *after* the `db_pool` + `portfolio_performance` UPSERT inside `save_daily_performance()`, so when the DB was down the archive line never ran — which is why `data/snapshots/` stayed empty and `derive_gold_trailing_high()` / the multi-day drawdown trend never went live. Extracted the archive payload into a shared **`_build_snapshot_archive_payload(snapshot, risk)`** helper (used by both the DB path and the new standalone function — no duplicated dict), and added a `__main__` entrypoint (`python -m ai_engine.risk_scorer`, `--with-db` for the full path). Seeded `data/snapshots/2026-06-21.json` so the archive is no longer empty.
2. **`portfolio_engine/fund_nav_tracker.py`** *(fixed — resolves queued SCBGOLDHE item)* — `estimate_nav_from_gold()` previously *accepted but ignored* the `hedged` flag, so SCBGOLDHE/SCBGOLDH NAVs were computed identically to the unhedged SCBGOLDE and spuriously floated with USD/THB. It now applies a **fixed hedge reference rate** (param `hedge_ref_rate` → env `GOLD_HEDGE_REF_RATE` → default 32.5) for hedged funds, so the hedged NAV **isolates the gold move** — the correct convention. `run_nightly_nav_snapshot()` now passes the ref rate and records it (not the floating rate) in the hedged funds' audit trail.
3. **`data/market_intel/2026-06-22.md`** *(new file)* — 7-section nightly report: gold's slide + the GS target cut (headline), SET + the BOT 1.00% correction, gold/currency, oil + Iran, US tech (SOX +61%, MRVL→S&P 500, Fed), regional, macro table + risk flags, sourced.
4. **`data/watchlist.json`** *(reconciled)* — `last_updated`→2026-06-22, USD/THB 32.52→32.82, gold spot $4,155, **GS gold target cut 5400→4900** (JPM 6,150), SCBGOLDE NAV est 4.24, SET 1,585.06, **BOT rate correction (live = 1.00%, not 1.25%)**, SOX +61% QTD, MRVL S&P 500 inclusion, and markers for tonight's snapshot-writer and hedged-NAV fixes.

### Verification
`ast.parse` clean on both modules. Hedged-vs-unhedged NAV unit-tested: unhedged moves with USD/THB (4341.46 @32.50 → 4401.57 @32.95), **hedged is FX-insensitive** (4341.46 at both). `_build_snapshot_archive_payload` checked for key coverage + null-safety on missing risk sub-dicts. The real **`save_daily_snapshot()` confirmed to write a dated archive file** (`2026-06-21.json`) end-to-end. `json.load` clean on `watchlist.json` (126 macro keys) and the snapshot seed. The project's own venv is macOS-linked so a full in-sandbox `archive_daily_snapshot()` run (which needs the cross-package import + DB) couldn't execute here — the import line is unchanged from the pre-existing DB path, so it carries no new risk; confirm on the next live nightly run.

### Next Priority (for next run)
**Confirm the scheduler invokes the new DB-free writer** — wire `python -m ai_engine.risk_scorer` (or a direct `archive_daily_snapshot()` call) into the nightly cron so `data/snapshots/` accumulates daily and `derive_gold_trailing_high()` self-updates. Once ≥2 real snapshots exist, verify the rolling trailing-high reads correctly and consider retiring the static `gold_recent_high_usd`. Watch for a **rescheduled US-Iran technical round** (adjust the `oil_scenario` collapse tail), and **propagate the corrected BOT rate (1.00%)** into any SCB NIM assumptions in `earnings_tracker`/`brief_generator`.

---

## Nightly Run — 2026-06-21 02:30 ICT

### Market Intelligence Summary
The week ended with two threads still dominant. **Gold closed ~$4,140** (Fri Jun 19), ~8% off the early-June ~$4,500 swing high, as the signed US-Iran ceasefire unwound the safe-haven bid and the **USD held a one-year high** post the hawkish Fed — a Fed/USD repricing, not a demand break (month-end est. ~$4,516; LBMA 2026 avg $4,742; GS $5,400 / JPM $6,000 intact). On **Iran**, the **interim deal was FORMALLY signed Jun 17** (60-day MOU), but the **Jun 19 first technical round in Switzerland was POSTPONED** (now Pakistan-mediated, no reschedule confirmed) with **440.9 kg of 60% HEU unresolved** — an execution snag, not a breakdown: Hormuz stayed open and **Brent held ~$80**. New domestic signal: **72.7% of analysts now expect the Bank of Thailand to cut to 1.00% by year-end** (from 1.25%) — a mild NIM headwind for SCB but supportive for the broader SET.

### Thai Holdings Update
- **BAFS**: No company news; cheaper jet fuel (~$80 Brent) a mild margin positive; aviation demand stable. H1 est. Aug 14.
- **PTTEP**: 134.50 THB (Jun 18). Brent ~$80 — premium fully unwound; earnings-growth headwind, not solvency (breakeven ~$45, dividend safe). Probability-weighted Brent ~$82. H1 est. Aug 11.
- **SCB**: Still the clearest beneficiary of a higher-for-longer Fed, but a domestic **BOT cut to 1.00%** (72.7% odds) would trim NIM — net constructive. **Earnings Jul 17** (alert Jul 14).
- **Gold Fund (SCBGOLDE)**: gold ~$4,140, USD/THB ~32.95 → est. NAV **~4.24 THB/unit** (baht weakness cushions the drop). `gold_drawdown_monitor` → `fed_driven_dip` (−8.0%) → hold/add.

### Technology Sector Highlight
Early-June **Nasdaq −4.18%** (worst day since Apr-2025) on Broadcom's soft AI-chip guide; **NVDA resilient** — CFO Kress (BofA conf.) says TAM can double, BofA reiterates Buy ($350 PT). **Intel–Apple US chip-design partnership** (Jun 18) lifted Intel/Micron; breadth narrow. **Japan**: BOJ hiked to 1%, **Nikkei record >70,000, +32% YTD**. **India**: Nifty near 24,000 on lower oil + RBI-cut hopes, but IT names soft (Accenture read-through). **China/HK**: Hang Seng −1.59% on weak data.

### Improvements Implemented Tonight
1. **`portfolio_engine/oil_scenario.py`** *(enhanced — last run's queued #1)* — Re-ranked the Brent scenarios to the post-Jun-17 reality: **deal_collapses tail bumped 7→9%** on the postponed Jun-19 Swiss talks (now Pakistan-mediated, no reschedule) + the unresolved 440.9 kg of 60% HEU; deal_signed 60→61, deal_partial 25→23, status_quo 8→7 (sum=100). Updated narratives to cite the **formal Jun-17 signing** and the **EIA ~$105-if-Hormuz-recloses** anchor for the collapse case. Resolves last run's "watch for a rescheduled talks date": talks postponed, deal intact, tail modestly fatter.
2. **`ai_engine/risk_scorer.py`** *(enhanced — last run's queued #2)* — Added **`derive_gold_trailing_high(window_days=60)`**: reads a rolling N-day max of `gold_drawdown_current_level` from `data/snapshots/*.json` and the gold-drawdown read now uses **`max(static_watchlist_high, derived_high)`**, so the drawdown trailing-high **self-updates** as snapshots accumulate and never regresses below a known peak. Safe on an empty archive (returns `None` → falls back to the static `gold_recent_high_usd`). Also archived **`gold_drawdown_current_level`** into the snapshot payload so the rolling max has data to read going forward. Window is env-overridable (`GOLD_TRAILING_WINDOW_DAYS`).
3. **`data/market_intel/2026-06-21.md`** *(new file)* — 7-section nightly report: gold's Fed-driven slide (headline), SET + new BOT easing-path signal, gold/currency, oil + the postponed Jun-19 Iran talks, US tech (Nasdaq/NVDA/Intel-Apple), regional (Japan record / HK weak / India), macro table + 6 risk flags, sourced.
4. **`data/watchlist.json`** *(reconciled)* — `last_updated`→2026-06-21. Added BOT rate (1.25%) + outlook, SET 1,587.07, PTTEP 134.50, USD/THB 32.95 (+1-yr high 32.97 Jun-10), Brent $80, Iran status (signed Jun-17 / Swiss talks postponed / Pakistan-mediated / HEU unresolved), EIA $105 contingency, and markers for the oil-tail and gold-trailing-high auto-derive changes.

### Verification
`ast.parse` clean on both modules. oil_scenario probabilities re-extracted: [61, 23, 7, 9] → **sum 100**. `derive_gold_trailing_high` logic tested in isolation: **empty archive → None**; seeded with {4360, 4140} + a malformed file → **4360.0** (rolling max correct, non-dated/bad files filtered). `json.load` clean on `watchlist.json` (113 macro keys). News cross-checked ≥2 outlets (Iran postponement: PBS/CBS/Axios; gold: GoldSilver/LiteFinance/LBMA; oil: EIA/JPM/TradingEconomics; SET & BOT: Kaohoon).

### Next Priority (for next run)
**Wire the nightly snapshot write so `data/snapshots/` actually fills** — `derive_gold_trailing_high()` and the multi-day drawdown trend only become live once `save_daily_performance()` runs nightly and archives `gold_drawdown_current_level`; the archive is still empty, so confirm the scheduler calls it (or add a lightweight standalone snapshot writer that doesn't require the Postgres path). Then: **seed SCBGOLDHE into `fund_nav_tracker.py`** so the hedged NAV can be tracked alongside the unhedged one (carried over, still pending). Watch for a **rescheduled US-Iran technical round** — if the 60-day window stalls further, bump the `deal_collapses` tail again; if talks resume cleanly, downgrade it.

---

## Nightly Run — 2026-06-20 02:30 ICT

### Market Intelligence Summary
Two threads converged Jun 19. **Gold fell a second straight session to ~$4,140** (−~2%) as the signed interim US-Iran ceasefire unwound the safe-haven bid and the **dollar hit a one-year high** post the hawkish Fed — ~5% off the $4,360 Jun-17 level and ~8% off the early-June ~$4,500 swing high. It is a **Fed/USD-driven repricing, not a demand break** (GS $5,400 / JPM ~$6,300 targets intact). Separately, the **Jun-19 first round of follow-up US-Iran technical talks at Bürgenstock was POSTPONED at short notice** (White House cited logistics; VP Vance postponed travel) — an early snag, NOT a breakdown: the interim deal/ceasefire hold and **Brent only ticked +0.9% to ~$80.6**. US markets were closed (Juneteenth). SET closed 1,585.06 (−0.13%); USD/THB weakened to ~32.93.

### Thai Holdings Update
- **BAFS**: No company news; cheaper jet fuel (~$80 Brent) a mild margin positive; aviation demand stable. H1 est. Aug 14.
- **PTTEP**: Brent ~$80 — premium fully unwound; earnings-growth headwind, **not** a solvency risk (breakeven ~$45, dividend safe). `oil_scenario_risk_flag` LOW; weighted view ≈ Brent $83, NI ~−11% vs base, yield ~4.5%. Dip with yield >4.5% = medium-term add zone. H1 est. Aug 11.
- **SCB**: ~142.5 THB; the clearest beneficiary of a higher-for-longer Fed at ~7.5% yield. **Earnings Jul 17** (27 days; alert Jul 14).
- **Gold Fund (SCBGOLDE)**: gold ~$4,140, USD/THB ~32.93 → est. NAV down to **~4.24 THB/unit** (baht weakness cushions part of the gold drop). New `gold_drawdown_monitor` classifies it **fed_driven_dip (−8.0%) → hold/add**, not a trend break.

### Technology Sector Highlight
US closed Jun 19 (Juneteenth). Last session Jun 18: **Nasdaq +1.91%, S&P +1.08%** led by chips on a reported **Intel–Apple US chip-design partnership** (Intel +10.6%, Micron ~+9%, NVDA ~+3%). Breadth narrow; IT-services weakness (Accenture −14.3%) a sentiment read-through for India IT (Infosys, Wipro). Japan: weak yen (~160) supportive, carry risk LOW. India: oil-import tailwind fully live with Brent ~$80.

### Improvements Implemented Tonight
1. **`ai_engine/risk_scorer.py`** *(enhanced — last run's queued #1)* — Added **`gold_drawdown_monitor(current_level, trailing_high, fed_policy_risk=...)`**: measures the gold/gold-fund drawdown from a trailing high and cross-references the live `fed_policy_risk_flag` to label it — `stable` / `fed_driven_dip` (hold-or-add) / `demand_softness_watch` / `deep_fed_dip` (hold-review) / `trend_break_watch` (reduce-review). Thresholds: dip 5%, break 12% (env-overridable). Unit-free, so works on NAV (THB) or gold spot (USD). Wired into `calculate_portfolio_risk()` (reads NAV or gold spot + recent-high from the watchlist, surfaces top-level `gold_drawdown`) and into the snapshot archive (`gold_drawdown_classification` / `_pct` / `_signal`) for multi-day trend tracking. Diagnostic only — the blended score is unchanged. *Note: last run's queued #3 (fed_policy_risk in the snapshot archive) was already present from the Jun-18 wiring — verified, no change needed.*
2. **`portfolio_engine/brief_generator.py`** *(enhanced)* — Added `_load_gold_drawdown()` (dual import path), computed it from the watchlist gold NAV/spot + recent high + the Fed flag, injected `gold_drawdown_flag` into the LLM context, and updated the Section 2 prompt so the brief now states the dip's classification + drawdown_pct + action signal (e.g. "gold drawdown: fed_driven_dip, −8.0% off the high → hold/add") — making the hold-vs-review call explicit instead of leaving it to the LLM.
3. **`data/market_intel/2026-06-20.md`** *(new file)* — 7-section nightly report: gold's deepening Fed-driven slide (headline), SET/holdings, oil + the postponed Jun-19 Iran talks, US tech (Juneteenth close, Intel–Apple), regional, macro table, 6 risk flags, sourced.
4. **`data/watchlist.json`** *(reconciled)* — `last_updated`→2026-06-20. Iran status flag → `interim_signed…; jun19_swiss_talks_postponed_logistical; ceasefire_intact` (resolves last run's "confirm the Jun-19 signing" query: talks postponed, deal intact, not a breakdown). Prices: gold $4,250→$4,140, SCBGOLDE NAV 4.30→4.24, USD/THB 32.52→32.93, Brent ~$80.6, SET Jun-19 1,585.06. Added `gold_recent_high_usd` ($4,500) as the drawdown trailing-high reference, US-Juneteenth-close note, and the module marker.

### Verification
`ast.parse` clean on both modules. `gold_drawdown_monitor` tested across cases: today (4140 from 4500, fed elevated 0.5875) → **fed_driven_dip, −8.0%, hold_or_add**; 2.2% dip → stable; 13.3% + fed → deep_fed_dip; 13.3% no-fed → trend_break_watch; 8% no-fed → demand_softness_watch; trailing_high=0 → safe 0.0/stable. `fed_policy_risk_flag(3.625, hawkish)` → elevated 0.5875 (unchanged). `json.load` clean on `watchlist.json` (102 macro keys). News cross-checked ≥2 outlets (Iran postponement: CNBC + Washington Times; gold: HDFC Sky + GoldSilver; oil: TradingEconomics; SET: KAOHOON).

### Next Priority (for next run)
**Watch for a rescheduled US-Iran talks date** — if the 60-day window stalls further, bump the `deal_collapses` tail in `oil_scenario.py` and flag an oil re-spike scenario; if talks resume cleanly, downgrade the tail. Then: **auto-derive the gold trailing-high** — once `data/snapshots/` accumulates daily NAV points, replace the static `gold_recent_high_usd` watchlist field with a rolling N-day max read from the snapshot archive so `gold_drawdown_monitor` self-updates. Lower priority: seed SCBGOLDHE into `fund_nav_tracker.py` so the hedged NAV can be tracked alongside the unhedged one.

---

## Nightly Run — 2026-06-19 02:30 ICT

### Market Intelligence Summary
The hawkish dot-plot from Wednesday's FOMC finally bit: **gold fell ~2.5% to ~$4,250 on Jun 18** (from ~$4,360) — a textbook real-yield reaction once the "no 2026 cuts, possibly two hikes" message sank in, and the exact headwind `fed_policy_risk_flag` (ELEVATED 0.59) was built to score. It is a **Fed-driven pullback, not a demand break** — GS $5,400 / JPM ~$6,000 medium-term gold targets are intact. In contrast, **US tech rebounded hard** (Nasdaq +1.5%, S&P +1.15%) led by chips, on a reported **Intel–Apple US chip-design partnership** (Intel +9.8%; MU +4.8%, AMD +3.9%, AVGO +3%, SOXX +4.6%). Oil stayed soft (**Brent ~$78**, fresh 3-month low) and the **US-Iran deal goes to its formal signing at the Bürgenstock resort (Lake Lucerne) today, Jun 19** (ceremonial; e-signing already done Jun 15). USD/THB range-bound ~32.52; SET closed 1,587.07 (-0.06%, light THB 63.78bn turnover).

### Thai Holdings Update
- **BAFS**: No company news; cheaper jet fuel (~$78 Brent) a mild margin positive; aviation demand stable. H1 est. Aug 14.
- **PTTEP**: Brent ~$77–80 — premium fully unwound; earnings-growth headwind, **not a solvency risk** (breakeven ~$45, dividend safe). `oil_scenario_risk_flag` LOW; probability-weighted view ≈ Brent $83, NI ~−11% vs base, yield ~4.5%. Dip with yield >4.5% = medium-term add zone. H1 est. Aug 11.
- **SCB**: ~142.5 THB; the clearest beneficiary of a higher-for-longer Fed at ~7.5% yield. **Earnings Jul 17** (28 days; alert Jul 14).
- **Gold Fund (SCBGOLDE)**: gold ~$4,250, USD/THB ~32.52 → est. NAV down ~2.3% to **~4.30 THB/unit** on the Fed-driven gold drop. Targets intact; higher-for-longer is the near-term swing factor.

### Technology Sector Highlight
US tech rallied Jun 18 (Nasdaq +1.5%) led by a fresh **Intel–Apple US chip-design partnership** — a second OEM/cloud diversification signal after the Alphabet deal, reinforcing the US on-shoring chip theme. Breadth was narrow (Russell 2000 −0.72%), and **IT-services lagged sharply (Accenture −14.3%, Cognizant −6.6%)** — a sentiment read-through to watch for India IT peers (Infosys, Wipro). Japan: weak yen (USD/JPY ~160) still supportive for exporters; carry risk LOW. India: Brent ~$78 keeps the oil-import tailwind fully live.

### Improvements Implemented Tonight
1. **`portfolio_engine/brief_generator.py`** *(enhanced)* — Completed last run's queued priority: wired both Jun-18 risk functions into the daily brief. Added `_load_fed_policy_risk()` helper (dual import path) that calls `risk_scorer.fed_policy_risk_flag()` from the watchlist's realised funds rate + dot-plot bias; imported and called `oil_scenario.probability_weighted_outlook()`. Both injected into the LLM context as `fed_policy_risk_flag` and `pttep_oil_weighted_outlook`. Prompt updated: Section 1 now states the single probability-weighted oil expectation alongside the scenario table; Section 2 now states the Fed-policy headwind on gold/baht (risk_level + score) and connects it to gold-fund NAV.
2. **`data/market_intel/2026-06-19.md`** *(new file)* — 7-section nightly intelligence: gold's Fed hangover (headline), SET/holdings, oil + Bürgenstock signing, US tech (Intel–Apple, Accenture drop), regional, macro table, 6 risk flags, sourced.
3. **`data/watchlist.json`** *(updated)* — Gold $4,360→$4,250 (-2.5% Fed hangover), SCBGOLDE NAV 4.42→4.30, USD/THB 32.52, Brent $78, SET 1,587.07, Hang Seng 24,494, Intel–Apple deal + Accenture drop noted, Jun 18/19 catalysts added, macro_context refreshed, brief-integration flag recorded.

### Next Priority (for next run)
**Confirm the Jun 19 Bürgenstock signing actually occurred** and set the Iran deal status to fully closed (or flag a breakdown → oil re-spike scenario). Then: **gold drawdown monitor** — add a `risk_scorer` helper that flags when the gold-fund NAV draws down >X% from a trailing high while `fed_policy_risk_flag` is ELEVATED, so the brief distinguishes a Fed-driven dip (hold/add) from a trend break. Also consider surfacing `fed_policy_risk_flag` into the snapshot archive trend (like the oil/Japan flags) for multi-day tracking.

---

## Nightly Run — 2026-06-18 02:30 ICT

### Market Intelligence Summary
The night's pending event resolved near the central case: the **FOMC held at 3.50–3.75% (3.625% mid), 12-0**, in Kevin Warsh's debut — but the **dot-plot came out hawkish** (9 of 18 dots a hike before end-2026, 6 of those two hikes; easing bias gone), and the SEP lifted year-end PCE to 3.6%, trimmed 2026 GDP to 2.2%. So **higher-for-longer is confirmed** — a real-yield headwind for gold and the baht — though **partly self-offsetting** because the same week's oil collapse eases the inflation impulse the dots are reacting to. Oil: **Brent fell to a 3-month low ~$79–80** after four down sessions, the Iran premium fully unwound into the deal-signed band (deal virtually signed Jun 15; Hormuz reopened; ceremonial signing Jun 19). Gold held firm ~$4,360 through the hawkish Fed; USD/THB range-bound ~32.55; SET consolidating ~1,588.

### Thai Holdings Update
- **BAFS**: No company news; cheaper jet fuel (~$80 Brent) a mild margin positive; aviation demand stable. H1 est. Aug 14.
- **PTTEP**: Brent ~$79–80 — premium fully unwound; the earnings-growth headwind has **largely played out, not a solvency risk** (breakeven ~$45, dividend safe). `oil_scenario_risk_flag` LOW. Dip with yield >4.5% = medium-term add zone. H1 est. Aug 11.
- **SCB**: ~142.5 THB; held the relief rally. **Earnings Jul 17** (29 days; alert Jul 14). ~7.5% yield — the clearest beneficiary of a higher-for-longer Fed among the holdings.
- **Gold Fund (SCBGOLDE)**: Gold ~$4,360 (held firm on its own safe-haven bid despite the hawkish dots). USD/THB ~32.55 → est. NAV ~4.42 THB/unit. GS $5,400 / JPM ~$6,000 intact; hawkish Fed = near-term swing factor.

### Technology Sector Highlight
US tech still consolidating post the Jun 5 semi shock; the structural concentration risk (~10 AI names ≈ ~40% of S&P 500 value, ~half of 2026 earnings growth) is unchanged and a hawkish Fed pressures high-multiple names at the margin, but $750bn hyperscaler capex and TSMC's ~73% foundry share anchor the cycle. Japan: weak yen (~160) supportive for exporters post-hike. India: oil-import tailwind now fully live with Brent ~$80. Vietnam's FTSE EM upgrade (Sep 21) remains the standout medium-term EM catalyst.

### Improvements Implemented Tonight
1. **`ai_engine/risk_scorer.py`** *(enhanced — last run's queued FOMC priority)* — Added **`fed_policy_risk_flag(fed_funds_rate_pct, dot_plot_bias)`**: scores the headwind US policy poses to gold + the baht book from two components — rate level above a ~3.0% neutral anchor (0–0.6) and the dot-plot bias (hawkish +0.40 / dovish −0.20). Wired into `calculate_portfolio_risk()` (reads `us_fed_funds_rate_pct` + `fomc_jun17_dot_plot_bias` from the watchlist, surfaces top-level `fed_policy_risk`) and into the snapshot archive (`fed_policy_risk_level`/`_score`). Realised state (3.625% + hawkish) → **ELEVATED (0.59)**. Additive; the blended score is unchanged.
2. **`portfolio_engine/oil_scenario.py`** *(recalibrated — last run's queued priority)* — Re-ranked the Brent scenarios by **realised probability** now that the deal is signed and Brent sits in the deal-signed band: `deal_signed_hormuz_open` re-anchored to $79 and marked REALISED (60%), `deal_partial` 25%, `status_quo` downgraded to 8%, `deal_collapses` downweighted to 7%; narratives rewritten to past-tense fact. Added **`probability_weighted_outlook()`** (probability-weighted expected Brent ~$83 / NI ~−11% vs base / yield ~4.5%), surfaced it in `run_oil_scenario_report()` as `weighted_outlook`, and moved the report's default current Brent from 87.5 → 80.
3. **`portfolio_engine/fee_analyzer.py`** *(enhanced — last run's queued lower-priority)* — Added **`compare_hedged_vs_unhedged_gold()`**: quantifies SCBGOLDE (unhedged) vs SCBGOLDHE (THB-hedged) — the ~0.15% p.a. hedge premium vs the FX P&L the hedge neutralises, given a USD/THB view. With USD/THB range-bound ~32.5 the verdict is **unhedged = lower-cost default**; hedging only pays if a stronger-baht view develops. FX math verified across flat/strong/weak baht cases.
4. **`data/watchlist.json`** *(reconciled)* — `last_updated`→2026-06-18, USD/THB→32.55. FOMC: replaced `fomc_jun17_status` with realised `fomc_jun17_result` (hold 3.625%, 12-0, hawkish 9/18 dots, PCE 3.6%) + `fomc_jun17_dot_plot_bias`. Prices: Brent ~$79.5, WTI ~$76, gold ~$4,360, SET Jun 16 ~1,588, SCBGOLDE NAV ~4.42. Catalysts: `2026-06-17_18` → COMPLETED with the realised FOMC; `2026-06-19` marked ceremonial. Added three module markers (fed flag / oil re-rank / hedged-compare).
5. **`data/market_intel/2026-06-18.md`** *(new file)* — 7-section reconciliation report led by the hawkish-hold FOMC, with per-market sections, a macro table, six risk flags, and sourced links.

### Verification
`ast.parse` clean on all three modules. Functional tests (deps stubbed for the sandbox): `probability_weighted_outlook()` weights sum to 100, expected Brent ~$82.8, NI ~−10.9%; scenario probabilities {signed 60, partial 25, status_quo 8, collapse 7}; `run_oil_scenario_report()` default Brent 80 and carries `weighted_outlook`. `compare_hedged_vs_unhedged_gold(500k,12m)`: FX-flat net advantage −750 THB (= the hedge premium exactly), baht −3% → +14,250 THB (avoided loss − premium), baht +3% → −15,750 THB (forfeited gain + premium) — all correct. `fed_policy_risk_flag`: (3.625, hawkish)→elevated 0.5875; (3.625, neutral)→low 0.1875; (3.625, dovish)→low 0.0; (3.0, hawkish)→elevated 0.40. `json.load` clean on `watchlist.json`. News cross-checked ≥2 outlets per event (FOMC: Fox Business + REX Shares; oil/Iran: CNBC + CNN + Fortune; gold: CNBC Select + TradingEconomics).

### Next Priority (for next run)
**Confirm the Jun 19 in-person Iran ceremony** occurred and, if so, mark the catalyst fully closed and downgrade the `deal_collapses` tail further. **Wire `fed_policy_risk` and the oil `weighted_outlook` into `brief_generator.py`** so the morning brief states the Fed headwind score and the probability-weighted oil number as facts (parallel to the catalyst/oil-risk integrations already done). Lower priority: with USD/THB range-bound, **add a small baht-trend signal** (e.g. 20-day USD/THB drift from the snapshot archive) to feed `compare_hedged_vs_unhedged_gold()`'s `expected_usd_thb_move_pct` automatically, and seed SCBGOLDHE into `fund_nav_tracker.py` so the hedged NAV can be tracked alongside the unhedged one.

---

## Nightly Run — 2026-06-17 02:30 ICT

### Market Intelligence Summary
Post-event reconciliation: two of the three pending event risks resolved overnight, both near the central case. The **BOJ hiked 25bp to 1.00%** (Jun 16, 7-1 vote, Asada dissent) — highest since 1995, as expected — but the feared **carry-unwind did NOT happen**: the yen stayed weak (USD/JPY held ~160), so `japan_policy_risk_flag()` now reads **LOW**. The **US-Iran deal was virtually signed Jun 15** by Trump + VP Vance at the G7 (earlier than the Jun 19 ceremony), reopening the Strait of Hormuz; **Brent fell to ~$81**, its steepest one-day drop in months, so PTTEP's premium has largely unwound into the modelled $72-80 deal-signed band. **FOMC is still pending** (decision ~01:00 ICT Jun 18). Correction to last night's estimate: the SET did NOT reverse to ~1,552 — the **official Jun 15 close was 1,591.72 (-0.04%)**, i.e. the relief rally held near 1,592.

### Thai Holdings Update
- **BAFS**: No company news; lower jet fuel (~$81 Brent) a mild margin positive; aviation demand stable. H1 results est. Aug 14.
- **PTTEP**: Brent ~$81, premium unwound — earnings-growth headwind now realised, not solvency (breakeven ~$45, dividend safe). `oil_scenario_risk_flag()` is now LOWER (Brent near the floor → less premium left to give back). A dip with yield >4.5% is a medium-term add zone. H1 est. Aug 11.
- **SCB**: ~142.5 THB; held the banking-led relief rally. Earnings Jul 17 (30 days; alert Jul 14); consensus seeded. ~7.5% yield.
- **Gold Fund (SCBGOLDE)**: Gold ~$4,350 (+~0.7%), held firm through the hike (own safe-haven bid, not yen-driven). USD/THB ~32.50 → est. NAV ~flat at ~4.40 THB/unit. GS $5,400 / JPM ~$6,000 intact.

### Technology Sector Highlight
US tech still consolidating after the Jun 5 semi shock (~$1T intraday) and partial rebound. Structural flag unchanged: ~10 AI names ≈ ~40% of S&P 500 value and ~half of 2026 expected earnings growth — index hostage to a single semi stumble. $750bn hyperscaler AI capex and TSMC's ~73% foundry share anchor the cycle. Japan: weak yen (~160) supportive for exporters post-hike. India IT soft but the oil-import tailwind is now fully live with Brent ~$81. Vietnam's FTSE EM upgrade (Sep 21) remains the standout medium-term EM catalyst.

### Improvements Implemented Tonight
1. **`portfolio_engine/brief_generator.py`** *(enhanced — last run's queued #1)* — Wired the **PTTEP position-level oil risk score** into the brief. Added `_load_oil_position_risk()` (dual-path import of `risk_scorer.oil_scenario_risk_flag`, graceful `{}` fallback), computed it in `generate_daily_brief()` from the watchlist Brent + `us_iran_status_flag`, injected it as `pttep_oil_risk_flag`, and updated the Section 1 prompt so the brief now states PTTEP's oil `risk_level` + `position_risk_score` alongside the scenario narrative (e.g. "oil risk: low (0.05)") rather than the scenario table alone.
2. **`ai_engine/risk_scorer.py`** *(enhanced — last run's queued #2)* — In `save_daily_performance()`, the daily snapshot archive payload now also carries `oil_commodity_risk` (PTTEP `position_risk_score`), `oil_commodity_risk_level`, and `japan_carry_risk_level`, so the snapshot trend loaders can chart these diagnostics over time alongside the blended score. Purely additive.
3. **`data/watchlist.json`** *(reconciled)* — `last_updated`→2026-06-17. BOJ: `boj_policy_rate_pct`→**1.00**, rewrote outlook→**realised result** (7-1 vote, USD/JPY ~160, no carry-unwind). Iran: `us_iran_status_flag`→`signed_virtual_2026-06-15_hormuz_reopened`, rewrote `us_iran_situation`/PTTEP/Brent notes (signed Jun 15, Hormuz open). Prices: Brent ~$81 (-4.1%), WTI ~$78, gold ~$4,350, USD/THB 32.50, **USD/JPY 160** (was ~152), SCBGOLDE NAV ~4.40. SET: corrected Jun 15 close to **1,591.72** (rally held, not the ~1,552 estimate). Added `fomc_jun17_status` + 4 new module/event markers. Catalyst calendar: Jun 15/16 marked COMPLETED, Jun 19 downgraded to ceremonial, FOMC moved to Jun 17-18.
4. **`data/market_intel/2026-06-17.md`** *(new file)* — 8-section reconciliation report: BOJ outcome, signed Iran deal + oil unwind, holdings, pending FOMC, regional/US-tech, gold/oil/FX table, six risk flags, sourced links.

### Verification
`ast.parse` clean on `brief_generator.py` and `risk_scorer.py`; `json.load` clean on `watchlist.json` (spot-checked BOJ 1.0 / Brent 81 / gold 4350 / USDTHB 32.5 / USDJPY 160 / iran flag). Logic check on the new oil-risk wiring: with Brent ~$81 just above the ~$75 deal-signed floor and `deal_confirmed=True`, `oil_scenario_risk_flag()` returns a small premium-unwind component (little premium left) and zero coverage-stress (well above the $60 stress floor) → **low** position risk, which correctly reflects that the oil downside has already played out rather than still looming. News reconciliation cross-checked against ≥2 outlets per event (BOJ: CNBC + investingLive; Iran: CNN + NBC; Brent: HDFC Sky + Fortune; SET: Kaohoon).

### Next Priority (for next run)
**FOMC reconciliation (Jun 17-18 window)**: set `us_fed_funds_rate_pct` to the realised outcome, capture whether the easing bias was removed and the dot-plot's 2026 bias (cuts vs hold vs hike), and update the gold/USD-THB read accordingly — a hawkish dot-plot is the main near-term gold/EM headwind. Also: **confirm the Jun 19 in-person Iran ceremony** occurred and mark the catalyst fully closed; and consider a small **`oil_scenario.py` recalibration** now that Brent is realised in the deal-signed band (re-rank scenarios by realised probability, downweighting the collapse/$105 case). Lower priority: add an **FX-hedged vs unhedged gold-fund comparison** (SCBGOLDE vs SCBGOLDHE) to `fee_analyzer.py` now that USD/THB is range-bound ~32.5.

---

## Nightly Run — 2026-06-16 02:30 ICT

### Market Intelligence Summary
The weekend's slipped catalyst firmed up: the **US-Iran framework deal is CONFIRMED** (14-point MoU — ends the war incl. Lebanon, reopens the Strait of Hormuz, lifts oil + some financial sanctions, unfreezes ~$24bn over a 60-day window), with a **formal signing ceremony scheduled Friday Jun 19 in Switzerland** and Hormuz reopening on signing. Brent has eased to **~$84–85, the lowest since early March**, so PTTEP's earnings-growth headwind is now live (still not a solvency risk — breakeven ~$45). Two central-bank decisions land in the next 48h: **BOJ today (Jun 16)**, a near-certain 25bp hike to 1.0% (highest since 1995), and **FOMC Jun 17**, a ~99% hold where the dot-plot is the real signal. Note: gold **rallied to ~$4,340 (+2.77%) Jun 15** despite the risk-on backdrop, and the **SET reversed to ~1,552** from its 1,592 Friday close as the market de-risked.

### Thai Holdings Update
- **BAFS**: No company news; aviation demand stable. Lower oil a mild fuel-cost positive. H1 results est. Aug 14.
- **PTTEP**: Deal confirmed → Brent ~$84–85 heading toward the $72–80 deal-signed band. Dividend holds even at $75 (breakeven ~$45). Earnings-growth headwind, not solvency; a deal-driven dip with yield >4.5% is a potential medium-term add zone. H1 results est. Aug 11.
- **SCB**: Gave back some of the banking-led relief rally in Monday's SET reversal. Earnings Jul 17 (31 days; alert Jul 14); consensus preview seeded. ~7.5% yield.
- **Gold Fund (SCBGOLDE)**: Gold ~$4,340 (+2.77%); USD/THB 32.56 → est. NAV up ~+2.3% to ~4.41 THB/unit. BOJ hike + yen strength could extend gold support. GS $5,400 / JPM ~$6,000 intact.

### Technology Sector Highlight
US AI concentration remains the structural risk — ~10 names ≈ ~40% of S&P 500 value and about half of 2026 expected earnings growth — so the Jun 5 semi shock (~$1T intraday) shows the fragility even amid a partial rebound (Micron, NVDA ~$207–215). TSMC anchors the cycle (~73% foundry share, FY guided >30%); $750bn hyperscaler AI capex intact. Regional reads: Japan semis pivot on the BOJ pace signal; India IT soft but the oil-import tailwind is now live; Vietnam's FTSE EM upgrade (Sep 21) is the standout medium-term EM catalyst.

### Improvements Implemented Tonight
1. **`portfolio_engine/brief_generator.py`** *(enhanced)* — Wired `catalyst_monitor.catalyst_alert_summary()` into the brief (last run's queued #1 priority). Added the import, computed the summary (graceful fallback), injected `catalyst_alerts` into the LLM context, and updated the prompt so every brief now OPENS with a **⚠️ Catalyst Watch** header listing slipped (needs-verification) and ≤5-day imminent catalysts as facts — instead of relying on the LLM to infer slippage from free-text notes.
2. **`ai_engine/risk_scorer.py`** *(enhanced)* — Added `oil_scenario_risk_flag(current_brent, pttep_weight, deal_confirmed)` (last run's carried-over priority) — a self-contained, dependency-light scorer of PTTEP's Brent downside with two components: **premium-unwind** (how far Brent sits above the ~$75 deal-signed floor, scaled up when the deal is confirmed) and **coverage-stress** (rises as Brent approaches the ~$45 breakeven). Wired into `calculate_portfolio_risk()`: reads current Brent + `us_iran_status_flag` from the watchlist, computes PTTEP's portfolio weight, surfaces a top-level `oil_commodity_risk` block and attaches the position score to PTTEP's per-holding record. Additive — the existing blended score formula is unchanged for backward compatibility.
3. **`data/market_intel/2026-06-16.md`** *(new file)* — 8-section nightly report led by the confirmed Iran deal + Jun 19 signing, with per-market sections (Thailand/SET reversal, US/Tech, BOJ today, FOMC tomorrow, Japan/China/India/Vietnam), a gold/oil/FX table, six risk flags, and sourced links.
4. **`data/watchlist.json`** *(updated)* — `last_updated`→2026-06-16; Iran status flag → `confirmed_framework_2026-06-14_signing_2026-06-19`; rewrote the Jun 14 catalyst to CONFIRMED and added a Jun 19 signing-ceremony entry; marked the Jun 15 SET-reversal note COMPLETED; refreshed Brent ~$84.5, gold ~$4,340, USD/THB 32.56, SCBGOLDE NAV ~4.41, SET latest reading ~1,552; corrected the BOJ note (Ueda's Jun-3 hawkish signal; hike lands today); fixed a pre-existing duplicate `nav_estimated_thb` key in SCBGOLDE; added the two new module markers.

### Verification
`ast.parse` clean on `brief_generator.py` and `risk_scorer.py`; `json.load` clean on `watchlist.json`. `oil_scenario_risk_flag` math spot-checked across Brent regimes ($84/$87.5/$105/$75/$58/$46) — premium-unwind and coverage-stress behave monotonically and cap at 1.0. `catalyst_monitor.catalyst_alert_summary(today=2026-06-16)` re-run against the updated calendar returns **slipped=0** (the Jun 14 deal now reads CONFIRMED; caught and fixed a false-positive where the word "slipped"/an unmarked status note tripped the schedule-override) and **imminent=3** (BOJ Jun 16, FOMC Jun 16-17, signing Jun 19) — exactly as intended.

### Next Priority (for next run)
**Post-event reconciliation (Jun 16–19 window)**: (a) set `boj_policy_rate_pct` to the realised BOJ outcome and re-run `japan_policy_risk_flag()` on the realised USD/JPY; (b) after FOMC Jun 17, update `us_fed_funds_rate_pct` and capture the dot-plot bias; (c) confirm the **Jun 19 signing ceremony** occurred and, if so, mark the catalyst CONFIRMED and refresh `oil_scenario.py` current Brent + re-rank scenarios by realised probability. Also: **wire `oil_scenario_risk_flag` output into the daily brief Section 1** (it already feeds risk_scorer) so Tho sees the position-level oil risk score alongside the scenario narrative, and **surface `oil_commodity_risk` in the portfolio snapshot archive** for trend tracking.

---

## Nightly Run — 2026-06-15 02:30 ICT

### Market Intelligence Summary
The headline correction tonight: the US-Iran peace deal that the calendar carried as "scheduled to be signed Sunday Jun 14" did **not** formally sign — Tehran disputed the timeline and is demanding any ceasefire also halt Israeli strikes in Lebanon; Qatari negotiators flew to Tehran Sunday to push closure. Consequence: the oil geopolitical premium has **not** unwound (Brent still ~$87, not the $72–80 "deal-signed" band), so PTTEP's earnings-growth headwind is **deferred, not realised**. BOJ is near-certain to hike 25bp to 1.0% on Jun 16 (highest in ~3 decades), and the FOMC (Jun 16–17) is a ~99% hold — both land tomorrow.

### Thai Holdings Update
- **BAFS**: No company news; aviation demand stable (14M+ arrivals). Rides the SET relief rally.
- **PTTEP**: Brent still ~$87 because the deal didn't sign — premium intact, a mild near-term positive vs last night. `oil_scenario.py` unchanged: dividend holds even at $75 (breakeven ~$45). Direction of risk unchanged.
- **SCB**: Closed 139.50 THB Jun 12 (+1.45%), led the banking relief rally. Earnings Jul 17 (32 days; alert Jul 14); consensus preview seeded. ~7.5% yield.
- **Gold Fund (SCBGOLDE)**: Gold ~$4,222–4,316; USD/THB ~32.7 → est. NAV ~4.31 THB/unit. Deal-unsigned = less safe-haven outflow than the deal-signed case; a BOJ hike + yen strength could re-support gold. GS $5,400 / JPM ~$6,000 targets intact.

### Technology Sector Highlight
US AI concentration is the standout risk: ~10 AI-linked names ≈ 40% of S&P 500 value and ~half of 2026 expected earnings growth. The Jun 5 semi wobble erased ~$1T in a day before a partial rebound (Micron +10%, NVDA ~$207 on LG deal). TSMC remains the anchor (foundry share ~73%, FY guided >30%). Alphabet's ~$80bn AI raise is a near-term share overhang. Japan semis (Advantest/Tokyo Electron) and India IT are the regional reads; Vietnam's FTSE EM upgrade (Sep 21) is the standout medium-term EM catalyst.

### Improvements Implemented Tonight
1. **`portfolio_engine/catalyst_monitor.py`** *(new file)* — Stdlib-only catalyst-slippage monitor. Parses the dated `catalysts` map in `watchlist.json`, classifies each into upcoming/today/overdue, and surfaces **"slipped"** entries (overdue + unconfirmed). Confirmation logic treats scheduling language ("SCHEDULED", "TO BE SIGNED", "EXPECTED", "EST.", "LIKELY", "PENDING") as overriding confirmation markers, so a calendar line like "deal SCHEDULED TO BE SIGNED" is *not* mistaken for a done deal. Verified live: correctly flags the Jun 14 Iran deal as slipped and the Jun 16 BOJ/FOMC as imminent. Exposes `classify_catalysts()`, `slipped_catalysts()`, `catalyst_alert_summary()` for the morning brief. Directly motivated by tonight's slippage.
2. **`portfolio_engine/performance_analytics.py`** *(bug fix)* — `load_snapshot_history()` caught `json.JSONDecodeError` but the module imports `json as _json`, so a corrupt snapshot file would have raised an unhandled `NameError` instead of being skipped with a warning. Changed to `_json.JSONDecodeError`. Protects the nightly snapshot-archive trend loader.
3. **`data/market_intel/2026-06-15.md`** *(new file)* — Full nightly report led by the Iran-deal slippage correction, with per-market sections (Thailand, US/Tech, BOJ, Japan/China/India/Vietnam), gold/oil/FX table, and five risk flags.
4. **`data/watchlist.json`** *(updated)* — `last_updated`→2026-06-15; rewrote the Jun 14 catalyst to "SLIPPED / NOT SIGNED" with the Lebanon sticking point; added Jun 15 Monday-open guidance; upgraded BOJ Jun 16 to "near-certain hike"; rewrote `macro_context.us_iran_situation` + added `us_iran_status_flag: slipped_unconfirmed_2026-06-14`; recorded the two new module markers. JSON re-validated.

### Verification
`ast.parse` clean on both new/edited Python files; `json.load` clean on watchlist.json; `catalyst_monitor.catalyst_alert_summary(today=2026-06-15)` run against live data returns slipped=1 (Iran Jun 14), imminent=2 (BOJ + FOMC Jun 16) as expected.

### Next Priority (for next run)
**Wire `catalyst_monitor.catalyst_alert_summary()` into `brief_generator.py`** so the morning brief opens with a "⚠️ Slipped/unconfirmed catalysts" line and a "📅 This week" line, instead of relying on the LLM to infer slippage from free-text notes. Also: **confirm the Iran signing outcome and the BOJ Jun 16 result first thing**, then update the catalyst calendar so the slippage flag clears.

---

## Nightly Run — 2026-06-14 02:30 ICT

### Market Intelligence Summary
The dominant event is the **US-Iran peace deal, scheduled to be signed today (Sunday June 14)** — Trump posted that the deal "is scheduled to get signed tomorrow" with the Strait of Hormuz "OPEN TO ALL" immediately after; Pakistan's PM (mediator) says a final text was reached and a US official cites ~80% odds. Terms: 60-day ceasefire extension, Hormuz reopening, naval blockade lifted, Iran forgoes enrichment 15–20 years, staggered sanctions relief. Brent settled $87.33 / WTI $84.88 (Jun 12, -3.4%); SET extended its rally to 1,592.41 (+1.28%, THB 67.4bn turnover); Nikkei +2.9% (66,078); Hang Seng +1.9% (ended a 7-session losing streak). **BOJ outlook revised back to hike-likely**: latest sell-side sees a 25bp move to 1.0% on Jun 15-16 as "highly probable," superseding last night's "uncertain" framing.

### Thai Holdings Update
- **BAFS**: No material news. Stable aviation demand; benefits indirectly from lower fuel costs and the SET rally. H1 results est. Aug 14.
- **PTTEP**: ⚠️ Direct exposure to the Iran deal. Brent $87.33 → likely $72–80 band if signed. New `oil_scenario.py` shows the dividend is maintained even at $75 (breakeven ~$45) — an earnings-growth headwind, not a solvency risk. LT thesis intact.
- **SCB**: Banking led the two-day SET rally; ~137.50 THB. Earnings Jul 17 (33 days). Consensus preview seeded tonight (net profit ~THB 23.5bn, NIM ~3.7%, NPL ~3.3%, interim div est ~THB 5.75).
- **Gold Fund (SCBGOLDE)**: Gold ~$4,222; USD/THB 32.72; est. NAV ~4.31 THB/unit. Risk-on is a short-term gold headwind; a BOJ hike (yen strength) could re-support. GS $5,400 / JPM $6,000 intact.

### Technology Sector Highlight
SpaceX (SPCX) closed +19% (~$161) on its Nasdaq debut. TSMC is the structural anchor — Q1-2026 record ~$35.6bn revenue, 73% foundry share, FY growth guided >30%. Broadcom's Jun 3 beat was overshadowed by soft Q3 AI-chip guidance (-14% Jun 4). FOMC Jun 16–17: ~99% hold at 3.5–3.75% (Warsh debut); futures lean toward 2026 hikes, not cuts. Nasdaq's ~7% pullback reads as healthy consolidation after the 20%+ rally off the March low.

### Improvements Implemented Tonight
1. **`portfolio_engine/oil_scenario.py`** *(new file)* — Brent-crude scenario analyzer for PTTEP. Transparent linear earnings-elasticity model (≈+1.5% net income per +$1 Brent around a $90 base, ~$45 breakeven). Functions: `pttep_sensitivity(brent)`, `dividend_capacity(brent)` (yield band with maintainable floor), `brent_scenarios()` (4 named Iran-deal scenarios: deal_signed_hormuz_open $75 / deal_partial $84 / status_quo $87.5 / deal_collapses $105, each with earnings + dividend impact), and `run_oil_scenario_report()` which builds a brief-injectable dict and persists to `data/oil_scenarios/YYYY-MM-DD.json`. Directly addresses the live PTTEP risk from the Iran deal signing today.
2. **`data/earnings/scb_h12026_preview.json`** *(new file)* — Consensus/estimate preview for SCB X H1-2026 (the queued "SCB earnings data model" priority). Includes net-profit range (~THB 23.5bn base), NIM (~3.7%), NPL (~3.3%), loan growth, cost/income, interim-dividend outlook (~THB 5.75 base), beat/inline/miss scenario reactions, and an advisory note for Tho. Created the `data/earnings/` directory (it did not exist on disk).
3. **`portfolio_engine/earnings_tracker.py`** *(enhanced)* — Added `load_earnings_preview(ticker)` (maps SCB.BK → preview JSON) and `pre_earnings_brief_enriched()` which attaches consensus-estimate context to the calendar alerts and expands the summary text. Wired `pre_earnings_brief_enriched` into `run_nightly_earnings_check()` output. Existing functions untouched.
4. **`portfolio_engine/brief_generator.py`** *(enhanced)* — Imported `run_oil_scenario_report`; reads current Brent from watchlist `macro_context` (fallback $87.5), runs the report (graceful on failure), injects `pttep_oil_scenarios` into the LLM context, and updated the Section 1 prompt to use it for a concrete PTTEP oil-sensitivity read rather than headline repetition.
5. **`data/watchlist.json`** *(updated)* — Iran deal "signing scheduled Sun Jun 14"; Brent $87.33 / WTI $84.88; SET 1,592.41 (+1.28%, THB 67.4bn); USD/THB 32.72; gold $4,222; BOJ outlook revised to hike-likely; VN-Index 1,798 added; SCB earnings-preview file reference; oil_scenario + scb_preview module flags; catalysts and macro_context refreshed.
6. **`data/market_intel/2026-06-14.md`** *(new file)* — 11-section nightly intelligence: Iran deal as dominant event, holdings update with oil-scenario read, SET rally, US/tech, revised BOJ outlook, Japan/India/China/Vietnam, gold/oil/FX table, and 5 risk flags.

### Verification
All edited/created files pass: `data/watchlist.json` and `data/earnings/scb_h12026_preview.json` parse as valid JSON; `oil_scenario.py`, `earnings_tracker.py`, `brief_generator.py` pass `ast.parse` syntax checks (no execution per safety rules). All changes additive — no existing functions deleted or modified destructively.

### Next Priority (for next run)
**Post-signing + post-FOMC + post-BOJ follow-up (Jun 16–17 window)**: (a) Confirm whether the Iran deal was formally signed Jun 14 and update PTTEP/Brent accordingly — if signed, refresh `oil_scenario.py` current_brent and re-rank the scenarios by realised probability. (b) After BOJ Jun 16, set `boj_policy_rate_pct` to the actual outcome and run `japan_policy_risk_flag()` on the realised USD/JPY. (c) After FOMC Jun 17, update `us_fed_funds_rate_pct` and the dot-plot guidance. Also: **wire `oil_scenario.py` into `risk_scorer.py`** so PTTEP's oil-scenario downside feeds the portfolio concentration/commodity risk score, not just the brief.

---

## Nightly Run — 2026-06-13 02:30 ICT

### Market Intelligence Summary
The dominant event overnight is Trump's statement that a US-Iran peace deal could be signed "this weekend," with a draft 14-point agreement including Hormuz reopening within 30 days. Brent crude fell -7% to ~$86.5, Nikkei surged +2.9% to 66,078, SET recovered to 1,588.89 (+1.05%), and Hang Seng ended a 7-session losing streak (+1.9%). SpaceX (SPCX) completed its Nasdaq debut at +24% above IPO price ($166.83 close). Critical revision: BOJ June 16 hike is now **uncertain** — the April decision was a hold (6-3 vote) and the incoming governor (Ayano Sato) is described as materially more dovish.

### Thai Holdings Update
- **BAFS**: No material news. Aviation demand stable. H1 results est. Aug 14.
- **PTTEP**: ⚠️ Brent -7% to ~$86.5 on Iran deal. Near-term headwind — Hormuz reopening in 30 days if deal signed could remove geopolitical premium. LT thesis intact.
- **SCB**: Banking sector **led SET recovery** Jun 12. Earnings Jul 17 (34 days). Pre-earnings alert in `earnings_tracker.py` will trigger Jul 14.
- **Gold Fund (SCBGOLDE)**: Gold $4,222 (down $94 from $4,316); USD/THB 32.74 (THB strengthened). Est. NAV ~4.312 THB/unit. Iran deal = risk-on = temporary gold headwind. LT targets unchanged.

### Technology Sector Highlight
SpaceX (SPCX) IPO closed at $166.83 (+24%) on 360M shares — largest IPO in history. NVDA at record $215.9B FY2026 revenue at 25.4x forward P/E. AMD +130% YTD. SOXX recovered from -10% single-day selloff. FOMC Jun 16–17: hold 3.5–3.75% near-certainty. BOJ uncertainty is the primary unknown for Nikkei/yen/gold direction.

### Improvements Implemented Tonight
1. **`portfolio_engine/earnings_tracker.py`** *(new file)* — Full earnings calendar system with: `EarningsEvent` dataclass, JSON persistence to `data/earnings/earnings_calendar.json`, `add_earnings_event()` / `get_earnings_events()` CRUD, `upcoming_earnings_alerts()` scanner (configurable window), `pre_earnings_brief()` context dict for LLM injection, `portfolio_earnings_summary()`, `seed_known_earnings()` pre-populated with SCB Jul 17, PTTEP Aug 11 (est), BAFS Aug 14 (est), and SCB H1 div Sep 15 (est), and `run_nightly_earnings_check()` entry point. Addresses the "SCB earnings preview module" priority from the Jun 12 DEVLOG.
2. **`ai_engine/risk_scorer.py`** *(enhanced)* — Added `japan_policy_risk_flag()` function monitoring BOJ carry-trade unwind risk via two inputs: (a) BOJ policy rate vs carry threshold (1.0%), (b) USD/JPY vs carry threshold (148) and severe threshold (140). Returns `risk_level`, `risk_score` (0–1), `flags`, and `recommendation`. Wired into `calculate_portfolio_risk()` to add `japan_carry_risk` to every risk assessment output. Reads BOJ rate and USD/JPY from `watchlist.json` dynamically.
3. **`portfolio_engine/brief_generator.py`** *(enhanced)* — Imported `pre_earnings_brief` and `run_nightly_earnings_check` from `earnings_tracker`. Added `earnings_context` fetch (3-day window) in `generate_daily_brief()`. Injected `earnings_alerts` into the LLM context dict. Updated Section 5 prompt instruction to include upcoming earnings notes when `earnings_alerts.has_upcoming_earnings` is True.
4. **`data/watchlist.json`** *(updated)* — Full refresh: gold $4,222 (from $4,316), Brent ~$86.5 (from $93.5), USD/THB 32.74 (from 32.98), SET 1,588.89 (from 1,563.59), Nikkei 66,078 (from ~63,000), Hang Seng 24,718 (from 24,566), Sensex 74,559 (from 73,983), SCBGOLDE NAV re-estimated 4.312. BOJ outlook revised (uncertain, not confirmed hike). Vietnam inflow estimate updated to $6B. SPCX IPO result added. USD/JPY entry added to currencies. Catalysts calendar fully refreshed with earnings dates.
5. **`data/market_intel/2026-06-13.md`** *(new file)* — 12-section nightly intelligence: SET recovery, PTTEP oil risk, Iran deal analysis, SpaceX IPO result, US markets, BOJ revised outlook, Japan/India/China/Vietnam updates, gold/currency table, and 5 risk flags.

### Next Priority (for next run)
**BOJ June 16 outcome follow-up**: After the BOJ decision, update `boj_policy_rate_pct` in `watchlist.json` and `macro_context`, run `japan_policy_risk_flag()` with the actual outcome, and assess gold/Nikkei/yen reaction. If hike to 1.0% confirmed: flag elevated carry risk; if hold: flag dovish shift under incoming Governor Sato. Also: **SCB earnings data model** — begin sketching `data/earnings/scb_h12026_preview.json` with consensus NIM/NPL/dividend estimates to enrich the pre-earnings brief when the Jul 14 alert fires.

---

## Nightly Run — 2026-06-12 02:30 ICT

### Market Intelligence Summary
SpaceX (SPCX) debuts on Nasdaq today at $135/share, $1.75T valuation — the largest IPO in history — and could be fast-tracked into the Nasdaq-100 within 15 days under Nasdaq's 2026 mega-IPO rule, creating a passive demand event. The AI chip sector is recovering from its $1.4T June 4–5 selloff after Broadcom's Q3 guidance miss, with fundamental $750B hyperscaler capex intact. BOJ hike to 1.0% is confirmed for June 16 (tomorrow); yen carry unwind risk is the primary near-term macro risk for EM assets. SET closed at 1,563 (-1.30%) on Fed rate concerns and THB weakness to ~32.98.

### Thai Holdings Update
- **BAFS**: No material news. Aviation demand stable; 14M+ arrivals Jan–May 2026. Next event: FY2026 interim div ~Sep 2026.
- **PTTEP**: Short-sold 542,600 shares June 10. Brent $93.5 supported by Strait of Hormuz closure (>3 months) and 2013-low US inventories. OPEC bullish (1.4M b/d growth). LT thesis intact.
- **SCB**: 137.50 THB (52w range 115–149.50). **Earnings July 17** is the next key catalyst. H1-2026 interim div est. Sep–Oct 2026.
- **Gold Fund (SCBGOLDE)**: Gold at $4,316; USD/THB ~32.98 → est. NAV ~4.448 THB/unit. Institutional targets GS $5,400 / JPM $6,000 — 25–44% upside from current. BOJ hike may support gold via yen correlation.

### Technology Sector Highlight
SpaceX IPO is the market event of the day ($1.75T valuation; possible QQQ fast-track in 15 days). Chip recovery is genuine — Broadcom Q3 guidance miss was idiosyncratic, not a demand collapse; hyperscaler AI capex rising to $750B confirms the supercycle. Intel (+8.5–11% on Alphabet deal) is the key diversification signal: cloud players are no longer NVDA-only. BOJ hike tomorrow will be the largest Nikkei/yen volatility event of June.

### Improvements Implemented Tonight
1. **`portfolio_engine/brief_generator.py`** *(enhanced)* — Added import of `tech_screener` from `opportunity_scanner`. Added `_load_snapshot_trend()` helper that reads last 7 days of portfolio snapshots via `load_snapshot_history()` (degrading gracefully if unavailable). In `generate_daily_brief()`, added async call to `tech_screener(top_n=3)` and `_load_snapshot_trend(days=7)`. Both results injected into the LLM context dict as `tech_screener_top3` and `portfolio_trend_7d`. Prompt updated: Section 3 now explicitly asks for data-driven momentum commentary using RSI/price_vs_sma20 from tech_screener; Section 5 now asks for a 7-day portfolio trend summary.
2. **`data/watchlist.json`** *(updated)* — USD/THB updated to 32.98; gold to $4,316; Brent to $93.5; SCBGOLDE NAV re-estimated to 4.448; SCB price/earnings date added; SpaceX IPO catalyst added; Hang Seng updated to 24,566 (5th loss session); India Sensex to 73,983; Japan PPI 6.3% added; Vietnam 28-stock list added; hyperscaler capex $750B noted; chip selloff recovery narrative updated; macro_context fully refreshed.
3. **`data/market_intel/2026-06-12.md`** *(new file)* — 10-section nightly intelligence: SET weakness + holdings update, gold/currency at $4,316, SpaceX IPO context, chip recovery narrative, BOJ hike tomorrow, India banks strength, Vietnam FTSE phasing detail, China 5th Hang Seng loss, oil Hormuz update, rate calendar table, and 4 risk flags.

### Next Priority (for next run)
**Post-BOJ impact report**: After June 16 BOJ hike, assess actual Nikkei/yen move and gold reaction. Update `risk_scorer.py` with a `japan_policy_risk_flag()` function that monitors BOJ rate relative to the carry trade threshold (JPY strengthening beyond 148/USD signals unwinding risk). Also: **SCB earnings preview module** — add a `portfolio_engine/earnings_tracker.py` that stores upcoming earnings dates for holdings and generates a pre-earnings brief 3 days before the event. First target: SCB X July 17.

---

## Nightly Run — 2026-06-11 02:30 ICT

### Market Intelligence Summary
US May CPI confirmed at 4.2% YoY (in-line) with softer core (+0.2% MoM vs feared 0.3%), suggesting energy-driven inflation has not yet fully spread — slight positive for risk assets and gold. BOJ hike to 1.0% on June 16 is now a 97%-probability event (highest Japanese rate since 1995), creating Nikkei correction and yen carry-unwind risk. Intel surged 11% on an Alphabet deal for 3M+ AI chips, signalling cloud capex diversification away from NVIDIA. SET recovered to 1,584 on June 9 after the June 8 rout, supported by 13th consecutive month of Thai PMI expansion.

### Thai Holdings Update
- **BAFS**: No material news. Aviation demand solid — 14M+ tourist arrivals Jan–May 2026. Next event: FY2026 interim dividend ~Sep 2026.
- **PTTEP**: Brent partially recovering to ~$94.27 from ceasefire crash low of $91. US-Iran strikes resumed June 7 restored partial geopolitical premium. LT thesis (low-cost producer, ~4.85% div yield) intact; analysts recommend as commodity/inflation hedge.
- **SCB**: Analysts explicitly recommend SCB as high-yield play in elevated bond yield environment (~7.5% est. yield). Next catalyst: H1-2026 interim div ~Sep-Oct 2026.
- **Gold Fund (SCBGOLDE)**: Gold testing $4,157–$4,255 support range. US CPI softer core provides slight relief. NAV est. ~4.462 THB/unit (gold ~$4,210 × THB 32.90 × 0.03215). GS $5,400 year-end target intact.

### Technology Sector Highlight
Intel +11% on Alphabet AI chip deal (3M+ custom chips) is the week's key signal — cloud hyperscalers diversifying chip sourcing away from NVIDIA. NVDA -1.4%, AVGO -3.9%, MU -3.5% on June 11 as AI valuation correction continues. Japan Nikkei up 30% YTD but correcting from peak 68,758 toward 63,000 support ahead of BOJ June 16 hike. Vietnam FTSE EM upgrade September 21 remains the highest-conviction medium-term regional catalyst.

### Improvements Implemented Tonight
1. **`ai_engine/risk_scorer.py`** *(enhanced)* — Wired `save_daily_snapshot()` into `save_daily_performance()`. Every nightly performance save now also archives a full JSON snapshot to `data/snapshots/YYYY-MM-DD.json`, including risk_score, risk_level, currency_risk_score, usd_thb_rate, and concentrated_positions. Completes the daily archive pipeline from last night's DEVLOG priority.
2. **`portfolio_engine/opportunity_scanner.py`** *(enhanced)* — Added `tech_screener()` function scanning 16 global tech/growth stocks across Nasdaq (NVDA, MU, AVGO, MSFT, GOOGL, INTC, AMD, TSM), Nikkei (6857.T, 8035.T, 6594.T), Nifty (INFY, WIT), Vietnam (VNM), and SET (GULF.BK, DELTA.BK). Uses yfinance for price data; computes RSI, SMA20/50 trend, volume ratio, and composite_score. Output is scan_opportunities()-compatible for unified reporting.
3. **`portfolio_engine/api.py`** *(enhanced)* — Exposed `tech_screener()` via new `GET /opportunities/tech?top_n=10` endpoint. Returns ranked momentum opportunities across all markets.
4. **`portfolio_engine/requirements.txt`** *(updated)* — Added `yfinance>=0.2,<1` dependency for tech_screener().
5. **`data/market_intel/2026-06-11.md`** *(new file)* — Full nightly intelligence: SET recovery, US CPI outcome, BOJ hike probability, Intel-Alphabet deal, gold technical support, Vietnam FTSE update, China/India/Japan status, full catalyst calendar.
6. **`data/watchlist.json`** *(updated)* — Gold range $4,157–$4,255, Brent $94.27 recovery noted, USD/THB 32.90, INTC +11% Intel-Alphabet signal added, tech_screener universe documented, India RBI hold at 5.25% added, macro context fully refreshed.

### Next Priority (for next run)
**Tech screener API integration into daily brief**: Extend `brief_generator.py` to call `tech_screener()` (or load its results from a cached JSON) and inject the top 3 cross-market tech signals into Brief Section 3 (US Technology & AI). This will give Tho real momentum data (not just headlines) on his globally-relevant tech universe. Also consider: **snapshot trend loader** — modify `generate_daily_brief()` to call `load_snapshot_history(days=7)` and add a 7-day portfolio trend line to Brief Section 5 (Portfolio Health).

---

## Nightly Run — 2026-06-10 02:30 ICT

### Market Intelligence Summary
Iran-Israel ceasefire announcement (June 9) is the dominant macro event: Brent crude fell sharply from ~$106 to ~$91/barrel, unwinding the geopolitical premium that had supported PTTEP. Gold softened to ~$4,247 (-1.2%) as safe-haven demand eased. The critical near-term pivot is today's US May CPI release (expected 4.2% YoY) — a hot print would pressure gold short-term but reinforce the inflation-hedge thesis. BOJ hike to 1.0% at June 16 is now confirmed (highest rate since 1995), adding yen/Nikkei risk. Baht weakened to 32.92/USD on strong US jobs data.

### Thai Holdings Update
- **BAFS**: No material news. FY2025 final dividend (~THB 0.20 est.) already paid May 2026. Next event: FY2026 interim ~Sep 2026. Aviation demand stable.
- **PTTEP**: ⚠️ Brent dropped $106 → ~$91 on Iran-Israel ceasefire. Near-term upside limited; long-term (low-cost producer, strong FCF, ~4.85% div yield) intact. FY2025 final div THB 4.65 paid Apr 22.
- **SCB**: High-yield play (est. 7.5%) in rate-hold environment. FY2025 div THB 11.28 paid May 7. Watch H1-2026 interim announcement (~Sep-Oct 2026 est.).
- **Gold Fund (SCBGOLDE)**: NAV est. ~4.497 THB/unit (gold $4,247 × THB 32.92). THB weakness partially offsets gold's decline from ATH. GS $5,400 year-end target intact.

### Technology Sector Highlight
US AI sector correcting: S&P500 -1%, Nasdaq -2% June 9 on valuation skepticism. NVDA -3%, Apple -3% (EU Siri ban). Structural AI theme intact — OpenAI IPO filed, Anthropic raised private credit, Micron/Seagate still +200% YTD. FOMC June 16-17: 97.8% probability hold at 3.5-3.75%. Vietnam FTSE EM upgrade September 21 ($1.53B passive inflows phased) remains the highest-conviction regional catalyst.

### Improvements Implemented Tonight
1. **`portfolio_engine/dividend_tracker.py`** *(new file)* — Full SET dividend calendar and alert system. Features: `DividendRecord` dataclass, `add_dividend()` / `get_dividends()` CRUD operations, `upcoming_ex_dates()` alert scanner (5-day advance warning), `calculate_trailing_yield()` for per-ticker yield analysis, `portfolio_dividend_summary()` for combined view, `seed_known_dividends()` pre-populated with researched historical records for BAFS/PTTEP/SCB (FY2024–2025), and `run_nightly_dividend_check()` entry point. Data persisted to `data/dividends/dividend_history.json`.
2. **`portfolio_engine/performance_analytics.py`** *(enhanced)* — Added `save_daily_snapshot()` function that writes daily portfolio state to `data/snapshots/YYYY-MM-DD.json` for historical trend analysis and performance charting. Added `load_snapshot_history()` to retrieve last N days of snapshots for brief generation and drawdown analysis.
3. **`data/market_intel/2026-06-10.md`** *(new file)* — Full nightly intelligence: oil price collapse on ceasefire, gold/CPI preview, BOJ hike confirmation, Vietnam FTSE detail, India RBI support, HK weakness, full catalyst calendar through Sep 2026.
4. **`data/watchlist.json`** *(updated)* — USD/THB updated to 32.92, gold to $4,247, Brent to ~$91, SCBGOLDE NAV re-estimated, Iran-Israel ceasefire impact flagged on PTTEP/Brent, dividend data added for all holdings.

### Next Priority (for next run)
**Performance snapshot nightly runner**: Wire `save_daily_snapshot()` into the nightly pipeline by adding a call in `ai_engine/risk_scorer.py`'s `save_daily_performance()` function — it already reads `portfolio_snapshot.json`; just pass that data to `save_daily_snapshot()` to build the archive. Also consider: **tech sector screener** in `opportunity_scanner.py` extending beyond SET to Nasdaq, Nikkei, Nifty for cross-market momentum signals.

---

## Nightly Run — 2026-06-09 02:30 ICT

### Market Intelligence Summary
SET continues to consolidate at 1,582 below the 1,600 resistance zone, but fundamentals remain strong (SET50 +40% over 12 months, robust tourism). The critical near-term catalyst is the US May CPI release on June 10 — any upside surprise could pressure gold and trigger risk-off across Asian markets. The BOJ is likely to hike to 1.0% at its June 16 meeting, which may dampen Nikkei and yen-adjacent assets. High oil prices (~$106/b Brent, Strait of Hormuz disruption) are a direct positive for PTTEP.

### Thai Holdings Update
- **BAFS**: No material news. Aviation demand stable with 14M+ tourist arrivals Jan–May 2026.
- **PTTEP**: Flagged by brokers as inflation hedge. Brent at ~$106/b strongly supports revenue outlook — thesis intact.
- **SCB**: Trading at 134.5 THB (+1.5%). Benefiting from high bond yield environment.
- **Gold Fund (SCBGOLDE)**: Gold spot ~$4,300; USD/THB 32.77 — mild THB weakness partially offsets gold's pull from ATH. GS year-end target $5,400 intact. Fee drag at 0.50% TER analysed tonight.

### Technology Sector Highlight
US AI supercycle intact: Micron up ~1,006% YTD, Alphabet committing $180–190B capex. Anthropic IPO filed at $965B valuation. SpaceX Nasdaq debut June 12 a sentiment indicator. India AI market $17B by 2027 (25% CAGR) — elevated valuations but strong structural growth. Vietnam FTSE EM upgrade September 21 remains a high-conviction medium-term catalyst.

### Improvements Implemented Tonight
1. **`portfolio_engine/fee_analyzer.py`** *(new file)* — Full fee analysis module with: `calculate_fund_cost()` for fund TER analysis (SCBGOLDE, SCBGOLDHE, SCBGOLDH), `calculate_set_equity_cost()` for SET brokerage/VAT/exchange fee round-trip calculation, `portfolio_fee_summary()` for portfolio-level cost report, `breakeven_holding_months_for_switch()` to compute when ETF switching covers FX friction, and `save_fee_report()` for JSON persistence to `data/fee_reports/`. Key finding: GLDM (TER 0.10%) saves ~0.40% p.a. vs SCBGOLDE (0.50%); breakeven vs FX round-trip ~18 months.
2. **`portfolio_engine/brief_generator.py`** *(enhanced)* — Added `_load_latest_market_intel()` and `_load_watchlist_snapshot()` helper functions that inject nightly market intelligence text and macro snapshot into the LLM prompt. Upgraded prompt to request 6 structured sections: Thailand/SET, Gold & Currency, US Tech & AI, Regional Markets, Portfolio Health, and Action Items. Brief now persona-aware (Tho's specific holdings) and multi-market by design.
3. **`data/market_intel/2026-06-09.md`** *(new file)* — Full nightly intelligence report: SET consolidation context, PTTEP oil catalyst, US CPI/FOMC/SpaceX catalysts, BOJ June 16 rate decision preview, Vietnam FTSE upgrade confirmed, India AI market sizing, China HK weakness, oil/OPEC data, weekly catalyst calendar.
4. **`data/watchlist.json`** *(updated)* — USD/THB updated to 32.77, gold spot to $4,300, Brent $106 added, gold ETF alternatives updated with GLDM (TER 0.10%), catalyst calendar added, macro_context expanded with Fed funds rate, CPI date, BOJ hike probability, and SCBGOLDE estimated NAV.

### Next Priority (for next run)
**Dividend Calendar module** (`portfolio_engine/dividend_tracker.py`): Track SET dividend announcements (ex-date, pay-date, per-share amount) for BAFS, PTTEP, and SCB. Auto-alert 5 days before ex-date. Store dividend history for yield analysis. This will complete the core income tracking capability for Tho's SET equity holdings.

---

## Nightly Run — 2026-06-08 02:30 ICT

### Market Intelligence Summary
The SET index is consolidating near 1,582 after reaching a multi-year high of 1,600, supported by foreign inflows and strong tourism data but capped by geopolitical tension and profit-taking. Gold has pulled back to ~$4,500/oz from its January 2026 ATH of $5,597, with Goldman Sachs projecting a year-end recovery to $5,400. The USD/THB rate has drifted to ~32.94 (mild baht weakness), which benefits Tho's gold fund position in THB terms. The US AI infrastructure supercycle continues but faces near-term volatility after Broadcom's unchanged full-year guidance triggered a 4% Nasdaq drop on June 5.

### Thai Holdings Update
- **BAFS.BK**: No material news. Aviation fuel demand stable with 14M+ tourist arrivals in Jan–May 2026.
- **PTTEP.BK**: Community PR (THB 20M football sponsorship); no operational news.
- **SCB.BK**: No significant news found. Banking sector broadly under pressure from inflation and oil price concerns.
- **Gold Fund (SCBGOLDE)**: Gold at ~$4,500 with USD/THB at 32.94 → estimated NAV ~4.65 THB/unit. Long-term thesis intact; GS target $5,400 by year-end.

### Technology Sector Highlight
US memory stocks (Micron, Seagate, WDC) up 200%+ YTD on AI data center demand. Broadcom AI chip revenue +106% YoY in Q1, guiding +140% YoY in Q2. India IT (TCS, Infosys, HCL) in strong bull run on agentic AI deal momentum — Nifty IT +4.23% in a single session. Vietnam is a key watch: FTSE Russell EM upgrade effective September 21, 2026 could channel significant foreign inflows.

### Improvements Implemented Tonight

1. **`portfolio_engine/fund_nav_tracker.py`** *(new file)* — Created a full NAV tracking module for SCB gold fund variants (SCBGOLDE, SCBGOLDHE, SCBGOLDH). Features: NAV estimation from gold spot + USD/THB, persistent history store in `data/snapshots/fund_nav_history.json`, fee drag calculator vs ETF alternatives (GLD, IAU, SGOL), and a `run_nightly_nav_snapshot()` function for automated nightly recording.

2. **`ai_engine/risk_scorer.py`** *(enhanced)* — Added `currency_risk_score()` function that converts USD/THB rate into a 0–1 risk score (higher when THB is weak). Added `concentration_flag()` to explicitly identify positions over 30% of portfolio. Updated `calculate_portfolio_risk()` to query the live USD/THB rate from the `market_prices` table, incorporate currency risk (5% weight), surface concentrated positions, and return `usd_thb_rate`, `currency_risk_score`, and `concentrated_positions` in the output dict.

3. **`ai_engine/macro_aggregator.py`** *(enhanced)* — Expanded `KEYWORDS` list from 9 → 32 entries, now covering BOJ (Japan), ECB (Europe), RBI (India), FOMC/Fed language, gold/XAU, oil/OPEC, baht/USD-THB currency terms, AI/semiconductor/data center topics, and Vietnam FTSE catalyst. Expanded `SECTORS` map to include PTTEP.BK, BAFS.BK, NVDA, MU, AVGO, MSFT, GOOGL, META, GLD, IAU, SCBGOLDE, VNM, INDA, EWJ, and FXI.

4. **`data/market_intel/2026-06-08.md`** *(new file)* — Structured nightly market intelligence report covering Thailand/SET, gold, USD/THB, US tech/AI, India, Vietnam, and a global macro summary table.

5. **`data/watchlist.json`** *(new file)* — Persistent watchlist tracking Tho's holdings, SET indices, US tech, EM ETFs, commodities, and currencies. Includes macro context snapshot and fee comparison notes for gold fund alternatives.

### Next Priority (for next run)
**Fee Analyzer module** (`portfolio_engine/fee_analyzer.py`): A standalone module to compare total cost of ownership across all holdings — management fees for funds, brokerage commissions for SET equities, and SET transaction tax. This will give Tho a clear annual cost breakdown and flag cases where switching to lower-cost equivalents would materially improve net returns over his 3-month–2-year holding horizon.

---

## Nightly Run — 2026-07-30 02:30 ICT

### Market Intelligence Summary
Two decision-relevant reversals tonight. (1) The oil **de-escalation STALLED and partly reversed**: the US intercepted a **"surprise" Iranian attack** on US forces (Jul-28), **Iran REJECTED Oman's 50-50 Strait-of-Hormuz proposal** (Jul-29, insisting on full inbound control), and ceasefire talks are only "restarting" and shaky — so **Brent bounced ~4-6% back toward ~$83-84** after last week's crash. (2) The **FOMC (Jul-29) delivered a HAWKISH HOLD**: rate held **3.50-3.75%** (5th straight) by a **9-3 vote** with three regional presidents (Hammack, Kashkari, Logan) **dissenting for a HIKE**; Chair Kevin Warsh again removed forward guidance. Both cut the same way for Tho — **gold stays Fed-capped ~$4,030**, PTTEP's realised-price erosion PAUSES, and BAFS's fuel relief PAUSES. **USD/THB ~33.49**.

### Thai Holdings Update
- **BAFS**: jet-fuel relief **PAUSES** — Brent bounced back toward ~$84; still below the ~$100 peak (net better) but the easing tailwind stopped. Last print **9.25 THB (Jul-28)**. H1 est ~Aug-14.
- **PTTEP**: realised-price erosion **PAUSES** — premium stops draining, but **not an add signal** (de-escalation-biased tape). **Q2-2026 results Aug-02 after-close** (analyst meeting Aug-03); Q2 (Apr-Jun) realised oil is a look-back below the late-July peak. Do not add.
- **SCB**: **155.00 THB** (Jul-24 close, held; 52w 123-160). Q2 read holds (THB 11,117m; NPL 3.17%; CAR 18.6%; no div). **Interim-dividend watch Aug-Sep** (~THB 2.00 base; 2025 interim THB 2.00 paid 2025-09-19). Yield ~7.3%.
- **Gold Fund (SCBGOLDE)**: gold ~$4,030 × USD/THB 33.49 → est NAV **~4.20 THB/unit**; weak-baht cushion intact. Year-end house band **$4,000-4,900** (GS 4900 / JPM 4500).

### Technology Sector Highlight
Big-Tech capex week: **MSFT & META reported after close Jul-29** (post-earnings reaction plays out Jul-30 — actuals not yet retrievable at run time); **AAPL & AMZN report after close Jul-30**. Focus = **FY27 AI-capex guidance vs ROI** (MSFT FY27 ~$190B; META FY26 ~$137B) after Alphabet's raised capex spooked the tape. Vietnam FTSE EM upgrade still Sep-21. No direct Tho exposure — global risk gauge.

### Improvements Implemented Tonight
1. **`portfolio_engine/oil_scenario.py`** *(re-ranked — DE-ESCALATION STALLS/REVERSES)* — Added a `2026-07-30` re-rank block for the Jul-28 surprise-attack intercept + Jul-29 Iran rejection of Oman's 50-50 Hormuz split + the ~4-6% Brent bounce. Migrated a sliver BACK from the de-escalation paths to the base/tails: **deal_signed 12→9** (clean full reopen harder), **deal_partial 30→28**, **status_quo 28→30** (drain stalled, Brent bounced), **lebanon 17→19**, **nuclear 13→14**. Rewrote the affected qualitatives, appended a Jul-30 clause to the `probability_weighted_outlook()` note, and moved `run_oil_scenario_report()` default **85.0→84.0**. Additive; every change carries a `2026-07-30` marker. Sum = 9+28+30+19+14 = 100.
2. **`data/watchlist.json`** *(refresh + FOMC digest + gold-flag reconciliation)* — `last_updated`→2026-07-30; **digested the Jul-29 FOMC** (`jul30_fomc_result`: hawkish 9-3 hold, 3 hike-dissents, Warsh removed guidance); added `jul30_` keys for gold ($4,030 / band $4,000-4,900 / NAV ~4.20), USD/THB (33.49), Brent bounce + oil re-rank, and Big-Tech capex week; updated BAFS/PTTEP/SCB holding notes; added Jul-30 (AAPL/AMZN) + Aug-02 (PTTEP capture) catalysts. **Resolved the open MS/UBS gold-target flag**: marked MS 5200 / UBS 5500 STALE_JUN2026_UNVERIFIED (above the current $4,000-4,900 consensus), pinned verified-current GS 4900 / JPM 4500. macro_context now **404 keys**; duplicate-key scan → NONE.
3. **`data/market_intel/2026-07-30.md`** *(new file)* — 6-section report + oil re-rank table + 5 risk flags: stalled-de-escalation + hawkish-hold headline, holdings (PTTEP/BAFS pause, SCB interim watch), gold & currency (+ target-flag resolution), US/Fed (FOMC 9-3 + Big-Tech capex), regional, oil re-rank; ≥2 outlets per major item.

### Verification
`ast.parse` clean on `oil_scenario.py`. Isolated scan: `probability_pct` = **[9,28,30,19,14] sum=100**; weighted-Brent recompute → **$92.2** (up from $91.2 — the stall correctly re-prices the tails up, above the ~$84 spot). `watchlist.json` reloaded via `object_pairs_hook` **duplicate-key scan → NONE** (404 macro keys; last_updated 2026-07-30; 8 `jul30_` keys; gold flag reconciled). News cross-checked ≥2 outlets per item (FOMC: Fed statement + CNBC + Fox Business; oil/Iran: CNN + Trading Economics + Fortune + Al Jazeera; gold: Yahoo + FXLeaders + goldsilver.com; FX: Trading Economics + Wise; Big-Tech: TipRanks + Bloomberg + Saxo). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `run_oil_scenario_report()` / `generate_daily_brief()` weren't exercised end-to-end — edits are additive and the math/loaders were verified in isolation; (b) **MSFT/META post-earnings reaction not yet retrievable** (reported after close Jul-29; plays out Jul-30) — digest next run alongside AAPL/AMZN; (c) SET/holdings live prices not cleanly retrievable at run time — carried last logged closes (SCB 155.0 Jul-24, BAFS 9.25 Jul-28); (d) `data/snapshots/` still holds only `2026-06-21.json` (the live macOS archive cron can't run here); (e) MS/UBS gold targets now explicitly marked stale rather than deleted (kept for audit trail, flagged unverified).

### Next Priority (for next run)
**Digest the MSFT/META (Jul-29) + AAPL/AMZN (Jul-30) capex prints** (AI-trade risk gauge — was the FY27 guidance a relief or a spook?). **Capture the PTTEP Q2/H1 result (Aug-02)** into `data/earnings/pttep_q22026_actual.json` (loader wiring done): realised Brent, ~560kboe/d volume, capex guidance, any interim dividend + reconciliation vs preview. **Watch the SCB interim-dividend declaration (Aug-Sep)** — set the Sep interim event `confirmed=True` with actual size/ex-date. **Track the oil two-sider**: if the ceasefire re-firms and Hormuz reopens → shift mass back to deal_partial/deal_signed toward Goldman ~$80 (PTTEP erosion resumes, BAFS tailwind); if the pause breaks or Yanbu flares → snap the tails toward $105-120 and flag PTTEP operational risk. Lower priority: **re-confirm the MS/UBS gold targets** if any outlet refreshes them, and **reconcile a clean SET close** for SCB/PTTEP/BAFS.

---

## Nightly Run — 2026-07-31 02:30 ICT

### Market Intelligence Summary
Two decision-relevant moves tonight. (1) **Oil RE-ESCALATED**, reversing last run's "de-escalation stall": Brent JUMPED **7.9% to $90.74** (Jul-29) after President Trump vowed to **"hit Iran hard"** for the intercepted Jul-28 surprise attack on US forces, then held **~$88** on Jul-30. (2) **Big-Tech capex week closed with a sharp bifurcation** — **MSFT +9-14%** (Azure +43%, crossed $100B FY revenue, capex kept disciplined) vs **META -9%** (no FY27 capex guidance, op margin 43%→31%, net income -14%). AAPL posted an 8th straight EPS beat (Tim Cook's final call) and AMZN's AWS grew 28% (fastest in 15 quarters) but with FCF down ~95% on ~$200B AI capex; their reaction plays out in the Jul-31 session. Gold ~$4,080 (Fed-capped); USD/THB ~33.65 (mild baht weakness).

### Thai Holdings Update
- **BAFS**: jet-fuel-cost headwind **RESUMES** — Brent back toward ~$88-90 after the +7.9% Jul-29 jump; the easing tailwind reversed. Last print **9.25 THB (Jul-28)**. H1 est ~Aug-14.
- **PTTEP**: realised-price tailwind **RESUMES** on re-escalation — but **NOT an add signal**; Q2 (Apr-Jun) realised is a look-back and **results land Aug-02 after-close** (analyst meeting Aug-03). Carried 141.00 THB (Jul-24).
- **SCB**: **155.00 THB** (Jul-24 close; no clean fresh SET close retrievable). **Interim-dividend watch Aug-Sep** (~THB 2.00 base; 2025 interim THB 2.00 paid 2025-09-19). Q2 read holds (NPL 3.17%, CAR 18.6%).
- **Gold Fund (SCBGOLDE)**: gold ~$4,080 × USD/THB 33.65 → est NAV **~4.20 THB/unit**; weak-baht cushion intact. Year-end band **$4,000-4,900** (GS 4900 / JPM 4500).

### Technology Sector Highlight
The AI-capex market lesson of the week crystallised: **disciplined spend rewarded (MSFT), un-guided spend punished (META)** — net modestly constructive for the AI trade after Alphabet's earlier capex spook. AAPL (services flywheel, leadership transition to John Ternus) and AMZN (AWS reaccelerating to +28%, but heavy AI capex draining FCF) reactions still to settle. No direct Tho exposure — global risk gauge only. Vietnam FTSE EM upgrade still Sep-21.

### Improvements Implemented Tonight
1. **`portfolio_engine/oil_scenario.py`** *(re-ranked — RE-ESCALATION CONFIRMED)* — Added a `2026-07-31` re-rank block for the Jul-29 Trump "hit Iran hard" threat + Brent's +7.9% jump to $90.74 (held ~$88 Jul-30). Migrated mass OFF the de-escalation paths and ONTO the base + escalation tails, and re-anchored status_quo Brent UP $86→$89: **deal_signed 9→7, deal_partial 28→24, status_quo 30→32, lebanon 19→22, nuclear 14→15** (sum 100; weighted Brent **~$94.3**, up from ~$92.2). Rewrote the affected qualitatives + the status_quo narrative, appended a Jul-31 clause to `probability_weighted_outlook()`, and moved `run_oil_scenario_report()` default **84.0→88.0**. Additive; every change carries a `2026-07-31` marker.
2. **`data/watchlist.json`** *(refresh + Big-Tech digest + oil re-rank)* — `last_updated`→2026-07-31, `usd_thb_rate`→33.65; added 7 `jul31_` macro keys (Big-Tech earnings digest, gold $4,080/NAV ~4.20, USD/THB 33.65, Brent ~$88 + oil re-rank, PTTEP-Aug02/SCB-interim watch); appended `oil_regime_jul31` notes to BAFS/PTTEP, a Jul-31 note to SCB, and Aug-02 (PTTEP Q2) + Aug-14 (BAFS H1) catalysts. macro_context now **412 keys**; duplicate-key scan → NONE.
3. **`data/market_intel/2026-07-31.md`** *(new file)* — 6-section report + oil re-rank table + 6 risk flags: re-escalation + MSFT/META bifurcation headline, holdings (PTTEP Aug-02, SCB interim watch), gold & currency, US/AI capex bifurcation, regional, oil re-rank; ≥2 outlets per major item.

### Verification
`ast.parse` clean on `oil_scenario.py`. Isolated scan of the Jul-31 scenarios block: `probability_pct` = **[7,24,32,22,15] sum=100**; weighted-Brent recompute → **$94.31** (up from $92.2, correctly above the ~$88-90 spot as the tails re-price the re-escalation). `watchlist.json` reloaded via `object_pairs_hook` **duplicate-key scan → NONE** (412 macro keys; last_updated 2026-07-31; 7 `jul31_` keys). News cross-checked ≥2 outlets per item (oil/Iran: CNBC + Trading Economics + Al Jazeera + Barchart; Big-Tech: Yahoo Finance + 24/7 Wall St. + Qz + CNBC; gold: CNBC + Fortune + Trading Economics; FX: Trading Economics + Wise). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `run_oil_scenario_report()` / `generate_daily_brief()` weren't exercised end-to-end — edits are additive and the math/loaders were verified in isolation; (b) **AAPL/AMZN post-earnings reaction not yet settled** (reported after close Jul-30; plays out Jul-31 session) — actuals captured, price reaction to confirm next run; (c) no clean fresh SET close retrievable — carried last logged closes (SCB 155.0 Jul-24, PTTEP 141.0 Jul-24, BAFS 9.25 Jul-28); (d) `data/snapshots/` still holds only `2026-06-21.json` (the live macOS archive cron can't run here).

### Next Priority (for next run)
**Capture the PTTEP Q2/H1 result (Aug-02, after-close)** into `data/earnings/pttep_q22026_actual.json`: realised Brent, ~560kboe/d volume, capex guidance, any interim dividend + reconciliation vs the CLSA/DBS preview. **Confirm the AAPL/AMZN price reaction** (was the AWS reaccel / services-flywheel read a relief or a spook — settle the global AI risk gauge). **Watch the SCB interim-dividend declaration (Aug-Sep)** — set the Sep interim event `confirmed=True` with actual size/ex-date once the board declares. **Track the oil two-sider**: if Trump's strike threat converts to action or Yanbu re-flares → snap the tails toward $105-120 and flag PTTEP operational risk + BAFS margin risk; if Hormuz genuinely reopens → shift mass back toward Goldman ~$80. Lower priority: reconcile a clean SET close for SCB/PTTEP/BAFS.

---

## Nightly Run — 2026-08-01 02:30 ICT

### Market Intelligence Summary
Two decision-relevant resolutions tonight. (1) **Oil eased / consolidated**: Brent slipped to **~$86** on Jul-31 (from ~$88) as Trump's "hit Iran hard" pledge went **un-acted-on**, though crude still closed the month **up >20%** and some tankers were still turned around in Hormuz — a consolidation, not a regime change. (2) The **AAPL/AMZN split resolved sharply** (closing last run's open flag): **AMZN +13-14%** (AWS +28%, AI-capex conviction rewarded) vs **AAPL -7 to -9%** (iPhone units +22% but services softness + soft current-quarter guidance amid a memory-price surge / chip shortages). Despite strong Big-Tech prints, **US indices closed the week LOWER** — tariffs + a softening labor market retook the wheel. Gold **~$4,068** (Fed-capped); **USD/THB ~33.39** — the baht **STRENGTHENED** from 33.65.

### Thai Holdings Update
- **BAFS**: jet-fuel-cost headwind **eases slightly** — Brent back to ~$86 (off the ~$100 late-July peak, still above the sub-$80 comfort zone). Stable tourism throughput. H1 est ~Aug-14. Last print **9.25 THB (Jul-28)**.
- **PTTEP**: realised-price tailwind **HOLDS but flattening** — **NOT an add signal**. **Q2-2026 results Aug-02 after-close** (analyst meeting Aug-03); preview CLSA ~THB 27.3bn / DBS ~THB 25.6bn, ASP ~$52.8/boe. Q2 realised is a look-back. Carried **141.00 THB (Jul-24)**.
- **SCB**: **155.00 THB carried (Jul-24)** — ⚠️ one outlet quoted **152.00 (Jul-24)**; SET clean-close reconciliation still open. **Interim-dividend watch Aug-Sep** (~THB 2.00 base; 2025 interim THB 2.00 paid 2025-09-19). Q2 read holds (NPL 3.17%, CAR 18.6%).
- **Gold Fund (SCBGOLDE)**: gold ~$4,068 × USD/THB 33.39 → est NAV **~4.15 THB/unit**, down ~1% as **both** gold dipped and the baht firmed — the weak-baht cushion **thinned** this run. Year-end band **$4,000-4,900**.

### Technology Sector Highlight
The AI-capex earnings arc closed with a clean lesson: **cloud/disciplined spend rewarded (MSFT +9-14%, AMZN +13-14%), un-guided / soft-services punished (META -9%, AAPL -7 to -9%)**. Net modestly constructive for the AI trade — but the market's tell was that indices STILL finished the week lower, so macro (tariffs, weak labor) outweighed the earnings. US July jobs report (Fri) is the next gauge. No direct Tho exposure. (Caveat: a general web search surfaced 2025-era Fed/jobs content that conflicts with the project's 2026 timeline — Warsh chair, hawkish 3.50-3.75% hold with hike-dissents — NOT overwritten; flagged.)

### Improvements Implemented Tonight
1. **`portfolio_engine/oil_scenario.py`** *(re-ranked — MILD EASING / CONSOLIDATION)* — Added a `2026-08-01` re-rank block for the Jul-31 ease to ~$86 with the strike threat NOT acted on. Trimmed the status_quo Brent anchor **89->86**, moved a sliver **deal_partial 24->25** and **lebanon 22->21** (deal_signed 7, status_quo 32, nuclear 15 held). Sum = 7+25+32+21+15 = 100. Rewrote the affected qualitatives + status_quo narrative, appended an Aug-01 clause to `probability_weighted_outlook()`, and moved `run_oil_scenario_report()` default **88.0->86.0**. Additive; every change carries a `2026-08-01` marker.
2. **`data/watchlist.json`** *(refresh + AAPL/AMZN resolution + FX/gold/oil update)* — `last_updated`->2026-08-01, `usd_thb_rate`->33.39; added **9 `aug01_` macro keys** (gold $4,068/NAV ~4.15, USD/THB 33.39 baht-strength, Brent ~$86 + oil re-rank, AAPL/AMZN resolved, SET 1,598 + SCB price flag, watch list); appended `oil_regime_aug01`/`note_aug01` to all four holdings; added Aug-01 FX + Aug-07 US-jobs catalysts. macro_context now **421 keys**; duplicate-key scan -> NONE.
3. **`data/snapshots/2026-08-01.json`** *(new file — resolves the long-open snapshots-archive flag)* — First fresh dated snapshot since 2026-06-21. Share counts carried from the seed (BAFS 18,200 / PTTEP 1,400 / SCB 1,400) × last logged closes → total ex-gold **THB 582,750**; plus USD/THB, Brent, gold, NAV est, and next catalysts. `risk_score` left null (Postgres path can't run in sandbox); SCB value carries the 152-vs-155 reconciliation caveat.
4. **`data/market_intel/2026-08-01.md`** *(new file)* — 6-section report + oil re-rank table + 5 risk flags: oil-consolidation + AAPL/AMZN-resolution headline, holdings, gold & currency, US/tech, regional/oil re-rank; ≥2 outlets per major item.

### Verification
`ast.parse` clean on `oil_scenario.py`. Isolated scan: `probability_pct` = **[7,25,32,21,15] sum=100**; weighted-Brent recompute → **$93.14** (down from $94.31, correctly above the ~$86 spot as the anchor drops to $86 and the top tail is trimmed). `watchlist.json` reloaded via `object_pairs_hook` **duplicate-key scan → NONE** (421 macro keys; last_updated 2026-08-01; 9 `aug01_` keys). `2026-08-01.json` snapshot parses; values arithmetic-checked (18200×9.25=168350, 1400×141=197400, 1400×155=217000, Σ=582750). News cross-checked ≥2 outlets/item (oil: CNBC + Trading Economics + Al Jazeera; AAPL/AMZN: CNBC + Qz + TradingKey + 24/7 Wall St.; gold: JM Bullion + LiteFinance + Yahoo; FX: exchange-rates.org + Wise + Long Forecast). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `run_oil_scenario_report()` / `generate_daily_brief()` weren't exercised end-to-end — edits are additive and the math/loaders were verified in isolation; (b) **PTTEP Q2 not yet out** (Aug-02 after-close) — capture next run; (c) no clean fresh SET close retrievable — carried last logged closes; the 152-vs-155 SCB discrepancy is flagged not resolved; (d) general Fed/jobs search returned 2025-contaminated data conflicting with the project timeline — not used.

### Next Priority (for next run)
**Capture the PTTEP Q2/H1 result (Aug-02 after-close)** into `data/earnings/pttep_q22026_actual.json`: realised Brent, ~560kboe/d volume, capex guidance, any interim dividend + reconciliation vs the CLSA ~THB 27.3bn / DBS ~THB 25.6bn preview. **Digest the US July jobs report** (weak-labor / tariff macro gauge) and whether the week's risk-off extends. **Watch the SCB interim-dividend declaration (Aug-Sep)** — set the Sep interim event `confirmed=True` with actual size/ex-date once the board declares. **Reconcile the SCB 152-vs-155 (Jul-24) print** with a verified SET close. **Track the oil two-sider**: strike-threat converts to action or Yanbu re-flares → snap tails toward $105-120 (PTTEP op risk, BAFS margin risk); genuine Hormuz reopen → shift toward Goldman ~$80.

---

## Nightly Run — 2026-08-02 02:30 ICT

### Market Intelligence Summary
The night's decisive item is **PTTEP's Q2-2026 print landing early** (the top open flag): net profit **USD 833m (+104% YoY vs $408m, +122% QoQ)** on **record 572,882 boe/d** volume and a **$52.89/boe** realised price (+20% YoY), with **H1 net income THB 39.03bn (+14%)** and a fresh **THB 4.50/share interim dividend payable Aug-28** — reconciling **in-line-to-beat** vs the CLSA ~THB 27.3bn / DBS ~THB 25.6bn preview. Oil sits in **mild-easing consolidation (~$86 Brent)**; the Jul-29 "$90.74 / hit-Iran-hard" spike has not been acted on. The US week closed **UP** (S&P +1.1%, Nasdaq +1.6%) but with a sharp Big-Tech split — cloud/disciplined spend rewarded (AMZN +15%, GOOGL +7%, MSFT +3%), AAPL (-7.4%) and META punished. Weekend run — no fresh SET/oil/FX prints (SET last ~1,610-1,629, recovered from 1,598 Jul-30).

### Thai Holdings Update
- **BAFS**: jet-fuel-cost headwind **eases slightly** on Brent ~$86 (off the ~$100 late-July peak, still above sub-$80 comfort). Stable tourism throughput. H1 results ~Aug-14. Last print 9.25 THB (Jul-28).
- **PTTEP**: ✅ **Q2 RESULTS CAPTURED** — USD 833m (+104% YoY / +122% QoQ), record ~573kboe/d, ASP $52.89/boe, H1 THB 39.03bn, **THB 4.50 interim div (pay Aug-28)**. In-line-to-beat vs preview. **Caveat:** captured the Apr-Jun premium — oil since eased to ~$86, so backward-looking. HOLD with good income; do NOT chase; better add on an oil pullback. Carried 141.00 THB (Jul-24).
- **SCB**: Q2 read holds (NPL 3.17%, CAR 18.6%). **Interim-dividend watch Aug-Sep** — none declared for 2026 yet. ⚠️ **152-vs-155 (Jul-24) price flag STILL OPEN** — carrying 155.00.
- **Gold Fund (SCBGOLDE)**: gold ~$4,054 x USD/THB ~33.39 -> est NAV **~4.15 THB/unit**; thin weak-baht cushion. Year-end band $4,000-4,900.

### Technology Sector Highlight
Big-Tech earnings arc closed constructive-but-bifurcated: **AMZN +15.3%** (AWS +28%), **GOOGL +6.9%**, **MSFT +3%** vs **AAPL -7.4%** (services soft + soft guidance; +$0.11 EPS from tariff-rebate refunds after SCOTUS struck some tariffs) and **META** weak on cash conversion. Market rewards disciplined/cloud AI spend, punishes un-guided spend. Tariff overhang persists (new 50% Section-338 on select Canadian goods effective Aug-19). Vietnam FTSE EM upgrade still Sep-21. No direct Tho exposure — global risk gauge. Next macro gauge = US July jobs (~Aug-7).

### Improvements Implemented Tonight
1. **`data/earnings/pttep_q22026_actual.json`** *(new file — RESOLVES THE TOP OPEN FLAG)* — Full PTTEP Q2/H1-2026 reported actuals + reconciliation vs the CLSA/DBS preview. Sections: `reported_results` (net profit USD 833m, +104% YoY / +122% QoQ, EPS $0.21, record 572,882 boe/d, ASP $52.89/boe, H1 THB 39.03bn / rev THB 176.76bn, FY26 target ~560kboe/d), `dividend_outcome` (THB 4.50 interim, pay Aug-28, ex-date TBC), `reconciliation_vs_preview` (in-line-to-beat), `thesis_assessment` (HOLD w/ income; backward-looking; add on pullback), and `advisory_note_for_tho`. Loader wiring already existed — `load_earnings_actual('PTTEP.BK')` now returns reported+reconciled and the brief auto-switches PTTEP from preview.
2. **`portfolio_engine/earnings_tracker.py`** *(updated comments/notes)* — Updated `load_earnings_actual` docstring + the `actual_map` PTTEP comment from "file pending / officially Aug-04" to CAPTURED-2026-08-02 with the headline figures; prepended a "RESULTS RELEASED & CAPTURED 2026-08-02" clause to the PTTEP `add_earnings_event` notes (original schedule note retained). No logic changed — additive documentation keeping the module honest now that the print is in.
3. **`data/watchlist.json`** *(refresh + PTTEP Q2 digest)* — `last_updated`->2026-08-02 (both _meta and top-level); added PTTEP `note_aug02` (Q2 result digest) and **5 `aug02_` macro keys** (pttep_q2_result, set_note, us_global, regional, watch). macro_context now **426 keys**; duplicate-key scan -> NONE.
4. **`data/market_intel/2026-08-02.md`** *(new file)* — 6-section report (Thailand/holdings, gold & currency, US tech, regional, oil two-sider) + 5 risk flags, PTTEP Q2 as headline; >=2 outlets per major item.

### Verification
`ast.parse` clean on `earnings_tracker.py`. `pttep_q22026_actual.json` parses (6 top-level sections; net USD 833 / YoY 104.0 / div 4.5). `watchlist.json` reloaded via `object_pairs_hook` **duplicate-key scan -> NONE** (426 macro keys; last_updated 2026-08-02 both; 5 aug02_ keys; PTTEP note_aug02 present). Reconciliation arithmetic checked: 833/408-1 = **+104.2%** (matches reported +104%); Q2 THB est 833 x ~32.7 = **~THB 27.2bn** ≈ CLSA 27.3bn (beat DBS 25.6bn). News cross-checked >=2 outlets per item (PTTEP: Kaohoon 587753 + Bitget H1 disclosure + PTTEP IR dividend page; oil: CNBC + TradingEconomics; gold: JM Bullion + FXLeaders + LiteFinance; US week: ts2.tech + 247wallst; VN: vietnam.vn + TradingEconomics). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `run_oil_scenario_report()` / `generate_daily_brief()` weren't exercised end-to-end — edits are additive and the loaders/math verified in isolation; (b) weekend run — no fresh SET/oil/FX closes; SCB 152-vs-155 (Jul-24) still unreconciled (carrying 155.00); USD/THB 33.39 carried; (c) PTTEP interim-dividend **ex-date TBC** (pay Aug-28 confirmed) and 2026 capex-guidance detail not in the results headline — confirm at the Aug-3 analyst meeting; (d) no snapshot written this run (weekend, no fresh closes — carry the Aug-01 snapshot).

### Next Priority (for next run)
**Confirm the PTTEP interim-dividend EX-DATE** (pay Aug-28 known) and **capture any 2026 capex-guidance detail** from the Aug-3 analyst meeting into `pttep_q22026_actual.json`. **Watch the SCB interim-dividend declaration (Aug-Sep)** — set the Sep interim event `confirmed=True` with actual size/ex-date once the board declares. **Digest the US July jobs report (~Aug-7)** — weak-labor/tariff macro gauge; does the tariff-driven risk-off resume? **Reconcile the SCB 152-vs-155 (Jul-24) print** with a verified SET close, and write a fresh dated snapshot once clean SET closes are retrievable. **Track the oil two-sider**: re-escalation / Yanbu flare -> tails $105-120 (PTTEP op risk, BAFS margin risk); genuine Hormuz reopen -> Goldman ~$80.

---

## Nightly Run — 2026-08-03 02:30 ICT

### Market Intelligence Summary
The night's decisive item is **PTTEP's Aug-03 analyst meeting** (the top open sub-watch), which **reaffirmed the ~560kboe/d FY26 volume target (+10%)** and flagged a **slight Q3 volume dip on planned Thailand+Malaysia maintenance** (normal seasonal turnarounds, not a reserves/demand issue) — a specific 2026 capex figure was not cleanly retrievable at run time. Post-Q2 the stock has **rallied to ~147-151 THB** (from 141.00 Jul-24). Separately the long-open **SCB 152-vs-155 price flag is RESOLVED** — an Aug-03 quote confirms 155.00 with previous close 152.50, so the 152 was simply the prior session's close. US markets slipped to **weekly losses** (Nasdaq ~-2%/5d) on new global tariffs + AI jitters + rising oil; **oil holds ~$88 consolidation** (Jul-29 $90.74 spike un-acted-on); **gold ~$4,044**; **baht steady at 33.39**.

### Thai Holdings Update
- **BAFS**: jet-fuel-cost headwind steady on Brent ~$88 (off the ~$100 late-July peak). Stable tourism throughput. H1 results ~Aug-14. Last clean print 9.25 THB (Jul-28).
- **PTTEP**: ✅ **Aug-03 analyst meeting captured** — FY26 ~560kboe/d target reaffirmed (+10%), slight Q3 volume dip on Thailand+Malaysia maintenance, capex figure TBC. Stock rallied to ~147-151 (fresh print mid ~148). THB 4.50 interim div pay Aug-28 (ex-date still TBC). HOLD with good income; do NOT chase — forward oil tape drives Q3, not this backward-looking Q2.
- **SCB**: ✅ **152-vs-155 flag RESOLVED** — 152.50 was the previous close, 155.00 the Jul-24 close (confirmed). Q2 read holds (NPL 3.17%, CAR 18.6%). Interim-dividend watch Aug-Sep still open (~THB 2.00 base; none declared for 2026 yet).
- **Gold Fund (SCBGOLDE)**: gold ~$4,044 x USD/THB 33.39 -> est NAV ~4.14 THB/unit; thin weak-baht cushion, roughly flat vs last run. Year-end band $4,000-4,900.

### Technology Sector Highlight
US risk-off resurfaced: all three indices posted WEEKLY LOSSES (Nasdaq ~-2%/5d) on new global tariffs taking effect + AI-capex jitters + rising oil + elevated bond yields — macro reclaimed the wheel despite the constructive Big-Tech arc (MSFT/AMZN/GOOGL rewarded on disciplined cloud/AI spend; AAPL -7.4%, META weak). Tariff overhang persists (50% Section-338 on select Canadian goods effective Aug-19). Asia firmer: Hang Seng 8-week high (~25,850), Shanghai ~3,832 on a semiconductor/AI rebound, Nikkei near record; Nifty softer. Next US macro gauge = July jobs ~Aug-7. No direct Tho exposure — global risk gauge.

### Improvements Implemented Tonight
1. **`data/earnings/pttep_q22026_actual.json`** *(RESOLVES THE TOP OPEN SUB-WATCH)* — Added an `analyst_meeting_2026_08_03` section: FY26 ~560kboe/d target reaffirmed (+10%), slight Q3 volume dip on planned Thailand+Malaysia maintenance, capex figure not cleanly retrievable (re-confirm if refreshed), interim-div ex-date still TBC, and a `read_for_tho`. Updated `thesis_assessment.watch_next` to mark the Aug-03 meeting held. Additive; `_added_by_nightly_agent` marker carried.
2. **`data/watchlist.json`** *(refresh + analyst-meeting + SCB-flag resolution)* — meta+top-level `last_updated`->2026-08-03; PTTEP `last_price_thb` 141->148 (fresh Aug-03 print, prior 141 preserved as `prior_price_thb`) + `note_aug03`; added **12 `aug03_` macro keys** (pttep_meeting, scb_price_resolved, gold $4,044/NAV ~4.14, USD/THB 33.39 steady, Brent ~$88 no re-rank, SET 1,624, US weekly-loss, regional+Vietnam-Aug21, watch). macro_context now **438 keys**; duplicate-key scan -> NONE.
3. **`data/snapshots/2026-08-03.json`** *(new file — fresh dated snapshot with a genuinely fresh holding print)* — PTTEP re-priced 141->148 (post-Q2 rally); SCB 155.00 confirmed (flag resolved); BAFS 9.25 carried. Total ex-gold **THB 592,550** (+THB 9,800 vs Aug-01, all PTTEP re-pricing). `risk_score` null (Postgres path can't run in sandbox).
4. **`data/market_intel/2026-08-03.md`** *(new file)* — 6-section report + 5 risk flags: PTTEP analyst meeting + SCB-flag-resolution headline, holdings, gold & currency, US/tech, regional (Vietnam Aug-21), oil two-sider; >=2 sources per major item.

### Verification
`json.load` clean on all edited/new files. `watchlist.json` reloaded via `object_pairs_hook` **duplicate-key scan -> NONE** (438 macro keys; last_updated 2026-08-03 both meta + top-level; 12 aug03_ keys; PTTEP price 148.0/2026-08-03). `pttep_q22026_actual.json` parses (7 sections incl. new analyst_meeting_2026_08_03; FY26 target 560000). Snapshot arithmetic checked: PTTEP 1400x148=207,200; BAFS 18200x9.25=168,350; SCB 1400x155=217,000; Σ=**592,550** (delta +9,800 vs 582,750 = 1400x(148-141)=9,800 ✓). SCB flag resolution corroborated by the Aug-03 quote (155.00 last / 152.50 previous close). News cross-checked >=2 sources per item (PTTEP: Kaohoon 587753 + PTTEP IR calendar; oil: Trading Economics + Investing.com; gold: Forbes + JM Bullion + Long Forecast; FX: Long Forecast + XE/Wise; US: CNBC + Yahoo; regional/VN: Trading Economics + Vietnam Briefing + Vietnam News). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `run_oil_scenario_report()` / `generate_daily_brief()` weren't exercised end-to-end — edits are additive JSON/data and were validated in isolation; (b) PTTEP fresh print is a ~147-151 band (Investing.com 147 / stockanalysis 151); mid ~148 taken — re-confirm a single clean SET close; (c) PTTEP 2026 capex figure not cleanly retrievable at run time — sub-watch left open; (d) interim-div ex-date still TBC (pay Aug-28 confirmed); (e) BAFS still on its last clean print 9.25 (Jul-28) — no fresh close retrievable; (f) oil ranking deliberately UNCHANGED (stable consolidation — no re-rank warranted).

### Next Priority (for next run)
**Confirm the PTTEP interim-dividend EX-DATE** (pay Aug-28 known) and **capture the 2026 capex figure** if an outlet/IR deck refreshes it. **Digest the US July jobs report (~Aug-7)** — weak-labor/tariff macro gauge; does the tariff-driven risk-off extend? **Watch the SCB interim-dividend declaration (Aug-Sep)** — set the Sep interim event `confirmed=True` with actual size/ex-date once the board declares. **Track the Vietnam FTSE Aug-21 constituent-list + cap-threshold release** (upgrade Sep-21) — the highest-conviction medium-term regional catalyst; consider whether to add a VNM/EM watch entry. **Reconcile a clean single SET close** for PTTEP (147-151 band) and BAFS (9.25 Jul-28). **Oil two-sider**: re-escalation/Yanbu flare -> tails $105-120 (PTTEP op risk, BAFS margin risk); genuine Hormuz reopen -> Goldman ~$80.

---

## Nightly Run — 2026-08-04 02:30 ICT

*(Run fired late at 00:00 ICT 2026-08-05, covering the missed Aug-04 slot. Prior entry: 2026-08-03.)*

### Market Intelligence Summary
The night's decisive item is a genuine **REGIME CHANGE in oil**: President Trump **CALLED OFF a planned "massive attack" on Iran** (Aug-03) after direct appeals from Saudi Arabia, the UAE, Qatar and Iran, said peace talks would **restart**, and said he expects the **Strait of Hormuz to reopen soon**. Brent fell **4.2% to ~$84** (WTI -5% to ~$80) and sat **~$81 on Aug-04** — the **lowest print of the entire conflict series**. Wall Street ran with it: **Dow all-time closing high 53,178.41 (+1.3%)**, S&P 500 +1.5% to 7,600.50, Nasdaq +2.1% to 25,913.90 (Palantir beat; AMD on deck). Second decisive item: the long-open **PTTEP interim-dividend EX-DATE resolved — XD 2026-08-14**. Counterweight kept: Iran **denies** direct US talks and offers only a **"temporary" Oman corridor**, and Trump called Tehran "unbelievably duplicitous" — so this is two-sided, not a settled peace.

### Thai Holdings Update
- **BAFS**: ✅ **the night's clearest winner** — fresh print **9.80 THB** (from 9.25 Jul-28, **+5.9%**). Brent ~$81 vs the ~$100 late-July peak is a material jet-fuel-cost tailwind (pass-through lag applies). Yield ~3.28%; 52w 6.70-17.60, so the recovery is early not stretched. **H1 results est. ~Aug-14; investor meeting confirmed Aug-28.**
- **PTTEP**: ✅ **EX-DATE RESOLVED** — interim **THB 4.50**, board approved Jul-31, **XD 2026-08-14**, pay **Aug-28**, last cum day **Aug-13**. Tho's 1,400 sh -> **THB 6,300 gross / ~THB 5,670 net** (10% withholding). Price **151.0** (from 148). Forward picture **deteriorated**: Q2's USD 833m was a look-back on the Apr-Jun premium; Q3 faces **both** a lower oil tape **and** the flagged Thailand+Malaysia maintenance volume dip. HOLD for the income, do **not** chase.
- **SCB**: 2026 interim **still undeclared**. Reference: 2025 interim THB 2.00 paid 2025-09-19; FY2025 final THB 11.28/sh (80% payout, THB 37,981m) approved at the Apr-08-2026 AGM, paid 2026-05-07. Carrying **155.00** (Jul-24). Least oil-sensitive — roughly neutral tonight.
- **Gold Fund (SCBGOLDE)**: gold **$4,068.68** x USD/THB **33.396** -> est NAV **~4.15 THB/unit**, flat vs Aug-03. Held above $4,060 **despite** the risk-on tape — Iran bid fading, NFP-week/Fed uncertainty keeping a floor. Band $4,000-4,900 held.

### Technology Sector Highlight
Sharp reversal of the tariff-driven weekly losses reported Aug-03: the AI trade rebounded from a volatile July on the oil crash, with all three US indices at/near records and the **Dow posting an all-time close**. Palantir's beat drove the S&P toward a record; AMD reports next. Tariff overhang persists (50% Section-338 on select Canadian goods effective Aug-19). Asia **lagged**: Nikkei -0.54% (63,410), Hang Seng -0.35%, Nifty opened -70.4 (24,703.90). **Vietnam outperformed: VN-Index +0.82% to 1,777**, with the FTSE constituent list now only 17 days out. No direct Tho exposure — global risk gauge.

### Improvements Implemented Tonight
1. **`portfolio_engine/oil_scenario.py`** *(re-ranked — DE-ESCALATION BREAKTHROUGH, the largest downside move of the series)* — Added a `2026-08-04` re-rank block for the called-off strike + restart of talks + Brent's break to ~$81. Migrated mass hard ONTO the de-escalation paths and OFF both tails, and re-anchored status_quo DOWN $86->$82: **deal_signed 7->12, deal_partial 25->33** (the Oman "temporary corridor" IS this scenario by definition — now the **MODAL** path), **status_quo 32->30** (anchor 86->82), **lebanon 21->15** (strike stood down *at Gulf request* cuts the regional-blow-up channel), **nuclear 15->10** (cancelled attack + talks restarting). Sum 100; weighted Brent **$93.14 -> $88.69**. Rewrote all five qualitatives + the status_quo narrative, appended an Aug-04 clause to `probability_weighted_outlook()`, and moved `run_oil_scenario_report()` default **86.0->82.0**. Additive; every change carries a `2026-08-04` marker.
2. **`data/earnings/pttep_q22026_actual.json`** *(RESOLVES THE TOP OPEN SUB-WATCH)* — `dividend_outcome.ex_date` set to the confirmed **2026-08-14** (was "TBC"), plus `board_approval_date` 2026-07-31, `last_cum_dividend_trading_day` 2026-08-13, three IR/press sources, and an `action_for_tho` block (THB 6,300 gross / ~5,670 net; do not sell before XD; the ~3% XD price drop is cash moving to him, not a loss; pre-XD adds repurchase his own dividend at a 10% tax cost). Added a new `oil_regime_read_2026_08_04` section flagging the **double Q3 headwind** (draining premium + maintenance volume dip) and re-framing the thesis as **income-led, not price-led**.
3. **`portfolio_engine/dividend_tracker.py`** *(new seed record — first CONFIRMED forward dividend)* — Added the FY2026 PTTEP interim `DividendRecord` (THB 4.50, XD 2026-08-14, record 08-15, pay 08-28, `source="SET_announcement"`) at the head of `seed_known_dividends()`. This is the first non-estimated forward-dated record in the seed, so **`upcoming_ex_dates()` will now fire a real 5-day alert** as XD approaches instead of returning empty. Notes carry the entitlement math and the do-not-add-pre-XD guidance. Additive — no existing record touched.
4. **`data/watchlist.json`** *(refresh + oil re-rank + ex-date resolution)* — meta + top-level `last_updated`->2026-08-04; **BAFS re-priced 9.25->9.80** and **PTTEP 148->151.0** (both fresh Aug-04 prints, priors preserved); added a structured `interim_dividend_2026` block to PTTEP; `note_aug04` + `oil_regime_aug04` on all four holdings; **14 `aug04_` macro keys** (headline, oil re-rank, oil counterweight, Brent 81, gold 4068.68, FX 33.396, US records, SET range, Asia, Vietnam FTSE, PTTEP ex-date, watch list); 4 new catalyst dates (Aug-04, 08-14, 08-21, 08-28). macro_context now **452 keys**; duplicate-key scan -> NONE.
5. **`data/snapshots/2026-08-04.json`** *(new file — two genuinely fresh holding prints)* — BAFS 9.80 and PTTEP 151.0 marked to the Aug-04 tape; SCB 155.00 carried. Total ex-gold **THB 606,760** (**+THB 14,210** vs Aug-03: BAFS +10,010, PTTEP +4,200). Added a `concentration_note` (SCB 35.8%, PTTEP 34.8%, BAFS 29.4% — two positions over the 30% flag) and a 7-item catalyst list. `risk_score` null (Postgres path can't run in sandbox).
6. **`data/market_intel/2026-08-04.md`** *(new file)* — 6-section report + oil re-rank table + 5 risk flags; >=2 sources per major item.

### Verification
`ast.parse` clean on `oil_scenario.py` and `dividend_tracker.py`. Isolated scan: `probability_pct` = **[12,33,30,15,10] sum=100**; weighted-Brent recompute -> **$88.69** (down from $93.14, correctly converging toward but still above the ~$81 spot as the tails keep pricing unrepaired physical damage). `watchlist.json` reloaded via `object_pairs_hook` **duplicate-key scan -> NONE** (452 macro keys; last_updated 2026-08-04 both meta + top-level; 14 aug04_ keys; BAFS 9.8 / PTTEP 151.0 / XD 2026-08-14). Snapshot arithmetic checked: BAFS 18,200x9.80=178,360; PTTEP 1,400x151=211,400; SCB 1,400x155=217,000; Sum=**606,760** (delta +14,210 = 18,200x0.55 + 1,400x3.00 = 10,010+4,200 ✓); weights recomputed 29.4/34.8/35.8%. All three edited/new JSON files `json.load` clean. News cross-checked >=2 outlets per item (oil/Iran: The National + CNN + Bloomberg + Trading Economics; PTTEP dividend: ThaiPR + energy-pedia + PTTEP IR; US: Yahoo + TheStreet + CNN; gold: Yahoo + CNBC Select + FXLeaders; FX: Trading Economics + Investing.com; regional/VN: India TV + Trading Economics + ACBS + Vietnam Briefing). **Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `run_oil_scenario_report()` / `generate_daily_brief()` / `upcoming_ex_dates()` weren't exercised end-to-end — edits are additive and the math/loaders verified in isolation; (b) **no clean SET close for SCB** — carried 155.00 (Jul-24); PTTEP 151.0 taken from a TradingView snapshot quoted -1.99%, BAFS 9.80 from Investing.com, both intraday-ish rather than confirmed official closes; (c) SET Aug-04 close itself not retrievable — logged the 1,616.56-1,631.58 range; (d) a **"JP Morgan $6,300 gold by end-2026"** headline surfaced from a secondary aggregator — **NOT adopted**, it conflicts with the pinned JPM 4500 and is unverified; (e) PTTEP 2026 **capex figure still unretrievable** — sub-watch held open; (f) the Aug-04 nightly slot was **missed** and this run backfills it.

### Next Priority (for next run)
**Digest the US July jobs / NFP report (~Aug-07)** — the week's macro gauge; the record highs were made into an unresolved labour print, so a weak number tests both the AI rebound and the Fed path. **Track the oil two-sider, now the single most important input**: if Iran converts the Oman "temporary corridor" into a real reopening -> shift further onto deal_signed toward Goldman ~$80 (more PTTEP erosion, more BAFS tailwind); if Trump's "duplicitous" read converts back into action -> snap the tails toward $105-120. **Capture BAFS H1-2026 results (~Aug-14)** — the first hard read on whether the oil relief is reaching margins; create `data/earnings/bafs_h12026_*.json` on the PTTEP pattern. **Confirm PTTEP XD passes cleanly on Aug-14** and log the ex-date price drop vs the THB 4.50 theoretical. **Watch the SCB 2026 interim declaration (Aug-Sep)** — still undeclared. **FTSE Vietnam constituent list Aug-21** — decide whether to open a formal VNM watch entry with a sizing view before the Sep-21 effective date. Lower priority: reconcile clean official SET closes; re-confirm the PTTEP 2026 capex figure.

---
## Nightly Run — 2026-08-05 02:30 ICT

### Market Intelligence Summary
The night's decisive item is that **the $80 floor BROKE**: Brent fell a further **5.13% to $79.47** (Aug-04) — the **first sub-$80 print of the entire conflict series** and below Goldman's ~$80 full-reopen anchor — after Trump said another US-Iran talks round would convene Monday Aug-04. This is **confirmation of the Aug-04 regime change, not a new one**, and three counterweights were deliberately kept: Iran **again denied direct US talks** (only the Oman corridor track is live), **Rubio confirmed NO final agreement**, and **Trump framed the round as Iran's "LAST CHANCE."** Second decisive item: **gold ROSE ~1% to $4,110-4,136 DESPITE record US equity highs** — bid on Fed rate-cut repricing after softer labour data, a weaker dollar and central-bank buying (Bank of Korea), **not** on Iran fear. US closed at records (Dow **53,178.41**, an all-time close).

### Thai Holdings Update
- **BAFS**: price **held 9.80** (Aug-04; no fresh clean close). Still the clean beneficiary of Brent at ~-20.5% from the ~$100 late-July peak — but the transmission is **indirect and lagged** (service fee per litre; benefit arrives via airline scheduling → throughput over 1-2 quarters). H1 est. Aug-14; investor meeting confirmed Aug-28.
- **PTTEP**: **151.0 → 145.0** (Aug-04 open 145.00 / high 146.00 / low 143.00) — gave back ~4% of the post-Q2 rally **exactly as the Aug-04 re-rank warned**. No new company information; breakeven ~$45 Brent means $79 is **premium erosion, not a thesis break**. Hold for the **income**: THB 4.50 interim, **XD Aug-14**, last cum day **Aug-13**, pay Aug-28 → THB 6,300 gross / ~5,670 net. Do not add before XD.
- **SCB**: **155.00 (Jul-24, stale) → 151.50** (TradingView Aug-04). ⚠️ A **137.50** quote from a Google Finance/MSN snippet was **NOT adopted** — it matches the stale 2026-06-11 figure already in `scb_h12026_preview.json`, i.e. a re-served June quote, not an 8.9% crash. 2026 interim **still undeclared**. **BOT held at 1.00%, next MPC Aug-26, and 3 of 27 economists now see a 25bp HIKE by year-end — NIM-supportive upside skew.**
- **Gold Fund (SCBGOLDE)**: gold ~$4,110 × USD/THB 33.28 → est NAV **~4.18 THB/unit** (from ~4.15).

### Technology Sector Highlight
US indices at records on the oil crash feeding an AI-trade rebound (S&P 7,600.50 +1.5%, Nasdaq 25,913.90 +2.1%, Dow all-time close). **AMD reported Q2 after the close Aug-04** (cons. ~$1.61 EPS / ~$11.31bn rev; data-centre ~$6.5bn vs $3.2bn yr-ago) having run **~8% INTO** the print after a 140% YTD run — a high bar; **reaction not yet retrievable, digest next run**. **US July NFP Fri Aug-07**: cons. +80k, u-rate 4.2%, AHE +3.5% — the records were made INTO an unresolved labour print, and softer labour is simultaneously what is bidding gold. Asia lagged (Nikkei +0.32%, Shanghai +0.33%, Hang Seng -0.60%, Nifty -70.4 at the open). **ECB expected to hold at 2.25% but markets price ~70% odds of a SEPTEMBER HIKE** — sub-$80 Brent weakens Lagarde's second-round-inflation argument, a mild dovish input.

### Improvements Implemented Tonight
1. **`portfolio_engine/oil_scenario.py`** *(re-ranked — THE $80 FLOOR BROKE)* — Added a `2026-08-05` re-rank block. Modest further migration (the large move already happened Aug-04): **deal_signed 12→15** (spot has traded THROUGH this scenario's $76-80 zone), **deal_partial 33→34** (still MODAL — Rubio's "progress, no agreement" IS this scenario), **status_quo 30→27 with anchor 82→79** (mark to $79.47), **lebanon 15→14**, **nuclear HELD at 10** — deliberately not trimmed, because "last chance" + no signature is precisely this path's trigger language. Sum 100; weighted Brent **$88.69 → $87.49**. Rewrote the affected qualitatives + status_quo narrative, appended an Aug-05 clause to `probability_weighted_outlook()`, moved `run_oil_scenario_report()` default **82.0 → 79.5**. Additive; every change carries a `2026-08-05` marker.
2. **`data/earnings/bafs_h12026_preview.json`** *(new file — CLOSES THE TOP QUEUED PRIORITY)* — First BAFS earnings preview, on the PTTEP/SCB pattern. Sections: `_meta` (est. Aug-14 print, confirmed Aug-28 investor meeting, Aug-09 alert), `price_context`, **`structural_model`** (the important one — BAFS charges a **service fee per litre** and does **not** take fuel-price risk, so oil transmits **indirectly and lagged** via airline scheduling → throughput; explicitly flags the "BAFS is a short-oil proxy" mistake), `house_estimates` (marked **LOW confidence** — no broker consensus was retrievable), `reaction_scenarios` (beat-on-volume / in-line / **miss-on-volume**, the risk the +5.9% rally is not pricing), `key_watch_items`, `oil_regime_context_2026_08_05`, `advisory_note_for_tho`, `next_actions_for_nightly_agent`. **Core framing: H1 = Jan-Jun, when Brent was mostly ELEVATED, so the August oil relief CANNOT be in these numbers — judge the print on THROUGHPUT, not margin. The undiscussed risk is Thai arrivals (~-8% YoY through Jan-Nov 2025; World Bank cut 2026 Thai growth to 1.6% partly on tourism), not oil.**
3. **`portfolio_engine/earnings_tracker.py`** *(loader wiring)* — Added `"BAFS.BK": "bafs_h12026_preview.json"` to `load_earnings_preview().preview_map` with a dated rationale comment, and extended the docstring. `load_earnings_preview('BAFS.BK')` now returns the preview so the brief can surface it ahead of Aug-14. No logic changed; no existing entry touched.
4. **`data/watchlist.json`** *(refresh + oil re-rank + SCB re-mark)* — meta + top-level `last_updated`→2026-08-05, `usd_thb_rate`→33.28; **PTTEP re-priced 151.0→145.0** and **SCB 155.0→151.5** (priors preserved, 137.50 conflict documented as rejected); `note_aug05`/`oil_regime_aug05` on all four holdings; BAFS `earnings_preview_file` pointer added; **14 `aug05_` macro keys** (headline, oil counterweight, oil re-rank, Brent, gold, FX, US market, US macro/NFP, Thailand/BOT, Asia, Europe/ECB, Vietnam FTSE, portfolio read, watch list); 4 new catalysts (Aug-04, Aug-07 NFP, **Aug-13 last cum day**, Aug-26 BOT MPC). macro_context now **466 keys**; duplicate-key scan → NONE.
5. **`data/snapshots/2026-08-05.json`** *(new file)* — Total ex-gold **THB 593,460**. Introduced a **`delta_attribution` + `prior_total_restated_thb`** field to separate the genuine day move from a mark correction: the headline -THB 13,300 vs Aug-04 is **-THB 8,400 real** (PTTEP 1,400 × -6.00) **plus -THB 4,900 of stale-mark correction** on SCB (155.00 was a 12-day-old carry). Weights **SCB 35.7 / PTTEP 34.2 / BAFS 30.1** — all three now at or over the 30% flag. Added `price_caveats` and an 8-item catalyst list. `risk_score` null (Postgres path can't run in sandbox).
6. **`data/market_intel/2026-08-05.md`** *(new file)* — 6-section report + oil re-rank table + 5 risk flags; ≥2 outlets per major item.

### Verification
`ast.parse` clean on `oil_scenario.py` and `earnings_tracker.py`; `json.load` clean on all new/edited JSON. Isolated scan of the Aug-05 scenarios block: `probability_pct` = **[15,34,27,14,10] sum=100**; weighted-Brent recompute → **$87.49** (down from $88.69, correctly converging toward but still ~$8 above the $79.47 spot as the tails keep pricing unrepaired damage and an unsigned deal); `run_oil_scenario_report()` default confirmed at 79.5. `preview_map` wiring confirmed and both mapped files confirmed present on disk. `watchlist.json` reloaded via `object_pairs_hook` **duplicate-key scan → NONE** (466 macro keys; last_updated 2026-08-05 both meta + top-level; 14 `aug05_` keys; PTTEP 145.0 / SCB 151.5). Snapshot arithmetic re-derived: 18,200×9.80=178,360; 1,400×145=203,000; 1,400×151.5=212,100; Σ=**593,460** ✓; restated day move **-8,400 = 1,400×(145-151)** ✓; weights sum 100.0 ✓. News cross-checked ≥2 outlets per item (oil/Iran: The National + Bloomberg + Trading Economics + Al Jazeera; US: Yahoo + TheStreet + Benzinga; AMD: TIKR + Seeking Alpha + 24/7 Wall St.; gold: Forbes Advisor + CNBC Select + Yahoo + FXLeaders + tiomarkets; FX: Long Forecast + exchangerates.org.uk; Thailand/BOT: Bangkok Post + BOT + Nation Thailand + World Bank; NFP: Continuum Economics + BLS + Kiplinger; Vietnam: Vietnam Briefing + Vietnam News + ACBS; Europe: Investing.com + Yahoo UK + MarketScreener).
**Caveats:** (a) cross-package imports + Postgres/venv can't run in this sandbox, so `run_oil_scenario_report()` / `generate_daily_brief()` / `load_earnings_preview()` weren't exercised end-to-end — edits are additive and the math/wiring/loaders were verified in isolation; (b) **no confirmed official SET closes this run** — PTTEP 145.00 is an Aug-04 intraday read (open 145 / high 146 / low 143), SCB 151.50 is a TradingView quote, BAFS 9.80 is carried from Aug-04; (c) the **SCB 137.50** figure was rejected as a stale re-served 2026-06-11 quote — flagged, not adopted, re-confirm next run; (d) **AMD Q2 reaction not yet retrievable** (reported after close Aug-04); (e) BAFS `house_estimates` are explicitly LOW confidence — **no broker consensus on BAFS H1-2026 was retrievable**, and the release date remains ESTIMATED at Aug-14; (f) a "JPM $6,000/oz gold" headline surfaced again and was again NOT adopted (conflicts with the pinned JPM 4,500); (g) PTTEP 2026 capex figure still unretrievable — sub-watch held open.

### Next Priority (for next run)
**Digest the US July NFP (Fri Aug-07, cons. +80k / 4.2%)** — the week's decisive macro gauge, and the one input currently driving BOTH the equity records and the gold bid; a weak number is *simultaneously* good for the gold sleeve and a risk to the AI-trade rebound. **Digest the AMD Q2 reaction** (reported after close Aug-04 having run ~8% into the print — AI-trade risk gauge). **Confirm the BAFS H1 release date** on the SET/BAFS IR calendar (currently ESTIMATED Aug-14) and stand ready to write `data/earnings/bafs_h12026_actual.json` + add `BAFS.BK` to `load_earnings_actual().actual_map`. **Confirm PTTEP XD passes cleanly Aug-14** and log the ex-date drop vs the THB 4.50 theoretical; note **Aug-13 is the last cum day**. **Decide the Vietnam question BEFORE Aug-21** — the FTSE constituent list + cap thresholds publish Aug-21 for the Sep-21 effective date; this is the highest-conviction medium-term regional catalyst on the board and Tho has zero exposure, so the deliverable is a formal VNM watch entry with an explicit sizing view *and* an FX/fee cost estimate (his stated concerns), not just a note. **Track the oil two-sider, still the single most important input**: a signature out of the "last chance" round → Goldman $76-80 (more PTTEP erosion, more BAFS relief); a collapse → tails snap to $105-120. **Re-confirm a clean official SET close** for all three names and re-verify the SCB 151.50 vs 137.50 conflict. Lower priority: PTTEP 2026 capex figure; consider whether the standing 30%+ concentration on all three positions warrants a formal `rebalancer.py` proposal rather than a recurring note.

---


## Nightly Run — 2026-08-06 02:30 ICT

### Market Intelligence Summary
The night's decisive item is that the Hormuz de-escalation moved from rhetoric to a **DRAFTED 60-DAY INTERIM DEAL**: the US, Iran and Oman are near an agreement with concrete terms — inbound ships routed north through Iranian territorial waters, outbound south through Omani waters, **no transit tolls**, main-lane naval **mines cleared within 30 days**, then two-way traffic under a permanent arrangement **still to be negotiated**. Qatar confirmed a draft; Trump said "more within 48 hours"; Axios reported Washington aimed to announce as early as Aug-05. This is **deal_partial crystallising, not deal_signed arriving**. The counterweight is severe and specific: the same parties struck a materially similar interim deal in **JUNE 2026 and it COLLAPSED** over hostilities on this same strait. The single most useful observation is that **Brent ROSE back above $80** on the news rather than extending its fall — the tape has already paid for this de-escalation and has stopped being rewarded for incremental good news. Second item: **gold rose a third straight session to ~$4,184** driven by the *inverse* of July's logic — de-escalation lowers energy-inflation expectations, which pulls forward Fed rate-cut pricing.

### Thai Holdings Update
- **BAFS**: **9.80 carried (Aug-04)** — no fresh clean SET close retrievable. Oil relief intact vs the ~$100 late-July peak but no longer improving. Standing correction holds: BAFS charges a **service fee per litre** and does not take fuel-price risk — judge the H1 print (est. ~Aug-14) on **throughput, not margin**; the underdiscussed risk is Thai arrivals. Investor meeting confirmed Aug-28. Weight 30.05%.
- **PTTEP**: **145.00 carried (Aug-04 intraday)**. A **162.50** quote surfaced in search and was **NOT ADOPTED** — irreconcilable with the Aug-04 range (145.00 / 146.00 / 143.00). 🚨 **Aug-13 is the last cum day** for the THB 4.50 interim (XD Aug-14, pay Aug-28) → **THB 6,300 gross / ~5,670 net**. Hold through it; do not add before XD. Weight 34.21%.
- **SCB**: **151.50 carried (Aug-04)**. 2026 interim **still undeclared** (2025 ref: THB 2.00 paid 2025-09-19). The rejected **137.50** stale-quote conflict remains unre-verified. Least oil-sensitive — neutral tonight. BOT MPC Aug-26 (policy 1.00%). **Largest position at 35.74%.**
- **Gold Fund (SCBGOLDE)**: gold **$4,110 → ~$4,184**, USD/THB **33.28 → 33.09** → est NAV **~4.18 → ~4.23 THB/unit**. Gold was **+1.80% in USD but only ~+1.22% in THB** — the stronger baht gave back about a third of the move, a live example of the unhedged FX cost this project tracks.

### Technology Sector Highlight
US indices closed at **record highs Aug-04** (Dow **54,085.88** +1.7%/+907pts, S&P **7,736.52** +1.8%, Nasdaq **26,584.99** +2.6%); Aug-05 was mixed — Dow and S&P climbed on the Hormuz headline while the **Nasdaq gave up its gains**. **AMD beat and fell ~8.9%**: record revenue $11.536bn (+50% YoY vs $11.284bn est), adj EPS $1.66 vs $1.62, record data-centre $6.72bn vs ~$6.5bn est — but the stock had run ~21% into the print and a report that SpaceX would drop AMD chips for Nvidia's Blackwell compounded it. **The bar in AI hardware is now set by positioning, not results.** Asia rallied Aug-05 (Nikkei +3.66% to 66,300.44, Shanghai +1.47% to 3,878.43, Hang Seng +0.24%, Sensex +626pts). **US July NFP Fri Aug-07**: cons. ~80-120k, u-rate expected to **rise to 4.3%** — a crosswind, since softer labour bids gold *and* threatens the equity tape.

### Improvements Implemented Tonight
1. **`portfolio_engine/oil_scenario.py`** *(re-ranked — DRAFTED 60-DAY INTERIM HORMUZ DEAL)* — Added a `2026-08-06` re-rank block. **deal_signed 15→17** (a signed permanent lane is now the defined end-state of a live drafted process, but sits BEYOND the 60-day window — deliberately only +2), **deal_partial 34→38** (a drafted 60-day interim corridor IS this scenario by definition; decisively **MODAL**), **status_quo 27→24 with the anchor marked UP 79→80.5** — an unusual pairing, made deliberate and explained in the narrative: mass migrates to de-escalation while spot *rose*, which is the evidence that the move is priced. **lebanon 14→12** (30-day mine-clearing addresses the unrepaired physical damage), **nuclear 10→9** (only −1: a 60-day clock expiring unsigned re-arms this in early October, and June's equivalent already collapsed once). Sum 100; weighted Brent **$87.49 → $87.11**. Rewrote the affected qualitatives + status_quo narrative, appended an Aug-06 clause to `probability_weighted_outlook()`, moved `run_oil_scenario_report()` default **79.5 → 80.5**. Additive; every change carries a `2026-08-06` marker.
2. **`portfolio_engine/foreign_access_cost.py`** *(NEW MODULE — closes the top queued priority)* — All-in cost of reaching a **foreign** market from a THB base, the gap `fee_analyzer.py` never covered (it prices only what Tho already owns). Models six cost lines: FX spread paid twice, commission **with a minimum-ticket floor**, fund loads, TER over the horizon, dividend withholding by jurisdiction, and — the line retail analysis omits — **structural currency drift** for managed-float currencies. Ships `CURRENCY_DRIFT_VS_USD` and `DIVIDEND_WITHHOLDING_PCT` registries, an `AccessRoute` dataclass, `access_cost()`, `compare_routes()`, and a worked `vietnam_access_report()`. Returns `breakeven_gross_return_pct` so a route can be compared directly against an idea's expected return, and raises explicit flags for a binding commission minimum, material currency drift, and **US estate-tax situs** (USD 60k NRA exemption). Written with **zero third-party imports and a guarded `utils.common` import specifically so it RUNS in the sandbox** — earlier nightly runs repeatedly logged "could not exercise end-to-end", and this module does not have that problem.
3. **`data/research/vietnam_ftse_2026.json`** *(NEW FILE — the queued Aug-21 decision, DECIDED)* — Full decision file: catalyst timeline, the widened **32-stock** eligible screen, market context, the costed route comparison, a diversification assessment, and an explicit verdict with falsification conditions. **Verdict: DO NOT BUY for this catalyst.** All-in cost of a 5%-of-book 24-month position is **10.80%** (Thai feeder) to **12.00%** (VNM US ETF) before the market does anything. Largest single cost on **both** routes is **VND structural drift ~6%/24m** — larger than either TER, and a near-certain drag rather than two-sided risk. The USD 15 commission floor is **1.67%** of a ~USD 897 ticket. Tripling the size to 15% of book only improves the best route **10.8% → 9.8%** — there is no size at which this becomes cheap. Also flags that the catalyst has been public since **Oct-2025** (a known-date passive flow is the most efficiently front-run event class), and that it is the **wrong instrument for the problem** it is proposed to solve, since Vietnam is a correlated ASEAN neighbour. Includes `explicitly_not_claimed` (this is not a view that Vietnam is a bad market) and five `next_actions_for_nightly_agent`.
4. **`portfolio_engine/rebalancer.py`** *(new function — the concentration question, finally expressed as code)* — Added `single_name_concentration_review()` plus `_load_snapshot_json()` and the `SINGLE_NAME_FLAG_PCT` / `SINGLE_COUNTRY_FLAG_PCT` constants. The existing `generate_rebalancing_plan()` rebalances by **asset class**, which is structurally blind twice over: it cannot see single-NAME concentration (three stocks and thirty look identical if both are "equity") and cannot see single-COUNTRY concentration **at all**. That is why the concentration issue has recurred as prose for weeks without ever becoming a proposal — no code path could express it. The new function runs **off the snapshot JSON with no Postgres, no LLM and no network**, and **proposes rather than trades**. It returns per-position weights, breach flags, trim sizes in THB *and shares*, country weights, and four honesty fields: `what_this_does_not_solve`, `mechanical_trim_caveat`, `sequencing_note` (selling PTTEP before Aug-13 forfeits ~THB 6,300 of entitled income to fix a few points of weight) and `cheapest_correction_first`.
5. **`data/watchlist.json`** *(refresh + oil re-rank + Vietnam decision)* — meta + top-level `last_updated`→2026-08-06, `usd_thb_rate`→33.09; `note_aug06` on all four holdings plus `oil_regime_aug06` on BAFS/PTTEP, `concentration_weight_pct_aug06` on all three equities, `est_nav_thb_per_unit_aug06` 4.23 on SCBGOLDE; **16 `aug06_` macro keys** (headline, oil counterweight, oil re-rank, the key observation, Brent, gold, FX, US market, AMD, NFP, Asia, Vietnam FTSE, **Vietnam decision**, concentration, portfolio read, watch list); 5 catalyst dates added/confirmed (Aug-07, Aug-13, Aug-21, Sep-21, ~Oct-04). macro_context now **482 keys**; duplicate-key scan → NONE.
6. **`data/snapshots/2026-08-06.json`** *(new file)* — Total ex-gold **THB 593,460, unchanged**, and the file says plainly that this is **an absence of data, not a flat market** (`marks_are_carried: true`, zero delta "by construction"). The genuinely new content is the **gold sleeve re-mark** (with the FX-offset arithmetic spelled out) and the **first embedded `concentration_review`**. Adds `price_caveats` documenting the rejected PTTEP 162.50, the unre-verified SCB 137.50, and ~$120/oz of gold feed dispersion, plus an 8-item catalyst list.
7. **`data/market_intel/2026-08-06.md`** *(new file)* — 6-section report + the oil re-rank table + the Hormuz deal-terms table + the Vietnam cost table + the concentration table + 5 risk flags; ≥2 outlets per major item.

### Verification
`ast.parse` clean on `oil_scenario.py`, `rebalancer.py` and `foreign_access_cost.py`; `json.load` clean on all new/edited JSON. **`foreign_access_cost.py` was EXECUTED end-to-end** (`python3 foreign_access_cost.py`) — this is the first nightly run where a new module was actually run rather than only parsed; outputs reproduced: 5%-of-book 24m → th_feeder 10.80% / vnm_us_etf 12.00%, and the 15%-of-book sensitivity → 10.80% / 9.78% with `commission_minimum_is_binding: true` in both cases. **`single_name_concentration_review()` was also EXERCISED** by AST-extracting it into a clean namespace (the module's `utils.common`/`asyncpg` imports are unavailable in the sandbox) — it reproduced SCB 35.74 / PTTEP 34.21 / BAFS 30.05, TH 100.0%, and total trim **THB 59,346** (34,062 + 24,962 + 322 ✓). Isolated scan of the Aug-06 scenarios block: `probability_pct` = **[17,38,24,12,9] sum=100**; weighted-Brent recompute → **$87.11** (76×17 + 84×38 + 80.5×24 + 105×12 + 115×9 = 8,711/100), correctly still ~$6.6 above the ~$80.5 spot as the tails keep pricing an unsigned deal and unrepaired damage; `run_oil_scenario_report()` default confirmed at 80.5. `watchlist.json` reloaded via `object_pairs_hook` **duplicate-key scan → NONE** (482 macro keys, 16 `aug06_` keys, last_updated 2026-08-06 both meta + top-level, fx 33.09). Gold NAV arithmetic re-derived: 4.18 × (4184/4110) × (33.09/33.28) = **4.231 → 4.23** ✓; THB-measured gain 1.0180 × 0.99429 − 1 = **+1.22%** vs +1.80% in USD ✓. News cross-checked ≥2 outlets per item (Hormuz: Axios + Israel Hayom + Boston Globe + PBS + Al Jazeera + The National; oil: Trading Economics + The National; gold: Yahoo + CNBC Select + Trading Economics + InteractiveCrypto; FX: Trading Economics; US: Yahoo/Zacks + TheStreet + CNN; AMD: CNBC + Investing.com + INDmoney + TIKR; NFP: Continuum + BLS + Kiplinger; Asia: India TV + ARMENPRESS; Vietnam: The Investor + Vietnam News + CNBC + Vietnam Briefing + ACBS; VNM ETF: VanEck + ETFdb).
**Caveats:** (a) **NO fresh clean SET closes for any holding** — all three equity marks carried from Aug-04, so the zero portfolio delta is an absence of data, not a flat market; (b) a **PTTEP 162.50** quote was surfaced and **REJECTED** (irreconcilable with the Aug-04 145/146/143 range — likely a different board or stale listing); the **SCB 137.50** conflict remains unre-verified; (c) **gold feed dispersion was unusually wide** — $4,183.85 (Yahoo) to $4,304.30 (Convex), ~$120/oz; the conservative $4,184 was taken and the range logged rather than averaged; (d) the Aug-05 US close was not cleanly separable from the Aug-04 record close in the available reporting — the Aug-04 record figures are used and Aug-05 is described qualitatively as mixed; (e) the `th_feeder_fund` route in the cost model uses **GENERIC placeholder fees** (~1.9% stacked TER, 1% front load) and is marked LOW confidence — no specific Thai Vietnam fund factsheet was pulled; likewise the 0.25% / USD 15 broker tariff is representative, not Tho's actual tariff; (f) the diversification correlation claim in the Vietnam file is **structural reasoning, not a measured statistic**, and is labelled as such; (g) the ~USD 6bn Vietnam passive-inflow figure is LOW confidence — repeated across secondary sources without consistent methodology; (h) cross-package imports + Postgres/venv still cannot run in this sandbox, so `run_oil_scenario_report()` / `generate_daily_brief()` / `generate_rebalancing_plan()` were not exercised end-to-end; (i) PTTEP 2026 capex figure still unretrievable — sub-watch held open.

### Next Priority (for next run)
**Digest the US July NFP (Fri Aug-07)** — the week's decisive gauge and an explicit crosswind: softer labour bids the gold sleeve while threatening the record-high equity tape. **Confirm whether the Hormuz interim deal was actually SIGNED** inside Trump's "48 hours" — a draft is not a signature, June's equivalent collapsed, and an unsigned 60-day expiry (~Oct-04) re-arms the escalation tails; if signed, consider whether `deal_partial` should convert toward `deal_signed`. **Aug-13 is the hard dated item** — confirm PTTEP trades cum through Aug-13 and log the Aug-14 XD drop against the THB 4.50 theoretical. **Capture BAFS H1-2026 (~Aug-14)** on the PTTEP pattern into `data/earnings/bafs_h12026_actual.json` and wire `BAFS.BK` into `load_earnings_actual().actual_map` — judge on throughput, not margin. **Re-verify clean official SET closes for all three names** and resolve both open quote conflicts (PTTEP 162.50, SCB 137.50); the portfolio has now gone two runs without a confirmed close, which is the weakest link in the whole pipeline. **Lift the `th_feeder_fund` route from LOW confidence** by pulling a real Thai Vietnam fund factsheet, and replace the placeholder broker tariff in `foreign_access_cost.vietnam_routes()` with Tho's actual offshore tariff — the Vietnam verdict does not depend on it, but the module will be reused for every future foreign idea and should be accurate before then. **Run a Thailand/Vietnam (and Thailand/EM) equity correlation study** to convert the diversification hypothesis into a measured number — this is the missing input for any real answer to the 100%-country-weight problem. Watch the **SCB 2026 interim declaration** (still undeclared) and **BOT MPC Aug-26**. Lower priority: PTTEP 2026 capex; add a materiality threshold to `single_name_concentration_review()` so a 0.05% breach like tonight's BAFS does not surface as an action.

---
## Nightly Run — 2026-08-07 02:30 ICT

### Market Intelligence Summary
Tonight's decisive item is **not** Hormuz — it is the **baht**. THB hit a **13–15 month low at 33.39–33.64** (from 33.09), now **−5.5% YTD**, and the stated cause chain runs straight through this project's existing models: a **high oil price → a larger energy import bill → a current-account deficit → a weaker baht**, compounded by off-peak tourism, moderating export momentum and a **BOT pinned at 1.00%** against a Fed that has not cut. Bangkok Post reports **capital fleeing Thai stocks**; foreigners sold a reported **THB 6.7bn**. On Hormuz, the news split in two directions at once and that split is the night's analytical call: the **bilateral leg firmed** (Iran and Oman agreed the route **coordinates in principle** — Bloomberg Aug-06 — plus sovereignty terms and a joint coordination centre, with the arrangement's life now stated at **2–4 months, not 60 days**) while the **trilateral leg did not** (Iran says the Iran–Oman deal does **not** by itself reopen the waterway and the **US must meet additional conditions**; Trump's "48 hours" lapsed unsigned; CNN's read is that the shape emerging is **"not one Trump wants"**). Third data point: **Brent ~$83.64, essentially unchanged**, on the day the coordinates were agreed — the **third consecutive session** where de-escalation news failed to push crude down.

### Thai Holdings Update
- **BAFS**: **9.80 carried (Aug-04)** — third run without a confirmed close. Standing correction holds: BAFS charges a **service fee per litre** and does not take fuel-price risk — judge H1 (~Aug-14) on **throughput, not margin**. New FX angle from tonight's module: a weaker baht makes Thailand a cheaper destination, a **mild, long-lagged positive** for arrivals and therefore throughput — real but swamped by the arrivals cycle, so not an FX hedge. Investor meeting Aug-28. Weight 30.05%, now classified **immaterial** (see below).
- **PTTEP**: **145.00 carried (Aug-04)**. 🚨 **Aug-13 is the last cum day** for the THB 4.50 interim (XD Aug-14, pay Aug-28) → **THB 6,300 gross / ~5,670 net**. Hold through it; do not add and **do not trim** before XD. A **147.00 (Jul-21)** reference and a 160.82 12-month average target surfaced — neither is a fresh close; the rejected **162.50** did **not** reappear. Weight 34.21%.
- **SCB**: **151.50 carried (Aug-04)**. 2026 interim **still undeclared**; confirmed references now pinned — 2025 interim **THB 2.00** paid **2025-09-19**, FY2025 total **THB 11.28** at an **80% payout**, final THB 9.28 paid 2026-05-07, and management's stated position that an interim "could be considered if performance meets expectations". Of the three, SCB is **most exposed to the foreign-outflow channel** driving the baht. **Largest position at 35.74%.**
- **Gold Fund (SCBGOLDE)**: gold **$4,184 → $4,252.59**, USD/THB **33.09 → 33.39** → est NAV **4.23 → 4.34 THB/unit**. Decomposed: **+1.64% in USD, +2.56% in THB — the currency ADDED 0.91pp, i.e. 35.4% of the gain.** This is the **exact mirror of Aug-06**, when a stronger baht gave back a third of the move. Two consecutive sessions, opposite signs: the unhedged FX line is **volatility, not a one-way drag** — which is a correction to how this log has characterised it.

### Technology Sector Highlight
US **Aug-06 close: Dow −0.7%, S&P 500 −0.1%, Nasdaq ~flat** on rising Treasury yields, earnings and the Hormuz headlines (Aug-04 record closes stand: Dow 54,085.88 / S&P 7,736.52 / Nasdaq 26,584.99). **US July payrolls land Friday Aug-07, after this run** — consensus **~80k** after 57k in June, u-rate forecast **steady at 4.2%**, with skew toward a higher u-rate given the Conference Board's "jobs plentiful" share falling in July to its **lowest since Feb-2021**; claims edged up but July planned layoffs hit a **two-year low**, a genuinely mixed set. **Semis**: global sales hit a record **$120.6bn in May 2026**, the **15th consecutive monthly record**, against a late-July selloff that removed **>$1tn** from chip names on "AI capex peaking faster than expected" fears — **Nvidia reports Aug-27**; Broadcom guides AI semi revenue **+200% YoY to $16.0bn**. Asia took a breather Aug-06 (**Nikkei 65,683.26 −0.93%, Hang Seng 25,530.28 −1.49%, Shanghai 3,900.35 +0.57%, Sensex +201pts**), **led lower by electronics and chip names**. Europe at record highs on earnings (**EU50 6,512 +0.49%**; DAX −0.1% on Siemens, FTSE +0.3%, CAC +0.7%).

### Improvements Implemented Tonight
1. **`portfolio_engine/currency_exposure.py`** *(NEW MODULE — the flagship)* — Separates the currency a position is **listed** in from the currency the underlying business **earns**. Written because the Aug-06 concentration review reported the book as **100% country-weight TH**, which is correct and misleading: PTTEP is a **THB instrument wrapped around a USD business** (USD-referenced revenue, USD functional currency), and every country/currency screen in this project counted it as fully domestic. Ships `CURRENCY_EXPOSURE_ASSUMPTIONS` (per-name `usd_revenue_share`, `thb_depreciation_beta`, confidence, basis, second_order and — deliberately — a **`how_to_falsify`** string on every entry), plus `look_through_currency_exposure()`, `fx_attribution()`, `oil_thb_transmission()`, `thb_scenario_table()` and `run_currency_exposure_report()`. **Result: 100% THB by listing, ~34.9% USD-linked by economics; portfolio beta to a 1% baht depreciation +0.094% — small but POSITIVE, so a weaker baht is mildly HELPFUL to this book.** The module also prices the **second channel from Brent to the portfolio** that `oil_scenario.py` never expressed: high oil → weaker THB → higher gold-sleeve NAV **and** higher PTTEP translated earnings, meaning **high oil is substantially SELF-HEDGING for this portfolio even though it is clearly negative for Thailand**. Every honesty field is present and load-bearing: `what_this_does_not_change` (the 100% TH country flag **STANDS** — look-through FX and country concentration are different risks), `the_dangerous_reading` (this is not an argument that the book is diversified), `where_it_breaks` (a **demand-led** oil collapse loses on every leg at once), `magnitude_caveat` (the entire FX scenario spread is smaller than one day's equity move — FX is second-order ex-gold and first-order only for the gold sleeve) and `NEXT_STEP_TO_MEASURE` (these are **structural assumptions, not regression betas**, and the exact regression required is specified). Zero third-party imports; **executed end-to-end** in the sandbox.
2. **`portfolio_engine/rebalancer.py`** *(materiality threshold — closes the queued lower-priority item)* — Added `MATERIALITY_MARGIN_PCT = 1.0` / `MIN_MATERIAL_TRIM_THB = 5000.0`, a per-position `material` flag, `material_name_breaches` / `immaterial_name_breaches` / `material_trim_thb`, an `immaterial_breach_note`, and a `status` that now keys off **material** breaches only. The Aug-06 run surfaced **BAFS at 30.05% against a 30.00% flag** as `action_suggested` — a 0.05pp breach, a **THB 322** trim, 32 shares. Two independent reasons that cannot be real: commission plus the 0.1% SET transaction levy consume a meaningful fraction of a THB 322 trade, and a 0.05pp weight difference is **far inside the uncertainty of a carried mark**. Immaterial breaches are still **reported**, just no longer actioned. Additive and backward-compatible — both thresholds are keyword arguments.
3. **`portfolio_engine/oil_scenario.py`** *(re-ranked — the bilateral/trilateral split)* — **deal_signed 17→14**, the **first downgrade of that path in the series**: an Iran/Oman-managed corridor under Iranian sovereignty is close to the **opposite** of the US-guaranteed free-transit regime the scenario requires, and a permanent lane got *further* away this session. **deal_partial 38→44**, now dominant by a wide margin — agreed coordinates, a joint coordination centre and a stated 2–4 month life *are* this scenario. **status_quo 24→21 with the anchor marked UP 80.5→83.5.** **lebanon HELD at 12** and **nuclear HELD at 9**, both deliberately: coordinates do not clear mines, the 30-day mine-clearing commitment has not started, the Jul-25 Yanbu/Jizan Red Sea damage is untouched by any Hormuz arrangement, and trimming again on the same headline would be double-counting; the nuclear tail is **postponed, not shrunk**. Sum 100; weighted Brent **$87.11 → $88.08** — note it **rose** while mass migrated to de-escalation, because the base *anchor* moved, not the tails. `run_oil_scenario_report()` default **80.5 → 83.64**, with the Brent/WTI feed dispersion recorded inline. Appended an Aug-07 clause to `probability_weighted_outlook()` including the new currency leg.
4. **`data/watchlist.json`** *(refresh)* — `last_updated` → 2026-08-07 (meta + top level), `usd_thb_rate` → 33.39; per-holding `note_aug07` plus **`usd_revenue_share` / `thb_depreciation_beta` / `fx_beta_confidence` written onto all four holdings** so the exposure assumptions live with the positions; `concentration_weight_pct_aug07` and the new `concentration_material_aug07` flag; **22 `aug07_` macro keys**; 4 catalysts added. macro_context now **504 keys**; duplicate-key scan → **NONE**.
5. **`data/snapshots/2026-08-07.json`** *(new file)* — Ex-gold **THB 593,460, unchanged for a third run**, and the file states plainly that this is an **absence of data, not a flat market** — with, for the first time, **positive evidence the market was not flat**: the SET index traded to a **low of 1,607.51 on Aug-06** against a **1,617.13 close on Aug-04**, alongside reported foreign net selling. Adds the first embedded **`currency_exposure`** block (per-position betas, the THB scenario table, the honesty fields), a fully decomposed **`gold_sleeve.fx_attribution`**, the **`oil_scenario_rerank`** block, 9 `price_caveats` and a 9-item catalyst list.
6. **`data/market_intel/2026-08-07.md`** *(new file)* — 8 sections: the baht headline with its causal chain, holdings, the Hormuz bilateral/trilateral table, the oil re-rank table, US/tech, a regional table, the full currency-exposure analysis, 8 risk flags and a dated calendar. ≥2 outlets per major item.

### Verification
`ast.parse` clean on `currency_exposure.py`, `rebalancer.py` and `oil_scenario.py`; `json.load` clean on both new/edited JSON files. **`currency_exposure.py` was EXECUTED end-to-end** (`python3 currency_exposure.py`) and its outputs independently re-derived by hand: economic USD share = (212,100×0.05 + 203,000×0.95 + 178,360×0.02)/593,460 = 207,022.2/593,460 = **34.88%** ✓; portfolio beta = 0.3574×(−0.30) + 0.3421×0.50 + 0.3005×0.10 = −0.10722 + 0.17105 + 0.03005 = **+0.09389 → 0.094** ✓. `fx_attribution()` reproduced the gold arithmetic: 1.016393 × 1.009066 − 1 = **+2.5608%** THB vs **+1.6393%** USD, FX share **35.4%**, cross term **+0.0149pp** reported rather than absorbed ✓; NAV 4.23 × 1.016393 × 1.009066 = **4.3383 → 4.34** ✓. **`single_name_concentration_review()` was EXERCISED** by AST-extracting it into a clean namespace (its `utils.common`/`asyncpg` imports are unavailable in the sandbox): it now returns **material `['SCB.BK','PTTEP.BK']`, immaterial `['BAFS.BK']`**, material trim **THB 59,024** against a total of **59,346** (difference **322** = the BAFS ticket ✓), with the immaterial note rendering correctly. Oil block re-scanned via AST: `probability_pct` = **[14,44,21,12,9] sum=100**; weighted-Brent recompute → **$88.08** (76×14 + 84×44 + 83.5×21 + 105×12 + 115×9 = 8,808.5/100) ✓; `run_oil_scenario_report()` default confirmed at **83.64**. `watchlist.json` reloaded via `object_pairs_hook` **duplicate-key scan → NONE** (504 macro keys, 22 `aug07_` keys). **Self-caught error, disclosed:** three of the `probability_qualitative` string edits initially **terminated their literals early and left orphaned trailing text**, breaking the module — caught by `ast.parse` immediately after the edits, repaired by truncating each line at its first valid terminator (683 / 665 / 453 stray characters removed), and re-verified. This is exactly why the parse gate runs before anything downstream. News cross-checked ≥2 outlets per item (Hormuz: Bloomberg + Al Jazeera + CNN + Axios; baht: Bangkok Post + Nation Thailand + Thailand Business News + Money & Banking + Trading Economics; BOT: Bangkok Post + itiger; oil: Fortune + Trading Economics; gold: CNBC + Fortune + JM Bullion + Yahoo; US: TheStreet + Yahoo + CNN; NFP: Reuters-via-Yahoo + Trading Economics; Asia: ARMENPRESS + India TV + STL.News; Europe: STL.News + Trading Economics; semis: CNBC + 24/7 Wall St. + Forbes; Vietnam: Vietnam Briefing + Vietnam News + The Investor + Investify; SCB: SCBX IR + MarketScreener + stockanalysis).
**Caveats:** (a) **THIRD consecutive run with no confirmed official SET close** for any holding — all three equity marks carried from Aug-04, so the zero delta is an absence of data; the SET index low of 1,607.51 is an **intraday low, not a close**, and cannot be used to mark positions; (b) **USD/THB source conflict on magnitude** — "13-month low of 33.40" vs "15-month low, 2026 low of 33.640"; direction corroborated four ways, **33.39 taken**, range logged; (c) **gold feed dispersion ~$56/oz** ($4,252.59 CNBC → $4,309 Yahoo) — conservative end taken; separately, last night's **rejected-as-high Convex $4,304 print now looks EARLY rather than wrong**, which is a mark against that rejection and is recorded as such; (d) **oil feed dispersion** — Brent $83.64 vs WTI $77.75 vs an unlabelled ~$75 crude print; the Brent-specific figure is used; (e) **the `thb_depreciation_beta` values are STRUCTURAL ASSUMPTIONS, not measured betas** — this is stated on every line of output, each carries a `how_to_falsify`, and `NEXT_STEP_TO_MEASURE` specifies the regression required; the SCB **−0.30** in particular is `medium_low` confidence and is the weakest number in the module; (f) the `oil_thb_transmission()` elasticity (**1.2% THB per $10 Brent**) is explicitly `low_order_of_magnitude_only` and the function states that at a 1–3 month horizon FX is dominated by rate differentials, not the current account, which it does **not** model; (g) the currency decomposition is **ex-gold** — the snapshot series tracks the gold sleeve by NAV per unit with no unit count, so including it would require a guess, and the module refuses to make one; (h) US July NFP releases **Friday Aug-07 after this run** and is not in these numbers; (i) cross-package imports + Postgres/venv still cannot run in this sandbox, so `run_oil_scenario_report()` / `generate_daily_brief()` / `generate_rebalancing_plan()` were not exercised end-to-end; (j) PTTEP 2026 capex still unretrievable and the SCB 137.50 conflict still unre-verified.

### Next Priority (for next run)
**Fix the SET price feed — this is now the top priority ahead of any new analysis.** Three runs without a confirmed close means every weight, every concentration flag and every portfolio delta in the last three snapshots rests on a stale Aug-04 mark, and tonight produced direct evidence (index low 1,607.51, reported foreign outflow) that the market moved while the book reported zero. Investigate `data_collector/market_data.py` and `diagnose_scraper.py` rather than searching for quotes again — **the retrieval path itself is the defect, not the availability of the data.** **Digest the US July NFP** (released Aug-07 after this run) and its crosswind: softer labour bids the gold sleeve and pressures the equity tape, and it is also the largest single input to the USD/THB differential now driving the baht. 🚨 **Aug-13 is the hard dated item** — confirm PTTEP trades cum through Aug-13 and log the Aug-14 XD drop against the THB 4.50 theoretical. **Capture BAFS H1-2026 (~Aug-14)** into `data/earnings/bafs_h12026_actual.json` on the PTTEP pattern and wire `BAFS.BK` into `load_earnings_actual().actual_map` — judge on **throughput**, and now also check whether management attributes any arrivals strength to the weak baht, which would be the first real test of the +0.10 beta. **Run the Thailand/Vietnam and Thailand/EM equity correlation study** — still the missing input to the 100%-country-weight problem, and now doubly needed because tonight's currency work could be misread as a partial answer to it. **Measure the FX betas properly**: load a 3-year daily series of the three names plus USDTHB into `data/research/` and regress each name's THB return on the USDTHB return with Brent as a control — until then the exposure module's headline number is an assumption, and the SCB −0.30 is the weakest link. **Confirm whether the Hormuz interim arrangement actually enters into force** and whether the US conditions are met; the expiry window has moved out to **Oct–Dec** on the 2–4 month framing. Also: **lift the `th_feeder_fund` route in `foreign_access_cost.py` from LOW confidence** with a real factsheet, watch the **SCB 2026 interim declaration** (undeclared; base case ~THB 2.00 around mid-September on the 2025 pattern) and **BOT MPC Aug-26** — where the baht at a 13–15 month low against a 1.00% policy rate is now a live tension rather than a background note.

---

## Nightly Run — 2026-08-08 02:30 ICT

### Market Intelligence Summary
The July US employment report missed badly — **nonfarm payrolls fell 23,000** against a **+80,000** consensus, the first decline in months — and the market's response ran through gold: **Comex December gold +2.3% to ~$4,401/oz**, a seven-week high, closing the week **+5%, the biggest weekly gain since January**. The nuance that matters is the direction of the Fed debate: this is a **hiking-bias regime**, not an easing one. Odds of a **September hike** fell to **43.9%** from 57%, with hold odds up to **56.1%** — the labour market is softening into an inflation backdrop still well above 2%, so a bad jobs print buys a *pause*, not a cut. Two-thirds of the payroll miss is public-sector (**government −53k, private +30k**), which is a softer read than the headline. Meanwhile the strongest tapes globally were ones Tho owns none of: **Nasdaq's best week since May** with semis **+5%**, and **European records on ~21% y/y earnings growth** revised up from 12.5% at quarter start — an earnings-led record rather than a multiple-led one.

### 🚨 The finding of the night: the price feed has been dead for 23 days
**The live market-data collector has not written anything since 2026-07-15 23:53 ICT.** Four independent, mutually corroborating pieces of evidence: `portfolio_snapshot.json` `generated_at` = **2026-07-15T11:30:14Z** (23.3d); `market_data_process.log` mtime **2026-07-15 23:53** with a tail ending in **`Shutdown requested by signal 15`**; log rotation stopping at **2026-07-14**; `heartbeat.json` stamped **2026-06-06** (62.3d).

The log tail is decisive — it is a **clean SIGTERM shutdown, not a crash**. The daemon was stopped deliberately (machine restart or manual stop) and **never brought back up**. This is a supervisor/launchd problem. **No amount of work on the fetch path would have fixed it.**

**This is a correction of three prior runs.** Aug-05, Aug-06 and Aug-07 each reported "no confirmed SET close" and each concluded the *retrieval path* was defective; Aug-07 explicitly queued "the retrieval path itself is the defect, not the availability of the data" as the top priority. **That diagnosis was wrong three times running**, and the Aug-07 run came within one step of catching it — it observed a SET index low of 1,607.51 and reported foreign outflows, direct evidence the market had moved while the book showed zero, and still attributed the gap to a scraper. The reason the wrong answer survived three iterations is structural: **a dead daemon and a broken parser are indistinguishable from downstream.** In both cases the last price simply stops advancing. Nothing in this codebase attached an *age* to a price, so a 23-day-old mark rendered identically to a fresh one, and a zero delta read as "flat market" when it meant "nobody asked the market."

### Thai Holdings Update
- **BAFS** — no confirmed close, 4th run. Mark carried at **9.80** (Aug-04). An undated ~9.25 quote surfaced in search and was **rejected as unverifiable**. Brent ~$83.29 sits in neither the sub-$80 relief zone nor the ~$95+ headwind zone, so jet-fuel cost is second-order tonight. H1-2026 results expected ~Aug-14.
- **PTTEP** — ✅ **Q2 CONFIRMED, resolving a long-open flag.** Net profit **US$833m, +104% y/y**; **record** sales volume **572,882 BOED**; ASP **$52.89/BOE** (+20% y/y). Interim dividend **THB 4.50/share**, board-approved 31-Jul, **XD 2026-08-14, pay 2026-08-28**. On 1,400 shares: **THB 6,300 gross / ~5,670 net** of 10% WHT. **Action is to do nothing** — hold through Aug-13. Buying *into* XD is not an opportunity; the price drops by roughly the dividend on Aug-14, so a pre-XD purchase repurchases his own money at a 10% tax cost.
- **SCB** — no confirmed close; mark carried at **151.50**. An undated ~151.5 quote *matches* the carried mark, but **a match is not a confirmation**: with the feed dead 23 days it is at least as likely the quote source is echoing a stale print as that the price is genuinely unchanged, so it was **not** treated as independent corroboration. BOT held at 1.00% (7-0, Jun-24); next MPC **Aug-26**.
- **Gold fund** — strong week (+5%), **but the FX leg has flipped.** USD/THB fell from the carried **33.39** to **33.118** (Aug-06) — the **baht strengthened 0.81%**. SCBGOLDE is unhedged, so that **subtracts ~0.8pp** from the THB NAV gain. **The "weak baht cushions the gold sleeve" tailwind quoted in recent briefs is now fading, not building.** The hold thesis is unchanged — a 5% USD gold week swamps 0.8% of FX — but the direction has reversed and must not be quoted from stale notes.

### Technology Sector Highlight
Nasdaq tracking its **best week since May**, second straight weekly gain, iShares Semiconductor ETF **+5% on the week**. **NVDA $219.22** (Aug-05 close), **+15.37% w/w, +17.68% YTD**; Q1 FY27 revenue **$81.6bn (+85.2% y/y)**, Data Center **$75.2bn**, networking **$14.8bn (+199% y/y)**. Europe's 2026 leaders are the same trade one layer down — wafers, chip-testing equipment, advanced substrates. Japan (Nikkei 65,606.71, −0.12%) and India (Sensex 74,243.34, −0.16%) were flat-to-soft; Hang Seng 25,668.03 (+0.54%); Vietnam VN-Index 1,768 (+0.19%), −4.62% m/m but +11.55% y/y. **The book remains ~100% Thailand**, so none of this week's strength was accessible. Noted, **not recommended** — the Thailand/Vietnam and Thailand/EM correlation study needed to size any diversification is still outstanding, and recommending a reallocation without it would be guessing.

### Improvements Implemented Tonight
1. **`data_collector/feed_health.py` (NEW, ~430 lines)** — the root-cause fix. Stdlib-only, read-only, non-throwing staleness monitor across four independent signals (snapshot `generated_at`, collector process log + shutdown-signature detection, orchestrator heartbeat, nightly artefacts). Deliberately **stdlib-only** because a health check that depends on the stack it is checking is worthless when the venv or DB is the broken thing; deliberately **non-throwing** because a monitor that can be silenced by an exception is not a monitor. Returns an explicit age in days plus a severity per check, and **refuses to report OK when it cannot prove freshness** (unknown age outranks known-dead, since a blind monitor is what produced this blind spot). `_interpret()` distinguishes "live collector down while nightly agent still running" from a generic staleness and names the correct remedy. Exit codes 0/1/2 for direct cron or launchd `KeepAlive` use. **Verified by running it: it correctly reports DEAD, identifies the clean-shutdown signature, and names the supervisor as the fix.**
2. **`portfolio_engine/brief_generator.py`** — added `_load_feed_health()` and wired `feed_health` into the brief context, plus a prompt directive placing a **🚨 DATA FEED WARNING block ahead of everything else**, including the Catalyst Watch header. Reads `data/feed_health.json` as a file rather than importing across the venv boundary. Two deliberate choices: the loader treats an **unreadable or missing report as UNVERIFIED, never as healthy**; and it **ages the health report itself**, because a check that last ran a week ago tells you the feed was fine a week ago, which is not the question. The prompt instructs that a stale feed makes every price, weight and "no change" in the brief a carried-forward mark of that age.
3. **`data_collector/market_data.py`** — fixed the `SCB_GOLD_FUND` pricing path. A Thai open-end fund has no exchange listing, so every 15-minute cycle drove it through `current_yfinance_price()`, burned all three retries (~6s), logged a full traceback and wrote `{"error": ...}`. That was a **category error, not a missing symbol** — a NAV is struck once daily post-close and is not an intraday quote. Added `NON_EXCHANGE_INSTRUMENTS`, `latest_fund_nav()` (reads `fund_nav_history.json` as a file — separate venvs make a cross-package import fail at runtime, and it **refuses to quote a NAV older than 7 days**) and `resolve_current_price()`, which always returns provenance (`price_as_of`, `price_source`, `is_modelled`) and **never falls back to an equity API for a fund**. Existing functions were extended, not replaced. Separately: unpriced holdings were silently omitted from `total_market_value_thb`, so the total described a *smaller* portfolio than Tho owns and every derived weight was correspondingly **overstated** — now tracked via `unpriced_holdings` / `valuation_complete` / `total_value_caveat`.
4. **Data artefacts** — `data/market_intel/2026-08-08.md`, `data/snapshots/2026-08-08.json` (4th carried run, marks unchanged, delta explicitly labelled *zero by construction, not by observation*), `data/watchlist.json` (+16 `aug08_` macro keys, PTTEP XD confirmed, three catalyst dates), `data/feed_health.json`.

**Verification.** All three touched Python files pass `ast.parse`. `feed_health.py` was executed standalone (read-only, stdlib, writes only its own report) and produced the correct DEAD verdict. `watchlist.json` reloaded via `object_pairs_hook` **duplicate-key scan → NONE** (520 macro keys, 16 `aug08_`). Snapshot arithmetic reconciles exactly against Aug-07: total **593,460.00**, weights **30.05 / 34.21 / 35.74**, delta **0.00**. PTTEP dividend recomputed independently: 4.50 × 1,400 = **6,300** gross, ×0.9 = **5,670** net ✓. FX: (33.118 − 33.39)/33.39 = **−0.81%** ✓. News cross-checked ≥2 outlets per item (NFP: CNBC + Quartz + RTÉ + BLS; gold: CNBC + Mining.com + Yahoo + cryptobriefing; Fed odds: LSEG via Mining.com; PTTEP: Bangkok Post + ThaiPR + Kaohoon; SET: Kaohoon; BOT: Nation Thailand + Bangkok Post; oil: Ukragroconsult + Trading Economics + Fortune; Europe: Euronews + Trading Economics + Investing.com; US tech: Quartz + CNBC + 24/7 Wall St.; Asia/Vietnam: Trading Economics).

**Self-caught error, disclosed.** The first version of tonight's `watchlist.json` notes cited carried marks of **PTTEP 144.00 / SCB 155.50 / BAFS 10.40**, taken from `data_collector/portfolio_snapshot.json`. Those are the **dead collector's 2026-07-15 figures**, not the nightly agent's carried marks, which are **145.00 / 151.50 / 9.80** per `data/snapshots/2026-08-07.json`. Corrected before the snapshot was written. The irony is instructive and worth recording: **the very first thing I did after diagnosing a stale-data bug was quote the stale file.** It is not enough to know a source is stale — the stale source has to be removed from reach, or it will be picked up again by reflex. The authoritative mark source is now pinned explicitly in `_meta.carried_marks_source`.

**Caveats.** (a) **FOURTH consecutive run with no confirmed SET close** — but unlike the prior three, the cause is now known and is not a data-availability problem; (b) the only firm SET figure retrievable was the **morning-session** print of 1,613.67, which **cannot mark positions**; (c) **US unemployment source conflict** — 4.1% falling (CNBC + RTÉ) vs 4.2% rising (Seeking Alpha); **4.1% adopted, unresolved**; (d) **VN-Index conflict** — 1,768 (dated Aug-07) vs an undated "record high 1,929"; 1,768 adopted, unresolved; (e) **gold dispersion ~$110** ($4,298 open / $4,401 Comex / $4,412 intraday) — conservative $4,401 taken; (f) **Brent dispersion third night running** ($82.15 / $83.29 / $86.04, $3.89 spread) — the Brent-labelled timestamped print taken; (g) `feed_health.py` thresholds are **calendar days, not trading days**, so a Friday snapshot read on Monday shows AGING — a deliberate false-positive direction, documented in the module, and **not** to be "fixed" by widening thresholds; (h) the gold sleeve remains **excluded** from portfolio totals because the series carries NAV per unit with no unit count, and the module refuses to guess; (i) `pnl_pct` is 0.0 for every holding in the collector snapshot because `avg_cost_price` is 0 in the DB — a **separate, unfixed data defect** that makes all reported P&L meaningless; (j) cross-package imports + Postgres/venv still cannot run in this sandbox, so `generate_daily_brief()` and `resolve_current_price()` were **not** exercised end-to-end — only `feed_health.py`, which is stdlib-only by design, was actually run.

### Next Priority (for next run)
**Restart the collector, then verify the fix end-to-end — nothing else matters until prices move again.** The remedy is the **supervisor/launchd job**, not the fetch code; confirm the process survives a reboot, then check that `feed_health.py` flips from DEAD to FRESH and that `portfolio_snapshot.json` advances. Until that happens every number in this project is a 4-day-old mark wearing a current date. **Then verify tonight's untested code actually runs**: `resolve_current_price()` and the `_load_feed_health()` brief path have only been parsed, not executed. **Fix `avg_cost_price = 0` in the holdings table** — caveat (i) means every P&L figure the system has ever reported is meaningless, which is arguably a worse defect than the stale feed because it fails silently in both directions and has never once been flagged. 🚨 **Aug-13 is the hard dated item**: confirm PTTEP trades cum through Aug-13 and log the Aug-14 XD drop against the THB 4.50 theoretical — this is now a *confirmed* date, not an estimate, so a miss would be unforced. **Capture BAFS H1-2026 (~Aug-14)** into `data/earnings/bafs_h12026_actual.json` on the PTTEP pattern and wire `BAFS.BK` into `load_earnings_actual().actual_map`; judge on **throughput**, and check whether management attributes any arrivals strength to the weak baht — though note that thesis is now weakening as the baht recovers. **Run the Thailand/Vietnam and Thailand/EM correlation study** — still the missing input to the 100%-country-weight problem, and this week's evidence (US semis +5%, European records, Thai tape flat) sharpens the cost of not having it. **Measure the FX betas properly** — the `thb_depreciation_beta` values remain structural assumptions, and tonight's baht reversal is exactly the regime in which an assumed beta will mislead. Also: **SCB 2026 interim declaration** (undeclared; base case ~THB 2.00 mid-September) and **BOT MPC Aug-26**.

---
## Nightly Run — 2026-08-09 02:30 ICT

### Market Intelligence Summary
**Tonight is a Sunday run: no market has traded since Friday 2026-08-07, which the Aug-08 run already covered.** There is therefore almost no new price information to report, and a file that claimed otherwise would be manufacturing it. What tonight delivers instead is **the resolution of three data conflicts carried for up to five runs, the correction of a mark this project adopted incorrectly, and two confirmed software defects** — one of which would have cost Tho a real alert this week. Globally: US and European equities closed at records on Friday (S&P 500 **7,757.64** +0.62%, Nasdaq **26,690.62** +1.3%, STOXX 600 at a fourth consecutive record) after a much weaker-than-expected July payrolls print, with Treasury yields falling and semis (+7% on the week) leading; Asia was mixed and quiet.

### Thai Holdings Update
- **SET INDEX — the four-run drought breaks.** Confirmed full-day close **1,612.00** on 2026-08-07, −2.64 pts (−0.16%), turnover **THB 63.39bn**. It reconciles cleanly with the morning print the Aug-08 run could only partially source (1,613.67 on THB 38.67bn): the afternoon added 24.72bn of turnover and 1.67 pts of decline. Sideways on *weaker* volume — absence of domestic drivers, not distribution.
- **BAFS:** no price. **A missed capture, and the estimate was wrong:** BAFS H1-2026 was scheduled to report **2026-08-06**, not the "~Aug-14" the Aug-08 run queued. The results are likely already published and were not retrieved. BAFS is 30% of the book by carried weight and now has no recent fundamental update at all.
- **PTTEP:** no price. XD **2026-08-14 — five days out**; last cum day **Thursday 2026-08-13**. THB 4.50 × 1,400 = **6,300 gross / ~5,670 net**. Action is to do nothing. Oil in the low $80s means the Q2 result is banked and the forward driver is flat.
- **SCB:** no price. No 2026 interim declaration yet.
- **Gold Fund:** see below — the most consequential item tonight.
- **Marks remain carried from 2026-08-04** (BAFS 9.80 / PTTEP 145.00 / SCB 151.50), fifth consecutive run. **A confirmed index close does not license marking individual positions** — the SET is not a proxy for three specific stocks, and inferring BAFS from a −0.16% index move would be exactly the manufactured precision these files have been trying to eliminate.
- **Foreign flows contradict the Aug-07 file:** foreigners were net **buyers** of >THB 40bn over the past month (~75–76bn YTD), where Aug-07 recorded "outflows". Inflow adopted as better-sourced and more recent; conflict logged rather than silently overwritten.

### Technology Sector Highlight
US: weak July NFP → falling yields → a tech-led record; SOXX +7% on the week, Nasdaq +5.2%. Europe: STOXX 600's fourth straight record, DAX 26,319.45 (+0.69%), same driver. Asia: Nikkei 65,606.71 (−0.12%), Hang Seng 25,668.03 (+0.54%), Nifty 24,571 (−0.27%). China: Unitree Robotics filed to raise ~CNY 6.1bn on the STAR Market — the first listed humanoid-robot maker; thematically notable, not actionable for a THB medium-term book. **Rate-path conflict logged:** one outlet reads the weak NFP as the Fed *holding* in September, others as strengthening the *cut* case; the corroborating evidence (yields, gold +5%, tech record) favours the cut, which is adopted with the disagreement kept visible.

### Improvements Implemented Tonight

1. **`portfolio_engine/cost_basis_guard.py` (NEW)** — the `avg_cost_price = 0` defect, flagged in memory since Aug-08 and never acted on, is now **quantified, confirmed against live data, and guarded**. With cost coerced to zero, `pnl = quantity × (price − cost)` collapses to `quantity × price`, so the system asserts **THB 608,579.99 of profit on a THB 608,579.99 book — an infinite return**. Two independent fingerprints prove it: `pnl_thb == market_value_thb` (the arithmetic signature of zero cost), and `pnl_pct = 0.0` alongside a non-zero `pnl_thb` (mutually contradictory, so at least one field is fabricated). The guard's principle is that **absent data must propagate as absent** — `None`, never `0`. It also reports `phantom_pnl_thb`, the figure the old path *would* have claimed, so the magnitude of the misstatement is visible rather than merely describable. Stdlib-only, runnable CLI (exit 0/1/2) like `feed_health.py`.

2. **`portfolio_engine/performance_analytics.py`** — P&L routed through the guard. Uncomputable P&L now publishes as `None` with `pnl_reliable: False`, `cost_basis_status`, `phantom_pnl_thb` and a caveat string; a top-level `pnl_reliable` boolean and `cost_basis_audit` block were added. Market values and weights are untouched, because they do not depend on cost basis and remain trustworthy. Nothing was removed; the import is defensive and degrades to "unreliable", never to a fabricated number.

3. **`portfolio_engine/dividend_tracker.py` — a live alert was silently broken. 🚨** `data/dividends/dividend_history.json` **had never been written.** `seed_known_dividends()` exists and holds the correct PTTEP record, but nothing calls it, and `_load_history()` returns `{}` when the file is absent — so `upcoming_ex_dates()` returned `[]`, which renders exactly like "no dividends are due". **The PTTEP alert due to fire tonight, at exactly the 5-day window, on a position Tho actually holds, would not have fired.** Added `_ensure_store_seeded()` (self-heals on first read, best-effort, never raises) and `store_status()` (lets callers distinguish "no dividends due" from "store never created"); `upcoming_ex_dates()` now uses the former. Store materialised at `data/dividends/dividend_history.json` (11 records).

4. **Data artefacts** — `data/market_intel/2026-08-09.md`, `data/snapshots/2026-08-09.json` (5th carried run), `data/watchlist.json` (+23 `aug09_` macro keys, 4 catalyst dates), `data/cost_basis_audit.json`, `data/dividends/dividend_history.json`.

### Two findings about how this project fails, not just what failed

**The dividend bug and the dead price feed are the same bug at different layers.** In both cases *absence of data renders identically to absence of events*: a 24-day-old price looks like a flat market, and an unwritten store looks like a calendar with no dividends in it. The fix in both cases is not better fetching — it is **making absence loud**. That is why `store_status()` and `pnl_reliable` exist tonight, and why the guard returns `None` rather than a number.

**A correction to the Aug-08 run's method, not just its output.** That run wrote: *"already seeded in `dividend_tracker.py`; the ex-date alert will fire."* That was verified against the **source code**, not the **store** — and the store is what the function reads. Confirming that the right data exists in a seed function is not confirming it is retrievable. Verification belongs at the **read path**.

### Corrections to previously published figures
- **Gold mark was wrong by ~1.3%.** The Aug-08 run adopted **$4,401** "conservatively" from a dispersion range. That figure was an 8:45 a.m. ET intraday print of **December COMEX futures**, not spot. The "dispersion" was not noise between competing quotes of one thing — it was **three different instruments** (futures open $4,298.30, futures intraday $4,411.70, spot ~$4,356) compared as one. **Taking a midpoint of incommensurable prints is not conservatism.** Corrected to spot **$4,341.78** (2026-08-08).
- **The gold *framing* was wrong for longer, and matters more.** Recent briefs described gold in terms of records and rallies. In fact **gold peaked at $5,589.38 on 2026-01-28 and is now ~22% below that**, having bottomed near $4,046 in July — a ~28% drawdown and the steepest quarterly correction since 2013. Last week's +5% is a **bounce inside a deep correction**, not a resumed bull market. This is **Tho's largest position (~35%)** and it had not been presented this way.
- **VN-Index conflict resolved at 1,768** (dated, Trading Economics). The undated "record 1,929" is uncorroborated and **discarded**.
- **The FX thesis has inverted, not faded.** USD/THB has gone 33.39 → 33.118 → **33.082**, −0.92% cumulative — a confirmed multi-day trend. The "weak baht cushions the unhedged SCBGOLDE sleeve" line that ran through these briefs for weeks now works the *other* way: a strengthening baht **subtracts** from THB returns on the unhedged gold sleeve, compounding a gold price 22% off its peak. **Both major return drivers on Tho's largest position currently point the same direction, and it is not the good one.**

### Verification actually performed
All three Python files pass `ast.parse`. **`cost_basis_guard.py` was executed standalone against the real snapshot** → `DEFECT_CONFIRMED`, exit 1, six findings across three tickers plus the portfolio-level fingerprint; it is stdlib-only and writes only its own report. **`dividend_tracker.py` was executed in an isolated copy** (`/tmp`, stubbed `utils.common`, throwaway `PROJECT_DIR`) so the real project was untouched: *before* — `store_exists: false`, `record_count: 0`, alerts `[]`; *after* — 11 records and the PTTEP alert firing with `days_until_ex_date: 5`. **The bug and the fix were both demonstrated, not argued.** Confirmed `seed_known_dividends()` being defined after `_ensure_store_seeded()` is a runtime-only reference that resolves correctly. Snapshot arithmetic reconciles exactly: 9.80×18,200 + 145.00×1,400 + 151.50×1,400 = **593,460.00**; weights **30.05 / 34.21 / 35.74** recomputed and matched; gold drawdown recomputed **−22.32%** vs stated −22.3; FX **−0.109%** d/d and **−0.922%** cumulative vs stated −0.11 / −0.92; PTTEP dividend 4.50×1,400 = **6,300** gross, ×0.9 = **5,670** net; SET reconciliation 63.39−38.67 = **24.72bn** and 1,613.67−1,612.00 = **1.67 pts**. `watchlist.json` reloaded with an `object_pairs_hook` duplicate-key scan → **NONE** (543 macro keys, 23 `aug09_`); `snapshots/2026-08-09.json` likewise clean.

### Caveats
(a) **Feed DEAD for the fifth consecutive run** — unchanged since the Aug-08 diagnosis, which remains correct: clean SIGTERM 2026-07-15 23:53 ICT, never restarted, a supervisor/launchd problem that **no nightly run can fix**. Five runs is long enough to say plainly that the analytical half of this project is now well ahead of its data half and the gap is widening. (b) Tonight's zero delta has **two** causes — the dead feed *and* a genuinely absent weekend session — so it is even less informative than the previous four. (c) `get_performance_summary()` was **not** executed end-to-end (needs Postgres, `httpx`, cross-package imports unavailable in this sandbox); the guard functions it calls were exercised directly, the integration around them was not. (d) **Disclosed overwrite:** the four catalyst dates written to `watchlist.json` used `dict.update()`, and the catalyst count stayed at 36 — meaning all four dates already existed and **prior text was replaced rather than merged**. The replacements are supersets in content and factually corrected, but this was an overwrite, not an append, and there is no VCS in this project to recover the originals. (e) The gold sleeve remains **excluded** from portfolio totals — NAV per unit with no unit count — which is no longer a bookkeeping nit: the largest position in the book is the one the system cannot value, at the exact moment gold is 22% off its high. (f) `avg_cost_price = 0` is **guarded, not fixed**; the guard makes the P&L honest by removing it, which is better than the old answer but is not the same as having P&L. Only Tho can supply real average costs. (g) Individual holding closes remain unobtainable while the feed is dead; the only prints found tonight were stale (BAFS 9.75, dated 17-Jun) or unusable. (h) Brent print dispersion continues for a fourth night; the pattern of loosely-sourced Brent quotes is now habitual and should be distrusted by default.

### Next Priority (for next run)
**Restart the collector — fifth run of saying so, and it remains the only item that unblocks everything else.** Then confirm `feed_health.py` flips DEAD → FRESH and `portfolio_snapshot.json` advances. **Retrieve BAFS H1-2026, which was reported ~2026-08-06 and missed** — this is now the highest-value *data* task: BAFS is 30% of the book, has no recent fundamental update, and the miss was caused by an estimated date being trusted over a checked one; capture it into `data/earnings/bafs_h12026_actual.json` on the PTTEP pattern and wire `BAFS.BK` into `load_earnings_actual().actual_map`, judging on **throughput** and checking whether management attributes anything to the baht (noting that thesis is now *inverted*, not merely weakening). 🚨 **Aug-13 is the hard dated item:** PTTEP must be held through Thursday's close; log the Aug-14 open against the THB 4.50 theoretical drop, since a materially different drop is information about demand rather than noise. **Ask Tho for real `avg_cost_price` values** — the guard has made the P&L honest by suppressing it, but suppression is a holding position, and this is the one defect only he can clear. **Solve the gold sleeve unit count**, which has now graduated from housekeeping to the most important unvalued number in the book. Then the standing items: the **Thailand/Vietnam and Thailand/EM correlation study** (still the missing input to the 100%-country-weight problem), **measuring the FX betas properly** rather than assuming them — tonight's confirmed baht reversal is precisely the regime where an assumed beta misleads — **SCB's 2026 interim declaration** (undeclared; base case ~THB 2.00 mid-September), and **BOT MPC Aug-26**.

---


## Nightly Run — 2026-08-10 02:30 ICT

### Market Intelligence Summary
The US July payrolls print — the datum four consecutive runs had been waiting for —
landed as a genuine miss: **23,000 jobs lost against +80,000 expected**, with
unemployment ticking down to 4.1%. Equities took it as good news, the S&P closing at a
record and the Nasdaq gaining 5.0% on the week, its strongest since April. Gold firmed
to ~USD 4,350 and Brent eased to ~USD 77 as the Hormuz interim arrangement was
confirmed **not signed** — Iran wants US and Israeli vessels excluded and transit fees
levied, the US wants unrestricted passage, and the two sides remain far apart. But the
important finding tonight was internal rather than external, and it is set out below.

### 🚨 The carried marks were wrong, not stale — a six-run silent error
Tonight's run set out to retrieve BAFS H1-2026 and instead discovered that the SET
marks this project has been carrying since 2026-08-04 were materially incorrect.

| Ticker | Carried | Actual 2026-08-07 close | Error |
|---|---|---|---|
| BAFS.BK | 9.80 | **11.60** | **+18.37%** |
| PTTEP.BK | 145.00 | **149.00** | +2.76% |
| SCB.BK | 151.50 | **153.50** | +1.32% |

The book ex-gold is **THB 634,620**, not THB 593,460 — understated by **THB 41,160
(+6.94%)**. The BAFS mark never corresponded to 2026-08-04 at all: the real close that
day was 10.80, and BAFS last traded near 9.80 in *late February*. The stock ran from
8.75 on 29 May to 11.60 on 7 August — **+32.6%** on a third of Tho's equity book — and
none of it was visible here. Every position value, total, weight and concentration
figure in the Aug-05 through Aug-09 snapshots is void, including the repeatedly
reported "BAFS = 30.05% of book" (it was ~33%).

Root cause is the family this project keeps meeting: **a value that is absent or
unverified renders downstream as a perfectly normal number.** A mark of unknown vintage
was stamped with a specific recent date, which made it unfalsifiable. New rule: *a
carried mark must carry the date it was observed, never the date it was copied.*

### Thai Holdings Update
- **BAFS — 11.60 (+4.50%)**, high 11.80 on 1,452,100 shares, ~3.7x the prior session.
  The session high *is* the 52-week high; the close sits at 95% of the 7.90–11.80 range.
  P/E 33.55, yield 2.84% — now the most expensive, lowest-yielding name in the book.
- **PTTEP — 149.00, unchanged** (an *observed* zero, unlike the five constructed ones
  before it). P/E 8.54, P/BV 1.04, yield 5.87%, IAA target 160.96, one broker at 179.
  🚨 **Last cum day Thu 2026-08-13**, XD Fri 08-14, THB 4.50 × 1,400 = 6,300 gross /
  ~5,670 net, pay 08-28. **Action: do nothing — hold through Thursday's close.**
- **SCB — 153.50 (−0.32%)**. P/E 11.44, P/BV 1.03, yield 7.35%. **The IAA consensus
  target of 152.47 is now BELOW the price** — first time in the tracked period that SCB
  trades through the street's own fair value. The 7.35% yield, not capital, now carries
  the thesis. 2026 interim still undeclared.
- **Gold sleeve — still unvalued.** NAV per unit known, unit count unknown, so Tho's
  largest position (~35%) remains excluded from every total. Spot ~4,350 is ~22% below
  the 2026-01-28 peak of 5,589.38: a bounce inside a deep correction, not a new bull.

### Correction: BAFS has not reported, and the Aug-09 alarm is retracted
The Aug-09 run recorded that BAFS reported ~2026-08-06 and that the print had been
missed. **Wrong.** The source article's figures — THB 56m net profit, +29% YoY, THB 0.11
dividend — are **Q2/2568, i.e. 2025**, XD 2025-08-28. The trap is **Buddhist-era year
labelling** (2568 = 2025, 2569 = 2026), a standing hazard for every Thai source this
project reads. Verified two ways: BAFS IR still headlines Q1/2026 as the latest
published period, and the FY2569 Q2 column in the quarterly grid is empty. The original
~14 August estimate stands. Q1/2026 for reference: revenue THB 991.01m, net profit
THB 151.8m (+6%), **aviation refuelling volume +5% YoY at 92% of pre-COVID**, pipeline
volume −8%, Fitch BBB(tha) Stable. Judge the H1 print on throughput, not margin.

### Technology Sector Highlight
US tech drove the week: Nasdaq +5.0%, S&P +3.5%, both at records, on the read that a
shrinking labour market removes any near-term tightening risk. Japan did **not**
participate — the Nikkei closed −0.12% at 65,606.71 on tech-sector concern and foreign
selling. Hang Seng +0.54% to 25,668.03 capped a mixed week. India has no upgrade-type
catalyst; its rising MSCI EM weight reflects Korean and Taiwanese weakness rather than
its own strength. Europe was not refreshed this run and is now two sessions stale.

### Improvements Implemented Tonight
1. **`data_collector/th_price_fallback.py` (NEW)** — an independent end-of-day SET price
   reader that needs no daemon, no PostgreSQL and no yfinance (standard library only).
   This is the structural answer to six runs of being blocked on a process restart the
   nightly agent cannot perform. Every accessor returns `None` on failure rather than 0
   or a carried value; every quote carries the as-of date parsed from its own row and
   undated rows are dropped rather than guessed; `latest_close()` **refuses** a quote
   older than the age limit so the fallback cannot become its own stale feed;
   `portfolio_marks()` returns `total_thb = None` if any leg is unpriced, because a
   partial sum understates a book while reading as a real number; Buddhist-era dates are
   converted explicitly. `self_test()` exercises the real parse against live HTML.
2. **`portfolio_engine/earnings_tracker.py`** — the BAFS seed note now carries the
   false-alarm retraction, the Buddhist-era explanation, both verification points, and an
   explicit instruction not to re-open the chase. No existing code path altered.
3. **`data/snapshots/2026-08-10.json`** — first non-carried snapshot in six runs, with a
   full `marks_correction` record naming what the error invalidates.
4. **`data/watchlist.json` / `data/market_intel/2026-08-10.md`** — refreshed marks,
   valuation detail, the four dated catalysts, and the resolved/open conflict ledger.

### Next Priority (for next run)
**Run `python3 data_collector/th_price_fallback.py` on Tho's host and confirm
`self_test()` returns ok — tonight's parser was verified against captured HTML but has
never touched the live network from the project machine**, and until it does, tonight's
marks rest on a hand-read page rather than a tested path. Then **wire the fallback into
`market_data.resolve_current_price()` as a labelled secondary source** so the brief and
the snapshot writer stop depending on a daemon that has been dead for 26 days; the mark
must be tagged as fallback-sourced wherever it surfaces. **The collector restart is
still the real fix and still needs Tho** — it is a supervisor/launchd job, not code.
🚨 **Thu 2026-08-13 is the hard dated item**: PTTEP must be held through the close; log
the Aug-14 open against the THB 4.50 theoretical drop, since a materially different drop
is information about demand rather than noise. **Capture BAFS H1-2026 (~Aug-14)** into
`data/earnings/bafs_h12026_actual.json` and wire `BAFS.BK` into
`load_earnings_actual().actual_map`, judging on throughput — and **check every Thai
source for Buddhist-era year labelling before trusting a figure**, which is now the
second-most expensive mistake this project has made. **Test the Fed path against the CPI
print due this week** — the Aug-09 run adopted a cut, Aug-07 coverage supports only a
hold, and the difference matters for both the gold sleeve and the baht. **Resolve the
USD/THB contradiction**: spot has fallen four consecutive marks while SCB FM forecasts
weakening toward 33.25 with a watch past 34. **Decide Vietnam before Aug-21**, when the
FTSE constituent list and cap thresholds publish — 11 days out, and Tho still has zero
exposure. Standing items unchanged: **ask Tho for real `avg_cost_price` values** (the
guard has made the P&L honest by suppressing it, but only he can clear it, and tonight's
correction makes the gap more costly — the system can now see BAFS has run ~33% off its
May lows and still cannot say whether Tho is up on it), **solve the gold sleeve unit
count**, run the **Thailand/Vietnam and Thailand/EM correlation study**, and **measure
the FX betas** rather than assuming them. Watch the **SCB 2026 interim declaration** and
**BOT MPC Aug-26**.

---

## Nightly Run — 2026-08-11 02:30 ICT

### Market Intelligence Summary
The Thai market had its best session in a while — **SET 1,624.36, +12.36 (+0.77%)**
on THB 61.74bn, DELTA-led on global tech sentiment — while Wall Street paused
(Dow −0.16% midday, AAPL −2.11%, NVDA −2.12%) and energy led everything on a
Hormuz deal that keeps almost-happening. Brent **$84.68**, WTI **$79.19**, S&P
energy sector **+4.46%**. But tonight's two most important findings are internal:
**the fallback price module written last night cannot run in the environment it
was written for**, and **this project has had the Fed narrative backwards.**

### 🚨 Finding 1: last night's top-priority fix was unrunnable, and running it proved it
The Aug-10 run shipped `data_collector/th_price_fallback.py` — a stdlib-only SET
price reader — specifically so the nightly agent could get marks without the dead
daemon, and queued "run `self_test()` live" as the single highest priority.

Tonight it was run live. Every ticker failed:

    urlopen error Tunnel connection failed: 403 Forbidden

Outbound HTTP from Python in the nightly agent's sandbox is refused at an egress
proxy. `curl`, `urllib`, everything. The parser was never in question; **the
caller has no network.** The structural consequence is worth stating flatly
because three runs of design rested on the opposite assumption:

> The nightly agent can read the web, but only through its own retrieval tooling.
> It cannot do so from inside Python. **No Python module in this project can be
> the nightly agent's price path.**

`th_price_fallback.py` is still correct and still useful — on **Tho's machine**,
where egress is open. It is a host-side tool that was queued as an agent-side
one. That is a planning error, not a coding one, and it would have been caught
last night by running the thing instead of verifying it against captured HTML.
The Aug-09 lesson — *verification belongs at the read path* — applied here and
was not applied.

### 🚨 Finding 2: the Fed narrative in this project has been backwards
The Aug-09 run adopted a **rate cut** as base case; Aug-10 queued "test the Fed
path against the CPI print." Monday's coverage settles it the other way:
markets were relieved because weak payrolls "eased fears of an upcoming Federal
Reserve **rate hike**", and officials "remain divided on whether to **raise**"
rates as they watch the oil shock feed inflation.

The live debate is **hold versus hike**, not hold versus cut. The −23,000 July
payrolls removed *hike* pressure; they never created cut expectations. **Adopted:
hold, with hike tail risk that rises if Wednesday's CPI runs hot.** This is not a
semantic difference — a hike-risk regime is a *headwind* for the gold sleeve
(Tho's largest position) where a cut would have been a tailwind, and every gold
comment in recent briefs was written under the wrong sign.

### Thai Holdings Update
- **PTTEP — 149.50 on 2026-08-10**, +0.50 (+0.336%), 11,852,577 shares, range
  148.50–150.00. 30d 141.00–153.00; 52w 104.00–164.00. Independently retrieved
  from stockinvest.us, which **also prints 149.00 for 2026-08-07 — corroborating
  the aio.panphol.com mark the Aug-10 run adopted.** That is the first time a
  fallback mark has been confirmed by a second vendor, and it materially raises
  confidence in last night's marks correction. 🚨 **Last cum day is Thursday
  2026-08-13**: THB 4.50 × 1,400 = **6,300 gross / ~5,670 net**, XD 08-14, pay
  08-28. **Action: hold, do nothing.**
- **BAFS — not re-observed since 2026-08-07 (11.60).** The mark is labelled with
  that session, not with tonight's date. **Oil has turned against it**: Brent back
  to ~$84.68 from ~$77 last week means the jet-fuel cost headwind is *resuming*.
  H1-2026 expected ~2026-08-14; judge on throughput, not margin.
- **SCB — not re-observed since 2026-08-07 (153.50).** Banks were among Monday's
  profit-taking sectors, so the true Monday print is more likely *below* 153.50 —
  an inference, deliberately **not** used to mark the position. No second source
  exists: stockinvest.us has no SCB data past 2026-07-15 (155.50), which happens
  to be the day the collector died. Coincidence, not causation.
- **Gold sleeve — unvalued, 8th run.** Futures **$4,393.90**, ~flat, **+7% MTD**,
  with $4,390 as the 100-day SMA. Still ~21% below the 2026-01-28 peak of
  5,589.38. NAV per unit known, **unit count unknown**, so the largest position in
  the book is still excluded from every total.
- **Equity book THB 635,320** (+700, +0.110% vs Aug-10). ⚠️ **The total is
  mixed-date** — a Monday PTTEP leg with Friday BAFS and SCB legs — and the delta
  is *entirely* PTTEP. BAFS and SCB are unchanged **because they were not
  re-observed, not because they did not move.**
- **Oil is the book's hinge, and the hedge is accidental.** PTTEP (32.9% of
  equity) sells oil; BAFS (33.2%) buys it as jet fuel. They sit on opposite sides
  of the same Hormuz headline. That is the closest thing to a hedge in this
  portfolio and nobody designed it.

### Corrections to previously published figures
- **Foreign flows, reversed.** The Aug-09 file recorded foreigners as net buyers
  of ">THB 40bn over the past month (~75–76bn YTD)". Actual: 1–10 Aug they are net
  **sellers of THB 9,015.26m**; YTD net buying has fallen to **66,918.87m**; local
  individuals (+6,359.03m MTD) are absorbing. Direction was misread, not just the
  level.
- **India retired, not superseded.** The Aug-08 "Sensex 74,243.34" is inconsistent
  with tonight's Sensex 78,501.59 / Nifty >24,500 pairing (implied ratio 3.03 vs
  3.20). The old figure is **discarded**.
- **Catalyst 2026-08-11 was factually wrong** — it carried "PTTEP H1-2026 results
  (estimated)". PTTEP Q2 was reported **2026-07-31** (US$833m, +104% y/y; record
  572,882 BOED). Corrected in place.

### Improvements Implemented Tonight
1. **`data_collector/observed_marks.py` (NEW, ~430 lines)** — the agent-side price
   path Finding 1 makes necessary. A provenance-carrying mark store: `source_name`,
   `source_url` and **`observed_as_of` (the trading session, from the source)** are
   *required*, and a mark missing any of them raises `MarkRejected` rather than
   being stored with a warning — a warning in a JSON file is not read at 2:30 a.m.
   `observed_as_of` and `retrieved_at` are separate fields and never conflated,
   because collapsing them is exactly what let a February BAFS price wear an August
   date for five runs. Corroboration is **counted, not assumed**: a second source
   agreeing within 0.25% raises the count; a second source *disagreeing* is logged
   to `conflicts` and **does not overwrite**, because two vendors disagreeing about
   one session is information and silently taking the newer one destroys it. Older
   quotes are kept as history and never replace a newer mark. `get_mark()` refuses
   past an age limit; `portfolio_marks()` returns `total_value: None` if any leg is
   unpriced, and flags `mark_date_mixed` so a Monday-plus-Friday total is never
   presented as a Monday total. Stdlib-only, CLI, exit codes.
2. **`data_collector/th_price_fallback.py`** — `self_test()` reported `ok: False`
   identically whether the page was unreachable or unparseable. Those have
   *opposite* remedies, and conflating them is the same failure family as a dead
   feed being indistinguishable from a broken parser, which cost this project six
   runs. Added failure classification (`NETWORK_BLOCKED` / `NETWORK_UNREACHABLE` /
   `HTTP_ERROR` / `PARSE_FAILURE` / `SOURCE_STALE`), per-symbol error capture, and
   `_diagnose()`, which names the **remedy** rather than restating the fault — and
   for the blocked case says explicitly *do not "fix" this by relaxing the parser*,
   which is the tempting wrong move. Nothing existing was removed.
3. **Data artefacts** — `data/observed_marks.json` (new store, 3 tickers, full
   source chains), `data/snapshots/2026-08-11.json`, `data/market_intel/2026-08-11.md`,
   `data/watchlist.json` (+25 `aug11_` macro keys, 1 catalyst added, 4 corrected).

### Verification actually performed
Both touched files pass `ast.parse`. **`th_price_fallback.self_test()` was
executed live** → `NETWORK_BLOCKED` on all three tickers with the correct
diagnosis; the finding above *is* the test output, not an inference.
**`observed_marks.py` was executed against real data**, exercising all four write
paths: new mark, same-session corroboration (PTTEP 149.00 from stockinvest.us
matching aio.panphol.com for 2026-08-07), newer-session supersession (→ 149.50 for
2026-08-10, correctly resetting corroboration to 1 because the *new* session has
only one source), and older-session history-only (SCB 155.50 @ 2026-07-15, BAFS
8.45 @ 2026-05-18 — neither displaced the current mark). Arithmetic reconciles:
11.60×18,200 = 211,120; 149.50×1,400 = 209,300; 153.50×1,400 = 214,900; **total
635,320**; weights **33.2305 / 32.9440 / 33.8255**, summing to exactly 100.0;
delta vs Aug-10 = **+700.00 = +0.1103%**; dividend 4.50×1,400 = **6,300**, ×0.9 =
**5,670**. `watchlist.json` duplicate-key scan before and after → **NONE** both
times; reload clean, 594 `macro_context` keys, 25 `aug11_`.

### Self-caught error, disclosed
The first watchlist write created a **new top-level `macro` key** and put all 25
of tonight's entries in it — while the real store is `macro_context` (569 keys).
Two hours of nightly context would have been invisible to every reader. Caught by
printing the key count and seeing `0 -> 25` where 569 was expected. Merged into
`macro_context` (no key collisions) and the stray removed. The general lesson is
the one this project keeps relearning in new costumes: **a write that succeeds is
not a write that landed in the right place**, and `dict.setdefault` will happily
manufacture a plausible-looking home for data nobody will ever read.

### Caveats
(a) **Collector dead 27 days, 8th run** — and now known to be unfixable from here
in *two* ways: the restart needs Tho's supervisor/launchd, and the fallback needs
Tho's network. (b) **Two of three equity legs were not observed tonight**; the
total is mixed-date and labelled as such. (c) **No mark is corroborated for its
current session** — `uncorroborated()` returns all three. (d) **Europe not
refreshed, three sessions stale**; **Vietnam not refreshed** with the FTSE list
ten days out. (e) Gold figures are the 2026-08-10 *early-session futures* print,
not spot — the Aug-09 run was burned by treating futures and spot as one series,
so the instrument is named. (f) BAFS vendor quotes remain irreconcilable (11.60 @
08-07, 8.45 @ 05-18, 9.95 @ 2025-10-21); only the first is usable and its 52-week
range conflicts with stockanalysis.com's, probably from vendor staleness,
unconfirmed. (g) `avg_cost_price = 0` is **guarded, not fixed** — P&L stays
suppressed until Tho supplies real costs. (h) Three catalyst entries were
**replaced rather than merged** (08-13, 08-21, 08-26); the replacements are
supersets, but there is no VCS here to recover the originals. (i) `observed_marks`
and the brief/snapshot writers were **not** exercised end-to-end together —
cross-package imports still need Postgres and separate venvs unavailable in this
sandbox.

### Next Priority (for next run)
🚨 **Thursday 2026-08-13 is the hard dated item and it is two days out**: PTTEP
must be held through the close; then log the Aug-14 open against the THB 4.50
theoretical drop, because a materially different drop is information about demand
rather than noise. **Get BAFS and SCB Monday/Tuesday closes** — tonight's gap is
the whole reason the total is mixed-date, and stockinvest.us serves PTTEP but not
current SCB, so a **third SET source** is needed and finding one is now a
first-class task, not housekeeping. **Wire `observed_marks.get_mark()` into
`market_data.resolve_current_price()` as a labelled source** ranked below the live
collector and above nothing, so the brief and snapshot writers stop depending on a
daemon that has been dead a month; the mark must surface to Tho tagged with its
session date and corroboration count. **Capture BAFS H1-2026 (~2026-08-14)** into
`data/earnings/bafs_h12026_actual.json` and wire `BAFS.BK` into
`load_earnings_actual().actual_map` — judge on throughput, and **check every Thai
source for Buddhist-era year labelling** (2569 = 2026) before trusting a figure.
**Read Wednesday's CPI against the corrected hold-vs-hike frame**, not the old
cut frame, and revisit every gold comment written under the wrong sign.
**Decide Vietnam before 2026-08-21** — ten days, five deferrals. Standing and
unchanged: **ask Tho for real `avg_cost_price` values**, **solve the gold sleeve
unit count** (the largest position in the book is the one the system cannot
value), run the **Thailand/Vietnam and Thailand/EM correlation study**, and
**measure the FX betas** rather than assuming them — the baht has now firmed
1.11% in four sessions, which is precisely the regime where an assumed beta
misleads. Watch **SCB's 2026 interim declaration** and **BOT MPC 2026-08-26**.

---

## Nightly Run — 2026-08-12 02:30 ICT

### Market Intelligence Summary
Wall Street drifted lower into tonight's CPI (**Dow −0.06%, S&P 500 −0.10% at
7,753, Nasdaq −0.39%**) with energy and small caps leading and large-cap tech
lagging, while **Brent pushed to ~$87–88 from ~$83 last week** as the Hormuz talks
deteriorated over the weekend and gold held **$4,396.53 spot**, above $4,400
intraday. But the run's real finding is infrastructural: **www.set.or.th is
reachable by the agent's retrieval tooling.** After eight runs of arbitrating
between vendors who disagreed with each other, this project now reads prices from
the exchange that issues them — and the first thing the exchange did was correct us.

### 🔑 Finding 1: the project has a first-party price source, and it has a trap in it
All three equity legs are marked **first-party** tonight. The BAFS vendor dispute
that has run since 2026-08-10 is closed. And PTTEP's page did something no vendor
has managed: **152.00 less its own published change of +2.50 reproduces 149.50 for
10 Aug**, independently confirming the aio.panphol.com / stockinvest.us chain. The
exchange corroborating the vendors is a different quality of evidence from two
vendors corroborating each other.

The exchange also hands us a **checksum**: SET's ceiling/floor is the prior close
±30% rounded to the SET tick (ceiling down, floor up). It is reproducible, so a
mangled `Prior` cannot pass silently. All three legs reconciled.

The trap is freshness. Within four minutes tonight, one site served three states:

    BAFS  stamp 12 Aug 02:34:39  Closed  Last 11.30  Prior 11.20  -> FINAL, session 11 Aug
    SCB   stamp 11 Aug 08:07:17  Closed  Last -      Prior 152.00 -> PREOPEN, Prior = 10 Aug
    SET   stamp 11 Aug 12:04:53  Open1   Last 1618.80             -> INTRADAY, not a close

Read naively all three "are" the current price. In fact **the stamp's calendar
date is not the session date** (BAFS is stamped the 12th and reports the 11th),
**SET prints "Closed" both before the open and after the close** — opposite
readings of `Prior` — and **the index number is a live tick that would have gone
into the book as a close.** That is the futures/spot error wearing new clothes.

### 🚨 Finding 2: last night's published book total was overstated by THB 9,380
The 11 Aug run published **THB 635,320**. Against the exchange's own 10 Aug closes
the true same-session figure is **THB 625,940** — **+1.4986% overstated**, entirely
from the two legs that were not re-observed:

- BAFS carried 11.60 (7 Aug) vs actual **11.20** on 10 Aug → **7,280** overstated
- SCB carried 153.50 (7 Aug) vs actual **152.00** on 10 Aug → **2,100** overstated
- PTTEP 149.50 → **0**. It was correct.

This is **not** the February-price failure repeating. Those marks were honestly
labelled with their 7 Aug session and were probably right for it. The narrower and
more useful lesson: **a stale mark decays silently, and a mixed-date total inherits
the decay of its oldest leg.** Last night's caveat said the total was mixed-date
and that BAFS and SCB were unchanged "because they were not re-observed, not
because they did not move." That was exactly right, and both had in fact moved
down. The caveat was correct and still cost 1.5% of accuracy — which argues the
caveat was not strong enough, not that it was wrong.

Worth recording as a small vindication of process: the 11 Aug run **inferred** SCB
was probably below 153.50 and **refused to mark on the inference**. It was right —
152.00. Refusing was still the correct policy; an inference that happens to be
right is not an observation.

### Thai Holdings Update
- **BAFS — 11.30 (2026-08-11), +0.10 (+0.89%).** Prior 11.20, open 11.20, H 11.30 /
  L 11.00, vol 514,576, value 5,752.31k, avg 11.18 (value÷volume gives 11.1787 ✓).
  52w **7.90–11.80**. The aggregator ฿8.40 is refuted as a current price, and that
  aggregator's whole series is suspect: it publishes a 52-week range of 6.70–12.70
  against the exchange's 7.90–11.80. **H1-2026 expected ~2026-08-14 — judge on
  throughput, not margin**, and check every Thai source for Buddhist-era years.
- **PTTEP — 152.00 (2026-08-11), +2.50 (+1.67%).** H 152.00 / L 150.00, vol
  24,455,699, value 3,694,375.93k. Rose with Brent. 🚨 **Last cum day Thursday
  2026-08-13**: THB 4.50 × 1,400 = **6,300 gross / 5,670 net**, XD 08-14, pay 08-28.
  Theoretical drop **2.9605%** on a 152.00 close. **Action: hold, do nothing.**
- **SCB — 152.00 (2026-08-10), one session stale.** Its page was a pre-open cache,
  so no 11 Aug close exists on file. Band reconciles (floor 106.50 / ceiling
  197.50). 2026 interim still undeclared (base case ~THB 2.00, mid-September).
- **Gold sleeve — unvalued, 9th run.** Spot **$4,396.53** (11 Aug 09:00 ET), above
  $4,400 intraday as Iran worsened; marked **spot**, per standing rule. A bullion
  site's 4,333.70/4,404.00 bid/ask is a 1.6% spread and was discarded rather than
  averaged. NAV per unit known, **unit count unknown** — the largest position in
  the book is still outside every total.
- **Book: THB 631,260 mixed-date** (BAFS and PTTEP @ 11 Aug, SCB @ 10 Aug), and
  **THB 625,940 on a clean, fully same-session 10 Aug basis — the first such total
  this project has ever produced.** Weights **32.5654 / 33.4377 / 33.9969**.
- 🚨 **The "accidental hedge" thesis failed its first test.** Last night's run
  observed that PTTEP sells oil while BAFS buys it as jet fuel and called it the
  book's only hedge. Tonight Brent rose ~5% and **both legs rose** (+1.67%, +0.89%).
  One session is not evidence, but the hedge did not operate. Until the betas are
  measured the book should be treated as **~33/33/33 concentrated and unhedged**,
  which is a materially worse risk description than "naturally offset".

### Technology Sector Highlight
Large-cap tech was the drag on 11 Aug while energy and small caps led — a rotation
consistent with a market repositioning for a hotter rate path rather than a softer
one. **Nikkei 66,970.22** rose; **Hang Seng −1.10% to 25,652.82** fell against the
regional trend; **Shanghai −0.82% to 3,934.09**. India was not retrieved (the stale
Sensex figure retired on 11 Aug has no replacement); Europe is four sessions stale;
Vietnam is a sixth deferral with the FTSE list on 21 Aug.

### 🚨 Finding 3: the Fed frame moves again — the market's base case is a HIKE
The 09 Aug run adopted a **cut**; the 11 Aug run corrected that to **hold with hike
tail risk**. Tonight goes one step further in the same direction: **CME FedWatch on
6 Aug put ~55% on a 25bp HIKE** at the 15–16 September FOMC versus ~45% hold, and
the July meeting carried **three dissents in favour of hiking**. Chair is **Kevin
Warsh**. July CPI printed at 08:30 ET on 12 Aug, *after* this run; Cleveland Fed
nowcast headline **+0.09% m/m / 3.42% y/y**, core **+0.21% m/m / 2.52% y/y**.
A hike regime is a **headwind for the gold sleeve**, Tho's largest position.

Offsetting it on the currency side: **USD/THB 33.1160, +0.35% — the baht weakened**,
reversing four sessions of strengthening. A weaker baht is a **tailwind** for the
unhedged gold sleeve in THB terms. The 11 Aug run flagged the opposite sign; the
sign has flipped and gold commentary should be read accordingly.

### ⚠️ Finding 4: the search layer blended a 2024 article into a 2026 answer
A query for August-2026 US CPI returned a confident, internally coherent synthesis
— *"headline eased to +2.5%, core +3.2%, shelter +0.5%, a 25bp cut firmly on the
table"* — built on an fxstreet URL ending **`202409111814`**: the **August 2024**
print. Every figure was two years old and it pointed at a **cut** in a market
pricing a **hike**. It was caught only by reading the URL.

**Adopted rule: a retrieved figure with no explicit in-text date is not a figure —
check the source URL for an embedded timestamp before use.** This joins the
Buddhist-era trap (2569 = 2026) and the futures/spot trap as a standing read-path
hazard. All three are the same failure: a number that looks current because nothing
on its face says otherwise.

### Improvements Implemented Tonight
1. **`data_collector/set_official.py` (NEW, ~430 lines)** — first-party SET quote
   reader. It **does not fetch**: the 11 Aug run proved Python egress is blocked in
   the agent sandbox, so retrieval and parsing are split on purpose — the agent
   supplies the bytes, the module supplies the interpretation, and *the
   interpretation is therefore testable by the agent even though the fetch is not.*
   That is the direct structural answer to 11 Aug's unrunnable-module error.
   Classifies pages **FINAL / PREOPEN / INTRADAY / UNKNOWN** and derives the session
   from the **Last Update clock time against SET trading hours, never from the
   stamp's calendar date**. `close_mark()` returns the close *and which field it came
   from* (`last` vs `prior`), because a caller that cannot tell those apart will
   eventually file a pre-open `Prior` as today's close. **INTRADAY refuses to yield
   a close at all.** Adds `band_check()` (reproduces the exchange's ±30% tick-rounded
   band as a checksum on `Prior`), `internal_consistency()` (value÷volume vs
   published average price; `Last` inside the day range), a Buddhist-era year guard,
   and `previous_trading_day()` — whose **inability to handle Thai public holidays is
   documented in the docstring rather than hidden**, because 2026-08-12 is very
   likely one. `fetch_and_parse()` exists for Tho's machine only and is explicitly
   marked as such.
2. **`data_collector/market_data.py`** — `resolve_current_price()` now falls through
   to the observed-mark store via a new `_observed_mark_price()` helper, ranked
   **below the live feed and above nothing**, returning session date, source URL and
   corroboration count. This closes the 11 Aug top-priority item. **Separately, a
   real defect was found and labelled in the yfinance path**: it stamps `as_of` with
   `date.today()` — the *retrieval* date, not the session — so a quote pulled on a
   Sunday wore a Sunday date. That is the same conflation that let a February BAFS
   price wear an August date for five runs. Added a non-breaking `as_of_basis` field
   (`"retrieval_date"` vs `"session_date"`) so consumers can finally tell the two
   apart. Nothing existing was removed; the yfinance path still wins when it works.
3. **Data artefacts** — `data/observed_marks.json` (3 marks superseded to
   first-party, 2 history rows added, 0 conflicts), `data/snapshots/2026-08-12.json`
   (carries both the mixed-date total and the clean same-session total, plus a
   full attribution of the 9,380 overstatement), `data/market_intel/2026-08-12.md`,
   `data/watchlist.json` (+32 `aug12_` keys into `macro_context`, 6 catalysts updated).

### Verification actually performed
All three touched Python files pass `ast.parse`. **`set_official.py` was executed
against the real retrieved page text for all three pages**, and the test **found a
genuine bug**: `prior_close()` dated BAFS's `Prior` to 2026-08-11 when it belongs to
2026-08-10 — the overnight-FINAL case, where the page reports the *previous*
session, so `Prior` is two steps back from the stamp. Fixed by resolving the
reporting session first and stepping back from it (`_reporting_session()`), then
re-tested. Post-fix: BAFS → FINAL, close 11.30 @ 2026-08-11, prior 11.20 @
2026-08-10; SCB → PREOPEN, close 152.00 @ 2026-08-10; SET index → INTRADAY,
**close refused**. Band checks reconcile on both stocks; BAFS value÷volume gives
11.1787 against a published 11.18. Tick rounding verified on all four band
endpoints. `previous_trading_day` verified across a weekend (Mon 08-10 → Fri 08-07).

**`_observed_mark_price()` was executed live** (extracted and run in isolation,
since `market_data` needs Postgres and yfinance) across all four paths: three hits
with correct session dates and provenance, one miss (`NOSUCH.BK` → `None`), and
**stale refusal** at `max_age_days=0` for both a 1-day-old and a 2-day-old mark.

Arithmetic reconciles: 11.30×18,200 = 205,660; 152.00×1,400 = 212,800 (×2);
**mixed total 631,260**. Clean 08-10 basis: 203,840 + 209,300 + 212,800 =
**625,940**; weights **32.5654 / 33.4377 / 33.9969** summing to **exactly 100.0**.
Overstatement 635,320 − 625,940 = **9,380**, and the per-leg attribution
(0.40×18,200 = 7,280) + (1.50×1,400 = 2,100) = **9,380** ✓. Dividend 4.50×1,400 =
**6,300**, ×0.9 = **5,670**; drop 4.50/152.00 = **2.9605%**.
`watchlist.json` duplicate-key scan before and after → **NONE** both times; keys
landed in `macro_context` (**594 → 626**, +32, zero collisions), not in a new
top-level key — the specific error self-caught on 11 Aug.

### Self-caught error, disclosed
The first draft of `data/market_intel/2026-08-12.md` refuted the aggregator's ฿8.40
BAFS quote on the grounds that it "sits below SET's own 52-week low". **That is
false — 8.40 > 7.90.** The quote is refuted as a *current* price by the exchange's
11.20/11.30 prints, and the aggregator is discredited more broadly by publishing a
52-week range of 6.70–12.70 against SET's 7.90–11.80. Caught on re-read, corrected
in both the intel file and `watchlist.json`, and the correction is left visible in
the file rather than quietly deleted. The lesson is uncomfortably close to tonight's
Finding 4: **a wrong reason for a right conclusion is still wrong**, and it is
easiest to skip the check when the conclusion already feels settled.

### Caveats
(a) **Collector dead 28 days, 9th run** — unfixable from here; needs Tho's
supervisor/launchd. (b) **SCB is one session stale**; its page served a pre-open
cache and re-fetching within the hour was deduplicated, so no 11 Aug SCB close was
obtainable tonight. The book total remains mixed-date and is labelled as such.
(c) **No mark is corroborated for its current session** — `uncorroborated()` still
returns all three; a single first-party source is authoritative but not corroborated,
and the store correctly declines to conflate those. (d) **Thai holidays are not
encoded** in `previous_trading_day()`; if 2026-08-12 is a holiday, sessions derived
around it will be off by one. (e) **India, Europe and Vietnam were not refreshed.**
(f) The US large-cap tick snapshot came from a page ticker with **no stated session
date** and is recorded as indicative, not as marks. (g) Brent ~$87–88 and last
night's $84.68 come from **different vendors** and are not strictly comparable.
(h) `avg_cost_price = 0` is **guarded, not fixed** — P&L stays suppressed.
(i) `set_official.py` was tested against **stock quote pages**; the index page
parses only partially (it correctly warns about layout drift) and is not supported.
(j) The new `market_data` fallback was **not** exercised end-to-end with the brief
and snapshot writers — cross-package imports still need Postgres and separate venvs
unavailable in this sandbox.

### Next Priority (for next run)
🚨 **Thursday 2026-08-13 is tomorrow and it is the hard dated item**: PTTEP must be
held through the close; then **log the 08-14 open against the THB 4.50 theoretical
drop (2.9605%)**, because a materially different drop is information about demand
rather than noise. **Get an 11 Aug and 12 Aug SCB close** — the pre-open cache is
the only reason the book is still mixed-date, and the fix is now trivial: re-read
the SET page at a time when it is in FINAL state. **Wire the SET holiday calendar**
(`set.or.th/en/about/event-calendar/holiday`) into `previous_trading_day()` — with
12 Aug likely a holiday this is no longer housekeeping, it silently mis-dates every
mark taken around it. **Capture BAFS H1-2026 (~08-14)** into
`data/earnings/bafs_h12026_actual.json` and wire `BAFS.BK` into
`load_earnings_actual().actual_map`; judge on **throughput**. **Read the 12 Aug CPI
against the HIKE base case**, and revisit gold commentary under the corrected sign
on both rates (headwind) and FX (tailwind). **Measure the PTTEP/BAFS oil betas** —
tonight's single session says the "hedge" may not exist, and a hedge that is assumed
rather than measured is worse than no hedge, because it suppresses the concentration
alarm that all three legs above 33% should be ringing. **Decide Vietnam before
2026-08-21.** Standing and unchanged: **ask Tho for real `avg_cost_price` values**
and **solve the gold sleeve unit count** — the largest position in the book is still
the one the system cannot value, and it is now nine runs old.

---

## Nightly Run — 2026-08-13 02:30 ICT

### Market Intelligence Summary
July US CPI cooled to **3.4% headline / 2.5% core**, pulling the September FOMC base
case back from HIKE to **HOLD with a ~1/3 hike tail** — the fourth restatement of that
frame in five runs and the second reversal. The Strait of Hormuz remains closed, with
gasoline **+24.6% y/y** now plainly visible inside the US inflation basket. Europe
closed at records (Euro Stoxx 50 6,553; Stoxx 600 660.8) while Asia was mixed.
**Thailand did not trade at all: 12 August was HM Queen Sirikit the Queen Mother's
Birthday**, the exact holiday last night's `previous_trading_day()` docstring
predicted it would mishandle.

### Thai Holdings Update
- **BAFS 11.30** (+0.10, +0.89%), session 11 Aug. Re-confirmed on a later exchange
  publish (stamp advanced 02:34:39 → 03:20:09, identical figures).
- **PTTEP 152.00** (+2.50, +1.67%), session 11 Aug. **Today is the last cum-dividend
  day**: DPS 4.50, XD 14 Aug, pay 28 Aug → THB 6,300 gross / 5,670 net on 1,400
  shares; theoretical ex-price **147.50**.
- **SCB 152.00 (0.00, 0.00%)** — ✅ **the stale-SCB item is closed.** The page now
  serves overnight-FINAL instead of the pre-open cache that blocked it on 11 Aug.
- **Gold sleeve — unvalued, 10th run.** NAV **23.7123**/unit at 11 Aug (+1.96%), fund
  NAV THB 8.05bn, bid/offer 23.6767/23.8749. Spot **$4,432.09** (12 Aug 09:00 ET) vs
  $4,396.53 at the same clock time on 11 Aug, **+0.81%** — a like-for-like comparison.
  December futures on the same page (4,430 / 4,470.40) were **not** used.
  **Unit count still unknown.**
- **Book: THB 631,260, fully same-session on 2026-08-11.** Weights 32.5793 /
  33.7104 / 33.7104. Unlike the 12 Aug run's clean total, which was for a session two
  days behind the market, this one is at the market's frontier.

### 🚨 Finding 1: the holiday the last run predicted, confirmed and encoded
`set_official.previous_trading_day()` shipped on 12 Aug with a docstring naming its
own limitation and the exact date that would break it. Asked for the session before
Thursday 13 August it answered **Wednesday 12 August — a day the exchange was shut.**
Every mark, cum/ex boundary and "previous close" derived from that would have been
**off by one session, while looking entirely ordinary**. Same class as the
February-price and Buddhist-era traps: wrong, and unremarkable-looking.

Confirmed two independent ways: the EOD publish stamp on all three holdings still
read `12 Aug 2026 03:20:09` at 02:30 ICT on 13 Aug — never advanced, because there
was nothing to publish — and contemporaneous reporting of the closure.

### ⚠️ Finding 2: last night's total was right for the wrong reason
SCB closed **unchanged** on 11 Aug. So last night's *mixed-date* total (THB 631,260)
equals tonight's *fully same-session* total (THB 631,260) — **identical, because the
stale leg happened not to move.** The number was right; the method was not. A
mixed-date total that comes out correct is still a mixed-date total, and this
coincidence must not be read as evidence the practice is safe. Recorded prominently
in the snapshot precisely because it is the kind of near-miss that otherwise gets
filed as a success.

### 🚨 Finding 3: the fee schedule — first hard numbers Tho's stated concern has ever had
Fees were one of the three founding concerns of this project. `fee_analyzer.py` has
been computing drag since 18 June from a TER **nobody ever supplied**. SCBAM's page
was read in full tonight:

| Management 0.436025% p.a. | max 1.07% |
| Trustee 0.0321% | max 0.107% |
| Registrar *"as announced"* | max 0.11% |
| **Front-end 0.535%** | brokerage 0.15% |

**Buying the fund costs more than owning it for a year** — the entry charge is
**1.227 years** of management fee. Per THB 100,000: a 3-month hold costs 0.80%
(**3.21% annualised**); 24 months costs 1.62% (**0.81% annualised**). *Holding period
alone swings the annualised fee 4x* — a quantified argument for the long end of Tho's
own 3mo–2yr mandate, and against incremental top-ups, each of which pays 0.535% again.

Three caveats all push the true number **up**: every total is a **lower bound**
(registrar "as announced", other fees "actual expenses"); SCBGOLD is a **feeder into
SPDR Gold Trust** whose ~0.40% sponsor fee sits inside the master and appears nowhere;
and the waivers are **waivers, not abolitions** — permitted maxima total 1.287% against
0.468% charged, **2.75x headroom**. Also newly established: the sleeve is **UNHEDGED**;
SCBAM runs a hedged class (SCBGOLDH) Tho does not hold.

### ⚠️ Finding 4: a signal that reverses every session is not a signal
The FX sign has flipped in **three consecutive runs** (11 Aug strengthening → 12 Aug
weakening → 13 Aug strengthening), each run dutifully reversing its predecessor's
gold commentary. Vendor noise alone (33.082 tonight vs 33.1160 last night for an
adjacent session, different vendors) is a meaningful fraction of the moves being
narrated. **Adopted rule: single-session FX moves get no portfolio interpretation.**
A class switch costs 0.535% — ~1.23 years of management fee and ~6x the largest daily
FX move in the sample. `gold_fee_drag.compare_share_classes()` therefore returns
`recommendation: None` **by design**, with the reason in the code rather than implied.

Relatedly, the 12 Aug run's HIKE base case rested on a CME FedWatch reading from
6 August that was **already six days stale when used** — taken before the 7 August
jobs miss that moved it. A policy frame rebuilt nightly from the freshest headline
will oscillate regardless of what the Fed does. **Revise on data releases, not on runs.**

### Technology Sector Highlight
US large-cap tech was again the drag: the S&P/Nasdaq/Dow set circulating under an
"August 12" headline (7,728.20 / 26,445.45 / 53,791.85) is in fact the **11 August**
close — the body text says "closed lower on Tuesday". On 12 August the indices *rose*
after CPI; a precise close was not obtained and is **left blank rather than guessed**.
That is the 12 Aug dating rule working on its first night in force. Nikkei **67,524**
(+0.83%, measured from Monday — Japan was shut Tuesday for Mountain Day), Hang Seng
**25,440** (−0.83%), Shanghai **3,946** (+0.32%), Sensex **77,966.35** (−0.24%, second
down session), DAX **26,357.07**, Euro Stoxx 50 **6,553** and Stoxx 600 **660.8** both
at records. India and Europe both refreshed after going stale.

### Improvements Implemented Tonight
1. **`data_collector/set_holidays.py` (NEW, ~290 lines)** — the SET non-trading-day
   calendar, closing the top-priority item from 12 Aug. Thailand-only by design
   (this answers "was the SET open", nothing else). Key decisions: the table is
   **dated and sourced per year**, and lookups outside its range **raise
   `YearNotCoveredError` rather than degrading to weekends-only** — a calendar that
   silently downgrades is the bug, not the fix. Thai holidays are **not
   extrapolable** (lunar observances move ~11 days/yr, substitution days depend on
   weekday placement, Cabinet adds ad-hoc holidays — 2026 has two), so refusing to
   guess is the only safe behaviour. `sessions_between()` counts **staleness in
   sessions, not calendar days**, because age limits in calendar days retire good
   marks over long weekends and keep bad ones over short ones. The bank-vs-exchange
   distinction is recorded in `NOTES` (SET sometimes trades when banks are shut; the
   source annotates those "(exch Open)" and 2025-10-13 is excluded on that basis) so
   the omission reads as a decision rather than an oversight.
2. **`data_collector/set_official.py`** — `previous_trading_day()` now delegates to
   the holiday calendar. Import is optional and failure is **non-fatal but not
   silent**: the new `holiday_calendar_status()` reports `holiday_aware` vs
   `weekend_only` so callers can tell which mode they are in instead of assuming.
   Out-of-table years fall through to the old behaviour rather than crashing. Nothing
   was removed; the previous implementation survives as the fallback path.
3. **`portfolio_engine/gold_fee_drag.py` (NEW, ~310 lines)** — the fee schedule as
   code. `annual_fee_drag()` returns totals explicitly flagged `is_lower_bound: True`
   with the excluded components **enumerated in the return value**, not in a comment,
   so a caller cannot present it as "the TER". `entry_fee_breakeven()` returns the
   entry charge in years of recurring fee against **two denominators**, because
   quoting one while naming the other is how a right number becomes a wrong claim.
   `currency_decomposition()` spells out that a **positive USD/THB change means a
   weaker baht and is a tailwind** for a THB holder — the specific sign error made on
   11 Aug and corrected on 12 Aug.
4. **Data artefacts** — `data/observed_marks.json` (SCB superseded to a FINAL 11 Aug
   mark; BAFS and PTTEP re-confirmed on the later publish, recorded as raising
   confidence but explicitly **not** as independent corroboration),
   `data/snapshots/2026-08-13.json`, `data/market_intel/2026-08-13.md`,
   `data/watchlist.json` (+74 `aug13_` keys into `macro_context`, 626 → 700).

### Verification actually performed
All three touched Python files pass `ast.parse`. **`set_holidays.py` was executed**
across nine cases: the motivating case (`previous_trading_day(2026-08-13)` → **2026-08-11**,
not 08-12); the holiday itself; `next_trading_day(2026-08-11)` → **2026-08-13**
(skipping the holiday); the **Songkran+weekend run** (`previous_trading_day(2026-04-16)`
→ **2026-04-10**, verified to be a Friday); a plain weekend crossing; `sessions_between(11 Aug, 13 Aug)`
= **1** against 2 calendar days; and out-of-range **raising** as specified.
**`set_official.py` was executed post-edit**: status reports `holiday_aware` years
[2025, 2026]; `previous_trading_day(2026-08-13)` → 2026-08-11; the 2028 out-of-table
case falls back cleanly to 2028-03-14 without crashing; `round_to_tick` still returns
106.5/197.5, confirming nothing existing broke.
**`gold_fee_drag.py` was executed** across all five public functions.

Arithmetic reconciles. Book: 11.30×18,200 = 205,660; 152.00×1,400 = 212,800 (×2);
**total 631,260**; weights 32.5793/33.7104/33.7104. Internal consistency on all three
legs (value÷volume vs published average): SCB **152.1267** vs 152.13, PTTEP **151.0640**
vs 151.06, BAFS **11.1787** vs 11.18. Bands reconcile with correct tick rounding on
all three. Dividend 4.50×1,400 = **6,300**, ×0.9 = **5,670**; drop 4.50/152.00 =
**2.9605%**; ex-price **147.50**. Gold NAV 0.4561/23.2562 = **1.9612%** (the first
draft wrote 1.9614 and was corrected). **Every world index was reconciled against the
level already on file rather than accepted**: Nikkei 66,970.22+553 = 67,523.22 vs
67,524; Hang Seng 25,652.82×0.9917 = 25,439.9 vs 25,440; Shanghai 3,934.09×1.0032 =
3,946.68 vs 3,946; SET 1,624.36−11.74 = 1,612.62 exactly. `watchlist.json`
duplicate-key scan → **NONE**; keys landed in `macro_context` (626 → 700, +74, zero
collisions), not a new top-level key.

### Caveats
(a) **Collector dead 29 days** — needs Tho's supervisor/launchd; unfixable from here.
(b) **The holiday table is a SECONDARY source.** It was transcribed from SCBAM's
published fund trading calendar because set.or.th's own holiday table renders
client-side and returned **empty**. SCBAM is a large regulated Thai asset manager and
its Thailand column tracks the exchange, but it is one step removed from the issuer;
2026-08-12 is separately corroborated, the other 19 dates are not. Re-derive from SET
when a renderer is available. (c) **No mark is corroborated by a second SOURCE** —
tonight's repeat retrievals are temporally independent but come from the same
publisher. (d) **Brent $87.72 is a 10 Aug print**, three days stale, carried because no
clean same-vendor 12 Aug figure was obtained; 12 Aug reporting says crude is "nearing
$90". (e) **The 12 Aug US close was not obtained** and is `null` in the snapshot rather
than filled with the 11 Aug figure. (f) **BAFS H1-2026 remains unresolved** — 06 Aug
(investing.com) vs ~14 Aug (12 Aug estimate); an aggregator returned a quarterly line
(sales 914.80 / NI 43.62 / EPS 0.05) with **no period label**, so it was **not adopted**,
per the 12 Aug rule. (g) **Vietnam: seventh deferral.** (h) `avg_cost_price = 0` still
guards P&L to suppressed. (i) The new holiday wiring was **not** exercised end-to-end
through the brief and snapshot writers — cross-package imports still need Postgres and
separate venvs unavailable here. (j) Half-days are not modelled.

### Next Priority (for next run)
🚨 **Log the 14 August PTTEP open against the 147.50 theoretical ex-price** — that
deviation is the actual information; the theoretical drop is not. **Resolve BAFS
H1-2026 from `set.or.th/.../financial-statement/latest/income`**, which is
server-rendered, rather than the news list that returned empty; judge on **throughput**.
**Build a price-history store** — this is now the blocking dependency for the oil-beta
work, which cannot proceed without a sample, and the hedge thesis has sat at one
contrary observation and zero confirming for three runs. **Re-derive the holiday table
from SET directly** if a client-side renderer becomes available, and extend it to 2027
before year-end. **Decide Vietnam before 2026-08-21.** Standing and unchanged, now with
a price attached: **ask Tho for the gold sleeve unit count** — tonight established that
the sleeve carries a 0.468% p.a. known drag, a 0.535% entry toll and full unhedged
USD/THB exposure, and it is *still* the one position the system cannot value, ten runs
on. **Ask Tho for real `avg_cost_price` values.**

---

## Nightly Run — 2026-08-14 02:30 ICT

### Market Intelligence Summary
The **IEA now expects global oil demand to CONTRACT by 1.6 mb/d in 2026** — demand
destruction from high prices, product shortages and the Strait of Hormuz closure,
where transits fell to **8 vessels on 11 August against 125–140/day pre-war**, a
~94% collapse. A demand-side downgrade arriving with a supply-side price is the
worst combination for PTTEP's medium-term earnings and is tonight's most
consequential item for Tho's book. In the US, July CPI (+0.1% m/m, 3.4% y/y; core
+0.2%/2.5%) and a **flat July PPI** against +0.2% expected have the market pricing
a September Fed hold; the S&P 500 cleared 7,800 for the first time on 13 August.

### Thai Holdings Update
- **PTTEP: 150.50** (13 Aug close, −1.50/−0.99% from 152.00). Open 151.50, range
  149.50–151.50, 20,592,787 shares, THB 3,104,940.36k. **Goes ex-dividend today.**
- **BAFS: 11.40** (+0.10/+0.88%), range 11.20–11.40, 319,014 shares. **H1-2026
  filing date resolved** — see below.
- **SCB: no close obtained.** Carried at its 11 Aug close of 152.00. See below.
- **Gold fund:** gold futures ~$4,446 / spot ~$4,401. Sleeve still unvalued —
  **eleventh consecutive run** — because the unit count is unknown.

### Technology Sector Highlight
Korea was the standout: **KOSPI +4.22% to 6,856.49**, into bull-market territory on
renewed AI interest. Nikkei +1.61% to 68,611.73 (Japan's chip subsidies may swing a
$6.4bn TSMC–Sony JV); Shenzhen +1.06%, Shanghai +0.44%, Hang Seng −0.21% — *all
13 Aug 09:40 ICT intraday, not closes*. US AI earnings were two-sided: Cerebras
−15.3% on a revenue miss. The item worth keeping: BofA notes **IT commodities rose
1.4% m/m and contributed 12bp to core goods inflation** — AI capex is now visibly
feeding the US inflation print, which cuts against the "AI is disinflationary"
framing this log has repeated before.

### Improvements Implemented Tonight
1. **`data_collector/set_quote_parser.py` (NEW, ~330 lines)** — status-gated
   interpretation of SET quote pages, written because of a live near-miss. All
   three holdings were retrieved within ~40 seconds; PTTEP and BAFS returned
   `Status: Closed` stamped 14 Aug 02:35 ICT, but **SCB returned `Status: Open1`
   stamped 13 Aug 09:59:37** — a cached snapshot from ten minutes into the morning
   session. Its `Last` of 152.00 is an intraday print. Booked naively it would have
   become "the 13 Aug close", and it would have passed every downstream sanity
   check, **because it happens to equal the genuine 11 Aug close of 152.00**. A
   wrong number that agrees with the previous right number is the hardest kind to
   catch, so it is caught at parse time. Design decisions: `QuoteSnapshot.close`
   returns `None` unless `kind == CLOSE`, and there is deliberately **no `price`
   convenience property** — every caller must state which semantics it wants,
   because "close enough" is the failure mode. A `Closed` status older than 24h is
   downgraded to `UNKNOWN` rather than trusted. `session_date_for()` encodes that a
   stamp before 10:00 ICT describes the **previous** session.
2. **`portfolio_engine/price_history.py` (NEW, ~340 lines)** — the price-history
   store, which the last three runs named as the blocking dependency for the
   oil-beta work. One row per (ticker, **session**), append-only with explicit
   supersede: a re-observation either agrees (and records whether the agreeing
   source was *independent*, since a repeat fetch of one publisher is not) or
   conflicts (both retained, conflict logged, **never averaged**). A confirmed
   close supersedes an unconfirmed mark; nothing else does. `beta()` **refuses**
   below 20 paired sessions and correlation below 10, returning `refusal_reason`
   instead of a number — a beta from four points is not a weak estimate, it is
   noise wearing a decimal point, and that refusal is precisely what the hedge
   thesis has needed someone to say. Writes are atomic via `os.replace`.
3. **`portfolio_engine/dividend_tracker.py`** — added `theoretical_ex_price()` and
   `ex_open_deviation()`. The new function takes `last_cum_session` and `ex_date`
   as **required** keyword arguments it uses only to validate itself, because of a
   real error corrected tonight (below). It cross-checks the named session against
   the SET holiday calendar and refuses when they disagree. Nothing was removed.
4. **Data artefacts** — `data/price_history/prices.json` (NEW, seeded with 5
   first-party bars), `data/snapshots/2026-08-14.json`,
   `data/market_intel/2026-08-14.md`, `data/observed_marks.json` (PTTEP and BAFS
   advanced to 13 Aug confirmed closes; SCB's rejected intraday retained as a
   rejection record), `data/watchlist.json` (+100 `aug14_` keys, 700 → 800).

### Corrections to previously published figures
- **PTTEP theoretical ex-price: 147.50 → 146.00.** The 13 Aug run computed
  152.00 − 4.50, using the 11 August close because it was the newest mark on file.
  But PTTEP traded on 13 August and closed at **150.50**, and *that* was the last
  **cum** session. Correct reference: 150.50 − 4.50 = **146.00**. The published
  figure was wrong by 1.50 — **one third of the dividend itself**. The arithmetic
  was never in doubt; the *reference price* was. This is the specific failure mode
  now blocked in code.
- **Drop ratio 2.9605% → 2.9900%** (4.50/150.50), same cause.
- **BAFS H1-2026 date conflict — RESOLVED, and both prior candidates were wrong.**
  SET's own filing index shows `Financial Statement : Q2/2026`, Consolidate,
  Reviewed, attached as `0669FIN110820261011160173E.zip`; the filename encodes
  **11 Aug 2026 10:11:16**. Not investing.com's 06 Aug, not the 12 Aug run's
  ~14 Aug estimate. The *figures* still did not render (client-side table), so the
  unlabelled aggregator line (914.80 / 43.62 / 0.05) is now *plausibly* Q2/2026
  but is **still not adopted** — plausible is not confirmed.
- **US 12 Aug closes obtained**, closing the 13 Aug run's explicit open item:
  S&P 7,748.50 / Nasdaq 26,588.49 / Dow 53,770.27. All three reconcile against the
  11 Aug levels on file to within 0.25 points, confirming that baseline was right.
- **Brent 87.72 (10 Aug, three days stale) retired**: 12 Aug settlements Brent
  **88.98**, WTI **83.27**.

### The structural finding: the queue asked for the impossible
The 13 Aug run's top-priority next action was *"log the 14 August PTTEP open
against the theoretical ex-price."* **That task was impossible at the moment it was
written.** This run begins at **02:30 ICT on 14 August**; the SET opens at
**10:00 ICT** — 7.5 hours later. A 02:30 nightly agent can never observe a same-day
open. This is not a data gap but a category error about what the agent can see, and
it would have recurred silently every time an event was queued for "tomorrow".
Adopted: same-day-open observations are queued for the run *after* the session.

### Verification actually performed
All three touched Python files pass `ast.parse`. **`set_quote_parser.py` was
executed** on tonight's three real retrievals plus four negative controls: PTTEP
and BAFS classified `CLOSE` and both attributed to session **2026-08-13** (not
08-14 — the pre-10:00 rule working); **SCB classified `INTRADAY` with `close ==
None`**; an 81.7h-old `Closed` stamp downgraded to `UNKNOWN`; a future-dated stamp
rejected; a `last` outside the day range flagged. **`price_history.py` was
executed** across insert / same-source repeat (`independent: False`) /
different-source repeat (`independent: True`) / conflict-retention /
confirmed-supersedes-unconfirmed; `returns()` reproduced 150.50/152.00 − 1 =
−0.009868 exactly; `beta()` with n=0 **refused** as designed; and on a synthetic
25-session sample with true β = 0.8 it recovered **0.8361** (r = 0.9728),
confirming the estimator itself is sound and the refusal is about sample size, not
a broken calculation. **`dividend_tracker.theoretical_ex_price()` was executed**:
the correct call returns **146.00** with drop ratio 2.9900% and net 4.05/share,
and **the 13 Aug error was reproduced and rejected** with the calendar naming
2026-08-13 as the session that should have been used. Three further guards
(dps ≥ price, cum-after-ex, malformed dates) all fire.

Arithmetic reconciles. Book: 11.40×18,200 = 207,480; 150.50×1,400 = 210,700;
152.00×1,400 = 212,800; **total 630,980** against 631,260 on 11 Aug, **−280
(−0.0444%)**; legs +1,820 / −2,100 / 0 sum to −280. Weights 32.8822 / 33.3925 /
33.7253. Internal consistency: PTTEP value÷volume **150.7781** vs published average
**150.78**; BAFS **11.2731** inside 11.20–11.40; SCB's rejected intraday
**152.0001** (self-consistent, which is the point — internal consistency does not
make an intraday print a close). **SET's published floor/ceiling 106.50 / 197.50
match our `round_to_tick` of 152.00 × 0.7 and × 1.3** — the first validation of
that function against the issuer rather than against ourselves. Every world index
was reconciled against the level already on file: Nikkei 67,524 × 1.0161 =
68,611.14 vs 68,611.73; Hang Seng 25,440 × 0.9979 = 25,386.58 vs 25,385.66;
Shanghai 3,946 × 1.0044 = 3,963.36 vs 3,963.84; **Sensex 77,966.35 − 104.87 =
77,861.48, matching to 0.01 points** — which is what decided the India conflict
below. `watchlist.json` duplicate-key scan → **NONE** (700 → 800, +100, zero
collisions).

### Conflicts adjudicated rather than averaged
- **India.** One headline read "Sensex gains 114 pts, Nifty ends at 24,396";
  another gave −104.87 / −82.60 and a third straight down session. Adopted the
  latter: it chains off the 12 Aug level on file to within **0.01 points**, and the
  other set chains to nothing.
- **SET dating.** A search summary dated the 1,612.62 close to 12 August. The
  source says "Last Tuesday"; 11 Aug 2026 is the Tuesday; 12 Aug was Mother's Day
  and the exchange was shut. **The holiday calendar built on 13 August held on its
  first live test.**
- **US CPI.** Kaohoon reported headline +0.2% m/m; TheStreet, citing BLS, gives
  headline +0.1% with core +0.2%. Adopted the BLS-granular set — Kaohoon appears to
  have conflated core with headline.
- **Gold "record".** A claimed $5,602.22 record on 28 Jan 2026 appeared in one
  low-quality source. **Not adopted**: it implies a −21% drawdown to today's
  ~$4,400 that nothing else corroborates.
- **Gold quote types.** Futures ~$4,446–4,462 and spot ~$4,401 differ by ~$45.
  Recorded separately; they are different instruments and must not be compared
  across quote types.

### Vietnam — closed after seven deferrals
The premise of every deferral was wrong: there is no 21 August constituent list to
wait for. FTSE Russell **confirmed** the Frontier → Secondary Emerging upgrade at
its March 2026 review (announced Oct 2025, confirmed 8 Apr 2026), effective
**21 September 2026**, phased into 2027. The sizing settles it: Vietnam is projected
at **0.22% of the FTSE Emerging Index** / 0.34% of Emerging All Cap, and the
preliminary 28-stock list still rests on **31 Dec 2024** data. A ten-month-
telegraphed reclassification worth ~22bp of a benchmark is not a medium-term
thesis. **Verdict: no position. Item closed.** Revisit only on a domestic catalyst.

### Caveats
(a) **Collector dead 30 days** — needs Tho's supervisor/launchd; unfixable from
here. (b) **The book is no longer fully same-session** — a regression from 11 Aug,
caused by SCB's rejected mark. Stated, not hidden. (c) **No mark is corroborated by
a second SOURCE**; set.or.th is first-party, which is better, but it is still one
publisher. (d) **SET 13 Aug full-day close not obtained** (only the morning session,
1,617.25) and left null. (e) **US 13 Aug closes not obtained**; the "cleared 7,800"
record is recorded as a headline claim, not a level. (f) **DAX 13 Aug not
obtained.** (g) **BAFS Q2 figures still unconfirmed** even though the filing date
now is. (h) **Gold sleeve unvalued, eleventh run.** (i) `avg_cost_price = 0` still
suppresses all P&L. (j) The new modules were **not** exercised end-to-end through
the brief and snapshot writers — cross-package imports still need Postgres and
separate venvs unavailable here; `dividend_tracker` had to be loaded with
`utils.common` stubbed because `httpx` is absent from this sandbox. (k) The price
history holds **2 sessions**; `coverage()` reports **19 more sessions** before any
beta is permitted.

### Next Priority (for next run)
🚨 **Log the actual 14 August PTTEP open against 146.00** — now correctly scheduled
for the run that *follows* the session, and note that the deviation, expressed as a
fraction of the 4.50 dividend, is the information; the theoretical drop is not.
**Recover the SCB 13 August close** and restore the book to same-session; if
set.or.th again returns a cached morning snapshot, that cache behaviour is itself
worth characterising (retry timing, or a second first-party endpoint). **Feed
`price_history` every night without exception** — it is now the only mechanism that
converts nightly work into a sample, and it is 19 sessions from earning the right
to answer the oil-beta question. Seed Brent into it alongside the equities, since
the hedge thesis needs the benchmark leg too. **Extend the holiday table to 2027**
before year-end and re-derive from SET directly if a client-side renderer becomes
available. Standing and unchanged, now in its eleventh run: **ask Tho for the gold
sleeve unit count** — the sleeve carries a 0.468% p.a. known drag, a 0.535% entry
toll and full unhedged USD/THB exposure, and it is still the one position the
system cannot value. **Ask Tho for real `avg_cost_price` values.**

---

## Nightly Run - 2026-10-30 02:30 ICT (research-only)
- Mode: research_only (config/self_develop.json); no code edited.
- Wrote data/market_intel/2026-10-30.md (164 headlines) and data/watchlist.json engine_snapshot (25 items).
- Factor alerts: brent, us_iran_news, earnings_xd; regime risk_on.

## Nightly Run - 2026-10-31 02:30 ICT (research-only)
- Mode: research_only (config/self_develop.json); no code edited.
- Wrote data/market_intel/2026-10-31.md (166 headlines) and data/watchlist.json engine_snapshot (25 items).
- Factor alerts: gold; regime risk_on.

## Nightly Run - 2026-11-01 02:30 ICT (research-only)
- Mode: research_only (config/self_develop.json); no code edited.
- Wrote data/market_intel/2026-11-01.md (234 headlines) and data/watchlist.json engine_snapshot (25 items).
- Factor alerts: gold; regime risk_on.

## Nightly Run - 2026-11-02 02:30 ICT (research-only)
- Mode: research_only (config/self_develop.json); no code edited.
- Wrote data/market_intel/2026-11-02.md (317 headlines) and data/watchlist.json engine_snapshot (33 items).
- Factor alerts: gold; regime risk_on.

## Nightly Run - 2026-11-03 02:30 ICT (research-only)
- Mode: research_only (config/self_develop.json); no code edited.
- Wrote data/market_intel/2026-11-03.md (528 headlines) and data/watchlist.json engine_snapshot (33 items).
- Factor alerts: brent, us_iran_news; regime risk_on.

## Nightly Run - 2026-11-04 02:30 ICT (research-only)
- Mode: research_only (config/self_develop.json); no code edited.
- Wrote data/market_intel/2026-11-04.md (545 headlines) and data/watchlist.json engine_snapshot (33 items).
- Factor alerts: brent, us_iran_news, jpythb; regime risk_on.

## Nightly Run - 2026-11-05 02:30 ICT (research-only)
- Mode: research_only (config/self_develop.json); no code edited.
- Wrote data/market_intel/2026-11-05.md (527 headlines) and data/watchlist.json engine_snapshot (33 items).
- Factor alerts: brent, us_iran_news, jpythb, gold, set_index; regime risk_on.

## Nightly Run - 2026-11-06 02:30 ICT (research-only)
- Mode: research_only (config/self_develop.json); no code edited.
- Wrote data/market_intel/2026-11-06.md (526 headlines) and data/watchlist.json engine_snapshot (33 items).
- Factor alerts: brent, us_iran_news, jpythb; regime risk_on.

## Nightly Run - 2026-11-07 02:30 ICT (research-only)
- Mode: research_only (config/self_develop.json); no code edited.
- Wrote data/market_intel/2026-11-07.md (508 headlines) and data/watchlist.json engine_snapshot (33 items).
- Factor alerts: brent, eurthb, jpythb, set_foreign_flow; regime risk_on.

## 2026-11-07 - Two-sided news-impact model (shadow only)
- Lesson: the 2026-11-05 US selloff (Nasdaq about -5.5%, S&P 500 about -4.4% per reports; SPY -4.41%, QQQ -6.49%, SMH -11.21% in our price file) was driven by AI/tech policy headlines after the Democratic sweep, not the election result itself. The model must score UP and DOWN news separately, by sector, and check each call against prices.
- Save point: local commit fd04701 (push BLOCKED: no git remote `origin` configured).
- Backups: ~/backups/investor_db/investor_db_20261107_093518.dump and ~/backups/code/investment_advisor_20261107_093518.tar.gz.
- Added: config/news_impact_rules.json (UP/DOWN regex per sector, proxies SPY/QQQ/SMH/XLE, 3-day decay 1/0.5/0.25); ai_engine/news_impact.py (classify, price check, append-only shadow log); ops/news_impact_backtest.py (read-only, gated per direction); ops/news_impact_shadow_run.py; ops/migrations/20261107_news_impact_shadow.sql (NOT run; owner to review and run); tests/test_news_impact.py (7 pass).
- Added data: data/news_impact/prices_daily.csv (yfinance daily closes, 14 tickers, 2024-06-03 to 2026-11-06); data/news_impact/backtest_2026-11-07.json; data/shadow/news_impact_shadow.jsonl.
- Backtest (14,411 headlines read, 840 matched, 234 events after de-duplication by sector/direction/reaction day): DOWN passed backtest_gate (129 events, mean signed day-0 +0.50%, hit 54.3%); UP failed (105 events, skill negative, hit 49.5%). UP stays out of scoring.
- Known noise: some non-US headlines match the broad-market and AI rules (e.g. Brazilian stocks, a Bitcoin story). DOWN pass is provisional; any rule change needs a new out-of-sample check.
- Not done: no DB writes; no advice, signal or weight changed; no scheduled routine created.

## Nightly Run - 2026-11-08 02:30 ICT (research-only)
- Mode: research_only (config/self_develop.json); no code edited.
- Wrote data/market_intel/2026-11-08.md (199 headlines) and data/watchlist.json engine_snapshot (33 items).
- Factor alerts: brent, set_index, set_foreign_flow; regime neutral.

## Nightly Run - 2026-11-09 02:30 ICT (research-only)
- Mode: research_only (config/self_develop.json); no code edited.
- Wrote data/market_intel/2026-11-09.md (116 headlines) and data/watchlist.json engine_snapshot (33 items).
- Factor alerts: brent, jpythb, set_index, set_foreign_flow; regime neutral.

## Nightly Run - 2026-11-10 02:30 ICT (research-only)
- Mode: research_only (config/self_develop.json); no code edited.
- Wrote data/market_intel/2026-11-10.md (525 headlines) and data/watchlist.json engine_snapshot (33 items).
- Factor alerts: brent, us_iran_news, jpythb, set_index; regime neutral.
