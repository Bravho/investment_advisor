import json
import numpy as np, pandas as pd
raw = json.load(open("funds_raw.json"))
def clip(x, a=0, b=100): return float(max(a, min(b, x)))
rows = []
for t, r in raw.items():
    c = pd.Series([v for _, v in r["closes"]], index=pd.to_datetime([d for d, _ in r["closes"]]))
    a = pd.Series([v for _, v in r["adj_closes"]], index=pd.to_datetime([d for d, _ in r["adj_closes"]]))
    end = c.index[-1]; last = float(c.iloc[-1])
    dv = pd.Series([v for _, v in r["dividends"]], index=pd.to_datetime([d for d, _ in r["dividends"]]))
    dv = dv[dv.index >= c.index[0]]
    w12 = dv[dv.index > end - pd.Timedelta(days=365)]
    hist_yld = float(w12.sum()) / last * 100
    info_yld = float(r["dividendYield"]) if r.get("dividendYield") is not None else None
    yld = hist_yld if hist_yld > 0 else (info_yld or 0)
    def ret(s, days):
        base = s[s.index <= end - pd.Timedelta(days=days)]
        return float(s.iloc[-1]/base.iloc[-1]-1)*100 if len(base) else None
    r1y_price = ret(c, 365); r3y_price = ret(c, 1095)
    r1y_total = ret(a, 365); r3y_total = ret(a, 1095)
    dr = a[a.index > end - pd.Timedelta(days=365)].pct_change().dropna()
    vol = float(dr.std()*np.sqrt(252)*100)
    mdd = float(((a/a.cummax())-1).min()*100)
    sma50 = float(a.tail(50).mean()); sma200 = float(a.tail(200).mean())
    trend = 80 if (a.iloc[-1] > sma50 > sma200) else 50 if a.iloc[-1] > sma200 else 20
    pre, post, rec = [], [], []
    for d in dv.index:
        idx = c.index.searchsorted(d)
        if idx < 11 or idx + 20 >= len(c): continue
        pre.append((c.iloc[idx-1]/c.iloc[idx-11]-1)*100); post.append((c.iloc[idx+10]/c.iloc[idx]-1)*100)
        rec.append(bool(c.iloc[idx:idx+21].max() >= c.iloc[idx-1]))
    n = len(rec); rec_rate = sum(rec)/n if n else None
    income = clip(yld/9*100)
    ret_score = clip(((r1y_total or 0)+10)/40*100)
    stab = clip(100 - vol*2.0 + mdd*0.5)
    xd = clip(rec_rate*100) if (rec_rate is not None and n >= 3) else 50
    stale = dv.empty or dv.index.max() < end - pd.Timedelta(days=365)
    flags = []
    if stale:
        overall = round((0.25*ret_score + 0.20*stab + 0.10*trend) / 0.55, 1)
        income = None; xd = None
        flags.append(f"distribution data in source stale (last {dv.index.max().date() if len(dv) else 'none'}) - yield and XD not scored")
    else:
        overall = round(0.30*income + 0.25*ret_score + 0.20*stab + 0.10*trend + 0.15*xd, 1)
    if yld > 12: flags.append(f"very high yield {yld:.1f}% with price down {round(float((c.iloc[-1]/c.iloc[0]-1)*100),0)}% over 3y - check for return of capital")
    if info_yld is not None and not stale and abs(hist_yld - info_yld) > 1.0: flags.append(f"history yield {hist_yld:.1f}% vs {info_yld:.1f}% - verify")
    if n < 3: flags.append("few distribution events")
    rows.append(dict(ticker=t, name=r.get("name"), last=round(last,3), last_date=r["last_date"],
        yield_pct=round(yld,2), r1y_price=r1y_price and round(r1y_price,1), r1y_total=r1y_total and round(r1y_total,1),
        r3y_total=r3y_total and round(r3y_total,1), vol_1y=round(vol,1), max_dd_3y=round(mdd,1), sma50=round(sma50,3), sma200=round(sma200,3),
        xd_events=n, xd_pre10=pre and round(float(np.mean(pre)),2), xd_post10=post and round(float(np.mean(post)),2), xd_recover20=rec_rate and round(rec_rate*100,0),
        scores=dict(overall=overall, income=income and round(income), total_return=round(ret_score), stability=round(stab), trend=trend, xd_timing=xd and round(xd)), flags=flags))
rows.sort(key=lambda x: -x["scores"]["overall"])
json.dump(rows, open("funds_scored.json","w"), ensure_ascii=False, indent=1)
for x in rows:
    print(x["ticker"], x["scores"], "yld", x["yield_pct"], "r1yT", x["r1y_total"], "r3yT", x["r3y_total"], "vol", x["vol_1y"], "mdd", x["max_dd_3y"], "xd", x["xd_events"], x["xd_recover20"], x["flags"])
