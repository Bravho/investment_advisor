"""Thai mutual-fund watch list (2026-10-31, Tho: separate tax-deductible and non-deductible Thai funds).

Separate from investment_watchlist on purpose: that table feeds yfinance prices, alerts and the predictions
generator, which do not apply to mutual funds. Data: Finnomena public fund API (free, no key; it republishes
SEC/AIMC fund data). SEC Thailand's open API (api.sec.or.th) needs a subscription key -> not configured -> not used.
Never invents NAVs/fees: missing -> None ('unknown'); NAV older than 7 days -> stale.
Advisory only - no orders.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger("portfolio_engine.fund_watchlist")
ICT = ZoneInfo("Asia/Bangkok")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
BASE = "https://www.finnomena.com/fn3/api/fund/v2/public/funds"
PAGE = "https://www.finnomena.com/fund/"
MAX_NAV_AGE_DAYS = 7

TAX_RULES_TH = {
    "ThaiESG": "ลดหย่อนได้ 30% ของเงินได้ สูงสุด 300,000 บาท/ปี · ต้องถือครบ 5 ปีนับจากวันซื้อ (ตรวจเงื่อนไขล่าสุดกับกรมสรรพากร/บลจ. ก่อนซื้อ)",
    "ThaiESGX": "ชนิดหน่วย ThaiESGX มีเงื่อนไขแยก (เงินใหม่/สับเปลี่ยนจาก LTF ช่วงปีภาษี 2568) — ยังไม่ยืนยันว่าปี 2569 ซื้อเพื่อลดหย่อนได้หรือไม่: unknown",
    "RMF": "ลดหย่อนได้ 30% ของเงินได้ สูงสุด 500,000 บาท (รวมกลุ่มเกษียณ PVD/กบข./ประกันบำนาญ/RMF) · ถือ ≥ 5 ปี และจนอายุ 55 ปี · ห้ามเว้นการซื้อเกิน 1 ปีติดต่อกัน",
    "SSF": "SSF ให้สิทธิลดหย่อนเฉพาะการซื้อปี 2563–2567 — ไม่ได้ใส่กองทุน SSF ในรายการ (ตรวจสอบอีกครั้งหากมีการขยายสิทธิ)",
}

# group: tax | general | usbond | usbond_uh ; status: holding | watching
REGISTRY: list[dict[str, Any]] = [
    # --- Tho's holdings
    dict(code="K-TNZ-ThaiESG", group="tax", tax_type="ThaiESG", status="holding", reason_th="ถืออยู่ — ThaiESG หุ้นไทยขนาดใหญ่ (KAsset)"),
    dict(code="ES-SETESG-ThaiESG-A", group="tax", tax_type="ThaiESG", status="holding", reason_th="ถืออยู่ — ThaiESG ดัชนีหุ้นไทยยั่งยืน (Eastspring)"),
    dict(code="TDSThaiESG-A", group="tax", tax_type="ThaiESG", status="holding", reason_th="ถืออยู่ — ThaiESG หุ้นไทยยั่งยืน (TISCO)"),
    dict(code="SCBGOLDE", group="general", tax_type=None, status="holding", reason_th="ถืออยู่ — ทองคำ ไม่ป้องกันค่าเงิน (ราคาขึ้นลงตามทองและค่าเงินบาท)"),
    # --- ThaiESG candidates
    dict(code="SCBTP(ThaiESGE)", group="tax", tax_type="ThaiESG", status="watching", reason_th="ThaiESG ของ SCBAM ชนิดซื้อออนไลน์ — เทียบค่าธรรมเนียมกับกองที่ถืออยู่"),
    dict(code="KTESG50-ThaiESG", group="tax", tax_type="ThaiESG", status="watching", reason_th="ThaiESG แบบดัชนี (Krungthai) — แนวคิดต้นทุนต่ำ ตามตลาด"),
    dict(code="KKP EQ THAI ESG", group="tax", tax_type="ThaiESG", status="watching", reason_th="ThaiESG หุ้นไทยเชิงรุก (KKP) — จากการเปรียบเทียบครั้งก่อน"),
    dict(code="K-ESGBF-ThaiESG", group="tax", tax_type="ThaiESG", status="watching", reason_th="ThaiESG ตราสารหนี้/ผสม (KAsset) — ทางเลือกความเสี่ยงต่ำกว่าหุ้น"),
    dict(code="K-70ThaiESGX-N", group="tax", tax_type="ThaiESGX", status="watching", reason_th="ตัวอย่าง ThaiESGX (ผสมหุ้น ~70%) — ต้องยืนยันเงื่อนไขภาษีปี 2569 ก่อน"),
    # --- RMF candidates
    dict(code="SCBRMS&P500", group="tax", tax_type="RMF", status="watching", reason_th="RMF หุ้นสหรัฐฯ S&P 500 (SCBAM) — กระจายนอกตลาดไทยพร้อมลดหย่อน"),
    dict(code="K-USXNDQRMF", group="tax", tax_type="RMF", status="watching", reason_th="RMF หุ้นเทค Nasdaq-100 (KAsset) — ความผันผวนสูง"),
    dict(code="ES-SET50RMF", group="tax", tax_type="RMF", status="watching", reason_th="RMF ดัชนี SET50 (Eastspring) — หุ้นไทยต้นทุนต่ำ"),
    dict(code="SCBGOLDHRMF", group="tax", tax_type="RMF", status="watching", reason_th="RMF ทองคำ ป้องกันค่าเงิน (SCBAM)"),
    dict(code="KFLTGOVRMF", group="tax", tax_type="RMF", status="watching", reason_th="RMF พันธบัตรรัฐบาลไทยระยะยาว (Krungsri) — ส่วนป้องกันความเสี่ยง"),
    dict(code="K-WORLDXRMF", group="tax", tax_type="RMF", status="watching", reason_th="RMF หุ้นทั่วโลก (KAsset) — กระจายหลายประเทศ"),
    # --- general (no tax benefit)
    dict(code="SCBS&P500E", group="general", tax_type=None, status="watching", reason_th="หุ้นสหรัฐฯ S&P 500 ป้องกันค่าเงิน — ลดความเสี่ยงค่าเงินบาท"),
    dict(code="KF-SP500MFX", group="general", tax_type=None, status="watching", reason_th="หุ้นสหรัฐฯ S&P 500 ไม่ป้องกันค่าเงิน — เทียบกับแบบป้องกัน"),
    dict(code="SCBWORLD(E)", group="general", tax_type=None, status="watching", reason_th="หุ้นทั่วโลก ป้องกันค่าเงิน — กระจายความเสี่ยงทั่วโลก"),
    dict(code="SCBGOLDHE", group="general", tax_type=None, status="watching", reason_th="ทองคำ ป้องกันค่าเงิน — เทียบกับ SCBGOLDE ที่ถืออยู่ (ไม่ป้องกัน)"),
    dict(code="SCBVIET(E)", group="general", tax_type=None, status="watching", reason_th="หุ้นเวียดนาม — ตลาดเกิดใหม่ที่เฝ้าดูอยู่"),
    dict(code="SCBCHAE", group="general", tax_type=None, status="watching", reason_th="หุ้นจีน — ติดตามโอกาสฟื้นตัว (ความเสี่ยงสูง)"),
    dict(code="K-CASH-A", group="general", tax_type=None, status="watching", reason_th="กองทุนตลาดเงิน — พักเงินสดระหว่างรอจังหวะ"),
    # --- US bonds, FX-hedged (added 2026-11-01, t35u). Hedge % = factsheet "FX Hedging" figure; policy is dynamic (manager's discretion)
    dict(code="TUSTREASURY", group="usbond", tax_type=None, status="watching", reason_th="พันธบัตรรัฐบาลสหรัฐฯ ล้วน (feeder iShares GOVT) · ป้องกันค่าเงิน 91.24% (factsheet 30 ก.ย. 69) · อายุเฉลี่ยตราสาร ~5 ปี 4 เดือน — ได้ประโยชน์ถ้าดอกเบี้ยลง/ตลาดตื่นตระหนก แต่ขาดทุนถ้า Fed ขึ้นดอกเบี้ย"),
    dict(code="DAOL-USTBILL", group="usbond", tax_type=None, status="watching", reason_th="ตั๋วเงินคลังสหรัฐฯ อายุ ≤ 1 ปี (ถือตรง) · ป้องกันค่าเงิน 62.82% (factsheet 19 ต.ค. 69) · อายุเฉลี่ย 49 วัน — แทบไม่มีความเสี่ยงดอกเบี้ย แต่ส่วนที่ไม่ป้องกัน (~37%) ขึ้นลงตามค่าเงินบาท"),
    dict(code="TUSBOND-A", group="usbond", tax_type=None, status="watching", reason_th="ตราสารหนี้สหรัฐฯ รวม (JPM US Aggregate: พันธบัตรรัฐ ~23%, MBS หน่วยงานรัฐ ~32%, หุ้นกู้ ~32%) · ป้องกันค่าเงิน 95.17% (30 ก.ย. 69) · อายุเฉลี่ย ~6 ปี"),
    dict(code="MUBOND-A", group="usbond", tax_type=None, status="watching", reason_th="ตราสารหนี้สหรัฐฯ รวม (กองหลักเดียวกับ TUSBOND แต่ค่าธรรมเนียมสูงกว่า) · ป้องกันค่าเงิน 98% (30 ก.ย. 69)"),
    # --- US bonds, UNHEDGED (added 2026-11-01, t36u). TLUSGOVRMF moved here from 'usbond' (unhedged by policy).
    dict(code="TLUSGOV", group="usbond_uh", tax_type=None, status="watching", ter_factsheet=(0.2568, "SEC factsheet M0853_2569, data 30 Sep 2026 (actual total expense, excl. other expenses)"), reason_th="พันธบัตรสหรัฐฯ 0–3 เดือน (SGOV) ไม่ป้องกันค่าเงินตามนโยบาย · ค่าใช้จ่ายรวมเก็บจริง 0.2568% ตาม factsheet 30 ก.ย. 69 (Finnomena แสดง 2.26% — น่าจะคลาดเคลื่อน) · ไม่มีค่าธรรมเนียมซื้อ/ขาย · ได้ดอกเบี้ยสหรัฐฯ เต็ม แต่ขึ้นลงตามค่าเงินบาท"),
    dict(code="TLUSGOVRMF", group="usbond_uh", tax_type="RMF", status="watching", reason_th="RMF พันธบัตรสหรัฐฯ 0–3 เดือน (SGOV) ไม่ป้องกันค่าเงิน · ค่าใช้จ่ายรวม 0.4494% (factsheet 30 ก.ย. 69) · ลดหย่อนภาษีได้ (เงื่อนไข RMF) · RMF พันธบัตรสหรัฐฯ กองเดียวที่พบ"),
    dict(code="TUSFIX", group="usbond_uh", tax_type=None, status="watching", reason_th="ตั๋วเงินคลังสหรัฐฯ 1–3 เดือน (BIL) · นโยบายป้องกันค่าเงินตามดุลยพินิจ แต่ตอนนี้ป้องกัน 0% (factsheet 30 ก.ย. 69) — ผู้จัดการอาจกลับมาป้องกันได้ · มีประวัติตั้งแต่ปี 2559"),
    dict(code="MUBONDUH-A", group="usbond_uh", tax_type=None, status="watching", reason_th="ตราสารหนี้สหรัฐฯ รวม (JPM US Aggregate; พันธบัตรรัฐ ~23%) ไม่ป้องกันค่าเงิน (0% ตาม factsheet 30 ก.ย. 69) · มีความเสี่ยงดอกเบี้ย + เครดิต · ค่าธรรมเนียมสูง (TER 0.94% + ขาย 1.07%)"),
]
BY_CODE = {r["code"]: r for r in REGISTRY}

DDL = """
CREATE TABLE IF NOT EXISTS fund_watchlist (
    code            VARCHAR(40) PRIMARY KEY,
    fund_id         VARCHAR(20),
    group_key       VARCHAR(10) NOT NULL,
    tax_type        VARCHAR(10),
    status          VARCHAR(10) NOT NULL DEFAULT 'watching',
    reason_th       TEXT,
    name_th         TEXT, name_en TEXT, amc VARCHAR(40),
    aimc_category   TEXT,
    risk_level      INTEGER,
    fx_hedge        TEXT,
    dividend_policy TEXT,
    inception_date  DATE,
    nav             DOUBLE PRECISION,
    nav_date        DATE,
    nav_stale       BOOLEAN,
    fees            JSONB,
    returns         JSONB,
    peer            JSONB,
    score           DOUBLE PRECISION,
    score_basis     JSONB,
    factsheet_url   TEXT,
    source          TEXT,
    source_url      TEXT,
    retrieved_at    TIMESTAMPTZ,
    error           TEXT,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS fund_nav_daily (
    code         VARCHAR(40) NOT NULL,
    nav_date     DATE NOT NULL,
    nav          DOUBLE PRECISION NOT NULL,
    aum          DOUBLE PRECISION,
    source       TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (code, nav_date)
);
"""


async def ensure_tables(pool: Any) -> None:
    async with pool.acquire() as conn:
        await conn.execute(DDL)
        for r in REGISTRY:  # seed / keep registry metadata in sync (no deletes)
            await conn.execute("""INSERT INTO fund_watchlist (code, group_key, tax_type, status, reason_th) VALUES ($1,$2,$3,$4,$5)
                                  ON CONFLICT (code) DO UPDATE SET group_key=EXCLUDED.group_key, tax_type=EXCLUDED.tax_type,
                                  status=EXCLUDED.status, reason_th=EXCLUDED.reason_th""",
                               r["code"], r["group"], r["tax_type"], r["status"], r["reason_th"])


def _get(url: str, timeout: float = 25) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    if not d.get("status"):
        raise RuntimeError(d.get("error_message") or "finnomena status false")
    return d["data"]


def _num(v: Any) -> Optional[float]:
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def _d(s: Any) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).date() if s else None
    except ValueError:
        return None


def _fees(detail: dict[str, Any], table: list[dict[str, Any]]) -> dict[str, Any]:
    """Fee table (rate = prospectus ceiling, actual_value = charged). detail.real_management_fee behaves like the ceiling
    (e.g. 3.21 vs 0.54 charged), so it is kept only as 'ceiling_detail'."""
    def row(word: str) -> Optional[dict[str, Any]]:
        return next((f for f in table if word in (f.get("description") or "")), None)
    mg, ter = row("การจัดการ"), row("ค่าใช้จ่ายรวมทั้งหมด")
    fe, be = row("Front-end"), row("Back-end")
    out = {"mgmt_max": _num(mg and mg.get("rate")), "mgmt_actual": _num(mg and mg.get("actual_value")),
           "mgmt_ceiling_detail": _num(detail.get("real_management_fee")), "ter_max": _num(ter and ter.get("rate")),
           "ter_actual": _num(ter and ter.get("actual_value")), "front_actual": _num(fe and fe.get("actual_value")),
           "back_actual": _num(be and be.get("actual_value")), "unit": "% ต่อปีของ NAV (front/back = % ต่อรายการ)"}
    notes = []
    if out["mgmt_actual"] == 0:
        notes.append("ค่าจัดการเก็บจริง 0% ตามตารางค่าธรรมเนียม — ยืนยันกับ factsheet")
    if out["ter_actual"] is None:
        notes.append("ค่าใช้จ่ายรวม (TER) ไม่มีในข้อมูล — unknown")
    out["note_th"] = " · ".join(notes) or None
    # score only on total expense (TER); a management fee alone understates cost, so no score without TER
    out["cost_for_score"] = out["ter_actual"]
    out["cost_for_score_basis"] = "TER (actual)" if out["ter_actual"] is not None else None
    return out


def _score(fees: dict[str, Any], perf: dict[str, Any]) -> tuple[Optional[float], dict[str, Any]]:
    cost = fees.get("cost_for_score")
    ra = pa = hz = None
    for h in ("3y", "1y"):
        r, sd = _num(perf.get(f"total_return_{h}")), _num(perf.get(f"std_{h}"))
        ar, asd = _num(perf.get(f"total_return_avg_{h}")), _num(perf.get(f"std_avg_{h}"))
        if None not in (r, sd, ar, asd) and sd > 0 and asd > 0:
            ra, pa, hz = r / sd, ar / asd, h
            break
    basis = {"definition_th": "คะแนน 0–100 = ต้นทุน 40 (ค่าใช้จ่าย 0%/ปี = 40, ≥ 2% = 0) + ผลตอบแทนต่อความผันผวน เทียบค่าเฉลี่ยกองทุนกลุ่มเดียวกัน (AIMC) 60 (เท่าค่าเฉลี่ย = 30, ดีกว่า 1 หน่วย = 60)",
             "cost": cost, "cost_basis": fees.get("cost_for_score_basis"), "ret_per_vol": round(ra, 3) if ra is not None else None,
             "peer_ret_per_vol": round(pa, 3) if pa is not None else None, "horizon": hz}
    if cost is None or ra is None:
        basis["missing_th"] = "ข้อมูลไม่พอ (" + ", ".join(x for x, v in (("ค่าใช้จ่ายรวม TER", cost), ("ผลตอบแทน/ความผันผวน ≥ 1 ปี", ra)) if v is None) + ") — ไม่ให้คะแนน"
        return None, basis
    c = 40 * max(0.0, 1 - min(cost, 2.0) / 2.0)
    r = 60 * min(1.0, max(0.0, 0.5 + 0.5 * (ra - pa)))
    basis.update(cost_pts=round(c, 1), riskadj_pts=round(r, 1))
    return round(c + r, 1), basis


def _fetch_one(code: str, fund_id: str) -> dict[str, Any]:
    det = _get(f"{BASE}/{fund_id}")
    time.sleep(0.25)
    perf = _get(f"{BASE}/{fund_id}/performance")
    time.sleep(0.25)
    fee = _get(f"{BASE}/{fund_id}/fee").get("fees") or []
    time.sleep(0.25)
    navs = _get(f"{BASE}/{fund_id}/nav/q?range=1Y").get("navs") or []
    time.sleep(0.25)
    return {"detail": det, "perf": perf, "fee": fee, "navs": navs}


def _ytd(navs: list[dict[str, Any]], today: date) -> Optional[float]:
    pts = [(_d(n["date"]), _num(n["value"])) for n in navs if _num(n.get("value"))]
    prev = [p for p in pts if p[0] and p[0] < date(today.year, 1, 1)]
    if not prev or not pts:
        return None
    return round((pts[-1][1] / prev[-1][1] - 1) * 100, 2)


async def refresh(pool: Any) -> dict[str, Any]:
    await ensure_tables(pool)
    today = datetime.now(ICT).date()
    lst = await asyncio.to_thread(_get, f"{BASE}?page=1&size=10000")
    ids = {x["short_code"]: x["fund_id"] for x in lst}
    ok, failed = [], {}
    for r in REGISTRY:
        code = r["code"]
        fid = ids.get(code)
        if not fid:
            failed[code] = "fund code not found in Finnomena list"
            async with pool.acquire() as conn:
                await conn.execute("UPDATE fund_watchlist SET error=$2, retrieved_at=now() WHERE code=$1", code, failed[code])
            continue
        try:
            raw = await asyncio.to_thread(_fetch_one, code, fid)
        except Exception as exc:  # noqa: BLE001
            failed[code] = str(exc)[:200]
            async with pool.acquire() as conn:
                await conn.execute("UPDATE fund_watchlist SET error=$2, retrieved_at=now() WHERE code=$1", code, failed[code])
            continue
        det, perf, navs = raw["detail"], raw["perf"], raw["navs"]
        nav_pts = [(_d(n["date"]), _num(n["value"]), _num(n.get("amount"))) for n in navs if _num(n.get("value")) is not None]
        nav_date, nav = (nav_pts[-1][0], nav_pts[-1][1]) if nav_pts else (None, None)
        fees = _fees(det, raw["fee"])
        if r.get("ter_factsheet"):  # 2026-11-01: Finnomena TER clearly off vs the SEC factsheet -> use the factsheet figure, keep both
            tv, tsrc = r["ter_factsheet"]
            fees["ter_actual_finnomena"] = fees.get("ter_actual")
            fees["ter_actual"] = fees["cost_for_score"] = tv
            fees["cost_for_score_basis"] = f"TER (actual) from {tsrc}"
            fees["note_th"] = " · ".join(x for x in (fees.get("note_th"), f"TER ใช้ตาม factsheet {tv}% (Finnomena แสดง {fees['ter_actual_finnomena']}%)") if x)
        rets = {k: _num(perf.get(f"total_return_{k}")) for k in ("1w", "1m", "3m", "6m", "1y", "3y", "5y")}
        rets["ytd"] = _ytd(navs, today)
        rets["as_of"] = str(_d(perf.get("day_end_date")) or "") or None
        rets["note_th"] = "% ผลตอบแทนรวม; 3 ปี/5 ปี = ต่อปี (annualised) · YTD คำนวณจาก NAV"
        peer = {"category": det.get("aimc_category_name_th"), "avg_return_1y": _num(perf.get("total_return_avg_1y")),
                "avg_return_3y": _num(perf.get("total_return_avg_3y")), "sharpe_1y": _num(perf.get("sharpe_ratio_1y")),
                "sharpe_3y": _num(perf.get("sharpe_ratio_3y")), "avg_sharpe_1y": _num(perf.get("sharpe_ratio_avg_1y")),
                "avg_sharpe_3y": _num(perf.get("sharpe_ratio_avg_3y")), "std_1y": _num(perf.get("std_1y")),
                "max_drawdown_1y": _num(perf.get("max_drawdown_1y")), "avg_max_drawdown_1y": _num(perf.get("max_drawdown_avg_1y"))}
        score, basis = _score(fees, perf)
        stale = nav_date is None or (today - nav_date).days > MAX_NAV_AGE_DAYS
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE fund_watchlist SET fund_id=$2, name_th=$3, name_en=$4, amc=$5, aimc_category=$6, risk_level=$7, fx_hedge=$8,
                       dividend_policy=$9, inception_date=$10, nav=$11, nav_date=$12, nav_stale=$13, fees=$14::jsonb, returns=$15::jsonb,
                       peer=$16::jsonb, score=$17, score_basis=$18::jsonb, factsheet_url=$19, source=$20, source_url=$21, retrieved_at=now(), error=NULL
                   WHERE code=$1""",
                code, fid, det.get("name_th"), det.get("name_en"), det.get("amc_name_en"), det.get("aimc_category_name_th"),
                det.get("risk_level"), det.get("exchange_rate_risk_spectrum") or None, det.get("dividend_policy"), _d(det.get("inception_date")),
                nav, nav_date, stale, json.dumps(fees, ensure_ascii=False), json.dumps(rets), json.dumps(peer, ensure_ascii=False),
                score, json.dumps(basis, ensure_ascii=False), det.get("fund_fact_sheet"),
                "Finnomena public fund API (republishes SEC/AIMC data)", PAGE + code)
            await conn.executemany(
                """INSERT INTO fund_nav_daily (code, nav_date, nav, aum, source) VALUES ($1,$2,$3,$4,$5) ON CONFLICT (code, nav_date) DO NOTHING""",
                [(code, d, v, a, "finnomena") for d, v, a in nav_pts if d])
        ok.append(code)
    _CACHE.pop("list", None)
    return {"ok": len(ok), "failed": failed, "funds": len(REGISTRY)}


_CACHE: dict[str, Any] = {}


async def get_list(pool: Any) -> dict[str, Any]:
    await ensure_tables(pool)
    today = datetime.now(ICT).date()
    async with pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch("SELECT * FROM fund_watchlist ORDER BY group_key DESC, status, score DESC NULLS LAST, code")]
        spark = {}
        for r in await conn.fetch("""SELECT code, array_agg(nav ORDER BY nav_date) v FROM fund_nav_daily
                                     WHERE nav_date > current_date - 95 GROUP BY code"""):
            spark[r["code"]] = [round(float(x), 4) for x in r["v"]]
    items = []
    for r in rows:
        for k in ("fees", "returns", "peer", "score_basis"):
            if isinstance(r.get(k), str):
                r[k] = json.loads(r[k])
        if r.get("nav_date"):
            r["nav_stale"] = (today - r["nav_date"]).days > MAX_NAV_AGE_DAYS
        r["tax_rule_th"] = TAX_RULES_TH.get(r.get("tax_type") or "")
        r["spark"] = spark.get(r["code"], [])
        r["is_foreign"] = bool(r.get("fx_hedge"))
        items.append(r)
    counts = {"tax": sum(1 for i in items if i["group_key"] == "tax"), "general": sum(1 for i in items if i["group_key"] == "general"),
              "usbond": sum(1 for i in items if i["group_key"] == "usbond"),
              "usbond_uh": sum(1 for i in items if i["group_key"] == "usbond_uh"),
              "by_tax_type": {t: sum(1 for i in items if i.get("tax_type") == t and i["group_key"] == "tax") for t in ("ThaiESG", "ThaiESGX", "RMF", "SSF")},
              "holding": sum(1 for i in items if i["status"] == "holding")}
    return {"items": items, "counts": counts, "tax_rules_th": TAX_RULES_TH, "stale_after_days": MAX_NAV_AGE_DAYS,
            "source": "Finnomena public fund API (SEC/AIMC data); SEC open API not used (needs subscription key)",
            "score_definition_th": "คะแนน 0–100 = ต้นทุน (TER) 40 + ผลตอบแทนต่อความผันผวนเทียบค่าเฉลี่ยกลุ่ม AIMC 60 (คำนวณเอง ไม่ใช่คำแนะนำซื้อขาย)",
            "note_th": "ข้อมูลภาษีเป็นสรุปเงื่อนไขทั่วไป ตรวจสอบกับกรมสรรพากร/บลจ. ก่อนซื้อ · ระบบไม่ส่งคำสั่งซื้อขาย"}


async def advisor_context(pool: Any) -> str:
    d = await get_list(pool)
    lines = ["=== THAI FUND WATCH LIST (Finnomena/SEC data; advisory only, Tho places orders himself) ==="]
    for grp, title in (("tax", "Tax-deductible (ThaiESG/ThaiESGX/RMF)"), ("general", "General funds (no tax benefit)"),
                       ("usbond", "US bond funds, FX-hedged (watch only; hedge % from factsheets; hedging THB costs ~ the US-TH short-rate gap)"),
                       ("usbond_uh", "US bond funds, UNHEDGED (watch only; full US yield but every 1% stronger baht = -1% on these; adds to direct USD exposure on top of SCBGOLDE)")):
        lines.append(f"  [{title}]")
        for i in d["items"]:
            if i["group_key"] != grp:
                continue
            rt = i.get("returns") or {}
            f = i.get("fees") or {}
            nav = f"NAV {i['nav']:.4f} ({i['nav_date']}{', STALE' if i.get('nav_stale') else ''})" if i.get("nav") else "NAV unknown"
            r = ", ".join(f"{k} {rt[k]:+.1f}%" for k in ("1m", "ytd", "1y", "3y") if rt.get(k) is not None)
            cost = f"TER {f['ter_actual']}%" if f.get("ter_actual") is not None else (f"mgmt fee {f.get('mgmt_actual')}% (TER unknown)" if f.get("mgmt_actual") is not None else "fees unknown")
            lines.append(f"  - {i['code']} [{i.get('tax_type') or 'general'}{', HOLDING' if i['status'] == 'holding' else ''}] {i.get('amc') or ''} {i.get('aimc_category') or ''}: "
                         f"{nav}; {r or 'returns unknown'}; {cost}; risk {i.get('risk_level') or 'unknown'}; FX {i.get('fx_hedge') or 'n/a (Thai assets)'}; "
                         f"watch score {i['score'] if i.get('score') is not None else 'n/a'} (cost+risk-adjusted vs peers); "
                         f"why: {i.get('reason_th') or ''}")
    lines.append("  Tax rules: " + " | ".join(f"{k}: {v}" for k, v in TAX_RULES_TH.items()))
    lines.append("  Quote these figures with their dates; fees from Finnomena may differ from the factsheet; never invent NAVs.")
    return "\n".join(lines)
