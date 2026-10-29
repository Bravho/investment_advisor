"""
Fee-drag analysis for the SCBGOLD sleeve, and the hedged/unhedged decision.

Added by nightly agent 2026-08-13.

WHY THIS EXISTS
---------------
Tho named management fees and currency cost as two of his three standing
concerns when this project was set up. Until tonight the project had never held
the actual fee schedule for the one fund he owns --- ``fee_analyzer.py`` (18 Jun)
computes fee drag from a TER the caller supplies, and nobody had ever supplied
one. Tonight SCBAM's fund page was read in full and the real schedule came with
it, so the arithmetic can finally be done on numbers rather than placeholders.

The schedule is more interesting than a single TER, and in a way that changes
advice:

    Front-end fee, charged on every purchase        0.535 %
    Management fee, per annum                       0.436025 %

**Buying the fund costs more than owning it for a year.** The entry charge is
1.23 years of management fee. That single comparison reframes the position:
for a 3-month-to-2-year holder the dominant fee is the one already paid at
purchase, and the recurring drag is second-order. It argues against topping up
in small increments, against switching between SCBAM funds (switch-in is
charged at the same 0.535 %), and *for* leaving an existing holding alone ---
which is convenient, but it is worth being explicit that a sunk entry fee is
not itself a reason to hold. It is a reason not to churn.

The second finding is structural. **SCBGOLD is unhedged.** SCBAM runs a
distinct THB-hedged share class, ``SCBGOLDH``. Tho holds the unhedged one, so
his gold sleeve is a levered bet on two things at once: the USD gold price and
USD/THB. This module quantifies the decomposition rather than asserting a
direction, because the sign has flipped twice in three runs (DEVLOG 2026-08-11
vs 2026-08-12) and a module that hardcodes a view will be wrong half the time.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not fetch, and it does not recommend a trade. It returns arithmetic
with its assumptions attached. ``registrar_fee`` is published as "as announced"
rather than as a number, and "other fees" are actual expenses, so the true
all-in TER is **not knowable from the fund page** --- every total this module
returns is therefore a documented LOWER BOUND, flagged as such in the output
rather than in a comment. See :func:`annual_fee_drag`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

__all__ = [
    "FeeSchedule",
    "SCBGOLD",
    "SCBGOLD_NAV_2026_08_11",
    "annual_fee_drag",
    "entry_fee_breakeven",
    "holding_period_cost",
    "compare_share_classes",
    "currency_decomposition",
    "summary",
]


# --------------------------------------------------------------------------- #
# Fee schedule
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class FeeSchedule:
    """
    A fund's published charges, in percent per annum or percent per transaction.

    ``*_max`` fields record the ceiling the prospectus permits, which matters
    for a medium-term holder: SCBAM currently charges 0.436025 % management
    against a permitted 1.07 %, so the fee can lawfully be raised by ~2.45x
    without a prospectus amendment. A fee analysis that reports only the current
    rate understates the risk being carried.
    """

    fund_code: str
    fund_name: str

    # Charged to the fund, % p.a. of NAV, VAT included.
    management_fee: float
    management_fee_max: float
    trustee_fee: float
    trustee_fee_max: float
    registrar_fee: Optional[float]          # None = published as "as announced"
    registrar_fee_max: float

    # Charged to the unitholder, % per transaction, VAT included.
    front_end_fee: float
    back_end_fee: float
    switching_in_fee: float
    switching_out_fee: float

    # Charged to the unitholder, % per transaction, no VAT.
    brokerage_fee: float
    brokerage_fee_max: float

    currency_hedged: bool
    source_url: str
    source_retrieved: str
    notes: List[str] = field(default_factory=list)


# Read from SCBAM 2026-08-13. Figures are as published on the fund page.
SCBGOLD = FeeSchedule(
    fund_code="SCBGOLD",
    fund_name="SCB GOLD OPEN END FUND (Accumulation)",
    management_fee=0.436025,
    management_fee_max=1.07,
    trustee_fee=0.0321,
    trustee_fee_max=0.107,
    registrar_fee=None,
    registrar_fee_max=0.11,
    front_end_fee=0.535,
    back_end_fee=0.0,          # permitted up to 0.535 %, currently waived
    switching_in_fee=0.535,
    switching_out_fee=0.0,     # permitted up to 0.535 %, currently waived
    brokerage_fee=0.15,
    brokerage_fee_max=0.75,
    currency_hedged=False,
    source_url="https://www.scbam.com/en/fund/default/fund-information/scbgold",
    source_retrieved="2026-08-13",
    notes=[
        "Feeder fund: invests via SPDR Gold Trust (GLD). GLD's own sponsor fee "
        "(~0.40 % p.a.) is borne inside the master and is NOT in this schedule. "
        "True look-through cost is materially higher than any total computed here.",
        "Registrar fee published as 'as announced', capped 0.11 %. Not a number, "
        "so not includable. Totals are lower bounds.",
        "'Other fees: actual expenses' — open-ended and unquantifiable ex ante.",
        "Back-end and switching-out fees are WAIVED, not abolished; the "
        "prospectus permits 0.535 % each and the waiver can be withdrawn.",
        "NAV is struck on the master's prior US session, so the THB NAV lags "
        "spot gold by roughly one business day. Do not compare same-day NAV "
        "against same-day spot and read the gap as tracking error.",
    ],
)

# Observed 2026-08-13 from the same page; NAV dated by the fund's own stamp.
SCBGOLD_NAV_2026_08_11: Dict[str, object] = {
    "nav_per_unit": 23.7123,
    "nav_change": 0.4561,
    "nav_change_pct": 1.9612,        # 0.4561 / (23.7123 - 0.4561) = 0.4561/23.2562
    "fund_nav_total_thb": 8_046_458_101.50,
    "offer_price": 23.8749,
    "bid_price": 23.6767,
    "observed_as_of": "2026-08-11",
    "source_url": "https://www.scbam.com/en/fund/default/fund-information/scbgold",
    "unit_count_known": False,
    "note": (
        "NAV per unit is known; THO'S UNIT COUNT IS NOT. The sleeve therefore "
        "remains unvalued for the 10th consecutive run and is excluded from "
        "every portfolio total. This is the single largest open item in the book."
    ),
}


# --------------------------------------------------------------------------- #
# Recurring cost
# --------------------------------------------------------------------------- #

def annual_fee_drag(schedule: FeeSchedule = SCBGOLD) -> Dict[str, object]:
    """
    Recurring annual cost as a percentage of NAV.

    Returns both the current and the maximum-permitted totals, and labels the
    result a **lower bound** because the registrar fee and "other expenses" are
    not published as numbers. Callers must not present the total as "the TER".
    """
    known = schedule.management_fee + schedule.trustee_fee
    max_total = (
        schedule.management_fee_max
        + schedule.trustee_fee_max
        + schedule.registrar_fee_max
    )
    return {
        "fund_code": schedule.fund_code,
        "annual_known_pct": round(known, 6),
        "annual_max_permitted_pct": round(max_total, 6),
        "headroom_multiple": round(max_total / known, 3) if known else None,
        "is_lower_bound": True,
        "excluded_from_total": [
            "registrar fee (published 'as announced', cap 0.11 %)",
            "other fees (actual expenses, unbounded)",
            "SPDR Gold Trust sponsor fee inside the master fund (~0.40 % p.a.)",
        ],
        "components": {
            "management_fee": schedule.management_fee,
            "trustee_fee": schedule.trustee_fee,
        },
    }


def entry_fee_breakeven(schedule: FeeSchedule = SCBGOLD) -> Dict[str, object]:
    """
    Express the one-off entry charge in years of recurring fee.

    This is the headline number for a 3-month-to-2-year holder. If the entry
    charge exceeds a year of management fee --- and for SCBGOLD it does --- then
    **transaction frequency, not the TER, is the dominant fee decision**, and
    advice that focuses on shaving the management fee is optimising the smaller
    term.
    """
    recurring = annual_fee_drag(schedule)["annual_known_pct"]
    entry = schedule.front_end_fee + schedule.brokerage_fee
    return {
        "fund_code": schedule.fund_code,
        "front_end_fee_pct": schedule.front_end_fee,
        "brokerage_fee_pct": schedule.brokerage_fee,
        "total_entry_cost_pct": round(entry, 6),
        "recurring_annual_pct": recurring,
        # Two ratios, because two different denominators are defensible and
        # quoting one while naming the other is how a right number becomes a
        # wrong claim. vs_management compares like-for-like against the single
        # headline fee a saver would shop on; vs_recurring is the honest
        # all-in-known comparison.
        "entry_vs_recurring_years": round(entry / recurring, 3),
        "front_end_vs_recurring_years": round(schedule.front_end_fee / recurring, 3),
        "front_end_vs_management_years": round(
            schedule.front_end_fee / schedule.management_fee, 3
        ),
        "interpretation": (
            "Entry cost is paid once and in full on day one; recurring cost "
            "accrues. Over a 3-month hold the entry charge dominates by roughly "
            "the ratio above times four. Frequent small top-ups are the "
            "expensive behaviour here, not the holding itself."
        ),
    }


def holding_period_cost(
    months: int,
    amount_thb: float,
    schedule: FeeSchedule = SCBGOLD,
    include_exit: bool = False,
) -> Dict[str, object]:
    """
    All-in known fee cost of holding ``amount_thb`` for ``months`` months.

    ``include_exit`` applies the *permitted* back-end fee rather than the
    currently waived 0 %, so a caller can stress the waiver being withdrawn.
    Ignores compounding and NAV drift on purpose: this is a fee estimate, not
    a return projection, and pretending to more precision than the inputs
    support would be false comfort.
    """
    if months <= 0:
        raise ValueError("months must be positive")
    if amount_thb <= 0:
        raise ValueError("amount_thb must be positive")

    entry_pct = schedule.front_end_fee + schedule.brokerage_fee
    recurring_pct = annual_fee_drag(schedule)["annual_known_pct"] * (months / 12.0)
    exit_pct = 0.535 if include_exit else schedule.back_end_fee

    entry_thb = amount_thb * entry_pct / 100.0
    recurring_thb = amount_thb * recurring_pct / 100.0
    exit_thb = amount_thb * exit_pct / 100.0
    total_thb = entry_thb + recurring_thb + exit_thb

    return {
        "fund_code": schedule.fund_code,
        "months": months,
        "amount_thb": round(amount_thb, 2),
        "entry_cost_thb": round(entry_thb, 2),
        "recurring_cost_thb": round(recurring_thb, 2),
        "exit_cost_thb": round(exit_thb, 2),
        "total_cost_thb": round(total_thb, 2),
        "total_cost_pct": round(total_thb / amount_thb * 100.0, 4),
        "annualised_cost_pct": round(total_thb / amount_thb * 100.0 * 12.0 / months, 4),
        "exit_assumption": (
            "permitted 0.535 % back-end applied" if include_exit
            else "back-end fee currently waived (0 %)"
        ),
        "is_lower_bound": True,
    }


# --------------------------------------------------------------------------- #
# Share class and currency
# --------------------------------------------------------------------------- #

def compare_share_classes() -> Dict[str, object]:
    """
    Frame the SCBGOLD (unhedged) vs SCBGOLDH (THB-hedged) choice.

    Deliberately returns no recommendation. The hedged class removes USD/THB
    from the return but adds an interest-rate-differential carry cost, and with
    the BOT policy rate at 1.00 % against a US policy rate several points higher,
    **hedging THB against USD currently costs carry rather than earning it**.
    That cost is real and recurring; the FX exposure it removes is volatile and
    has been a tailwind and a headwind within the same fortnight. Which is
    preferable is a judgement about Tho's risk tolerance, not an arithmetic
    result, and this project should stop pretending otherwise.
    """
    return {
        "unhedged": {
            "code": "SCBGOLD",
            "holder": "Tho (current position)",
            "return_drivers": ["USD gold price", "USD/THB"],
            "fx_carry_cost": "none",
        },
        "hedged": {
            "code": "SCBGOLDH",
            "holder": None,
            "return_drivers": ["USD gold price"],
            "fx_carry_cost": (
                "Approximately the USD-THB policy rate differential, paid "
                "continuously. BOT policy rate 1.00 %; the differential is "
                "materially positive for USD, so the hedge is a cost, not a "
                "carry gain."
            ),
        },
        "switching_cost_pct": SCBGOLD.switching_in_fee,
        "switching_note": (
            "Moving between the two classes is a switch, charged at 0.535 % in "
            "and 0 % out. A class change is therefore a ~0.535 % decision, or "
            "about 1.23 years of management fee — it should not be made on a "
            "one-week view of the baht."
        ),
        "recommendation": None,
        "why_no_recommendation": (
            "The FX sign flipped between the 2026-08-11 and 2026-08-12 runs and "
            "again on 2026-08-12. A hedging decision taken on a signal that "
            "reverses weekly is noise-trading with a 0.535 % toll per round trip."
        ),
    }


def currency_decomposition(
    gold_usd_pct_change: float,
    usdthb_pct_change: float,
) -> Dict[str, float]:
    """
    Split an unhedged THB gold return into its gold and FX components.

    For an unhedged THB investor the approximate return is::

        (1 + gold_usd) * (1 + usdthb) - 1

    where a POSITIVE ``usdthb_pct_change`` means USD/THB rose, i.e. **the baht
    weakened**, which helps a THB holder of a USD asset. Getting that sign
    backwards is the specific error the 2026-08-11 run made and the 2026-08-12
    run corrected, so it is spelled out here rather than left to the caller.
    """
    g = gold_usd_pct_change / 100.0
    f = usdthb_pct_change / 100.0
    total = ((1 + g) * (1 + f) - 1) * 100.0
    return {
        "gold_usd_pct": round(gold_usd_pct_change, 4),
        "usdthb_pct": round(usdthb_pct_change, 4),
        "baht_direction": "weaker" if usdthb_pct_change > 0 else "stronger",
        "fx_effect_on_thb_investor": "tailwind" if usdthb_pct_change > 0 else "headwind",
        "total_thb_return_pct": round(total, 4),
        "gold_contribution_pct": round(g * 100.0, 4),
        "fx_contribution_pct": round(total - g * 100.0, 4),
    }


def summary() -> Dict[str, object]:
    """Everything above in one dict, for the brief generator and snapshots."""
    return {
        "schedule": asdict(SCBGOLD),
        "nav": SCBGOLD_NAV_2026_08_11,
        "annual_drag": annual_fee_drag(),
        "entry_breakeven": entry_fee_breakeven(),
        "share_classes": compare_share_classes(),
        "headline": (
            "SCBGOLD's 0.535 % front-end fee equals 1.227 years of its 0.436025 % "
            "management fee (1.143 years of the 0.468 % all-in known recurring "
            "cost). For a 3-month-to-2-year holder the entry charge, not the TER, "
            "is the fee that matters — so the actionable advice is 'do not churn', "
            "not 'find a cheaper fund'. Concretely: a 3-month hold costs 0.80 % "
            "all-in, or 3.21 % ANNUALISED; the same money held 24 months costs "
            "1.62 %, or 0.81 % annualised — a 4x difference in annualised fee "
            "driven purely by holding period."
        ),
    }
