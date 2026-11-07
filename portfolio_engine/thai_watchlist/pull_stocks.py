import json, sys, warnings
warnings.filterwarnings("ignore")
import yfinance as yf
TICKERS = ["ADVANC.BK","AOT.BK","BAFS.BK","BBL.BK","KBANK.BK","KTB.BK","TTB.BK","TISCO.BK","TCAP.BK","LH.BK",
           "PTT.BK","PTTEP.BK","SCB.BK","TOP.BK","BA.BK","KTC.BK","CPALL.BK","DELTA.BK","BDMS.BK","GULF.BK"]
out = {}
for t in TICKERS:
    try:
        tk = yf.Ticker(t)
        h = tk.history(period="3y", auto_adjust=False)
        divs = tk.dividends
        info = {}
        try:
            info = tk.info or {}
        except Exception as e:
            info = {"_err": str(e)}
        rec = {
            "last_date": str(h.index[-1].date()) if len(h) else None,
            "last_close": float(h["Close"].iloc[-1]) if len(h) else None,
            "closes": [[str(i.date()), float(v)] for i, v in h["Close"].dropna().items()],
            "dividends": [[str(i.date()), float(v)] for i, v in divs.items()],
            "info": {k: info.get(k) for k in ["longName","sector","industry","trailingPE","forwardPE","trailingEps","forwardEps",
                      "dividendYield","trailingAnnualDividendRate","payoutRatio","returnOnEquity","revenueGrowth","earningsGrowth",
                      "profitMargins","priceToBook","marketCap","fiftyTwoWeekHigh","fiftyTwoWeekLow","currency","_err"] if k in info},
        }
        out[t] = rec
        print(t, rec["last_date"], rec["last_close"], len(rec["dividends"]), file=sys.stderr)
    except Exception as e:
        out[t] = {"error": str(e)}
        print(t, "ERR", e, file=sys.stderr)
json.dump(out, open("stocks_raw.json","w"))
