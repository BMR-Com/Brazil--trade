"""Spreads & arbs table for coffee and sugar, built from the desk's own settlements.

Layout follows the usual broker daily (calendar switches, arabica/robusta arb, Brazil arb, white premium); every
number is computed here from stored closes, nothing is copied from a publisher.

Inputs : data/contracts/KC.csv, data/contracts/SB.csv          (per-contract ICE closes, contract,date,close)
         coffee/data/prices_curve.csv                         (ICE London robusta contracts RC*, last ~400 days)
         coffee/data/prices_cont.csv                          (B3 arabica 4/5 front ICF1!, US$/60kg bag)
         sugar/data/prices_contracts.csv                      (ICE London No. 5 white contracts W*)
Output : data/markets/spread_tables.json

Rows: value (latest settlement), day change (same contracts, previous session), 1-year percentile of the same
position (front/2nd, 2nd/3rd, ...) over the last 252 sessions, and the spread as % of the deferred leg.
Front contracts roll at first notice (KC, RC) or expiry (SB, W) - approximate exchange calendars.
A missing main input raises (the workflow step shows the failure).
"""
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "markets", "spread_tables.json")
LB_T = 22.0462          # lb per metric tonne / 100 (US$/t -> c/lb divide by this)
LB_BAG = 132.277        # lb per 60 kg bag
MON = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6, "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}
MNAME = {1: "Jan", 3: "Mar", 5: "May", 7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}
BD = pd.offsets.BDay()


def roll_date(sym, code):
    """Approximate last day a contract is treated as 'front' (exclusive)."""
    y, m = int(code[-4:]), MON[code[-5]]
    first = pd.Timestamp(y, m, 1)
    if sym in ("KC", "RC"):                 # first notice: KC ~7, RC ~4 business days before the delivery month
        return first - (7 if sym == "KC" else 4) * BD
    if sym == "SB":                         # No. 11 expires on the last trading day of the month before delivery
        return first - 1 * BD
    if sym == "W":                          # No. 5 expires 16 calendar days before the delivery month
        return first - pd.Timedelta(days=16)
    raise ValueError(sym)


def load():
    def need(p):
        p = os.path.join(ROOT, p)
        if not os.path.exists(p):
            raise SystemExit(f"missing input {p}")
        return pd.read_csv(p)
    kc = need("data/contracts/KC.csv").rename(columns={"contract": "symbol"})
    sb = need("data/contracts/SB.csv").rename(columns={"contract": "symbol"})
    curve = need("coffee/data/prices_curve.csv")
    rc = curve[curve.symbol.str.match(r"^RC[FHKNUX]\d{4}$")]
    sp = need("sugar/data/prices_contracts.csv")
    w = sp[sp.symbol.str.match(r"^W[HKQVZ]\d{4}$")]
    cont = need("coffee/data/prices_cont.csv")
    icf = cont[cont.symbol == "ICF1!"][["date", "close"]]
    out = {}
    for k, d in (("KC", kc), ("SB", sb), ("RC", rc), ("W", w)):
        d = d[["symbol", "date", "close"]].dropna()
        d = d[d.close > 0]
        d["date"] = pd.to_datetime(d.date)
        if d.empty:
            raise SystemExit(f"no {k} closes")
        out[k] = d.pivot_table(index="date", columns="symbol", values="close").sort_index()
    icf["date"] = pd.to_datetime(icf.date)
    out["ICF"] = icf.set_index("date").close.sort_index()
    return out


def chain(sym, wide, date, n=6):
    """Active contracts on a date, nearest first, with a close that day."""
    row = wide.loc[date].dropna()
    cs = [c for c in row.index if roll_date(sym, c) > date]
    cs.sort(key=lambda c: (int(c[-4:]), MON[c[-5]]))
    return cs[:n]


def label(c):
    return f"{MNAME.get(MON[c[-5]], c[-5])}{c[-2:]}"


def pctile(hist, v):
    h = pd.Series(hist).dropna()
    if len(h) < 60 or v is None or np.isnan(v):
        return None
    return round(float((h < v).mean() * 100 + (h == v).mean() * 50), 0)


def r(v, d=2):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), d)


def pos_series(sym, wide, i, j, days, fn):
    """History of fn(price_i, price_j) for the i-th and j-th active contracts (position-based, so it rolls)."""
    vals = []
    for t in days:
        cs = chain(sym, wide, t, max(i, j) + 1)
        if len(cs) > max(i, j):
            vals.append(fn(wide.at[t, cs[i]], wide.at[t, cs[j]]))
    return vals


def calendar_rows(sym, wide, unit, npairs, group):
    days = wide.index[-260:]
    t = days[-1]
    prev = wide.index[-2]
    cs = chain(sym, wide, t, npairs + 1)
    rows = []
    for i in range(min(npairs, len(cs) - 1)):
        a, b = cs[i], cs[i + 1]
        v = wide.at[t, a] - wide.at[t, b]
        pv = wide.at[prev, a] - wide.at[prev, b] if not (np.isnan(wide.at[prev, a]) or np.isnan(wide.at[prev, b])) else np.nan
        hist = pos_series(sym, wide, i, i + 1, days[-252:], lambda x, y: x - y)
        rows.append({"group": group, "label": f"{label(a)}/{label(b)}", "legs": [a, b], "position": f"{i + 1}/{i + 2}",
                     "unit": unit, "value": r(v), "pct_of_deferred": r(v / wide.at[t, b] * 100, 2),
                     "chg": r(v - pv), "pctile_1y": pctile(hist, v), "date": t.strftime("%Y-%m-%d")})
    return rows


def kc_rc_rows(D):
    kc, rc = D["KC"], D["RC"]
    common = kc.index.intersection(rc.index)
    if len(common) < 2:
        return []
    t, prev = common[-1], common[-2]
    kcs = chain("KC", kc, t, 6)
    rcs = chain("RC", rc, t, 8)
    rows = []
    # matched months (KC Mar vs RC Mar, ...): the first two KC months that robusta also lists
    pairs = [(a, b) for a in kcs for b in rcs if a[-5:] == b[-5:]][:2]
    days = common[-252:]
    for k, (a, b) in enumerate(pairs):
        v = kc.at[t, a] - rc.at[t, b] / LB_T
        pv = kc.at[prev, a] - rc.at[prev, b] / LB_T
        ratio = kc.at[t, a] / (rc.at[t, b] / LB_T)
        hist, hr = [], []
        for d in days:              # same position history: k-th matched month on each day
            ks, rs = chain("KC", kc, d, 6), chain("RC", rc, d, 8)
            pr = [(x, y) for x in ks for y in rs if x[-5:] == y[-5:]]
            if len(pr) > k and not np.isnan(rc.at[d, pr[k][1]]):
                hist.append(kc.at[d, pr[k][0]] - rc.at[d, pr[k][1]] / LB_T)
                hr.append(kc.at[d, pr[k][0]] / (rc.at[d, pr[k][1]] / LB_T))
        rows.append({"group": "Arabica / robusta arb", "label": f"KC {label(a)} − RC {label(b)}", "legs": [a, b], "unit": "c/lb",
                     "value": r(v), "chg": r(v - pv), "pctile_1y": pctile(hist, v), "date": t.strftime("%Y-%m-%d"),
                     "ratio": r(ratio, 3), "ratio_pctile_1y": pctile(hr, ratio)})
    return rows


def b3_rows(D):
    kc, icf = D["KC"], D["ICF"] / LB_BAG * 100
    common = kc.index.intersection(icf.index)
    if len(common) < 2:
        return []
    t, prev = common[-1], common[-2]
    days = common[-252:]
    def val(d):
        cs = chain("KC", kc, d, 2)
        return (icf.loc[d] - kc.at[d, cs[0]], cs[0]) if cs else (np.nan, None)
    v, a = val(t)
    pv = icf.loc[prev] - kc.at[prev, a] if a else np.nan
    hist = [val(d)[0] for d in days]
    return [{"group": "Brazil arb", "label": f"B3 arabica 4/5 front − KC {label(a)}", "legs": ["ICF1!", a], "unit": "c/lb",
             "value": r(v), "chg": r(v - pv), "pctile_1y": pctile(hist, v), "date": t.strftime("%Y-%m-%d"),
             "note": "B3 US$/bag converted at 132.277 lb/bag; B3 front month may differ from the KC month"}]


def white_rows(D):
    sb, w = D["SB"], D["W"]
    common = sb.index.intersection(w.index)
    t, prev = common[-1], common[-2]
    # usual pairing: No. 5 Mar/May/Aug/Oct/Dec against No. 11 Mar/May/Jul/Oct/next Mar
    match = {"H": ("H", 0), "K": ("K", 0), "Q": ("N", 0), "V": ("V", 0), "Z": ("H", 1)}

    def pairs_on(d, n=3):
        ws, ss = chain("W", w, d, 6), set(chain("SB", sb, d, 8))
        out = []
        for c in ws:
            m, dy = match[c[-5]]
            s = f"SB{m}{int(c[-4:]) + dy}"
            if s in ss and not np.isnan(sb.at[d, s]):
                out.append((c, s))
        return out[:n]

    days = common[-252:]
    rows = []
    for k, (a, b) in enumerate(pairs_on(t)):
        v = w.at[t, a] - sb.at[t, b] * LB_T
        pv = w.at[prev, a] - sb.at[prev, b] * LB_T
        hist = []
        for d in days:
            p = pairs_on(d)
            if len(p) > k:
                hist.append(w.at[d, p[k][0]] - sb.at[d, p[k][1]] * LB_T)
        rows.append({"group": "White premium", "label": f"No.5 {label(a)} − No.11 {label(b)}", "legs": [a, b], "unit": "$/t",
                     "value": r(v, 1), "chg": r(v - pv, 1), "pctile_1y": pctile(hist, v), "date": t.strftime("%Y-%m-%d"),
                     "pct_of_deferred": r(v / (sb.at[t, b] * LB_T) * 100, 1)})
    return rows


def flat_rows(sym, wide, unit, group, n=2):
    t, prev = wide.index[-1], wide.index[-2]
    out = []
    for c in chain(sym, wide, t, n):
        out.append({"group": group, "label": label(c), "legs": [c], "unit": unit, "value": r(wide.at[t, c]),
                    "chg": r(wide.at[t, c] - wide.at[prev, c]), "date": t.strftime("%Y-%m-%d")})
    return out


def main():
    D = load()
    coffee = (flat_rows("KC", D["KC"], "c/lb", "Settlements: ICE arabica") + flat_rows("RC", D["RC"], "$/t", "Settlements: ICE robusta")
              + calendar_rows("KC", D["KC"], "c/lb", 5, "Arabica switches") + calendar_rows("RC", D["RC"], "$/t", 4, "Robusta switches")
              + kc_rc_rows(D) + b3_rows(D))
    sugar = (flat_rows("SB", D["SB"], "c/lb", "Settlements: ICE No. 11") + flat_rows("W", D["W"], "$/t", "Settlements: ICE No. 5")
             + calendar_rows("SB", D["SB"], "c/lb", 4, "No. 11 switches") + calendar_rows("W", D["W"], "$/t", 3, "No. 5 switches")
             + white_rows(D))
    if not [x for x in coffee if x["group"] == "Arabica switches"] or not [x for x in sugar if x["group"] == "White premium"]:
        raise SystemExit("spread tables incomplete")
    asof = max(x["date"] for x in coffee + sugar)
    out = {"built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "asof": asof,
           "coffee": coffee, "sugar": sugar,
           "notes": ["Spread = nearby minus deferred; positive = inverted (nearby premium), negative = carry.",
                     "Day change uses the same two contracts on the previous session; the 1-year percentile ranks today's value "
                     "against the same position (1st/2nd month etc.) over the last 252 sessions, so it rolls with the curve.",
                     "Arabica/robusta arb: KC c/lb minus robusta $/t ÷ 22.0462; ratio = KC ÷ robusta in c/lb.",
                     "White premium: No. 5 $/t minus No. 11 c/lb × 22.0462 (Mar/Mar, May/May, Aug/Jul, Oct/Oct, Dec/Mar).",
                     "Sources: ICE settlements and B3 front month via the desk's price files (TradingView feed)."]}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print("spread tables", asof, len(coffee), len(sugar))


if __name__ == "__main__":
    sys.exit(main())
