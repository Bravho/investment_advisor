# Cross-border institutional allocation and the investment-advisor project

Date: 2026-11-02 ICT

## Executive conclusion

Large international funds do not simply rank countries by GDP growth or news sentiment. They choose a portfolio under mandate, benchmark, liquidity, currency, risk-budget, legal-access and implementation constraints. The useful prediction target for this project is therefore not “money moves from country A to B” as one number. It is a set of channel-specific probabilities: foreign equity pressure, foreign bond pressure, currency-hedging pressure and slow structural allocation.

The project already observes many useful inputs (SET foreign net flow, NVDR, VIX, US yields, USD/THB, policy rates, oil, price regime, geopolitics and country-index proxies). Its main gaps are country-relative features, expected real/hedged returns, benchmark events, market-accessibility changes, growth/earnings revisions and point-in-time historical flow data. Until those gaps and a walk-forward test are addressed, the new score must remain shadow/context-only.

## How institutions actually decide

### 1. Mandate and benchmark define the feasible decision

An emerging-market equity manager usually begins with a benchmark weight, tracking-error limit and country/sector caps. A passive fund must trade index changes; an active benchmark-aware fund can underweight or overweight, but large deviations consume risk budget. Benchmark changes can therefore create flows even when the macro view is unchanged. BIS research documents benchmark effects on both passive and active allocations, including the staged inclusion of China A-shares in MSCI EM.

### 2. Expected return is relative and currency-aware

For equities, managers compare expected earnings growth, revisions, valuation, profitability and price momentum against peers. For bonds, they compare expected total return: yield/carry plus roll-down plus expected duration return, less default risk, expected FX loss and hedging cost. The destination policy rate alone is not enough. BIS evidence emphasizes that FX swaps and yield-curve slopes materially affect cross-border bond allocation and that reference, investment and funding currencies can differ.

### 3. Global “push” conditions set the risk budget

VIX/global volatility, US rates, dollar strength, global liquidity and drawdowns determine whether funds can take emerging-market risk. IMF work finds that global risk aversion and global rates are important at higher frequency. These conditions often decide whether there is an EM allocation wave at all.

### 4. Local “pull” conditions decide where the wave goes

Relative growth, inflation credibility, real rates, fiscal/external balances, reserves, political stability, governance, financial depth and market liquidity distinguish recipient countries. Different investor types respond differently: long-only equity funds emphasize long-run growth and institutions; bond funds emphasize inflation, fiscal credibility and hedged carry; hedge funds respond faster to catalysts and positioning; sovereign/pension funds move more slowly.

### 5. Accessibility can dominate attractiveness

MSCI’s framework captures the implementation test: foreign-ownership openness, ease of inflows/outflows, operational efficiency, instruments and institutional stability, in addition to size and liquidity. A cheap market that cannot absorb institutional size, repatriate capital reliably, settle efficiently or hedge currency will not receive the allocation its valuation alone suggests.

### 6. Flow mechanics and feedback matter

Client subscriptions/redemptions, margin and volatility targets, dealer balance sheets, FX hedging, month/quarter-end rebalancing, index review dates and crowded positioning can force trades. Inflows can strengthen the currency and lift prices, inducing return-chasing; outflows can do the reverse. This reflexivity means observed flow and return must be modeled with lags and never used contemporaneously as a clean predictor.

### 7. Geopolitics changes bilateral allocation

Geopolitical alignment, sanctions, custody risk and supply-chain exposure can affect where a fund is legally or practically willing to invest. IMF evidence indicates geopolitical distance affects bilateral fund allocations, while stronger institutions can mitigate the effect.

## Feature architecture for this project

| Layer | Horizon | Candidate features | Project status |
|---|---:|---|---|
| Global push | days-weeks | VIX level/change, DXY, US 2Y/10Y, global equity trend, liquidity proxy | Mostly present |
| Country pull | weeks-months | relative index momentum, earnings revisions, valuation, growth/inflation surprises, real-rate differential, current account/reserves | Partial |
| Currency/hedging | days-months | FX trend/volatility, forward points, cross-currency basis, hedging cost, reserve adequacy | Spot FX present; hedging data absent |
| Flow confirmation | same day-weeks | foreign exchange trading, SET foreign flow, NVDR, bond flows, ETF creations | SET daily + NVDR present; history/channel breadth weak |
| Mechanical | known dates | MSCI/FTSE review, inclusion weight, futures roll, month/quarter-end rebalance | Absent |
| Structural | quarters-years | accessibility, free float/liquidity, governance, capital controls, tax/custody/settlement | Absent |
| Event/news | hours-weeks | policy surprise, election, capital control, downgrade, index decision, sanctions | Headlines present; event taxonomy/model not live |

### Correct target variables

Train separate models where data permit:

1. Thailand foreign-equity net flow over the next 5 and 20 sessions, scaled by market turnover or free-float capitalization.
2. Direction and magnitude bucket, rather than an over-precise point forecast.
3. SET/SET50 excess return over regional or EM benchmark after the signal, to test whether predicted flow pressure adds information useful to advice.
4. USD/THB response and a mediation test: whether the flow feature improves index forecasts beyond FX and global-risk variables.
5. Later: foreign bond flow and yield/FX targets, kept separate from equity.

### Leakage-safe sequence

At close of day *t*, freeze only data that were genuinely available then. Predict flows/returns for *t+1…t+5* or *t+1…t+20*. Today’s observed SET foreign flow is a confirmation label, not part of today’s lead score. Macro releases need vintage/release timestamps; revised final values cannot be backfilled as though they were known historically.

Use expanding or rolling walk-forward validation, embargo overlapping horizons, and compare against: zero flow, trailing mean, flow autocorrelation, and the existing price-only regime. Report rank correlation, sign accuracy, calibration, incremental index-return information coefficient, and strategy performance after realistic costs. Test Thailand separately; do not assume a global coefficient transports to SET.

## Advice integration rules

The advisor should use the layer as a qualifier, never a standalone buy/sell command:

- High-coverage inflow pressure + observed buying + improving relative momentum: raise confidence in a bullish Thai-index view, subject to valuation and frozen forecast.
- Positive lead but observed selling: call out divergence; it may be early, wrong, or blocked by a mechanical event. Do not average the two into false certainty.
- Outflow pressure + weaker baht + rising VIX: emphasize downside/FX risk for SET, banks and ThaiESG; for PTTEP, also examine the offset from oil/USD revenue.
- Flow pressure that conflicts with company fundamentals should affect timing/confidence, not erase the stock thesis.
- Low coverage: say “insufficient data”; never translate it into neutral conviction.
- Respect owner-hold rules for PTTEP and SCB. Flow analysis may describe risk but cannot recommend selling/trimming those holdings.

## News-to-feature mapping

Generic positive/negative news sentiment is too noisy. Map news into causal events with direction, surprise and expiry:

- Central-bank decision/guidance → expected real-rate and FX-hedging return.
- Fiscal package, GDP or earnings revision → relative growth/earnings feature.
- Election, court decision or protest → political-risk premium with an event window.
- Capital control, foreign-ownership, tax, settlement or short-selling rule → accessibility feature.
- MSCI/FTSE announcement → benchmark weight and estimated mechanical demand.
- Sovereign rating/outlook → credit/funding-risk feature.
- War/sanction/shipping shock → global-risk and country/sector exposure; do not double count across geo and news scores.
- Commodity shock → terms-of-trade effect by country and sector, not one universal sign.

Every extracted event should store source, publication time, affected countries/channels, expected sign, confidence, expiry and whether it was anticipated. Only the unexpected component should become a model feature.

## Implementation completed in this change

- `config/country_flow_model.json`: documented shadow weights, thresholds and guardrails.
- `portfolio_engine/country_flows.py`: leakage-safe lead-score combiner, observed-flow confirmation, conservative Thailand report (including a coarse SET-vs-SPY SMA200 relative state) and advisor context.
- Portfolio API endpoints: `/country-flows/thailand` and `/country-flows/advisor-context`.
- Main advisor now receives the context on every advice request. The block explicitly forbids calling an under-covered score a forecast and forbids inferring bond/FDI flows from SET equity data.
- Unit tests verify weight renormalization, minimum coverage, confirmation thresholds and exclusion of observed flow from the lead score.

The score is intentionally not connected to signals, frozen forecasts, construction weights or trade plans. That requires a point-in-time history and a passing walk-forward gate.

## Recommended next build order

1. Persist daily SET foreign-flow history reliably and verify gaps/revisions; normalize by turnover.
2. Add Thailand-vs-EM/Asia relative momentum and volatility with point-in-time prices.
3. Add official Thai bond foreign-flow data as a separate channel.
4. Add consensus growth/earnings revision vintages or honest, timestamped public proxies.
5. Add an index-review calendar and estimated passive demand using free-float changes.
6. Add expected real-rate and FX-forward/hedging-cost inputs; replace nominal carry.
7. Backtest 5/20-session flow and excess-return targets; calibrate thresholds only on training folds.
8. After a passing gate, introduce the feature first as a confidence modifier with a small capped effect, then monitor live attribution before any larger role.

## Primary sources

- IMF, *Capital Flows—Review of Experience with the Institutional View* (2016): growth differentials, risk aversion and interest-rate differentials as core portfolio-flow drivers. https://www.imf.org/external/np/pp/eng/2016/110416a.pdf
- IMF, *Portfolio Flows, Global Risk Aversion and Asset Prices in Emerging Markets* (2014): weekly push/pull framework and dynamic interaction with prices and FX. https://www.elibrary.imf.org/view/journals/001/2014/156/article-A001-en.xml
- IMF, *A Gravity Model of Geopolitics and Financial Fragmentation* (2024): geopolitical distance, institutions and bilateral fund allocations. https://www.elibrary.imf.org/view/journals/001/2024/196/article-A001-en.xml
- BIS, *Global portfolio investments and FX derivatives* (2025): FX hedging, yield curves and cross-border bond investment. https://www.bis.org/publ/work1273.pdf
- BIS, *Which exchange rate matters to global investors?* (2024): investment, reference and funding currency channels. https://www.bis.org/publications/working-paper-1210-which-exchange-rate-matters-global-investors
- BIS, *Changing patterns of capital flows* (2021): benchmark effects and China A-share inclusion case. https://www.bis.org/publ/cgfs66.pdf
- MSCI, *2026 Global Market Accessibility Review*: foreign ownership, capital mobility, operating framework, instruments and institutional stability. https://app2.msci.com/webapp/index_ann/DocGet?format=html&lang=en&pub_key=03Ct2I7v%2BzM%3D
- IMF Portfolio Investment Positions by Counterpart Economy (PIP/CPIS): slow bilateral position data for structural priors, not tactical timing. https://data.imf.org/datasets/IMF.STA%3APIP
- US Treasury International Capital system: monthly US cross-border securities and banking data. https://home.treasury.gov/data/treasury-international-capital-tic-system
- World Bank Worldwide Governance Indicators: structural governance estimates with explicit uncertainty; not a standalone investment rating. https://www.worldbank.org/en/publication/worldwide-governance-indicators
