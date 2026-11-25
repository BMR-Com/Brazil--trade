"""India and Thailand annual sugar models: year-on-year % change in USDA production from price support / prices and
growth-stage weather.

Target: y_t = log(P_t / P_t-1), P = USDA PSD sugar production for marketing year t (India Oct-Sep, Thailand Dec-Nov;
PSD year t starts in calendar year t). For India, sugar diverted to ethanol is added back first (USDA counts sugar after
diversion), so the model explains the cane crop, not ethanol policy; the call is then netted for the assumed diversion.

India drivers (all known before harvest of MY t):
  frp_l1   change in the cane support price per point of basic recovery (SMP to 2008/09, FRP after) for the season
           that started the October before planting (season t-1): sets plantings for MY t
  frp_l2   the same one season earlier (ratoons and the cane cycle)
  mon_t    monsoon (Jun-Sep, year t) rain at the cane points, % of 1991-2020 normal: yield and recovery of MY t
  mon_l1   monsoon of year t-1: reservoirs and soil water for plantings of MY t
  ylag     last year's change (the 3-4 year cane cycle: arrears, area swings)
Thailand drivers:
  px_l1    change in the No.11 nearby in baht, average Oct(t-2)-Sep(t-1): price known when MY t cane is planted
  rain_t   May-Oct (year t) rain, % of normal: growth of MY t cane
  rain_l1  May-Oct of year t-1: ratoon stand and plantings
  ylag     last year's change

Tests: expanding-window out of sample from 2000 (fit on years before t only) and leave-one-year-out.
Inputs: data/sugar/cane_model/{psd_full.csv, chirps.csv, era5/<id>.csv.gz, wx/<id>.csv.gz, meta.json, sb_monthly.csv,
fx_thb.csv}; the weather source with the best out-of-sample fit is used. Output: data/sugar/cane_model/annual_forecast.json (calls and variables only); --lab PATH writes backtests.
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

# Cane support price, Rs/quintal, by sugar season (key = calendar year the season starts in October) and the basic
# recovery it is fixed at. SMP 1990/91-2008/09 (RBI Handbook table 26; 1993/94, 1995/96, 1996/97, 1998/99 and 2001/02
# from Ministry notifications as reported; 2002/03 excludes the one-off drought relief); FRP from 2009/10 (Cabinet
# releases: 2024/25 Rs 340, 2025/26 Rs 355, 2026/27 Rs 365 at 10.25%).
SUPPORT = {1990: (22.00, 8.5), 1991: (26.00, 8.5), 1992: (31.00, 8.5), 1993: (34.50, 8.5), 1994: (39.10, 8.5),
           1995: (42.50, 8.5), 1996: (45.90, 8.5), 1997: (48.45, 8.5), 1998: (52.70, 8.5), 1999: (56.10, 8.5),
           2000: (59.50, 8.5), 2001: (62.05, 8.5), 2002: (64.50, 8.5), 2003: (73.00, 8.5), 2004: (74.50, 8.5),
           2005: (79.50, 9.0), 2006: (80.25, 9.0), 2007: (81.18, 9.0), 2008: (81.18, 9.0), 2009: (129.84, 9.5),
           2010: (139.12, 9.5), 2011: (145.00, 9.5), 2012: (170.00, 9.5), 2013: (210.00, 9.5), 2014: (220.00, 9.5),
           2015: (230.00, 9.5), 2016: (230.00, 9.5), 2017: (255.00, 9.5), 2018: (275.00, 10.0), 2019: (275.00, 10.0),
           2020: (285.00, 10.0), 2021: (290.00, 10.0), 2022: (305.00, 10.25), 2023: (315.00, 10.25),
           2024: (340.00, 10.25), 2025: (355.00, 10.25), 2026: (365.00, 10.25)}
# Sugar diverted to ethanol, Mt, by season (ISMA as reported; 2018/19-2020/21 approximate; 2026/27: oil companies'
# 2026/27 tender excludes the sugar route, so 0 is the base case, with last season's level as the other case).
DIVERSION = {2018: 0.3, 2019: 0.9, 2020: 2.2, 2021: 3.4, 2022: 4.1, 2023: 2.15, 2024: 3.5, 2025: 3.1}
DIV_CASES_2026 = {"no sugar-route ethanol": 0.0, "diversion as in 2025/26": 3.1}

SPECS = {"IN": ["frp_l1", "frp_l2", "mon_t", "mon_l1", "ylag"], "TH": ["px_l1", "rain_t", "rain_l1", "ylag"]}
ALT = {"IN": [["frp_l1", "mon_t", "mon_l1"], ["frp_l1", "frp_l2", "mon_t", "mon_l1"], ["mon_t", "mon_l1", "ylag"],
              ["frp_l1", "frp_l2", "ylag"]],
       "TH": [["px_l1", "rain_t", "rain_l1"], ["rain_t", "rain_l1", "ylag"], ["px_l1", "ylag"], ["px_l1", "rain_t"]]}
NAMES = {"IN": "India", "TH": "Thailand"}
WIN = {"IN": (6, 9), "TH": (5, 10)}


def die(m):
    print("cane_annual:", m, file=sys.stderr)
    sys.exit(2)


def r2(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def rd(x, n=3):
    return None if x is None or not np.isfinite(x) else round(float(x), n)


def window_rain(cc, src):
    """Weighted window rain by year and % of normal: CHIRPS monthly (src='chirps'), ERA5 daily ('era5') or NASA POWER ('wx')."""
    meta = json.loads((D / "meta.json").read_text())
    pts = {k: v for k, v in meta.get("points", meta).items() if v[0] == cc}
    m0, m1 = WIN[cc]
    if src == "chirps":
        f = D / "chirps.csv"
        if not f.exists():
            return None, None, None
        c = pd.read_csv(f)
        c = c[c.point.isin(pts)]
        c["y"], c["m"] = c.month.str[:4].astype(int), c.month.str[5:7].astype(int)
        if "days" in c:   # drop months that are not complete yet
            dim = pd.to_datetime(c.month + "-01").dt.days_in_month
            c = c[c.days.isna() | (c.days >= 0.9 * dim)]
        c = c[(c.m >= m0) & (c.m <= m1)]
        n = c.groupby(["point", "y"]).rain_mm.count()
        s = c.groupby(["point", "y"]).rain_mm.sum()[n == m1 - m0 + 1].unstack(0)
        wv = pd.Series({k: v[4] for k, v in pts.items()}).reindex(s.columns)
        tot = (s * wv).sum(axis=1, min_count=len(wv)) / wv.sum()
        tot = tot.dropna()
        return 100 * tot / tot.loc[CLIM[0]:CLIM[1]].mean(), c.month.max(), src
    tot, wsum, last = None, 0.0, None
    for pid, v in pts.items():
        f = D / src / f"{pid}.csv.gz"
        if not f.exists():
            continue
        d = pd.read_csv(f, index_col=0, parse_dates=True)
        x = d[(d.index.month >= m0) & (d.index.month <= m1)].rain
        n = x.groupby(x.index.year).count()
        s = x.groupby(x.index.year).sum()
        days = (pd.Timestamp(2001, m1, 1) + pd.offsets.MonthEnd(0) - pd.Timestamp(2001, m0, 1)).days + 1
        s = s[n >= 0.95 * days]
        tot = s * v[4] if tot is None else tot.add(s * v[4], fill_value=np.nan)
        wsum += v[4]
        last = d.index.max()
    if tot is None:
        return None, None, None
    tot = tot / wsum
    norm = tot.loc[CLIM[0]:CLIM[1]].mean()
    return 100 * tot / norm, last, src


def observed_to_date(cc, src, year):
    """Window rain so far in `year` (% of the normal for the same days) when the window is not complete."""
    if src == "chirps":
        return None, None
    meta = json.loads((D / "meta.json").read_text())
    pts = {k: v for k, v in meta.get("points", meta).items() if v[0] == cc}
    m0, m1 = WIN[cc]
    num = den = 0.0
    frac = None
    for pid, v in pts.items():
        f = D / src / f"{pid}.csv.gz"
        if not f.exists():
            continue
        d = pd.read_csv(f, index_col=0, parse_dates=True).rain
        a, b = pd.Timestamp(year, m0, 1), min(d.index.max(), pd.Timestamp(year, m1, 1) + pd.offsets.MonthEnd(0))
        if b < a:
            continue
        cur = d.loc[a:b].sum()
        clim = np.mean([d.loc[a.replace(year=y):b.replace(year=y)].sum() for y in range(CLIM[0], CLIM[1] + 1)])
        num += v[4] * cur; den += v[4] * clim
        frac = ((b - a).days + 1) / ((pd.Timestamp(year, m1, 1) + pd.offsets.MonthEnd(0) - a).days + 1)
    return (100 * num / den if den else None), frac


def build(cc, src):
    psd = pd.read_csv(D / "psd_full.csv")
    p = psd[(psd.Country_Code == cc) & (psd.Attribute_Description == "Production")].set_index("Market_Year").Value / 1000
    p = p.sort_index()
    if cc == "IN":
        p = p + pd.Series(DIVERSION).reindex(p.index).fillna(0.0)      # gross of ethanol diversion
    F = pd.DataFrame({"prod": p})
    F["y"] = np.log(F["prod"]).diff()
    F["ylag"] = F.y.shift(1)
    w, last, used = window_rain(cc, src)
    if w is None:
        return None, None
    if cc == "IN":
        sp = pd.Series({k: v[0] / v[1] for k, v in SUPPORT.items()})
        ch = np.log(sp).diff()
        F["frp_t"] = ch.reindex(F.index)                 # season starting Oct t (announced mid-year t)
        F["frp_l1"] = ch.reindex(F.index - 1).values
        F["frp_l2"] = ch.reindex(F.index - 2).values
        F["mon_t"] = w.reindex(F.index).values
        F["mon_l1"] = w.reindex(F.index - 1).values
    else:
        sb = pd.read_csv(D / "sb_monthly.csv", index_col=0)
        sb.index = pd.PeriodIndex(sb.index, freq="M")
        fx = pd.read_csv(D / "fx_thb.csv", parse_dates=["date"])
        fx = fx.set_index("date").thb_per_usd.astype(float).resample("MS").mean()
        fx.index = fx.index.to_period("M")
        thb = (sb.sb_nearby_c_lb * fx.reindex(sb.index)).dropna()
        yr = thb.groupby([(i.year + (1 if i.month >= 10 else 0)) for i in thb.index]).mean()   # Oct(y-1)..Sep(y)
        F["px_l1"] = np.log(yr).diff().reindex(F.index - 1).values
        F["rain_t"] = w.reindex(F.index).values
        F["rain_l1"] = w.reindex(F.index - 1).values
    return F, last


def fit(tr, feats):
    X = np.column_stack([np.ones(len(tr))] + [tr[f].values for f in feats])
    co, *_ = np.linalg.lstsq(X, tr.y.values, rcond=None)
    return co


def pred(co, row, feats):
    return float(co[0] + sum(c * row[f] for c, f in zip(co[1:], feats)))


def backtest(F, feats, last_year):
    G = F.loc[:last_year].dropna(subset=["y"] + feats)
    oos_y, oos_p, loo_y, loo_p = [], [], [], []
    for t in G.index:
        tr = G[G.index < t]
        if t >= TEST0 and len(tr) >= 12:
            oos_y.append(G.y[t]); oos_p.append(pred(fit(tr, feats), G.loc[t], feats))
        tr2 = G[G.index != t]
        loo_y.append(G.y[t]); loo_p.append(pred(fit(tr2, feats), G.loc[t], feats))
    co = fit(G, feats)
    ins = [pred(co, G.loc[t], feats) for t in G.index]
    return {"years": f"{G.index.min()}-{G.index.max()}", "n": len(G), "r2_in_sample": rd(r2(G.y, ins)),
            "r2_oos_from_2000": rd(r2(oos_y, oos_p)) if len(oos_y) > 5 else None, "n_oos": len(oos_y),
            "r2_loo": rd(r2(loo_y, loo_p)), "mae_oos_pct": rd(100 * np.mean(np.abs(np.array(oos_y) - np.array(oos_p))), 1),
            "coef": {f: rd(c, 4) for f, c in zip(["const"] + feats, co)}}, co


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--lab", default="")
    a = ap.parse_args()
    for f in ("psd_full.csv", "meta.json", "sb_monthly.csv"):
        if not (D / f).exists():
            die(f"missing {f}")
    pub, lab = {}, {}
    for cc, feats in SPECS.items():
        best = None
        for src in ("chirps", "era5", "wx"):
            if cc == "TH" and not (D / "fx_thb.csv").exists():
                continue
            F, last = build(cc, src)
            if F is None:
                continue
            last_full = int(F.dropna(subset=["y"]).index.max()) - 1   # latest USDA year is a forecast: test on years before
            st, co = backtest(F, feats, last_full)
            alts = {"+".join(f): backtest(F, f, last_full)[0] for f in ALT[cc]}
            lab.setdefault(cc, {})[src] = {"main": st, "alternatives": alts}
            if best is None or (st["r2_oos_from_2000"] or -9) > (best[1]["r2_oos_from_2000"] or -9):
                best = (src, st, co, F, last)
        if best is None:
            continue
        src, st, co, F, last = best
        yrs = sorted(F.index)
        cur = int(F.dropna(subset=["y"]).index.max())            # USDA's current year (2026)
        calls = {}
        for t in (cur, cur + 1):
            row = F.reindex([t]).iloc[0].copy() if t in F.index else pd.Series(dtype=float)
            if cc == "IN":
                sp = pd.Series({k: v[0] / v[1] for k, v in SUPPORT.items()})
                ch = np.log(sp).diff()
                row["frp_l1"], row["frp_l2"] = ch.get(t - 1, np.nan), ch.get(t - 2, np.nan)
            w, _, _ = window_rain(cc, src)
            k_t, k_l1 = ("mon_t", "mon_l1") if cc == "IN" else ("rain_t", "rain_l1")
            row[k_l1] = w.get(t - 1, np.nan) if w is not None else np.nan
            obs, frac = observed_to_date(cc, src, t)
            row[k_t] = w.get(t, np.nan) if (w is not None and t in w.index) else (obs if frac and frac >= 0.7 else 100.0)
            if t == cur + 1:   # this year's change becomes next year's lag: use the model's own call for it
                row["ylag"] = calls[cur]["model_log_change"]
            else:
                row["ylag"] = F.y.get(t - 1, np.nan)
            if cc == "TH":
                if t == cur + 1:
                    sb = pd.read_csv(D / "sb_monthly.csv", index_col=0)
                    sb.index = pd.PeriodIndex(sb.index, freq="M")
                    fx = pd.read_csv(D / "fx_thb.csv", parse_dates=["date"]).set_index("date").thb_per_usd.astype(float)
                    fx = fx.resample("MS").mean(); fx.index = fx.index.to_period("M")
                    thb = (sb.sb_nearby_c_lb * fx.reindex(sb.index)).dropna()
                    yr = thb.groupby([(i.year + (1 if i.month >= 10 else 0)) for i in thb.index]).mean()
                    row["px_l1"] = float(np.log(yr.get(t - 1) / yr.get(t - 2))) if (t - 1) in yr and (t - 2) in yr else np.nan
                else:
                    row["px_l1"] = F.px_l1.get(t, np.nan)
            if any(not np.isfinite(row.get(f, np.nan)) for f in feats):
                calls[t] = {"model_log_change": None}
                continue
            lc = pred(co, row, feats)
            prev = F["prod"].get(t - 1, np.nan) if t == cur else np.nan
            calls[t] = {"model_log_change": lc, "model_pct": rd(100 * (np.exp(lc) - 1), 1),
                        "inputs": {f: rd(row[f], 3) for f in feats},
                        "window_obs_share": rd(frac, 2) if t == cur + 1 or t not in (w.index if w is not None else []) else 1.0}
        psd = pd.read_csv(D / "psd_full.csv")
        up = psd[(psd.Country_Code == cc) & (psd.Attribute_Description == "Production")].set_index("Market_Year").Value / 1000
        o = {"country": NAMES[cc], "weather_source": {"chirps": "CHIRPS", "era5": "ERA5"}.get(src, "NASA POWER"),
             "usda_prev_year_mt": rd(up.get(cur - 1), 2), "usda_current_year_mt": rd(up.get(cur), 2),
             "usda_current_pct": rd(100 * (up.get(cur) / up.get(cur - 1) - 1), 1)}
        for t, c in calls.items():
            if c.get("model_pct") is None:
                o[str(t)] = None; continue
            g = np.exp(c["model_log_change"])
            e = {"model_pct_change": c["model_pct"]}
            if cc == "IN":
                gross_prev = up.get(t - 1, np.nan) + DIVERSION.get(t - 1, 0.0) if t == cur else None
                if t == cur:
                    gross = gross_prev * g
                    e["implied_usda_basis_mt"] = {k: rd(gross - v, 2) for k, v in DIV_CASES_2026.items()}
                    e["implied_pct_vs_usda_prev"] = {k: rd(100 * ((gross - v) / up.get(t - 1) - 1), 1) for k, v in DIV_CASES_2026.items()}
                else:
                    e["note"] = "gross cane-sugar change; apply to the 2026/27 gross figure"
            else:
                if t == cur:
                    e["implied_usda_basis_mt"] = rd(up.get(t - 1) * g, 2)
            o[str(t)] = e
        pub[cc] = o
        lab[cc]["chosen_source"] = src
        lab[cc]["calls"] = {str(k): v for k, v in calls.items()}
        lab[cc]["frame"] = F.reset_index().rename(columns={"index": "year"}).round(4).to_dict(orient="records")
    out = {"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
           "target": "year-on-year % change in USDA sugar production (apply to any forecaster's prior-year figure)",
           "countries": pub,
           "variables_used": ["USDA PSD sugar production", "India cane support price (SMP/FRP)", "India sugar diverted to ethanol",
                              "monsoon / May-Oct rain at cane points (CHIRPS, ERA5, NASA POWER)", "ICE No.11 nearby in baht",
                              "last year's change"]}
    OUT.write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(pub, indent=1, default=float)[:3000])
    if a.lab:
        Path(a.lab).write_text(json.dumps(lab, indent=1, default=float))
        for cc, v in lab.items():
            for s, x in v.items():
                if isinstance(x, dict) and "main" in x:
                    print(cc, s, "main", {k: x["main"][k] for k in ("n", "r2_in_sample", "r2_oos_from_2000", "r2_loo", "mae_oos_pct")})
                    for k, y in x["alternatives"].items():
                        print("   ", k, y["r2_in_sample"], y["r2_oos_from_2000"], y["r2_loo"])


if __name__ == "__main__":
    main()
