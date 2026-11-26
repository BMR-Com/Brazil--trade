"""Arabica minus robusta spread in US cents per pound -> data/coffee/kc_rc_spread.json (Coffee > Arabica / robusta).

Inputs (all already collected by the coffee workflow; nothing is downloaded here):
  coffee/data/prices_cont.csv    KC1! KC2! RC1! RC2! daily closes (TradingView, settlement bars) from 1995
  coffee/data/prices_curve.csv   KC and RC contract closes, last ~400 days
  data/contracts/KC.csv          KC contract closes from 2004 (used to label which contract KC1! is on)
Kept here:
  data/coffee/rc_contracts.csv   RC contract closes, appended from prices_curve.csv on every run so the
                                 contract-level robusta history keeps growing past the 400-day window

Robusta $/t is converted with  c/lb = $/t / 22.0462.
Matched nearby = the nearest KC month paired with the same RC month (Mar/Mar, May/May, Jul/Jul, Sep/Sep;
Dec arabica against Jan robusta, or Nov robusta for the two weeks when Jan is not yet a front-two month).
Front = KC1! minus RC1! as listed. Only dates on which both exchanges settled are used.

Usage: python models/kc_rc_spread.py
"""
import json, os, sys
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONT = os.path.join(ROOT, "coffee", "data", "prices_cont.csv")
CURVE = os.path.join(ROOT, "coffee", "data", "prices_curve.csv")
KCC = os.path.join(ROOT, "data", "contracts", "KC.csv")
RCC = os.path.join(ROOT, "data", "coffee", "rc_contracts.csv")
OUT = os.path.join(ROOT, "data", "coffee", "kc_rc_spread.json")
LB = 22.0462
KC_M = {"H": 3, "K": 5, "N": 7, "U": 9, "Z": 12}
RC_M = {"F": 1, "H": 3, "K": 5, "N": 7, "U": 9, "X": 11}
MNAME = {1: "Jan", 3: "Mar", 5: "May", 7: "Jul", 9: "Sep", 11: "Nov", 12: "Dec"}
KC_ROLL, RC_ROLL = 15, 4   # trading days before the first trading day of the delivery month (KC learned from contract data, RC = first notice)


def rd(v, n=2):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), n)


def settled_only(df):
    """Drop today's bars if the run is before both settlements (London 17:30, New York 13:30 ET)."""
    now = datetime.now(timezone.utc)
    if now.hour < 19:
        df = df[df.date != now.strftime("%Y-%m-%d")]
    return df


def keep_rc_contracts():
    cu = settled_only(pd.read_csv(CURVE))
    cu = cu[cu.symbol.str.startswith("RC")][["symbol", "date", "close", "volume"]].rename(columns={"symbol": "contract"})
    if os.path.exists(RCC):
        cu = pd.concat([pd.read_csv(RCC), cu])
    cu = cu.dropna(subset=["close"]).drop_duplicates(["contract", "date"], keep="last").sort_values(["contract", "date"])
    cu.to_csv(RCC, index=False)
    return cu


def code(ctr):
    return ctr[2], int(ctr[3:])


def rule_labels(dates, months, roll, prefix):
    """Front and second contract for each date from the roll rule, using the series' own trading calendar."""
    dates = list(dates)
    rolls = []   # (roll date, contract that becomes front)
    y0, y1 = int(dates[0][:4]), int(dates[-1][:4]) + 2
    codes = sorted(months.items(), key=lambda kv: kv[1])
    seq = [(y, c, m) for y in range(y0, y1 + 1) for c, m in codes]
    idx = pd.Index(dates)
    for k in range(1, len(seq)):
        y, c, m = seq[k - 1]   # contract that rolls off
        first = idx.searchsorted(f"{y}-{m:02d}-01")
        if first >= len(idx):
            first = len(idx) + (pd.Timestamp(f"{y}-{m:02d}-01") - pd.Timestamp(dates[-1])).days * 5 // 7
        rolls.append((first - roll, seq[k]))
    front, second = [], []
    j = 0
    for i in range(len(dates)):
        while j < len(rolls) and i >= rolls[j][0]:
            j += 1
        a = seq[j] if j < len(seq) else seq[-1]
        b = seq[j + 1] if j + 1 < len(seq) else seq[-1]
        front.append(f"{prefix}{a[1]}{a[0]}"); second.append(f"{prefix}{b[1]}{b[0]}")
    return front, second


def kc_labels(kc1):
    f, s = rule_labels(kc1.index, KC_M, KC_ROLL, "KC")
    lab = pd.DataFrame({"f": f, "s": s}, index=kc1.index)
    if os.path.exists(KCC):   # exact labels where the contract file confirms them
        kp = pd.read_csv(KCC).pivot_table(index="date", columns="contract", values="close")
        for d, v in kc1.items():
            if d in kp.index:
                row = kp.loc[d].dropna(); m = row[(row - v).abs() < 0.051]
                if len(m) == 1 and m.index[0] != lab.at[d, "f"]:
                    c, y = code(m.index[0]); order = "HKNUZ"; i = order.index(c)
                    nxt = f"KC{order[(i + 1) % 5]}{y + (1 if i == 4 else 0)}"
                    lab.at[d, "f"], lab.at[d, "s"] = m.index[0], nxt
    return lab


def pct(x, v, minn=50):
    x = np.asarray([a for a in x if a is not None and np.isfinite(a)])
    return None if len(x) < minn or v is None else float((x < v).mean() * 100 + (x == v).mean() * 50)


def stats(s, v, d, years=5):
    w = s[s.index >= str(int(d[:4]) - years) + d[4:]]
    return {"pct5y": rd(pct(w.values, v), 0), "pct_all": rd(pct(s.values, v), 0), "min5y": rd(w.min(), 1), "max5y": rd(w.max(), 1),
            "med5y": rd(w.median(), 1), "min5y_date": w.idxmin(), "max5y_date": w.idxmax()}


def change(s, days):
    t = pd.Timestamp(s.index[-1]) - pd.Timedelta(days=days)
    p = s[s.index <= t.strftime("%Y-%m-%d")]
    return rd(s.iloc[-1] - p.iloc[-1], 1) if len(p) else None


def main():
    if not os.path.exists(CONT) or not os.path.exists(CURVE):
        sys.exit("::error::coffee price files missing (coffee/scripts/fetch.py not run?)")
    rcc = keep_rc_contracts()
    c = settled_only(pd.read_csv(CONT))
    p = c.pivot_table(index="date", columns="symbol", values="close")
    need = ["KC1!", "KC2!", "RC1!", "RC2!"]
    if any(n not in p for n in need):
        sys.exit("::error::KC1!/KC2!/RC1!/RC2! missing from prices_cont.csv")
    kc = p[["KC1!", "KC2!"]].dropna(); rc = p[["RC1!", "RC2!"]].dropna()
    kl = kc_labels(kc["KC1!"])
    rf, rs = rule_labels(rc.index, RC_M, RC_ROLL, "RC")
    rl = pd.DataFrame({"f": rf, "s": rs}, index=rc.index)
    rpiv = rcc.pivot_table(index="date", columns="contract", values="close")
    kpiv = pd.read_csv(KCC).pivot_table(index="date", columns="contract", values="close") if os.path.exists(KCC) else pd.DataFrame()
    cpiv = settled_only(pd.read_csv(CURVE)); cpiv = cpiv[cpiv.symbol.str.startswith("KC")].pivot_table(index="date", columns="symbol", values="close")

    common = kc.index.intersection(rc.index)
    if len(common) < 1000:
        sys.exit("::error::too little common KC/RC history")
    rows = []
    for d in common:
        k1, k2 = kl.at[d, "f"], kl.at[d, "s"]; r1, r2 = rl.at[d, "f"], rl.at[d, "s"]
        kc_c, kc_y = code(k1)
        km = KC_M[kc_c]
        want = [(kc_y + 1, 1), (kc_y, 11)] if km == 12 else [(kc_y, km)]
        pick = None
        for wy, wm in want:
            for lab, col in ((r1, "RC1!"), (r2, "RC2!")):
                rcode, ry = code(lab)
                if ry == wy and RC_M[rcode] == wm:
                    pick = (lab, rc.at[d, col]); break
            if pick: break
        if not pick:
            continue
        kv = kc.at[d, "KC1!"]; rv = pick[1] / LB
        rows.append((d, k1, pick[0], kv, pick[1], kv - rv, kv / rv, kv - rc.at[d, "RC1!"] / LB))
    S = pd.DataFrame(rows, columns=["date", "kc", "rc", "kc_px", "rc_usd_t", "spread", "ratio", "front"]).set_index("date")
    if S.empty:
        sys.exit("::error::no matched KC/RC dates")
    d = S.index[-1]; last = S.iloc[-1]
    sp, ra, fr = S.spread, S.ratio, S.front

    # March against March, by contract year (KC from the contract file or curve, RC from its contract file or the labelled front two)
    march = {}
    for y in range(int(S.index[0][:4]) + 1, int(d[:4]) + 2):
        kcn, rcn = f"KCH{y}", f"RCH{y}"
        kser = pd.concat([kpiv[kcn].dropna() if kcn in kpiv else pd.Series(dtype=float), cpiv[kcn].dropna() if kcn in cpiv else pd.Series(dtype=float)])
        kser = kser[~kser.index.duplicated(keep="last")]
        if kser.empty:   # before the contract file: KC1!/KC2! when labelled March
            m1 = kl.index[kl.f == kcn]; m2 = kl.index[kl.s == kcn]
            kser = pd.concat([kc.loc[m1, "KC1!"], kc.loc[m2, "KC2!"]])
        rser = rpiv[rcn].dropna() if rcn in rpiv else pd.Series(dtype=float)
        m1 = rl.index[rl.f == rcn]; m2 = rl.index[rl.s == rcn]
        rlab = pd.concat([rc.loc[m1, "RC1!"], rc.loc[m2, "RC2!"]])
        rser = pd.concat([rlab, rser]); rser = rser[~rser.index.duplicated(keep="last")]
        x = pd.concat([kser.rename("k"), rser.rename("r")], axis=1).dropna().sort_index()
        x = x[(x.index >= f"{y - 1}-06-01") & (x.index <= f"{y}-02-28")]
        if len(x) < 20:
            continue
        s = (x.k - x.r / LB)
        march[str(y)] = {"dates": list(s.index), "spread": [rd(v, 1) for v in s], "ratio": [rd(v, 3) for v in (x.k / (x.r / LB))]}
    my = str(int(d[:4]) + (1 if int(d[5:7]) >= 3 else 0))
    mnow = march.get(my)
    mar = None
    if mnow and mnow["dates"][-1] == d:
        mv = mnow["spread"][-1]
        md = d[4:]
        same = []
        for y, v in march.items():   # March spread on the same calendar date (nearest trading day within 4 days) in earlier contracts
            if y == my: continue
            target = f"{int(y) - (int(my) - int(d[:4]))}{md}"
            ds = pd.Index(v["dates"]); i = ds.searchsorted(target)
            for j in (i, i - 1):
                if 0 <= j < len(ds) and abs((pd.Timestamp(ds[j]) - pd.Timestamp(target)).days) <= 4:
                    same.append({"contract": f"Mar {y}", "date": ds[j], "spread": v["spread"][j], "ratio": v["ratio"][j]}); break
        vals = [r["spread"] for r in same]
        mar = {"contract": f"Mar {my}", "spread": mv, "ratio": mnow["ratio"][-1], "same_date": same[-12:],
               "pct_same_date": rd(pct(vals, mv, 5), 0), "kc": f"KCH{my}", "rc": f"RCH{my}"}

    # seasonal overlay of the matched nearby spread by calendar week
    W = S[["spread", "ratio"]].copy(); W.index = pd.to_datetime(W.index)
    W["yr"] = W.index.year; W["wk"] = np.minimum((W.index.dayofyear - 1) // 7 + 1, 52)
    g = W.groupby(["yr", "wk"]).mean()
    cy = int(d[:4]); yrs = [y for y in sorted(W.yr.unique()) if y >= cy - 10]
    seas = {"weeks": list(range(1, 53)), "years": {}, "ratio_years": {}}
    for y in yrs:
        seas["years"][str(y)] = [rd(g.spread.get((y, w)), 1) for w in range(1, 53)]
        seas["ratio_years"][str(y)] = [rd(g.ratio.get((y, w)), 3) for w in range(1, 53)]
    prior = [y for y in range(cy - 5, cy)]
    band = {"min": [], "max": [], "avg": [], "rmin": [], "rmax": [], "ravg": []}
    for w in range(1, 53):
        v = [g.spread.get((y, w)) for y in prior if (y, w) in g.index]
        r = [g.ratio.get((y, w)) for y in prior if (y, w) in g.index]
        for k, arr in (("", v), ("r", r)):
            band[k + "min"].append(rd(min(arr), 3 if k else 1) if arr else None); band[k + "max"].append(rd(max(arr), 3 if k else 1) if arr else None)
            band[k + "avg"].append(rd(np.mean(arr), 3 if k else 1) if arr else None)
    seas["band5"] = band; seas["band_years"] = [str(y) for y in prior]
    wk = int(min((pd.Timestamp(d).dayofyear - 1) // 7 + 1, 52))
    same_wk = [g.spread.get((y, wk)) for y in prior if (y, wk) in g.index]
    same_wk_r = [g.ratio.get((y, wk)) for y in prior if (y, wk) in g.index]

    def leg(name):
        return f"{MNAME[KC_M[name[2]]] if name.startswith('KC') else MNAME[RC_M[name[2]]]} {name[-2:]}"

    st, sr, sf = stats(sp, last.spread, d), stats(ra, last.ratio, d), stats(fr, last.front, d)
    out = {
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "as_of": d, "unit": "US cents per lb",
        "now": {
            "pair": f"KC {leg(last.kc)} − RC {leg(last.rc)}", "kc": last.kc, "rc": last.rc, "kc_px": rd(last.kc_px, 2),
            "rc_usd_t": rd(last.rc_usd_t, 0), "rc_c_lb": rd(last.rc_usd_t / LB, 2),
            "spread": rd(last.spread, 1), "ratio": rd(last.ratio, 3), "front": rd(last.front, 1),
            "chg_1w": change(sp, 7), "chg_1m": change(sp, 30), "chg_1y": change(sp, 365),
            "spread_stats": st, "ratio_stats": sr, "front_stats": sf,
            "week": wk, "seas_avg5": rd(np.mean(same_wk), 1) if same_wk else None, "seas_min5": rd(min(same_wk), 1) if same_wk else None,
            "seas_max5": rd(max(same_wk), 1) if same_wk else None, "seas_ratio_avg5": rd(np.mean(same_wk_r), 3) if same_wk_r else None,
            "rc_front_usd_t": rd(rc["RC1!"].iloc[-1], 0), "rc_front_date": rc.index[-1],
            "rc_front_low_since": next((dd for dd, v in rc["RC1!"].iloc[-2::-1].items() if v <= rc["RC1!"].iloc[-1]), None),
        },
        "march": mar,
        "history": {"dates": list(S.index), "spread": [rd(v, 1) for v in sp], "ratio": [rd(v, 3) for v in ra]},
        "march_by_year": {y: v for y, v in march.items() if int(y) >= int(my) - 6},
        "seasonal": seas,
        "variables": ["ICE US arabica (KC) settlements, US cents per lb", "ICE Europe robusta (RC) settlements, US$ per tonne ÷ 22.0462",
                      "Matched delivery months: Mar/Mar, May/May, Jul/Jul, Sep/Sep, Dec arabica/Jan robusta", "Ratio = arabica ÷ robusta, both in cents per lb"],
    }
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    n = out["now"]
    print(f"kc_rc_spread: {d} {n['pair']} {n['spread']} c/lb ratio {n['ratio']} ({st['pct5y']} pct 5y); "
          f"March {mar['spread'] if mar else '-'}; history {S.index[0]} to {d}, {len(S)} days; RC contracts {rcc.contract.nunique()}")


if __name__ == "__main__":
    main()
