"""Brazil sugar export-flow model from public data.

Inputs (all already in the repo):
  - MAPA fortnightly sugar production by state (sugar/data/mapa_fortnight.csv)
  - MDIC/SECEX monthly exports, HS 1701, raw and white (data/exports_*.csv)
  - USDA PSD Brazil human consumption (sugar/data/psd_sugar.csv)

Builds a monthly Brazil balance (production − consumption − exports), forecasts exports for the next month and the
next three months with a linear model refit each month, and records each month's export surprise (actual − forecast).
Writes data/sugar/flows.json.
"""
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sugar" / "flows.json"
FEATS = ["tot", "prod3", "avail"]


def monthly():
    m = pd.read_csv(ROOT / "sugar/data/mapa_fortnight.csv", parse_dates=["start", "end"])
    m = m[m.end.dt.is_month_end & (m.uf != "TOTAL")]
    w = m.pivot_table(index=["safra", "end"], columns=["region", "uf"], values="sugar_t", aggfunc="sum").sort_index()
    w = w.groupby(level=0).transform(lambda x: x.ffill().cummax()).fillna(0)   # cumulative by state, no resets

    def mon(c):
        c = c.reset_index(); c.columns = ["safra", "end", "v"]
        c["p"] = c.groupby("safra").v.diff().fillna(c.v)
        return c.groupby(c.end.dt.to_period("M")).p.sum() / 1e6

    prod = mon(w.sum(axis=1))
    frames = []
    for fn in ["exports_pre2015.csv", "exports_2015on.csv"]:
        p = ROOT / "data" / fn
        if p.exists():
            x = pd.read_csv(p, dtype={"ncm": str}, usecols=["year", "month", "ncm", "kg_net"])
            frames.append(x[x.ncm.str[:4] == "1701"])
    d = pd.concat(frames)
    d["type"] = np.where(d.ncm.str[4:6].isin(["13", "14"]), "raw", np.where(d.ncm.str[4:6] == "12", "beet", "white"))
    d = d[d.type != "beet"]
    d["ym"] = pd.PeriodIndex.from_fields(year=d.year, month=d.month, freq="M")
    E = d.pivot_table(index="ym", columns="type", values="kg_net", aggfunc="sum").fillna(0) / 1e9
    E["tot"] = E.raw + E.white
    psd = pd.read_csv(ROOT / "sugar/data/psd_sugar.csv")
    cons = psd[(psd.Country_Name == "Brazil") & (psd.Attribute_Description == "Human Dom. Consumption")].set_index("Market_Year").Value / 1000
    D = pd.DataFrame({"prod": prod}).join(E, how="outer")
    D = D[D.index >= pd.Period("2018-04", "M")].copy()
    D["safra"] = [p.year if p.month >= 4 else p.year - 1 for p in D.index]
    D["cons"] = [cons.get(s, cons.iloc[-1]) / 12 for s in D.safra]
    D = D.dropna(subset=["tot"])
    D["prod"] = D["prod"].fillna(0)
    D["bal"] = D["prod"] - D["cons"] - D["tot"]
    D["avail"] = D.groupby("safra").bal.cumsum()
    D["prod3"] = D["prod"].rolling(3).sum()
    return D


def fit_predict(D, tgt, ly, h):
    feats = FEATS + [ly]
    X = D[feats + [tgt]]
    hist = []
    for t in X.index:
        if t < pd.Period("2021-04", "M"):
            continue
        tr = X[(X.index <= t - h)].dropna()
        if len(tr) < 24 or X.loc[t, feats].isna().any():
            continue
        b = np.linalg.lstsq(np.c_[np.ones(len(tr)), tr[feats]], tr[tgt], rcond=None)[0]
        hist.append((t, float(np.r_[1, X.loc[t, feats]] @ b), X.loc[t, tgt]))
    return hist


def main():
    D = monthly()
    D["y1"] = D.tot.shift(-1); D["ly1"] = D.tot.shift(11)
    D["y3"] = D.tot.shift(-1) + D.tot.shift(-2) + D.tot.shift(-3); D["ly3"] = D.tot.shift(11) + D.tot.shift(10) + D.tot.shift(9)
    h1 = fit_predict(D, "y1", "ly1", 1)
    h3 = fit_predict(D, "y3", "ly3", 3)
    last = D.index[-1]
    nxt = [p for p in pd.period_range(last + 1, periods=3, freq="M")]
    f1 = next((p for t, p, y in h1 if t == last), None)
    f3 = next((p for t, p, y in h3 if t == last), None)
    surp = [(str(t + 1), round(y - p, 3)) for t, p, y in h1 if not pd.isna(y)]
    hist = D.tail(36)
    out = {"generated": date.today().isoformat(), "last_month": str(last),
           "forecast": {"next_month": str(nxt[0]), "next_month_mt": None if f1 is None else round(f1, 2),
                        "next_month_ly": round(float(D.tot.get(nxt[0] - 12, np.nan)), 2),
                        "next3": f"{nxt[0]}–{nxt[-1]}", "next3_mt": None if f3 is None else round(f3, 2),
                        "next3_ly": round(float(sum(D.tot.get(p - 12, 0) for p in nxt)), 2)},
           "surprise": {"months": [s[0] for s in surp[-24:]], "mt": [s[1] for s in surp[-24:]]},
           "balance": {"months": [str(p) for p in hist.index], "prod": hist["prod"].round(3).tolist(), "exports": hist.tot.round(3).tolist(),
                       "cons": hist.cons.round(3).tolist(), "season_build": hist.avail.round(3).tolist()},
           "variables": ["MAPA monthly sugar production (last 3 months)", "SECEX exports last month", "Season-to-date Brazil balance (production − consumption − exports)",
                         "Exports in the same months last year"]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out))
    print("sugar flows", out["forecast"], surp[-4:])


if __name__ == "__main__":
    main()
