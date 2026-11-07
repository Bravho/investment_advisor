import json, warnings
warnings.filterwarnings("ignore")
import yfinance as yf
FUNDS = ["CPNREIT.BK","WHART.BK","FTREIT.BK","LHHOTEL.BK","TTLPF.BK","DIF.BK","TFFIF.BK","EGATIF.BK","BTSGIF.BK","TDEX.BK"]
out = {}
for t in FUNDS:
    tk = yf.Ticker(t)
    raw = tk.history(period="3y", auto_adjust=False)
    adj = tk.history(period="3y", auto_adjust=True)
    info = {}
    try: info = tk.info or {}
    except Exception: pass
    out[t] = {"name": info.get("longName"), "last_date": str(raw.index[-1].date()),
              "closes": [[str(i.date()), float(v)] for i, v in raw["Close"].dropna().items()],
              "adj_closes": [[str(i.date()), float(v)] for i, v in adj["Close"].dropna().items()],
              "dividends": [[str(i.date()), float(v)] for i, v in tk.dividends.items()],
              "dividendYield": info.get("dividendYield"), "trailingPE": info.get("trailingPE"),
              "priceToBook": info.get("priceToBook"), "category": info.get("category"), "quoteType": info.get("quoteType")}
    print(t, out[t]["name"], out[t]["last_date"], len(out[t]["dividends"]), file=__import__("sys").stderr)
json.dump(out, open("funds_raw.json", "w"))
