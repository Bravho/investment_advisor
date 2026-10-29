"""
oil_scenario.py — Brent crude scenario analyzer for PTTEP.BK exposure.

Tho holds PTTEP (PTT Exploration & Production), a low-cost upstream oil & gas
producer whose revenue, earnings and dividend capacity are highly sensitive to
the realised Brent crude price. The US-Iran interim deal (signed Jun 17) drained
most of the geopolitical premium through June — but as of 2026-07-15 that deal has
COLLAPSED and the premium has RE-EMBEDDED. The truce broke down ~Jul 8 (Iran struck
commercial ships in Hormuz); US forces bombed 80+ targets inside Iran over Jul 12-13;
Iran's IRGC re-closed the Strait of Hormuz; and on Jul 13 the US reimposed a naval
blockade + a 20% cargo toll (effective Jul 14). Brent surged ~+10% on the week to
~$86 (Jul-14) as ~230 loaded tankers sit stranded in the Gulf and Hormuz crossings
fell >50% w/w (though ~8M bbl still transited Sunday with US military escort — a
blockade-and-toll, not yet a total cutoff). This module quantifies what different
Brent price regimes
mean for PTTEP so the daily brief and risk scorer can reason about the position in
concrete terms rather than headlines.

UPDATE 2026-07-16 — PARTIAL WALK-BACK: Trump ABANDONED the 20% Strait of Hormuz
cargo toll (CNBC, Jul-14) — the economic-friction leg of the Jul-13 measures is
now OFF, even as US airstrikes and the naval blockade continue. Brent eased
accordingly, settling ~$84.7 (Jul-14, Sep future ~$85.9) vs the ~$86-88 the Jul-15
re-rank assumed. Net: the realised base is a touch LOWER and slightly LESS
frictional than 24h ago, so this run trims the status_quo Brent anchor to ~$85 and
nudges a sliver of weight from status_quo toward deal_partial (the toll drop is a
mild de-escalation signal). The active-conflict tails are unchanged — strikes and
the blockade persist. See the 2026-07-16 re-rank block in brent_scenarios().

UPDATE 2026-07-24 — MAJOR RE-ESCALATION (Brent through $100): the Jul-16 partial
walk-back did NOT hold. Over Jul 18-23 the conflict widened: US airstrikes on Iran
ran a ninth consecutive night, Iran-backed Houthis struck two Saudi tankers in the
Red Sea and declared a blockade of Saudi ports (a SECOND disrupted trade route on
top of Hormuz), and tankers were reportedly hit off Saudi Arabia (Jul-23). Brent
surged ~+7% on Jul-23 to ~$100.7 (Trading Economics), the highest since May, +36%
month-on-month, with analysts flagging $120 as the next stop (CNBC). This run
therefore RE-RANKS hard toward the escalation tails: the two $105 tails are now
substantially REALISED, status_quo is re-anchored UP from $85 to ~$98 (the realised
blockade-plus-Red-Sea base), and deal_partial/deal_signed are cut further (we have
escalated, not de-escalated). Expected Brent moves to ~$101. PTTEP read: strong
realised-price TAILWIND with materially elevated operational/transit risk; BAFS read
flips to a jet-fuel-cost HEADWIND at $100 oil. See the 2026-07-24 re-rank block in
brent_scenarios().

The model is deliberately simple and transparent (a linear earnings-elasticity
to Brent around a base case), suitable for medium-term (3m-2y) position sizing —
NOT a trading model. All assumptions are documented inline and easily tuned.

Public API:
  - brent_scenarios()          -> dict of named Brent scenarios with PTTEP impact
  - pttep_sensitivity(brent)   -> single-price impact estimate
  - dividend_capacity(brent)   -> estimated dividend yield band at a Brent level
  - run_oil_scenario_report()  -> full report dict for brief injection + JSON save

Added by nightly agent 2026-06-14
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.common import PROJECT_DIR, configure_logging

logger = configure_logging("portfolio_engine.oil_scenario")

# ---------------------------------------------------------------------------
# Model assumptions (tune these as fundamentals update)
# ---------------------------------------------------------------------------

# Base case anchors the linear sensitivity model.
_BASE_BRENT_USD = 90.0          # reference Brent price for "neutral" PTTEP earnings
_PTTEP_BREAKEVEN_USD = 45.0     # approx. all-in cash cost / breakeven for a low-cost producer
_BASE_TRAILING_YIELD_PCT = 4.85 # PTTEP trailing dividend yield at base case
_LAST_PRICE_THB = 147.50        # last recorded PTTEP price (2026-04-23)

# Earnings elasticity: pct change in net income per $1 change in Brent, around base.
# A low-cost producer with high operating leverage: roughly +1.5% net income per +$1
# Brent near the $90 anchor (above breakeven, fixed cost base mostly covered).
_NET_INCOME_PCT_PER_USD = 0.015

# Dividend follows earnings with a payout buffer: yield scales ~0.6x of earnings move
# (PTTEP smooths dividends and retains for capex), floored at a minimum maintainable yield.
_DIV_BETA_TO_EARNINGS = 0.6
_MIN_MAINTAINABLE_YIELD_PCT = 3.0

_REPORT_DIR = PROJECT_DIR / "data" / "oil_scenarios"


# ---------------------------------------------------------------------------
# Core model
# ---------------------------------------------------------------------------

def pttep_sensitivity(brent_usd: float) -> dict[str, Any]:
    """
    Estimate PTTEP earnings impact at a given Brent price, relative to base case.

    Returns a dict with:
      brent_usd, delta_vs_base_usd, est_net_income_change_pct,
      margin_above_breakeven_usd, qualitative.
    """
    delta = brent_usd - _BASE_BRENT_USD
    ni_change_pct = round(delta * _NET_INCOME_PCT_PER_USD * 100, 1)
    margin_above_be = round(brent_usd - _PTTEP_BREAKEVEN_USD, 1)

    if brent_usd >= 100:
        qualitative = "Strong tailwind — well above breakeven; upside to earnings and dividend."
    elif brent_usd >= 85:
        qualitative = "Constructive — comfortably above breakeven; earnings near/above base."
    elif brent_usd >= 70:
        qualitative = "Neutral-to-soft — earnings below base but dividend likely maintained."
    elif brent_usd >= 55:
        qualitative = "Pressured — margin compresses; dividend coverage to watch."
    else:
        qualitative = "Stressed — approaching breakeven; dividend at risk."

    return {
        "brent_usd": round(brent_usd, 1),
        "delta_vs_base_usd": round(delta, 1),
        "est_net_income_change_pct": ni_change_pct,
        "margin_above_breakeven_usd": margin_above_be,
        "qualitative": qualitative,
    }


def dividend_capacity(brent_usd: float) -> dict[str, Any]:
    """
    Estimate PTTEP forward dividend-yield band at a given Brent price.

    Scales the base trailing yield by earnings change x dividend beta, floored
    at a minimum maintainable yield. Returns a low/base/high band on the current
    trailing yield (the band reflects payout-policy uncertainty).
    """
    sens = pttep_sensitivity(brent_usd)
    ni_change_frac = sens["est_net_income_change_pct"] / 100.0
    adj = 1 + (ni_change_frac * _DIV_BETA_TO_EARNINGS)
    base_yield = max(_BASE_TRAILING_YIELD_PCT * adj, _MIN_MAINTAINABLE_YIELD_PCT)
    return {
        "brent_usd": round(brent_usd, 1),
        "est_yield_low_pct": round(base_yield * 0.9, 2),
        "est_yield_base_pct": round(base_yield, 2),
        "est_yield_high_pct": round(base_yield * 1.1, 2),
        "dividend_at_risk": base_yield <= _MIN_MAINTAINABLE_YIELD_PCT + 0.2,
    }


# ---------------------------------------------------------------------------
# Named scenarios
# ---------------------------------------------------------------------------

def brent_scenarios() -> dict[str, Any]:
    """
    Return a set of named Brent scenarios tied to the current Iran-deal context,
    each with the PTTEP earnings and dividend impact.

    Scenarios (June 2026 context):
      - deal_signed_hormuz_open     : peace deal signed, Hormuz reopens -> premium gone
      - deal_partial                : ceasefire holds but full normalisation slow
      - status_quo                  : earlier ~$87 range persists
      - lebanon_spillover_reclosure : DISCRETE regional tail — Lebanon front drags
                                      Iran into re-closing Hormuz -> oil re-spike
      - nuclear_track_breakdown     : DISCRETE negotiation tail — roadmap/IAEA fails
    """
    # Re-ranked after the Jun 17 FORMAL signing — the deal-signed band is the
    # REALISED case, so the mass sits on deal_signed/deal_partial.
    # Updated 2026-06-24: BOTH oil tails RECEDED further. (1) The NUCLEAR track
    # keeps de-risking — Swiss talks resumed with a roadmap, IAEA inspectors back
    # in, and now the US has granted Iran a 60-DAY OIL-SALES LICENSE with Hormuz
    # traffic PICKING UP (Iran shipped >30M bbl last week) — Brent fell to a
    # ~3-MONTH LOW ~$77. (2) The Jun 19-20 Lebanon->Hormuz reclosure THREAT is
    # being WALKED BACK rather than executed. So the single "deal_collapses" case
    # is now SPLIT into TWO DISCRETE tails (matching the new
    # risk_scorer.lebanon_spillover_flag): `lebanon_spillover_reclosure` (the
    # regional channel, decoupled from the talks) and `nuclear_track_breakdown`
    # (the negotiation failing). Both trimmed: lebanon 8 -> 5 (threat receding),
    # nuclear -> 3 (roadmap + IAEA). deal_signed raised 62 -> 64 on the oil
    # license + rising transit; status_quo 6. Sum = 64+22+6+5+3 = 100. EIA still
    # models ~$105 Brent if Hormuz re-closes — anchors BOTH spike tails.
    # Added by nightly agent 2026-06-24
    #
    # RE-RANKED 2026-07-13: the "premium fully gone" conviction eased; Brent
    # firmed ~5% back to ~$76. Weights were deal_signed 58, deal_partial 26,
    # status_quo 6, lebanon 6, nuclear 4. Added by nightly agent 2026-07-13
    #
    # RE-RANKED 2026-07-15 — REGIME FLIP (opposite direction): the interim deal
    # has COLLAPSED into an active US-Iran conflict. Truce broke ~Jul 8, US bombed
    # 80+ Iranian targets Jul 12-13, Iran RE-CLOSED Hormuz, and the US reimposed a
    # naval blockade + 20% cargo toll (effective Jul-14). Brent surged +~10% w/w to
    # ~$86; ~230 tankers stranded, crossings down >50% (but ~8M bbl still transiting
    # under US escort — blockade-and-toll, NOT a total cutoff, hence ~$86 realised
    # rather than the $105 full-closure anchor). This INVERTS the Jul-13 read: the
    # "deal_signed / premium drained" leg is no longer the realised case — the
    # escalation legs are. Mass moved OFF deal_signed and ONTO the realised
    # blockade band + the two escalation tails: deal_signed 58 -> 8, deal_partial
    # 26 -> 24, status_quo 6 -> 30 (now the realised "blockade-but-flowing" ~$86-88
    # base), lebanon_spillover_reclosure 6 -> 18 (reclosure now ACTIVE), and
    # nuclear_track_breakdown 4 -> 20 (deal-collapse is REALISED, strikes ongoing).
    # Sum = 8+24+30+18+20 = 100. The $105 anchor on the tails = EIA full-Hormuz-
    # closure case. Risk skew for PTTEP flips from downside to UPSIDE (bullish
    # earnings) with elevated Middle East operational risk. Added by nightly agent 2026-07-15
    #
    # RE-RANKED 2026-07-16 — PARTIAL WALK-BACK (toll dropped): Trump ABANDONED the
    # 20% Hormuz cargo toll (CNBC Jul-14); the economic-friction leg is OFF while
    # airstrikes/blockade continue. Brent eased to ~$84.7 settle (Jul-14; Sep future
    # ~$85.9) vs the ~$86-88 the Jul-15 read assumed. So: status_quo Brent anchor
    # 87.5 -> 85.0 (toll removed = slightly less friction) and its weight 30 -> 28;
    # deal_partial 24 -> 26 (the toll drop is a mild de-escalation tell). Escalation
    # tails UNCHANGED (18 / 20) — strikes + blockade persist; deal_signed held at 8.
    # Sum = 8+26+28+18+20 = 100. Added by nightly agent 2026-07-16
    #
    # RE-RANKED 2026-07-24 — MAJOR RE-ESCALATION (Brent through $100): the Jul-16
    # walk-back reversed. Nine straight nights of US strikes on Iran; Houthis struck
    # two Saudi tankers in the Red Sea and declared a Saudi-port blockade (a SECOND
    # trade route down alongside Hormuz); Brent surged ~+7% Jul-23 to ~$100.7 (+36%
    # m/m), highest since May, with $120 flagged as the next stop. The realised print
    # (~$100) now sits AT the escalation-tail anchors, so mass moves onto them and the
    # base re-anchors up: deal_signed 8 -> 6, deal_partial 26 -> 12 (we escalated, not
    # de-escalated), status_quo anchor 85 -> 98 and weight 28 -> 34 (realised
    # blockade-plus-Red-Sea base), lebanon_spillover_reclosure 18 -> 24 (Red Sea is the
    # realised wider-regional second front), nuclear_track_breakdown 20 -> 24 with its
    # anchor lifted 105 -> 115 (sustained bombing campaign toward the $120 warning).
    # Sum = 6+12+34+24+24 = 100. Weighted Brent ~$101. Added by nightly agent 2026-07-24
    #
    # RE-RANKED 2026-07-25 — ESCALATION BROADENS TO A THIRD SUPPLY ROUTE. Incremental
    # tightening on the Jul-24 major re-rank: Brent settled ~$101.06 (4th straight
    # weekly gain, +14.6% on the week); Hormuz crossings fell to a SINGLE tanker
    # Thursday (lowest since May-7); and a NEW, non-Middle-East disruption appeared —
    # Kazakhstan cut output after suspected Ukrainian drone strikes closed the Caspian
    # Pipeline Consortium (CPC) Black Sea export terminal. Three disrupted routes now
    # (Hormuz + Red Sea + CPC) with de-escalation receding. Modest shift: status_quo
    # anchor 98 -> 100 (realised print, now embedding the CPC supply loss, weight held
    # at 34); deal_partial 12 -> 10 (a near-term climb-down is even less likely with a
    # widening, three-front disruption); lebanon_spillover_reclosure 24 -> 25 and
    # nuclear_track_breakdown 24 -> 25 (tails absorb the trimmed de-escalation mass).
    # Sum = 6+10+34+25+25 = 100. Weighted Brent ~$102. Added by nightly agent 2026-07-25
    #
    # RE-RANKED 2026-07-26 — FIRST DE-ESCALATION TELL (peak fear may be passing).
    # The Jul-24 session broke the one-way escalation: Brent settled DOWN 3.9% at
    # ~$96.78 (WTI $89.31) after reports that China is pushing — with Pakistan
    # mediating — a resumption of US-Iran talks centred on Hormuz (CNBC/Reuters,
    # Jul-24). This is a diplomatic TELL, not a resolution: US strikes continue,
    # and the THREE physical disruptions all persist (Hormuz constrained, Houthi
    # Red Sea/Saudi-port blockade, Kazakhstan's CPC Black Sea terminal still offline
    # with output cut). Pakistan flagged a PRECONDITION — a halt to attacks on Saudi/
    # Gulf targets — that is not yet met. So this mirrors the Jul-16 partial-walk-back
    # handling: shift a MODEST sliver from the escalation tails toward the
    # de-escalation path, and mark the realised print down to the Jul-24 settle,
    # WITHOUT declaring de-escalation. Moves: status_quo anchor 100 -> 97 (Jul-24
    # realised $96.78; weight held at 34 — supply is still physically disrupted);
    # deal_partial 10 -> 14 (the diplomatic channel reopened and oil fell 3.9%, so
    # the primary downside path gains probability); lebanon_spillover_reclosure
    # 25 -> 23 and nuclear_track_breakdown 25 -> 23 (talks-exploration trims the
    # total-closure / sustained-campaign tails); deal_signed held at 6 (still needs a
    # durable dual-front truce). Sum = 6+14+34+23+23 = 100. Weighted Brent ~$100
    # (still above spot — the tails price persistent physical-supply risk). Additive;
    # every change carries a 2026-07-26 marker. Added by nightly agent 2026-07-26
    #
    # RE-RANKED 2026-07-27 — DE-ESCALATION FIRMS (pause, not just talks-about-talks).
    # The Jul-26 "tell" hardened into action: the US and Iran PAUSED attacks on each
    # other for a SECOND straight day (Fortune/Fox, Jul-26), snapping a 13-day streak
    # of nightly US airstrikes, while Iran continued talks with OMAN over safe passage
    # of ships through Hormuz ("progress" reported). This is a genuine de-escalation
    # STEP — no longer merely a diplomatic rumour — though NOT yet a resolution:
    # Pakistan's precondition (a halt to Saudi/Gulf attacks) is still unmet, the three
    # physical disruptions (Hormuz constrained, Red Sea/Saudi-port blockade, CPC Black
    # Sea terminal) remain, and Brent held ~$96.78 (fear premium eased but barrels stay
    # off the market). So continue shifting a MODEST sliver from the escalation tails
    # onto the de-escalation paths, WITHOUT calling status_quo down materially (supply
    # is still physically disrupted): deal_signed 6 -> 8 (a durable dual-front truce is
    # now plausible after a two-day mutual pause), deal_partial 14 -> 18 (the Oman
    # Hormuz channel + the pause make partial throughput restoration the live primary
    # downside path), status_quo 34 -> 32 (premium continues to ease; anchor HELD at 97
    # — Brent unchanged ~$96.78), lebanon_spillover_reclosure 23 -> 21 and
    # nuclear_track_breakdown 23 -> 21 (the pause lowers total-closure / sustained-
    # campaign odds further). Sum = 8+18+32+21+21 = 100. Weighted Brent ~$98 (still
    # above spot — the tails price the persistent three-front physical disruption).
    # Additive; every change carries a 2026-07-27 marker. Added by nightly agent 2026-07-27
    #
    # RE-RANKED 2026-07-28 — TWO-SIDED: BILATERAL PAUSE HOLDS, RED SEA FRONT RE-OPENS.
    # The US-Iran bilateral de-escalation continued (pause held; Iran-Oman Hormuz
    # safe-passage talks ongoing), BUT over the weekend (Jul-25) the Houthis struck
    # Saudi Aramco on the RED SEA — a missile/drone attack that set the Jizan refinery
    # burning and hit Yanbu, Saudi Arabia's MAIN Red Sea oil port and the primary
    # workaround route for barrels skirting the blockaded Hormuz (Washington Post /
    # Al Jazeera / Reuters, Jul-25/26). So the two tracks now point opposite ways: the
    # bilateral truce path keeps firming while the PHYSICAL Red Sea disruption deepened
    # at exactly the workaround chokepoint. Brent held ~$96.78 — the two effects roughly
    # offset. Net move is a small counter-rotation vs Jul-27, NOT a continuation of the
    # de-escalation drift: deal_partial 18 -> 16 (near-term throughput restoration is
    # less clean while the Red Sea workaround port is under fire), lebanon_spillover_
    # reclosure 21 -> 23 (the Red Sea second front just RE-escalated — Yanbu/Jizan hit).
    # Held: deal_signed 8, status_quo 32 (anchor HELD at 97 — Brent unchanged ~$96.78),
    # nuclear_track_breakdown 21 (the bilateral pause still caps the sustained-campaign
    # tail). Sum = 8+16+32+23+21 = 100. Weighted Brent ~$98.9 (firmer than Jul-27's ~$98
    # — the Red Sea re-escalation re-prices the physical tail). Additive; every change
    # carries a 2026-07-28 marker. Added by nightly agent 2026-07-28
    #
    # RE-RANKED 2026-07-29 — DECISIVE DE-ESCALATION; FEAR PREMIUM DRAINS.
    # The two-sided stand-off broke to the DOWNSIDE. On Jul-27 the US PAUSED lethal
    # strikes (after a 13-day campaign) and Iran HALTED retaliation; on Jul-28 Iran was
    # reported discussing Hormuz shipping with BOTH Oman AND Saudi Arabia (CNN / Fortune /
    # CNBC, Jul-27/28) — i.e. the Saudi/Gulf leg that had been the unmet precondition is
    # now actively being negotiated. Oil crashed: Brent -7%+ Jul-27, settling ~$84-86 on
    # Jul-28 (WTI back below $80) as the geopolitical premium came out. Goldman: Brent
    # moderates to ~$80 by year-end IF Hormuz fully reopens. So the mass migrates hard onto
    # the de-escalation paths and the base re-anchors DOWN: status_quo anchor 97 -> 86
    # (Brent realised mid-$80s) and weight 32 -> 28; deal_partial 16 -> 30 (mid-$80s + the
    # broadening Oman/Saudi talks make this the LIVE realised path); deal_signed 8 -> 12
    # (a durable dual-front truce reopening Hormuz toward ~$76-80 is now the Goldman base-
    # case IF talks convert); lebanon_spillover_reclosure 23 -> 17 (trimmed but NOT gone —
    # the Jul-25 Yanbu/Jizan physical damage is unrepaired, so the Red Sea tail stays
    # live); nuclear_track_breakdown 21 -> 13 (paused strikes + halted retaliation + Saudi
    # talks make an open-ended campaign much less likely). Sum = 12+30+28+17+13 = 100.
    # Weighted Brent ~$91.2 — still ABOVE the ~$85 spot because the two escalation tails
    # (105/115, 30% combined) correctly price the unrepaired physical disruption and the
    # pause-could-break risk. PTTEP: realised-price tailwind ERODING fast — do NOT add into
    # a draining premium; BAFS: jet-fuel headwind EASING (net positive). Additive; every
    # change carries a 2026-07-29 marker. Added by nightly agent 2026-07-29
    #
    # RE-RANKED 2026-07-30 — DE-ESCALATION STALLS / PARTIALLY REVERSES.
    # The one-way drain of the fear premium stopped. On Jul-28 the US intercepted what it
    # called a "surprise attack" by Iran on US forces in the Middle East (CNN, Jul-28), and
    # on Jul-29 Iran REJECTED Oman's proposal for shared 50-50 control of the Strait of
    # Hormuz, insisting it retain full control of the inbound lane (Investing/Reuters,
    # Jul-29). Ceasefire talks are "shaky" and only being restarted. Brent, which had
    # crashed to ~$84-86, BOUNCED ~4-6% back toward $83-84 on Jul-29 as renewed hostilities
    # reignited the premium (Trading Economics / Fortune, Jul-29). Net: the de-escalation is
    # NOT dead but it has stalled, so a sliver of mass migrates BACK from the de-escalation
    # paths toward the base and the tails: deal_signed 12 -> 9 (Iran's explicit rejection of
    # a Hormuz split makes a CLEAN full reopen harder), deal_partial 30 -> 28 (still the
    # realised mid-$80s path but dented), status_quo 28 -> 30 (the drain stalled and Brent
    # bounced — the base firms), lebanon_spillover_reclosure 17 -> 19 (surprise-attack
    # intercept + unrepaired Yanbu/Jizan keep the physical tail live), nuclear_track_breakdown
    # 13 -> 14 (shaky ceasefire + Hormuz-deal rejection modestly lift open-ended-campaign
    # risk). Sum = 9+28+30+19+14 = 100. Weighted Brent ~$92.2 (up from ~$91.2 — the stall is
    # correctly re-pricing the tails UP). PTTEP: realised-price erosion PAUSES here — the
    # premium stops draining, but do NOT add (still a de-escalation-biased tape, and the Q2
    # Apr-Jun realised print is a look-back, not the spot). BAFS: jet-fuel relief PAUSES.
    # Additive; every change carries a 2026-07-30 marker. Added by nightly agent 2026-07-30
    #
    # RE-RANKED 2026-07-31 — RE-ESCALATION CONFIRMED (Brent back above $90).
    # The Jul-30 "stall" resolved to the UP-side. On Jul-29 Brent JUMPED 7.9% to settle
    # $90.74 after President Trump said the US "will hit Iran hard" in retaliation for the
    # intercepted Jul-28 surprise attack on US forces (CNBC, Jul-29); on Jul-30 Brent eased
    # below $90 but HELD most of the gain (~$88, CNBC/Trading Economics). Iran still insists
    # on full control of the inbound Hormuz lane and the Red Sea (Houthi) front is unresolved.
    # Forecasters re-priced UP: Barclays $100/$105/$110 for Hormuz normalisation by end-Jul /
    # end-Aug / later (Barchart), JPM ~$86 Q3; EIA's $74 3Q26 is now the dovish outlier. So a
    # further sliver migrates OFF the de-escalation paths and ONTO the base + escalation tails,
    # and the status_quo Brent anchor is marked UP $86 -> $89 to track the realised print:
    # deal_signed 9 -> 7 (a "hit Iran hard" tape makes a clean full reopen even less likely),
    # deal_partial 28 -> 24 (the mid-$80s de-escalation path is dented again), status_quo 30 -> 32
    # with anchor 86 -> 89 (Brent bounced back toward ~$88-90 — the base firms and re-anchors up),
    # lebanon_spillover_reclosure 19 -> 22 (surprise-attack retaliation + unrepaired Yanbu/Jizan
    # keep the total-cutoff tail live), nuclear_track_breakdown 14 -> 15 (the explicit US strike
    # threat lifts open-ended-campaign risk). Sum = 7+24+32+22+15 = 100. Weighted Brent ~$94.3
    # (up from ~$92.2, above the ~$88-90 spot — the tails correctly price the re-escalation).
    # PTTEP: realised-price tailwind RESUMES — but this is still NOT a chase-up signal (the Q2
    # Apr-Jun realised print is a look-back and results land Aug-02). BAFS: jet-fuel-cost headwind
    # RESUMES with Brent back toward $90. Additive; every change carries a 2026-07-31 marker.
    # Added by nightly agent 2026-07-31
    #
    # RE-RANKED 2026-08-01 — MILD EASING / CONSOLIDATION (threat NOT yet acted on).
    # The re-escalation did not extend. On Jul-31 Brent EASED to ~$86 (from ~$88 Jul-30),
    # though it still closed the month up MORE than 20% on the geopolitical premium
    # (CNBC / Trading Economics, Jul-31). Trump's "hit Iran hard" pledge has so far NOT
    # converted into a new strike, and while some tankers were still forced to turn around
    # in the Strait of Hormuz (physical friction persists), no fresh attack materialised.
    # So this is a modest consolidation, NOT a regime change: shave the status_quo Brent
    # anchor $89 -> $86 to track the Jul-31 print, migrate a small sliver from the top
    # escalation tail back to the primary de-escalation path, and hold the rest:
    # deal_signed 7 (held — a clean full Hormuz reopen still needs talks to convert),
    # deal_partial 24 -> 25 (mild easing nudges the mid-$80s path up a touch),
    # status_quo 32 (held; anchor 89 -> 86 to mark the realised easing),
    # lebanon_spillover_reclosure 22 -> 21 (the strike threat was NOT acted on this run —
    # trim the total-cutoff tail a notch, though unrepaired Yanbu/Jizan keeps it live),
    # nuclear_track_breakdown 15 (held — the pledge keeps open-ended-campaign risk elevated).
    # Sum = 7+25+32+21+15 = 100. Weighted Brent ~$93.1 (down from ~$94.3, still above the
    # ~$86 spot — the tails keep pricing the unrepaired physical disruption + threat risk).
    # PTTEP: realised-price tailwind HOLDS but flattening — still NOT a chase-up signal
    # ahead of the Q2 result (Aug-02 after-close). BAFS: jet-fuel-cost headwind EASES
    # slightly with Brent back toward ~$86. Additive; every change carries a 2026-08-01
    # marker. Added by nightly agent 2026-08-01
    #
    # RE-RANKED 2026-08-04 — DE-ESCALATION BREAKTHROUGH (largest downside move of the series).
    # This is a REGIME CHANGE, not a consolidation. On Aug-03 President Trump CALLED OFF a
    # planned "massive attack" on Iran after direct appeals from Saudi Arabia, the UAE, Qatar
    # and Iran itself, said peace talks would RESTART, and stated he expects the Strait of
    # Hormuz to reopen soon (CNN live-blog Aug-02/03; The National Aug-03; Bloomberg Aug-03).
    # Brent CRASHED 4.2% to ~$84 intraday Monday (WTI -5% to ~$80), then sat ~$81 on Aug-04
    # recovering only part of the prior session's sharp losses (Trading Economics Aug-04).
    # That is the LOWEST Brent print in this whole scenario series and it is driven by a
    # POLICY act (a strike stood down at Gulf request), not a drift. Counter-weight kept:
    # Iran DENIES that direct US talks are underway and has only offered a "temporary" safe
    # corridor via Oman rather than a full reopening, and Trump called Tehran's leadership
    # "unbelievably duplicitous" — so the clean full-reopen end-state is NOT yet realised.
    # Moves: deal_signed 7 -> 12 (a called-off strike + an explicit presidential expectation
    # of reopening makes the Goldman ~$80/full-drain end-state materially more plausible),
    # deal_partial 25 -> 33 (the Oman "temporary corridor" IS this scenario by definition,
    # and mid-$80s-and-below is what the tape printed — now clearly the REALISED path),
    # status_quo 32 -> 30 with anchor 86 -> 82 (mark to the ~$81-84 realised print),
    # lebanon_spillover_reclosure 21 -> 15 (a strike stood down AT GULF REQUEST sharply cuts
    # the regional-blow-up channel, though unrepaired Yanbu/Jizan keeps the tail alive),
    # nuclear_track_breakdown 15 -> 10 (an open-ended barrel-removing campaign is much less
    # probable with the attack cancelled and talks restarting). Sum = 12+33+30+15+10 = 100.
    # Weighted Brent ~$88.7 (down from ~$93.1) — still above the ~$81 spot because the tails
    # price the unrepaired physical damage and Iran's non-committal posture, but converging.
    # PTTEP: realised-price tailwind now ERODING AGAIN — the Q2 print (USD 833m) captured the
    # Apr-Jun premium and is a LOOK-BACK; Q3 faces both a lower oil tape AND the flagged
    # Thailand+Malaysia maintenance volume dip. Do NOT chase; the THB 4.50 interim (XD Aug-14)
    # is the reason to hold, not the price momentum. BAFS: jet-fuel-cost relief RESUMES and is
    # now the cleanest read in the portfolio — Brent ~$81 is the lowest since the conflict
    # began. Additive; every change carries a 2026-08-04 marker.
    # Added by nightly agent 2026-08-04
    #
    # RE-RANKED 2026-08-05 — THE $80 FLOOR BROKE. Confirmation, not a new regime.
    # On Aug-04 Brent fell a further 5.13% to $79.47 — the FIRST sub-$80 print of the
    # entire conflict series and below the Goldman ~$80 full-reopen anchor — after Trump
    # said another round of talks would begin Monday Aug-04 (The National Aug-04;
    # Bloomberg Aug-03/04; Trading Economics). Two counterweights kept and deliberately
    # NOT priced away: (1) Iran again DENIED direct US talks, saying its only live
    # discussions are with OMAN on reopening Hormuz; (2) Secretary of State Rubio said
    # progress had been made with Iran and Oman but that NO FINAL AGREEMENT exists, and
    # Trump framed the round as Iran's "LAST CHANCE" — hard language that can snap back.
    # So the market is now pricing the de-escalation END-STATE ahead of any signed deal.
    # Moves (all modest — the big migration already happened on Aug-04):
    #   deal_signed_hormuz_open 12 -> 15 (spot has now traded THROUGH this scenario's
    #     $76-80 zone; a talks round actually convening makes the full-drain end-state
    #     the second-most-likely path rather than a tail),
    #   deal_partial 33 -> 34 (still the MODAL path — the Oman "temporary corridor" is
    #     literally this scenario, and Rubio's "progress but no agreement" describes it),
    #   status_quo 30 -> 27 with anchor 82 -> 79 (mark to the $79.47 realised print),
    #   lebanon_spillover_reclosure 15 -> 14 (a convening talks round further thins the
    #     regional-blow-up channel; NOT closed — Yanbu/Jizan damage is still unrepaired),
    #   nuclear_track_breakdown 10 HELD (Trump's "last chance" framing is exactly the
    #     trigger language for this path, so it does NOT get trimmed alongside the others).
    # Sum = 15+34+27+14+10 = 100. Weighted Brent ~$87.5 (down from ~$88.7) — still ~$8
    # above the $79.47 spot because the two tails keep pricing unrepaired physical damage
    # and an unsigned deal. Read for Tho is UNCHANGED in direction but stronger:
    # BAFS is the cleanest beneficiary (jet fuel at the lowest Brent of the conflict);
    # PTTEP's realised-price premium keeps draining — note the stock has ALREADY given
    # back ~151 -> ~145 on Aug-04 — so hold for the THB 4.50 interim (XD Aug-14), do not
    # chase. Additive; every change carries a 2026-08-05 marker.
    # Added by nightly agent 2026-08-05
    #
    # RE-RANKED 2026-08-06 — A DRAFTED 60-DAY INTERIM HORMUZ DEAL. The Aug-05 tape
    # moved from "progress, no agreement" to an actual DRAFTED arrangement: the US,
    # Iran and Oman are near a 60-DAY interim deal to reopen the Strait, with concrete
    # terms — inbound ships routed north through Iranian territorial waters, outbound
    # south through Omani waters, NO transit fees or tolls, and the main lane's naval
    # MINES CLEARED WITHIN 30 DAYS, after which two-way traffic resumes under a
    # permanent arrangement still to be negotiated by Iran and Oman. Qatar confirmed an
    # interim proposal was drafted; Trump said talks were "moving along very nicely"
    # with more known "within 48 hours"; Axios reported Washington aimed to announce as
    # early as Wednesday Aug-05.
    #
    # Read carefully: this is deal_partial CRYSTALLISING, not deal_signed arriving. A
    # 60-day interim corridor with the permanent lane EXPLICITLY DEFERRED is the textbook
    # definition of partial de-escalation, so the mass goes there first.
    #
    # Counterweights kept — and one is severe: the parties reached a materially similar
    # interim agreement in JUNE, and it COLLAPSED over escalating hostilities focused on
    # the strait. That is direct precedent for failure of this exact instrument, so the
    # escalation tails are trimmed only modestly and NOT closed out. Note also that spot
    # did NOT extend its fall — Brent ROSE back above $80 on Aug-05 while holding most of
    # the prior two sessions' losses, i.e. the market has already largely paid for the
    # deal and is no longer being rewarded for it.
    #
    # Moves:
    #   deal_signed 15 -> 17 (a signed permanent lane is now a defined END-STATE of a
    #     live process rather than an aspiration — but it is explicitly deferred past
    #     the 60-day window, so the rise is deliberately small),
    #   deal_partial 34 -> 38 (a DRAFTED 60-day interim corridor IS this scenario, by
    #     definition; strengthened as the MODAL path),
    #   status_quo 27 -> 24 with anchor 79 -> 80.5 (mark to the Aug-05 recovery above
    #     $80; weight keeps migrating to the de-escalation paths),
    #   lebanon 14 -> 12 (a 30-day mine-clearing commitment directly addresses the
    #     unrepaired physical damage that has been holding this tail open),
    #   nuclear 10 -> 9 (the "last chance" round produced a draft rather than a
    #     collapse — trimmed only one point, because a 60-day clock that expires
    #     unsigned re-arms this path in October).
    # Sum 100; weighted Brent $87.49 -> $87.11. Additive; every change carries a
    # 2026-08-06 marker.
    # Added by nightly agent 2026-08-06
    scenarios = {
        "deal_signed_hormuz_open": {
            "brent_usd": 76.0,
            "narrative": (
                "GAINING PLAUSIBILITY (Jul-27): would require a durable truce that reopens "
                "Hormuz AND ends the Red Sea front, draining the premium back toward ~$76. "
                "Odds RAISED 6 -> 8 — the US and Iran have now PAUSED attacks for a second "
                "straight day (snapping a 13-day airstrike streak) and Iran-Oman Hormuz talks "
                "are progressing, so a durable dual-front truce is no longer the tail-of-the-tail. "
                "Still gated: Pakistan's precondition (a halt to Saudi/Gulf attacks) is unmet and "
                "the physical disruptions persist, so this remains a de-escalation END-STATE, not "
                "yet the realised case. Odds RAISED 8 -> 12 (Jul-29): with strikes paused, "
                "Iran's retaliation halted, and Hormuz talks now broadening to Saudi Arabia AND "
                "Oman, a durable dual-front truce reopening Hormuz is the Goldman base case "
                "(~$80 by year-end IF Hormuz fully reopens) — no longer the tail-of-the-tail."
            ),
            "probability_pct": 14,
            "probability_qualitative": "de-escalation end-state — CUT 17->14 (Aug-07), the first DOWNGRADE of this path in the series and the key call of the night: the bilateral leg firmed but the trilateral leg did not. Iran and Oman agreed the shipping-route COORDINATES 'in principle' (Bloomberg, Aug-06) — but Iran states explicitly that an Iran-Oman route agreement does NOT by itself reopen the waterway, and that the US must meet ADDITIONAL CONDITIONS before vessels transit freely. Trump's 'more within 48 hours' (Aug-05) lapsed without a signature and Washington's targeted Wednesday announcement slipped. CNN's read is the structural point: the arrangement taking shape is 'not one Trump wants' — a corridor managed by Iran and Oman through a joint coordination centre, with Iranian sovereignty over the inbound lane, is nearly the opposite of the US-guaranteed free-transit regime this scenario requires. A permanent free-transit lane got FURTHER away this session, not closer. PRIOR (Aug-06): RAISED 15->17 on a signed permanent lane becoming the defined end-state of a live drafted process",
        },
        "deal_partial": {
            "brent_usd": 84.0,
            "narrative": (
                "Partial de-escalation: some Hormuz throughput is restored (Iran-Oman safe-passage "
                "talks) and oil eases back toward the mid-$80s. Odds RAISED 14 -> 18 (Jul-27): the "
                "de-escalation FIRMED from a rumour into action — the US and Iran PAUSED attacks "
                "for a SECOND straight day and Iran continued Hormuz talks with Oman. This is now "
                "the LIVE primary DOWNSIDE path. Odds TRIMMED 18 -> 16 (Jul-28): the Jul-25 Houthi "
                "strike on Aramco's Yanbu (Saudi's MAIN Red Sea workaround port) + the Jizan "
                "refinery fire means a clean near-term throughput restoration is harder even as the "
                "bilateral pause holds. Still gated — Pakistan's Saudi/Gulf-ceasefire precondition "
                "is unmet — so it is a live, not yet realised, path. Odds RAISED 16 -> 30 "
                "(Jul-29): this is now essentially the REALISED path — the US-Iran mutual pause "
                "held, Iran opened Hormuz talks with Saudi Arabia as well as Oman, and Brent "
                "CRASHED ~7% to settle ~$84-86 (WTI back below $80). The mid-$80s de-escalation "
                "case is what the tape is pricing."
            ),
            "probability_pct": 44,
            "probability_qualitative": "partial de-escalation — RAISED 38->44 (Aug-07) and now the dominant path by a wide margin: the interim corridor moved from DRAFTED to AGREED IN PRINCIPLE on its bilateral leg. Iran and Oman have settled the geographic coordinates of the safe route, plus technical arrangements, sovereignty terms and a JOINT COORDINATION CENTRE to manage traffic and collect vessel information. Iran's deputy foreign minister now puts the arrangement's life at TWO TO FOUR MONTHS or longer — longer than the 60 days assumed on Aug-06, which extends this scenario's dwell time and pushes the expiry re-arm date out toward Oct-Dec rather than early October. Everything that made deal_signed harder makes this path easier: a managed, time-boxed, sovereignty-preserving corridor IS this scenario, and it is what both Tehran and Muscat actually want. Restraint kept: the June 2026 interim deal on this same strait collapsed, and 'agreed in principle' is still not 'in force'. PRIOR (Aug-06): RAISED 34->38 on the drafted 60-day interim terms",
        },
        "status_quo": {
            "brent_usd": 83.5,  # 2026-08-07: 80.5 -> 83.5 (Brent ~$83.64 on Aug-06, all but unchanged from Aug-05 — a THIRD consecutive session in which de-escalation news failed to push crude down); PRIOR 2026-08-06: 79.0 -> 80.5 (Brent ROSE back above $80 on Aug-05 while holding most of the prior two sessions' losses)
            "narrative": (
                "RE-ANCHORED UP SLIGHTLY (Aug-06): a DRAFTED 60-DAY INTERIM HORMUZ DEAL. "
                "The US, Iran and Oman are near an interim arrangement with concrete terms — "
                "inbound ships north through Iranian territorial waters, outbound south through "
                "Omani waters, NO tolls, main-lane mines cleared within 30 days, then two-way "
                "traffic under a permanent deal still to be negotiated. Qatar confirmed a draft "
                "exists; Trump said talks were 'moving along very nicely' with more known within "
                "48 hours. Crucially, spot did NOT extend its fall on the news — Brent ROSE back "
                "above $80 while holding most of the prior two sessions' losses, so the anchor is "
                "marked UP 79 -> 80.5 even as the weight is trimmed 27 -> 24. Read that pairing "
                "literally: the tape has ALREADY paid for the de-escalation and is no longer being "
                "rewarded for incremental good news, which caps how much further PTTEP erosion or "
                "BAFS relief this channel can deliver from here. Counterweight, and it is a "
                "serious one: the parties struck a materially similar interim deal in JUNE and it "
                "COLLAPSED over hostilities focused on this same strait — direct precedent for "
                "failure of this exact instrument. "
                "PRIOR (Aug-05): THE $80 FLOOR BROKE. Brent fell a further "
                "5.13% to $79.47 on Aug-04 — the first sub-$80 print of the whole conflict "
                "series and below Goldman's ~$80 full-reopen anchor — after Trump said another "
                "round of talks would begin Monday Aug-04. Anchor cut 82 -> 79 to mark it; "
                "weight trimmed 30 -> 27 as mass keeps migrating to the de-escalation paths. "
                "Counterweights kept: Iran again DENIED direct US talks (only the Oman corridor "
                "track is live) and Rubio said progress was made but NO FINAL AGREEMENT exists, "
                "with Trump framing the round as Iran's 'last chance'. So the tape is pricing "
                "the END-STATE ahead of any signature. PTTEP premium keeps draining and the "
                "stock has already given back ~151 -> ~145; BAFS jet-fuel relief is now the "
                "cleanest read in the portfolio at the lowest Brent of the conflict. "
                "PRIOR (Aug-04): DE-ESCALATION BREAKTHROUGH. Trump CALLED OFF a "
                "planned massive strike on Iran on Aug-03 after appeals from Saudi Arabia, the UAE, "
                "Qatar and Iran, said talks would restart, and said he expects Hormuz to reopen "
                "soon. Brent fell 4.2% to ~$84 (WTI -5% to ~$80) and sat ~$81 on Aug-04 — the "
                "lowest print of the series. Anchor cut 86 -> 82 to mark it; weight trimmed 32 -> 30 "
                "as mass migrates to the de-escalation paths. PTTEP realised-price tailwind now "
                "ERODING AGAIN (Q2 was a look-back; Q3 faces a lower tape AND maintenance volume "
                "dip); BAFS jet-fuel relief RESUMES and is the cleanest portfolio read. "
                "PRIOR (Aug-01): mild consolidation — Brent eased to ~$86 on Jul-31 "
                "(from ~$88) with Trump's strike threat NOT yet acted on, though it still closed "
                "the month up >20%. Anchor trimmed 89 -> 86 to track the print; weight HELD at 32. "
                "PTTEP realised-price tailwind holds but flattening; BAFS jet-fuel headwind eases. "
                "PRIOR (Jul-31): the fear premium REBUILT. Brent jumped 7.9% to $90.74 "
                "on Jul-29 after Trump vowed to 'hit Iran hard' for the intercepted surprise "
                "attack, then held ~$88 on Jul-30. Anchor raised 86 -> 89 to track the realised "
                "bounce; weight raised 30 -> 32 as the de-escalation drift reverses. PTTEP "
                "realised-price tailwind RESUMES; BAFS jet-fuel headwind RESUMES. "
                "PRIOR (Jul-29): the premium DRAINED. Brent fell ~7% and settled "
                "~$84-86 (from ~$96.78) after the US paused strikes, Iran halted retaliation, and "
                "Hormuz talks broadened to Oman AND Saudi Arabia. Anchor cut 97 -> 86 to mark the "
                "realised print; weight trimmed 32 -> 28 as mass migrates to deal_partial/"
                "deal_signed. Physical disruption is only PARTLY repaired (the Jul-25 Yanbu/Jizan "
                "Red Sea damage is unfixed), so a residual base premium remains — but the fear "
                "premium is largely gone. PTTEP realised-price tailwind now MODEST and eroding; "
                "BAFS jet-fuel headwind EASING (net positive for BAFS)."
            ),
            "probability_pct": 21,
            "probability_qualitative": "base TRIMMED 24->21 with anchor marked UP 80.5->83.5 (Aug-07) — the same deliberate pairing as Aug-06, now on its third consecutive session and therefore no longer a curiosity but the central observation of the whole oil view: probability mass keeps migrating to de-escalation while SPOT KEEPS RISING. Brent printed ~$83.64 on Aug-06, essentially unchanged from Aug-05, on a session that delivered agreed Iran-Oman route coordinates. Crude has now declined to fall on de-escalation headlines three times running. The inference is that the reopening is fully priced and the residual ~$8 premium over the weighted de-escalation cases is being held against something else — unrepaired Red Sea capacity, OPEC discipline, or the simple fact that an agreed corridor moves no barrels until mines are cleared. PRIOR (Aug-06): TRIMMED 27->24 with anchor 79->80.5",
        },
        "lebanon_spillover_reclosure": {
            "brent_usd": 105.0,
            "narrative": (
                "ESCALATION TAIL — RE-ESCALATED (Jul-28): the wider-regional Red Sea front, which "
                "the Jul-27 pause had been trimming, RE-OPENED — on Jul-25 the Houthis struck "
                "Aramco's Yanbu (Saudi Arabia's MAIN Red Sea oil port, the primary workaround for "
                "barrels skirting blockaded Hormuz) and set the Jizan refinery burning, in "
                "retaliation for Saudi strikes on Hodeidah. Odds RAISED back 21 -> 23: the physical "
                "second choke point is now actively under fire even as the US-Iran BILATERAL track "
                "pauses, keeping the total-cutoff / full-regional-war tail (past the EIA ~$105 "
                "anchor) live. Odds TRIMMED 23 -> 17 (Jul-29): the US-Iran bilateral pause held "
                "and Iran opened Saudi-track Hormuz talks, so a full regional blow-up is less "
                "likely — but this tail is NOT closed out, because the Jul-25 Yanbu/Jizan physical "
                "damage is unrepaired and a Red Sea flare-up could re-price barrels fast. Tracked "
                "by risk_scorer.lebanon_spillover_flag."
            ),
            "probability_pct": 12,
            "probability_qualitative": "escalation tail — HELD at 12 (Aug-07), deliberately NOT trimmed alongside the de-escalation re-rank: the Aug-06 news was a coordinates agreement, and coordinates do not clear mines. The 30-day mine-clearing commitment that justified the Aug-06 cut has not started, and nothing this session touched the Jul-25 Yanbu/Jizan Red Sea damage, which sits on the workaround route and is untouched by any Hormuz arrangement. Trimming this tail again on diplomatic progress alone would be double-counting the same headline. PRIOR — CUT 14->12 (Aug-06): the interim draft commits to clearing the main lane's naval MINES WITHIN 30 DAYS, which directly addresses the unrepaired physical damage that has been the main reason this tail stayed open. Not closed out — the Jul-25 Yanbu/Jizan damage is separate, sits on the Red Sea workaround route, and is untouched by a Hormuz agreement. PRIOR (Aug-05): a talks round actually convening Aug-04 further thins the regional-blow-up channel. Still NOT closed out — the Jul-25 Yanbu/Jizan damage remains unrepaired and a Red Sea flare re-prices barrels past $105 fast",
        },
        "nuclear_track_breakdown": {
            "brent_usd": 115.0,
            "narrative": (
                "ESCALATION TAIL — ODDS TRIMMED AGAIN (Jul-27): the interim deal remains collapsed "
                "but the US and Iran have now PAUSED strikes for a second straight day, further "
                "reducing the odds of an OPEN-ENDED sustained campaign. Odds TRIMMED 23 -> 21 "
                "(anchor held at 115): a campaign that removes Iranian barrels and/or closes Hormuz "
                "outright still drives Brent toward the $120 level analysts flagged (CNBC, Jul-23), "
                "but that path is less likely with a mutual pause and Oman talks live. Odds "
                "TRIMMED 21 -> 13 (Jul-29): with strikes PAUSED, Iran's retaliation HALTED, and "
                "the Saudi/Gulf leg now in negotiation, an open-ended barrel-removing campaign is "
                "materially less probable. Re-escalates fast if the pause breaks."
            ),
            "probability_pct": 9,
            "probability_qualitative": "escalation tail — HELD at 9 (Aug-07). Two Aug-06 developments pull in opposite directions and net to no change: the interim arrangement's stated life extended to TWO-TO-FOUR MONTHS (pushing the unsigned-expiry re-arm date out from ~Oct-04 toward Oct-Dec, which is mildly favourable), but Iran conditioning free transit on further US concessions keeps the nuclear track explicitly entangled with the maritime one, which is the exact linkage this path needs. A tail that is merely POSTPONED is not a smaller tail. PRIOR — CUT 10->9 (Aug-06), a single point only: the 'last chance' round produced a DRAFT rather than a collapse, which is the good outcome, but the instrument on the table is a 60-DAY INTERIM with the permanent lane deferred — so an unsigned expiry re-arms this path around early October, and the June interim deal on this same strait already collapsed once. PRIOR (Aug-05): HELD at 10, deliberately NOT trimmed alongside the others: Trump framed the Aug-04 round as Iran's 'LAST CHANCE' and Rubio confirmed no final agreement, which is precisely the trigger language for this path. A collapsed 'last chance' round is the single fastest route back to $115-120",
        },
    }
    for name, sc in scenarios.items():
        b = sc["brent_usd"]
        sc["pttep_impact"] = pttep_sensitivity(b)
        sc["dividend_capacity"] = dividend_capacity(b)
    return scenarios


def probability_weighted_outlook() -> dict[str, Any]:
    """
    Collapse the named scenarios into a single probability-weighted expectation
    for Brent and PTTEP earnings, using the re-ranked probability_pct weights.

    Useful for the daily brief: gives Tho one expected-value number alongside the
    scenario table, and makes the realised-probability re-ranking explicit.

    Added by nightly agent 2026-06-18
    """
    scenarios = brent_scenarios()
    total_w = sum(sc.get("probability_pct", 0) for sc in scenarios.values()) or 1
    exp_brent = sum(
        sc["brent_usd"] * sc.get("probability_pct", 0) for sc in scenarios.values()
    ) / total_w
    exp_ni_pct = sum(
        sc["pttep_impact"]["est_net_income_change_pct"] * sc.get("probability_pct", 0)
        for sc in scenarios.values()
    ) / total_w
    exp_div = dividend_capacity(exp_brent)
    return {
        "weights_sum_pct": total_w,
        "expected_brent_usd": round(exp_brent, 1),
        "expected_net_income_change_pct": round(exp_ni_pct, 1),
        "expected_yield_base_pct": exp_div["est_yield_base_pct"],
        "note": (
            f"Probability-weighted Brent ~${exp_brent:.0f} (the two escalation tails still carry the "
            f"mass ABOVE the ~$85 spot, pricing the unrepaired physical damage) -> est. PTTEP net "
            f"income {exp_ni_pct:+.1f}% vs base, yield ~{exp_div['est_yield_base_pct']}%. As of "
            "Jul-29 the de-escalation turned DECISIVE — the US PAUSED strikes, Iran HALTED "
            "retaliation, and Hormuz talks broadened to Saudi Arabia AND Oman (the Saudi/Gulf leg "
            "that was the missing precondition), so Brent CRASHED ~7% to ~$84-86 and the fear "
            "premium largely drained. The skew for PTTEP earnings is now MODEST-and-eroding (not "
            "the large tailwind of last week): mid-$80s de-escalation (deal_partial) is the "
            "realised path and mass has migrated onto deal_partial/deal_signed. Do NOT add PTTEP "
            "into a draining premium. Two-sided still: a durable Hormuz reopening takes Brent "
            "toward Goldman's ~$80 (further PTTEP erosion, but a clear BAFS tailwind), while a "
            "pause breakdown or Red Sea (Yanbu) flare re-prices the tails back toward $105-120 fast. "
            "UPDATE Jul-30: the drain STALLED — the US intercepted a 'surprise' Iranian attack "
            "(Jul-28), Iran REJECTED Oman's 50-50 Hormuz split (Jul-29), and Brent BOUNCED ~4-6% "
            "back toward $83-84. Mass migrated a sliver BACK to status_quo/tails (weighted Brent "
            "~$91->~$92); PTTEP erosion PAUSES (premium stops draining) but this is not an add "
            "signal, and BAFS jet-fuel relief PAUSES. "
            "UPDATE Jul-31: RE-ESCALATION CONFIRMED — Brent JUMPED 7.9% to $90.74 (Jul-29) after "
            "Trump vowed to 'hit Iran hard' for the intercepted attack, holding ~$88 on Jul-30. "
            "status_quo re-anchored 86->89 and mass shifted further onto the base + escalation "
            "tails (weighted Brent ~$92->~$94). PTTEP realised-price tailwind RESUMES but it is "
            "STILL not a chase-up signal (Q2 print lands Aug-02); BAFS jet-fuel headwind RESUMES. "
            "UPDATE Aug-01: MILD EASING / CONSOLIDATION — Brent eased to ~$86 on Jul-31 (from ~$88) "
            "with the 'hit Iran hard' threat NOT yet acted on, though it still closed the month up "
            ">20%. status_quo anchor trimmed 89->86, a sliver moved deal_partial 24->25 and lebanon "
            "22->21 (weighted Brent ~$94->~$93). PTTEP realised tailwind HOLDS but flattening — do "
            "NOT chase ahead of the Aug-02 Q2 print; BAFS jet-fuel headwind eases slightly. "
            "UPDATE Aug-04: DE-ESCALATION BREAKTHROUGH — a REGIME CHANGE, not a drift. Trump "
            "CALLED OFF a planned massive strike on Iran (Aug-03) after appeals from Saudi Arabia, "
            "the UAE, Qatar and Iran, said talks would restart, and said he expects Hormuz to "
            "reopen soon; Brent fell 4.2% to ~$84 (WTI -5% to ~$80) and sat ~$81 on Aug-04, the "
            "lowest print of the series. Mass migrated hard onto the de-escalation paths "
            "(deal_signed 7->12, deal_partial 25->33 — now the MODAL path via Iran's temporary "
            "Oman corridor) and OFF both tails (lebanon 21->15, nuclear 15->10), with status_quo "
            "re-anchored 86->82 and trimmed 32->30 (weighted Brent ~$93->~$89). For Tho this "
            "flips the intra-portfolio read: BAFS is now the cleanest beneficiary (jet-fuel "
            "relief resumes at the lowest Brent of the conflict) while PTTEP's realised-price "
            "tailwind ERODES AGAIN — the USD 833m Q2 was a LOOK-BACK on the Apr-Jun premium and "
            "Q3 faces both a lower tape and the flagged Thailand+Malaysia maintenance volume dip. "
            "Hold PTTEP for the THB 4.50 interim (XD Aug-14, pay Aug-28), do NOT chase the "
            "post-Q2 rally to ~151. Two-sided still: Iran DENIES direct talks and offers only a "
            "'temporary' corridor while Trump calls Tehran 'unbelievably duplicitous', so a "
            "breakdown snaps the tails back toward $105-120 fast. "
            "UPDATE Aug-05: THE $80 FLOOR BROKE — confirmation of the Aug-04 regime change, not "
            "a new one. Brent fell a further 5.13% to $79.47 on Aug-04, the first sub-$80 print "
            "of the series and below Goldman's ~$80 full-reopen anchor, after Trump said another "
            "talks round would convene Monday Aug-04. Modest further migration: deal_signed "
            "12->15, deal_partial 33->34 (still MODAL), status_quo 30->27 re-anchored 82->79, "
            "lebanon 15->14, nuclear HELD at 10 (weighted Brent ~$89->~$87.5). The nuclear tail "
            "is deliberately NOT trimmed: Trump called the round Iran's 'LAST CHANCE' and Rubio "
            "confirmed NO final agreement, so the market is pricing the end-state ahead of any "
            "signature. For Tho the direction is unchanged but stronger: BAFS is the clean "
            "beneficiary; PTTEP's premium keeps draining and the stock has ALREADY given back "
            "~151 -> ~145 on Aug-04 — hold for the THB 4.50 interim (XD Aug-14, pay Aug-28), do "
            "NOT chase, and treat a pullback that keeps the yield >4.5% as the add zone. "
            "UPDATE Aug-06: A DRAFTED 60-DAY INTERIM HORMUZ DEAL — deal_partial crystallising, "
            "NOT deal_signed arriving. The US, Iran and Oman are near an interim arrangement with "
            "concrete terms: inbound ships north through Iranian territorial waters, outbound "
            "south through Omani waters, NO transit tolls, main-lane naval mines cleared within "
            "30 days, then two-way traffic under a permanent deal STILL TO BE NEGOTIATED. Qatar "
            "confirmed a draft; Trump said 'more within 48 hours'; Axios reported Washington "
            "aimed to announce as early as Aug-05. Moves: deal_signed 15->17, deal_partial 34->38 "
            "(decisively MODAL), status_quo 27->24 with the anchor marked UP 79->80.5, lebanon "
            "14->12, nuclear 10->9 (weighted Brent ~$87.5->~$87.1). The single most useful "
            "observation tonight is the PAIRING of a trimmed base weight with a RAISED base "
            "anchor: Brent ROSE back above $80 on the deal news rather than extending its fall, "
            "which means the tape has already PAID for this de-escalation and has stopped being "
            "rewarded for incremental good news. For Tho that caps the channel in BOTH directions "
            "— the remaining BAFS jet-fuel relief and the remaining PTTEP premium erosion are now "
            "mostly priced, so neither name should be re-traded on further Hormuz headlines. Two "
            "counterweights kept and one is severe: the parties struck a materially similar "
            "interim deal in JUNE and it COLLAPSED over hostilities on this same strait, and the "
            "60-day clock expiring unsigned re-arms the escalation tails around early October. "
            "UPDATE Aug-07: THE BILATERAL LEG FIRMED AND THE TRILATERAL LEG DID NOT — this is the "
            "first re-rank in the series that moves deal_signed DOWN while moving deal_partial UP, "
            "and the split is the whole point. Iran and Oman AGREED THE ROUTE COORDINATES 'in "
            "principle' (Bloomberg, Aug-06), together with technical arrangements, sovereignty "
            "terms and a JOINT COORDINATION CENTRE; Iran's deputy FM now puts the arrangement's "
            "life at TWO TO FOUR MONTHS or longer, not 60 days. But Iran states plainly that the "
            "Iran-Oman agreement does NOT by itself reopen the waterway and that the US must meet "
            "ADDITIONAL CONDITIONS first; Trump's '48 hours' lapsed without a signature and the "
            "targeted Wednesday announcement slipped. CNN's framing is the structural read: the "
            "arrangement taking shape is 'not one Trump wants' — an Iran/Oman-managed corridor "
            "under Iranian sovereignty is close to the OPPOSITE of a US-guaranteed free-transit "
            "regime. Moves: deal_signed 17->14 (first downgrade of this path), deal_partial 38->44 "
            "(dominant by a wide margin), status_quo 24->21 with the anchor marked UP 80.5->83.5, "
            "lebanon HELD at 12, nuclear HELD at 9 (weighted Brent ~$87.1->~$88.1). Note the "
            "weighted number ROSE even as mass migrated to de-escalation — that is the base anchor "
            "moving, not the tails. THIRD CONSECUTIVE SESSION of the trimmed-weight/raised-anchor "
            "pairing: Brent ~$83.64 on Aug-06, essentially unchanged, on a day that delivered "
            "agreed coordinates. Crude has now declined to fall on de-escalation news three times "
            "running, which is as clear a 'fully priced' signal as this series has produced. Both "
            "tails HELD deliberately: coordinates do not clear mines, the 30-day mine-clearing "
            "commitment has not started, and the Jul-25 Yanbu/Jizan Red Sea damage is untouched by "
            "any Hormuz arrangement — trimming again on the same headline would be double-counting. "
            "NEW THIS RUN — THE CURRENCY LEG: `currency_exposure.oil_thb_transmission()` now prices "
            "the second channel by which Brent reaches this book. Thailand is a net energy importer, "
            "and the stated cause of the baht's 13-15 month low (33.39-33.64) is the oil-driven "
            "current-account deficit. So sustained high Brent weakens the THB, which LIFTS the "
            "unhedged SCBGOLDE sleeve and PTTEP's USD-referenced translated earnings. For Tho, high "
            "oil is substantially SELF-HEDGING at the portfolio level even though it is clearly "
            "negative for Thailand at the country level. The scenario that breaks the hedge is a "
            "DEMAND-LED oil collapse, where PTTEP earnings fall and the baht does not strengthen."
        ),
    }


# ---------------------------------------------------------------------------
# Report builder + persistence
# ---------------------------------------------------------------------------

def run_oil_scenario_report(current_brent_usd: float = 83.64) -> dict[str, Any]:  # 2026-08-07: 80.5 -> 83.64 (Brent $83.64 on Aug-06, ~flat vs Aug-05 — a THIRD straight session where de-escalation news did not push crude down; NOTE the feed dispersion this session: Brent $83.64 vs a separate "crude around $75" print and WTI $77.75, so the Brent-specific figure is used and the dispersion is logged); PRIOR 2026-08-06: 79.5 -> 80.5 (Brent ROSE back above $80 on Aug-05 on a DRAFTED 60-day interim Hormuz deal — the market had already paid for the de-escalation, so good news stopped being rewarded); PRIOR 2026-08-05: 82.0 -> 79.5 (THE $80 FLOOR BROKE — Brent -5.13% to $79.47 on Aug-04, first sub-$80 print of the series, ahead of the Aug-04 talks round; Iran still denies direct talks and Rubio confirms no final agreement)
    """
    Build a full PTTEP oil-scenario report for daily-brief injection and save a
    JSON copy to data/oil_scenarios/YYYY-MM-DD.json.

    Returns the report dict. Safe to call nightly.

    Added by nightly agent 2026-06-14
    """
    scenarios = brent_scenarios()
    current = pttep_sensitivity(current_brent_usd)
    current_div = dividend_capacity(current_brent_usd)

    # Build a compact human-readable summary for prompt injection.
    lines = [
        f"PTTEP / Brent scenario snapshot (current Brent ~${current_brent_usd:.0f}):",
        f"  • Current: {current['qualitative']} "
        f"(net income {current['est_net_income_change_pct']:+}% vs base, "
        f"est. yield ~{current_div['est_yield_base_pct']}%).",
    ]
    for name, sc in scenarios.items():
        lines.append(
            f"  • {name} (Brent ${sc['brent_usd']:.0f}): "
            f"NI {sc['pttep_impact']['est_net_income_change_pct']:+}% vs base, "
            f"yield ~{sc['dividend_capacity']['est_yield_base_pct']}% — "
            f"{sc['probability_qualitative']}."
        )

    report = {
        "ticker": "PTTEP.BK",
        "generated_at": datetime.utcnow().isoformat(),
        "current_brent_usd": current_brent_usd,
        "current_impact": current,
        "current_dividend_capacity": current_div,
        "model_assumptions": {
            "base_brent_usd": _BASE_BRENT_USD,
            "breakeven_usd": _PTTEP_BREAKEVEN_USD,
            "net_income_pct_per_usd": _NET_INCOME_PCT_PER_USD,
            "div_beta_to_earnings": _DIV_BETA_TO_EARNINGS,
            "base_trailing_yield_pct": _BASE_TRAILING_YIELD_PCT,
        },
        "scenarios": scenarios,
        # Added by nightly agent 2026-06-18: probability-weighted expectation
        # using the re-ranked weights (deal-signed band now carries most mass).
        "weighted_outlook": probability_weighted_outlook(),
        "summary_text": "\n".join(lines),
        "advisory_note": (
            "PTTEP is a low-cost producer (breakeven ~$45 Brent), so the elevated Brent regime "
            "(~$96.78 as of Jul-24, off the ~$101 peak) remains a large earnings/dividend TAILWIND "
            "— record ~560kboe/d Q2 volume plus higher realised prices reinforce the bullish Q2 "
            "setup (results now expected ~Aug-2/3, analyst meeting Aug-3; the seeded Aug-4 date is "
            "within a day — verify on the SET/PTTEP IR calendar). But as of Jul-27 the de-escalation "
            "FIRMED: the US and Iran paused attacks for a second straight day and Iran-Oman Hormuz "
            "talks are progressing. That sharpens the two-sided risk a medium-term holder must size "
            "for: (1) the premium is now increasingly a FEAR-premium that can unwind fast if the "
            "pause holds and Hormuz throughput normalises (the deal_partial path back toward the "
            "mid-$80s) — so the upside is NOT durable; and (2) PTTEP's Middle East footprint "
            "(notably Oman/UAE) adds real operational/transit risk only if the pause breaks and "
            "Hormuz closes outright. Net: hold the core, do NOT add into a premium that is now "
            "actively eroding, and treat a de-escalation pullback that keeps yield >4.5% as the "
            "preferred add zone. Note the mirror-image relief for BAFS (jet fuel) as oil eases off "
            "the peak. Informational, not a trade recommendation."
        ),
    }

    try:
        _REPORT_DIR.mkdir(parents=True, exist_ok=True)
        out = _REPORT_DIR / f"{datetime.utcnow().date().isoformat()}.json"
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Oil scenario report saved to %s", out)
    except OSError as exc:
        logger.warning("Could not save oil scenario report: %s", exc)

    return report


if __name__ == "__main__":
    import pprint

    pprint.pprint(run_oil_scenario_report())
