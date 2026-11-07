import json, math
import numpy as np, pandas as pd
raw = json.load(open("stocks_raw.json"))
rows = []
def rsi(s, n=14):
    d = s.diff().dropna(); g = d.clip(lower=0).tail(n).mean(); l = -d.clip(upper=0).tail(n).mean()
    return 100.0 if l == 0 else float(100 - 100/(1+g/l))
def clip(x, a=0, b=100): return float(max(a, min(b, x)))
for t, r in raw.items():
    if "error" in r: continue
    c = pd.Series([v for _, v in r["closes"]], index=pd.to_datetime([d for d, _ in r["closes"]]))
    last = float(c.iloc[-1]); info = r["info"]
    divs = pd.Series([v for _, v in r["dividends"]], index=pd.to_datetime([d for d, _ in r["dividends"]]))
    end = c.index[-1]
    divs = divs[divs.index >= c.index[0]]
    med6 = float(divs.tail(6).median()) if len(divs) else 0.0
    outl = divs[divs > 2.5*med6] if len(divs) else divs
    reg = divs[~divs.index.isin(outl.index)]
    w12 = reg[reg.index > end - pd.Timedelta(days=365)]
    div12 = float(w12.sum())
    if len(w12) == 1: div12 *= 2  # semiannual payer with one payment in window
    hist_yld = div12 / last * 100 if last else 0
    yld = float(info.get("dividendYield") or 0) if info.get("dividendYield") is not None else hist_yld
    one_offs = [[str(i.date()), float(v)] for i, v in outl.items()]
    hist_incomplete = len(divs) < 4
    years_paid = sorted(set(divs.index.year)) if len(divs) else []
    sma50 = float(c.tail(50).mean()); sma200 = float(c.tail(200).mean()) if len(c) >= 200 else None
    r14 = rsi(c)
    ret6m = float(c.iloc[-1]/c[c.index <= end - pd.Timedelta(days=182)].iloc[-1]-1)*100
    ret1y = float(c.iloc[-1]/c[c.index <= end - pd.Timedelta(days=365)].iloc[-1]-1)*100 if len(c) > 240 else None
    hi52 = float(c[c.index > end - pd.Timedelta(days=365)].max()); dd52 = (last/hi52-1)*100
    # XD study: ex-date = dividend date; raw closes (not adjusted)
    pre, post, gap, rec = [], [], [], []
    for d, dv in divs.items():
        if d not in c.index: 
            idx = c.index.searchsorted(d)
        else:
            idx = c.index.get_loc(d)
        if idx < 11 or idx + 20 >= len(c): continue
        pre.append((c.iloc[idx-1]/c.iloc[idx-11]-1)*100)
        post.append((c.iloc[idx+10]/c.iloc[idx]-1)*100)
        gap.append((c.iloc[idx]/c.iloc[idx-1]-1)*100)
        rec.append(bool(c.iloc[idx:idx+21].max() >= c.iloc[idx-1]))
    n = len(rec)
    avg_pre = float(np.mean(pre)) if n else None; avg_post = float(np.mean(post)) if n else None
    rec_rate = (sum(rec)/n) if n else None
    # scores
    payout = info.get("payoutRatio")
    dy = clip(yld/7*100)
    if payout is not None and payout > 1.0: dy = min(dy, 40)
    pe = info.get("trailingPE"); pb = info.get("priceToBook")
    if pe is None or pe <= 0: val = 10
    else:
        val = 90 if pe < 10 else 70 if pe < 15 else 55 if pe < 20 else 40 if pe < 30 else 20
        if pb and pb <= 1: val = min(100, val + 10)
    g = [x for x in [info.get("revenueGrowth"), info.get("earningsGrowth")] if x is not None]
    growth = clip((np.mean(g)+0.10)/0.40*100) if g else 40
    roe = info.get("returnOnEquity") or 0; pm = info.get("profitMargins") or 0
    quality = clip(clip(roe/0.20*50) + clip(pm/0.20*50))
    tech = 20
    if sma200 and last > sma50 and last > sma200: tech = 80
    elif last > sma50 or (sma200 and last > sma200): tech = 50
    if 40 <= r14 <= 65: tech += 10
    if r14 > 70: tech -= 15
    if ret6m < 0: tech -= 10
    tech = clip(tech)
    xd = clip(rec_rate*100) if (rec_rate is not None and n >= 3) else 50
    overall = round(0.25*dy + 0.15*growth + 0.15*val + 0.15*quality + 0.15*tech + 0.15*xd, 1)
    flags = []
    if payout is not None and payout > 1.0: flags.append("payout>100%")
    if info.get("earningsGrowth") is not None and info["earningsGrowth"] < -0.1: flags.append("earnings falling")
    if pb and pb > 5: flags.append("high P/B")
    if abs(hist_yld - yld) > 1.0: flags.append(f"history yield {hist_yld:.1f}% vs {yld:.1f}% - verify")
    if one_offs: flags.append("one-off payout excluded: " + ", ".join(f"{d} {v}" for d, v in one_offs))
    if hist_incomplete: flags.append("dividend history incomplete")
    if n < 3: flags.append("few XD events")
    rows.append(dict(ticker=t, name=info.get("longName"), sector=info.get("sector"), last=round(last,2), last_date=r["last_date"],
        yield_pct=round(yld,2), hist_yield=round(hist_yld,2), div_years=years_paid[-3:], trailingPE=pe and round(pe,1), pb=pb and round(pb,2), roe=roe and round(roe*100,1),
        rev_g=info.get("revenueGrowth") and round(info["revenueGrowth"]*100,1), eps_g=info.get("earningsGrowth") and round(info["earningsGrowth"]*100,1),
        payout=payout and round(payout*100,0), sma50=round(sma50,2), sma200=sma200 and round(sma200,2), rsi=round(r14,1),
        ret6m=round(ret6m,1), ret1y=ret1y and round(ret1y,1), dd52=round(dd52,1),
        xd_events=n, xd_pre10=avg_pre and round(avg_pre,2), xd_post10=avg_post and round(avg_post,2), xd_gap=gap and round(float(np.mean(gap)),2),
        xd_recover20=rec_rate and round(rec_rate*100,0),
        scores=dict(overall=overall, dividend=round(dy), growth=round(growth), value=round(val), quality=round(quality), technical=round(tech), xd_timing=round(xd)),
        flags=flags, one_offs=one_offs))
rows.sort(key=lambda x: -x["scores"]["overall"])
json.dump(rows, open("stocks_scored.json","w"), ensure_ascii=False, indent=1)
for x in rows:
    print(x["ticker"], x["scores"]["overall"], x["scores"], "yld", x["yield_pct"], "pe", x["trailingPE"], "rsi", x["rsi"], "xdN", x["xd_events"], "pre", x["xd_pre10"], "post", x["xd_post10"], "rec", x["xd_recover20"], x["flags"])
