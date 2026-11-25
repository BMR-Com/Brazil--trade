"""India and Thailand annual sugar models: year-on-year % change in USDA production.

Target: y_t = log(P_t / P_t-1), P = USDA PSD sugar production for marketing year t (India Oct-Sep, Thailand Dec-Nov;
PSD year t starts in calendar year t, so MY 2026 = the 2026/27 crop). For India, sugar diverted to ethanol is added back
first (USDA counts sugar after diversion), so the model explains the cane crop, not ethanol policy; the call is then
netted for an assumed diversion. Apply the % change to any forecaster's previous-year figure.

India (error-correction form):
  lP1     log production last year            } together: production is pulled toward a level set by the cane
  lF1     log cane support price last season  } support price (SMP to 2008/09, FRP after, per point of recovery;
                                                 the 2009 switch from SMP to FRP is spliced out)
  ylag2   change two years back (the cane cycle: big crops -> low prices/arrears -> less planting two seasons on)
  S_t     Maharashtra + north Karnataka Jun-Sep rain this year, % of normal (rain-fed yield and recovery)
  U_l1    Uttar Pradesh Jun-Sep rain last year, % of normal (plantings and ratoons for this crop)
Thailand:
  px_l1   change in ICE No.11 (in baht where USD/THB is available, else US cents) averaged Oct(t-2)-Sep(t-1),
          the price known when the MY t cane is planted
  gap     last year's level against the average of the three before (stand and ratoon cycle)
  def_t   May-Oct rain shortfall this year (below-normal part only), % of normal
  def_l1  the same last year
Rain: CHIRPS (station-blended, data/sugar/cane_model/chirps.csv), with ERA5 and NASA POWER kept as checks.
Tests: expanding window from 2000 (fit on earlier years only) and leave-one-year-out; written with --lab PATH only.
Output: data/sugar/cane_model/annual_forecast.json (calls and the variables used).
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "sugar" / "cane_model"
OUT = D / "annual_forecast.json"
CLIM = (1991, 2020)
TEST0 = 2000

# Cane support price, Rs/quintal, by sugar season (key = calendar year the season starts in October), and the basic
# recovery it is fixed at. SMP 1990/91-2008/09 (RBI Handbook; 1993/94, 1995/96, 1996/97, 1998/99 and 2001/02 as
# reported; 2002/03 without the one-off drought relief); FRP from 2009/10 (Cabinet releases; 2026/27 Rs 365).
SUPPORT = {1990: (22.00, 8.5), 1991: (26.00, 8.5), 1992: (31.00, 8.5), 1993: (34.50, 8.5), 1994: (39.10, 8.5),
           1995: (42.50, 8.5), 1996: (45.90, 8.5), 1997: (48.45, 8.5), 1998: (52.70, 8.5), 1999: (56.10, 8.5),
           2000: (59.50, 8.5), 2001: (62.05, 8.5), 2002: (64.50, 8.5), 2003: (73.00, 8.5), 2004: (74.50, 8.5),
           2005: (79.50, 9.0), 2006: (80.25, 9.0), 2007: (81.18, 9.0), 2008: (81.18, 9.0), 2009: (129.84, 9.5),
           2010: (139.12, 9.5), 2011: (145.00, 9.5), 2012: (170.00, 9.5), 2013: (210.00, 9.5), 2014: (220.00, 9.5),
           2015: (230.00, 9.5), 2016: (230.00, 9.5), 2017: (255.00, 9.5), 2018: (275.00, 10.0), 2019: (275.00, 10.0),
           2020: (285.00, 10.0), 2021: (290.00, 10.0), 2022: (305.00, 10.25), 2023: (315.00, 10.25),
           2024: (340.00, 10.25), 2025: (355.00, 10.25), 2026: (365.00, 10.25)}
# Sugar diverted to ethanol, Mt, by season (ISMA as reported; 2018/19-2020/21 approximate).
DIVERSION = {2018: 0.3, 2019: 0.9, 2020: 2.2, 2021: 3.4, 2022: 4.1, 2023: 2.15, 2024: 3.5, 2025: 3.1}
# 2026/27: the oil companies' 2026/27 tender reportedly leaves out the sugar route, so 0 is the base case.
DIV_CASES = {"no sugar diverted to ethanol": 0.0, "diversion as in 2025/26": 3.1}

REGIONS = {"S": (["in_mh_w", "in_mh_m", "in_ka_n"], 6, 9), "U": (["in_up_w", "in_up_c"], 6, 9),
           "TH": (["th_kk", "th_ud", "th_ns", "th_kb", "th_cy"], 5, 10)}
SPECS = {"IN": ["lP1", "lF1", "ylag2", "S_t", "U_l1"], "TH": ["px_l1", "gap", "def_t", "def_l1"]}
ALT = {"IN": [["ylag2"], ["ylag2", "S_t", "U_l1"], ["lP1", "lF1"], ["lP1", "lF1", "ylag2"],
              ["ylag2", "S_t", "U_l1", "frp_l1"]],
       "TH": [["def_t", "def_l1"], ["px_l1"], ["px_l1", "def_t", "def_l1"], ["gap", "def_t", "def_l1"]]}
NAMES = {"IN": "India", "TH": "Thailand"}


def die(m):
    print("cane_annual:", m, file=sys.stderr)
    sys.exit(2)


def r2(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def rd(x, n=3):
    return None if x is None or not np.isfinite(x) else round(float(x), n)


def monthly_rain(src):
    """point x month table (mm) from CHIRPS monthly, or from ERA5 / POWER daily files."""
    if src == "chirps":
        f = D / "chirps.csv"
        if not f.exists():
            return None
        c = pd.read_csv(f)
        if "days" in c:
            dim = pd.to_datetime(c.month + "-01").dt.days_in_month
            c = c[c.days.isna() | (c.days >= 0.9 * dim)]
        return c.pivot(index="month", columns="point", values="rain_mm")
    out = {}
    for pts, _, _ in REGIONS.values():
        for p in pts:
            f = D / src / f"{p}.csv.gz"
            if f.exists():
                d = pd.read_csv(f, index_col=0, parse_dates=True).rain
                g = d.groupby(d.index.strftime("%Y-%m"))
                s = g.sum()[g.count() >= 27]
                out[p] = s
    return pd.DataFrame(out) if out else None


def region_pct(M, reg):
    """Window rain, % of 1991-2020 normal, averaged over the region's points. A year whose window is only partly in
    (the current year) is scored on the months that are in, against the normal for those months."""
    pts, m0, m1 = REGIONS[reg]
    pts = [p for p in pts if M is not None and p in M.columns]
    if not pts:
        return pd.Series(dtype=float), {}
    X = M[pts].copy()
    X["y"], X["m"] = X.index.str[:4].astype(int), X.index.str[5:7].astype(int)
    X = X[(X.m >= m0) & (X.m <= m1)]
    norm_m = X[(X.y >= CLIM[0]) & (X.y <= CLIM[1])].groupby("m")[pts].mean()
    out, part = {}, {}
    for y, g in X.groupby("y"):
        g = g.dropna(subset=pts)
        if g.empty:
            continue
        ms = list(g.m)
        pct = (g[pts].sum() / norm_m.loc[ms].sum() * 100).mean()
        out[y] = pct
        if len(ms) < m1 - m0 + 1:
            part[y] = f"{len(ms)} of {m1 - m0 + 1} months"
    return pd.Series(out).sort_index(), part


def support_series():
    sp = pd.Series({k: v[0] / v[1] for k, v in SUPPORT.items()})
    l = np.log(sp)
    ch = l.diff()
    med = ch.drop(2009).loc[2000:].median()
    jump = ch[2009] - med                     # SMP -> FRP switch, not a real price change
    l[l.index >= 2009] -= jump
    ch[2009] = med
    return l, ch


def price_series():
    sb = pd.read_csv(D / "sb_monthly.csv", index_col=0)
    sb.index = pd.PeriodIndex(sb.index, freq="M")
    s, unit = sb.sb_nearby_c_lb, "US cents/lb"
    f = D / "fx_thb.csv"
    if f.exists():
        fx = pd.read_csv(f, parse_dates=["date"]).set_index("date").thb_per_usd.astype(float).resample("MS").mean()
        fx.index = fx.index.to_period("M")
        x = (s * fx.reindex(s.index)).dropna()
        if len(x) > 300:
            s, unit = x, "baht"
    yr = s.groupby([i.year + (1 if i.month >= 10 else 0) for i in s.index]).agg(["mean", "count"])
    return yr["mean"][yr["count"] == 12], unit      # Oct(y-1)..Sep(y) average, full seasons only


def build(cc, src):
    psd = pd.read_csv(D / "psd_full.csv")
    p = psd[(psd.Country_Code == cc) & (psd.Attribute_Description == "Production")].set_index("Market_Year").Value / 1000
    p = p.sort_index()
    usda = p.copy()
    if cc == "IN":
        p = p + pd.Series(DIVERSION).reindex(p.index).fillna(0.0)
    F = pd.DataFrame({"prod": p})
    lp = np.log(F["prod"])
    F["y"] = lp.diff()
    F["ylag"], F["ylag2"] = F.y.shift(1), F.y.shift(2)
    F["gap"] = lp.shift(1) - pd.concat([lp.shift(k) for k in (2, 3, 4)], axis=1).mean(axis=1)
    F["lP1"] = lp.shift(1)
    M = monthly_rain(src)
    part = {}
    if cc == "IN":
        l, ch = support_series()
        F["lF1"] = l.reindex(F.index - 1).values
        F["frp_l1"] = ch.reindex(F.index - 1).values
        for r in ("S", "U"):
            w, pr = region_pct(M, r)
            if w.empty:
                return None, None, None, None
            F[r + "_t"], F[r + "_l1"] = w.reindex(F.index).values, w.reindex(F.index - 1).values
            part.update({f"{r} {k}": v for k, v in pr.items()})
        extra = {"support": l, "rain": {r: region_pct(M, r)[0] for r in ("S", "U")}}
    else:
        yr, unit = price_series()
        F["px_l1"] = np.log(yr).diff().reindex(F.index - 1).values
        w, pr = region_pct(M, "TH")
        if w.empty:
            return None, None, None, None
        F["rain_t"], F["rain_l1"] = w.reindex(F.index).values, w.reindex(F.index - 1).values
        F["def_t"], F["def_l1"] = np.minimum(F.rain_t - 100, 0), np.minimum(F.rain_l1 - 100, 0)
        part.update({f"TH {k}": v for k, v in pr.items()})
        extra = {"price": yr, "unit": unit, "rain": w}
    return F, usda, part, extra


def fit(tr, feats):
    X = np.column_stack([np.ones(len(tr))] + [tr[f].values for f in feats])
    co, *_ = np.linalg.lstsq(X, tr.y.values, rcond=None)
    return co


def pred(co, row, feats):
    return float(co[0] + sum(c * row[f] for c, f in zip(co[1:], feats)))


def backtest(F, feats, last_year):
    G = F.loc[:last_year].dropna(subset=["y"] + feats)
    oy, op, ot, ly, lq = [], [], [], [], []
    for t in G.index:
        tr = G[G.index < t]
        if t >= TEST0 and len(tr) >= 10:
            oy.append(G.y[t]); op.append(pred(fit(tr, feats), G.loc[t], feats)); ot.append(int(t))
        ly.append(G.y[t]); lq.append(pred(fit(G[G.index != t], feats), G.loc[t], feats))
    co = fit(G, feats)
    ins = [pred(co, G.loc[t], feats) for t in G.index]
    return {"fit_years": f"{G.index.min()}-{G.index.max()}", "n": len(G), "r2_in_sample": rd(r2(G.y, ins)),
            "r2_oos_from_2000": rd(r2(oy, op)) if len(oy) > 5 else None, "n_oos": len(oy),
            "mae_oos_pct": rd(100 * np.mean(np.abs(np.array(oy) - np.array(op))), 1) if oy else None,
            "r2_loo": rd(r2(ly, lq)), "coef": {f: rd(c, 4) for f, c in zip(["const"] + feats, co)},
            "oos_pairs": [[t, rd(a, 4), rd(b, 4)] for t, a, b in zip(ot, oy, op)]}, co


def forecast(cc, F, usda, extra, co, feats, cur):
    """Calls for MY cur (USDA's current year) and cur+1, each from inputs known now."""
    calls, prod = {}, {cur - 1: F["prod"][cur - 1]}
    for t in (cur, cur + 1):
        r = {}
        prev = prod.get(t - 1)
        r["lP1"] = np.log(prev) if prev else np.nan
        lvl = [np.log(prod[k]) if k in prod else np.log(F["prod"].get(k, np.nan)) for k in (t - 2, t - 3, t - 4)]
        r["gap"] = r["lP1"] - np.mean(lvl)
        ys = {k: F.y.get(k, np.nan) for k in (t - 1, t - 2)}
        if t == cur + 1:
            ys[t - 1] = calls[cur]["log"]
        r["ylag"], r["ylag2"] = ys[t - 1], ys[t - 2]
        if cc == "IN":
            l, ch = support_series()
            r["lF1"], r["frp_l1"] = l.get(t - 1, np.nan), ch.get(t - 1, np.nan)
            for k in ("S", "U"):
                w = extra["rain"][k]
                r[k + "_t"] = w.get(t, 100.0)             # a year not yet seen counts as normal
                r[k + "_l1"] = w.get(t - 1, 100.0)
        else:
            yr = extra["price"]
            r["px_l1"] = float(np.log(yr[t - 1] / yr[t - 2])) if (t - 1) in yr and (t - 2) in yr else np.nan
            w = extra["rain"]
            r["def_t"] = min(w.get(t, 100.0) - 100, 0)
            r["def_l1"] = min(w.get(t - 1, 100.0) - 100, 0)
        if any(not np.isfinite(r[f]) for f in feats) or calls.get(t - 1, {}).get("log", 0) is None:
            calls[t] = {"log": None, "inputs": {f: rd(r[f]) for f in feats}}
            continue
        lc = pred(co, r, feats)
        prod[t] = prev * np.exp(lc)
        calls[t] = {"log": lc, "pct": rd(100 * (np.exp(lc) - 1), 1), "level": prod[t],
                    "inputs": {f: rd(r[f], 3) for f in feats}}
    return calls


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--lab", default="")
    a = ap.parse_args()
    for f in ("psd_full.csv", "sb_monthly.csv"):
        if not (D / f).exists():
            die(f"missing {f}")
    pub, lab = {}, {}
    for cc, feats in SPECS.items():
        runs = {}
        for src in ("chirps", "era5", "wx"):
            F, usda, part, extra = build(cc, src)
            if F is None:
                continue
            cur = int(usda.index.max())
            st, co = backtest(F, feats, cur - 1)       # USDA's current year is still a forecast: test on years before
            runs[src] = (st, co, F, usda, part, extra, cur,
                         {"+".join(f): {k: v for k, v in backtest(F, f, cur - 1)[0].items() if k != "oos_pairs"}
                          for f in ALT[cc]})
        if not runs:
            continue
        src = "chirps" if "chirps" in runs else next(iter(runs))
        st, co, F, usda, part, extra, cur, alts = runs[src]
        calls = forecast(cc, F, usda, extra, co, feats, cur)
        o = {"country": NAMES[cc], "rain_source": {"chirps": "CHIRPS", "era5": "ERA5"}.get(src, "NASA POWER"),
             "usda": {str(cur - 1): rd(usda[cur - 1], 2), str(cur): rd(usda[cur], 2),
                      "current_pct": rd(100 * (usda[cur] / usda[cur - 1] - 1), 1)},
             "partial_weather": part}
        for t, c in calls.items():
            lab_t = f"{t}/{str(t + 1)[2:]}"
            if c.get("log") is None:
                o[lab_t] = None; continue
            e = {"pct_change": c["pct"]}
            if cc == "IN":
                e["basis"] = "cane sugar before ethanol diversion"
                if t == cur:
                    e["implied_usda_mt"] = {k: rd(c["level"] - v, 2) for k, v in DIV_CASES.items()}
                    e["implied_pct_vs_usda_prev"] = {k: rd(100 * ((c["level"] - v) / usda[t - 1] - 1), 1)
                                                     for k, v in DIV_CASES.items()}
                else:
                    e["implied_usda_mt_if_no_diversion"] = rd(c["level"], 2)
            else:
                e["implied_usda_mt"] = rd(c["level"], 2)
            o[lab_t] = e
        pub[cc] = o
        lab[cc] = {"chosen_rain_source": src, "spec": feats, "price_unit": extra.get("unit"),
                   "by_source": {s: {"main": v[0], "alternatives": v[7]} for s, v in runs.items()},
                   "calls": {str(k): v for k, v in calls.items()},
                   "frame": F.reset_index().rename(columns={"index": "year"}).round(4).to_dict(orient="records")}
    out = {"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
           "target": "year-on-year % change in sugar production (apply to any forecaster's previous-year figure)",
           "countries": pub,
           "variables_used": ["USDA sugar production history", "India cane support price (SMP, then FRP)",
                              "India sugar diverted to ethanol", "monsoon rain in Maharashtra, Karnataka and Uttar Pradesh",
                              "May-Oct rain in Thailand's cane belt", "ICE No.11 raw sugar price (in baht)",
                              "recent production swings"]}
    OUT.write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(pub, indent=1, default=float))
    if a.lab:
        Path(a.lab).write_text(json.dumps(lab, indent=1, default=float))
        for cc, v in lab.items():
            for s, x in v["by_source"].items():
                m = x["main"]
                print(cc, s, "main", m["n"], m["r2_in_sample"], m["r2_oos_from_2000"], m["n_oos"], m["r2_loo"], m["mae_oos_pct"])
                for k, y in x["alternatives"].items():
                    print("   ", k, y["r2_in_sample"], y["r2_oos_from_2000"], y["n_oos"], y["r2_loo"])


if __name__ == "__main__":
    main()
