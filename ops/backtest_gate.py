"""Candidate-vs-baseline acceptance gate for forecast backtests."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def gate(
    baseline: Mapping[str, Mapping[str, Any]],
    candidate: Mapping[str, Mapping[str, Any]],
    max_hit_drop: float = 0.01,
) -> Dict[str, Any]:
    """Apply the owner's mean-skill/mean-hit acceptance rule.

    Only horizons present in both inputs with numeric ``skill`` and ``hit``
    values are compared.  With no comparable horizons the verdict fails.
    """
    common = []
    for horizon in sorted(set(baseline) & set(candidate)):
        bs = _number(baseline[horizon].get("skill"))
        bh = _number(baseline[horizon].get("hit"))
        cs = _number(candidate[horizon].get("skill"))
        ch = _number(candidate[horizon].get("hit"))
        if None not in (bs, bh, cs, ch):
            common.append((horizon, bs, bh, cs, ch))
    if not common:
        return {
            "pass": False,
            "mean_skill_base": None,
            "mean_skill_cand": None,
            "mean_hit_base": None,
            "mean_hit_cand": None,
            "reason": "no common horizons with numeric skill and hit",
        }
    count = float(len(common))
    mean_skill_base = sum(row[1] for row in common) / count
    mean_hit_base = sum(row[2] for row in common) / count
    mean_skill_cand = sum(row[3] for row in common) / count
    mean_hit_cand = sum(row[4] for row in common) / count
    skill_ok = mean_skill_cand > mean_skill_base
    hit_floor = mean_hit_base - float(max_hit_drop)
    hit_ok = mean_hit_cand >= hit_floor
    passed = skill_ok and hit_ok
    if passed:
        reason = "candidate mean skill improved and mean hit stayed within the allowed drop"
    elif not skill_ok and not hit_ok:
        reason = "candidate mean skill did not improve and mean hit fell below the allowed floor"
    elif not skill_ok:
        reason = "candidate mean skill did not improve"
    else:
        reason = "candidate mean hit fell below the allowed floor"
    return {
        "pass": passed,
        "mean_skill_base": mean_skill_base,
        "mean_skill_cand": mean_skill_cand,
        "mean_hit_base": mean_hit_base,
        "mean_hit_cand": mean_hit_cand,
        "reason": reason,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--max-hit-drop", type=float, default=0.01)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    verdict = gate(baseline, candidate, args.max_hit_drop)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
