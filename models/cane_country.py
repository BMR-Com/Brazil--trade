"""Country cane-sugar crop model: weather in the growth stages, ENSO and last year's crop -> this year's crop.

For each origin the target is the year-on-year change in USDA PSD cane sugar production,
y_t = log(P_t) - log(P_t-1), explained by a small fixed set of agronomic variables that are all known by the start of
that marketing year's harvest (window rain or root-zone wetness, the previous season's window, frost / heat days and
the previous year's change). Each spec was fixed from the phenology note before looking at test results.

Inputs (relative to the repo root):
  data/sugar/cane_model/psd_full.csv   USDA PSD sugar (1000 MT raw value), 'Cane Sugar Production'
  data/sugar/cane_model/wx/<id>.csv.gz daily point weather (NASA POWER): date, rain, tmax, tmin, gwr
  data/sugar/cane_model/meta.json      points {id: [country, label, lat, lon, weight]}
  data/sugar/cane_model/oni.csv        NOAA ONI (season, year, total, anom)

Output: data/sugar/cane_model/country_forecast.json (final numbers only).
  --lab PATH  also writes the full backtest statistics, coefficients and per-year predictions to PATH (keep it
              outside the repo: it is private research).
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "sugar" / "cane_model"
OUT = D / "country_forecast.json"

FIRST, LAST = 1982, 2025          # target years used for fitting (2026 is USDA's current-year forecast)
TEST0 = 2000                      # first expanding-window test year
MIN_TRAIN = 15
CLIM = (1991, 2020)
# Target and moisture metric were chosen once, by one rule for every country (best median expanding-window level skill
# over the grid yoy / yoy-minus-drift / trend deviation x rain / root-zone wetness); --lab re-runs that grid as a check.
TARGET, MOIST = "yoy", "rain"
OBS_MIN = 0.7                     # a window counts as observed when >= 70% of its days are in the data
SEASONS = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def months(a, b):
    """Window from (year offset, month) a to b inclusive, e.g. ((-1, 10), (0, 3)) = Oct(t-1)..Mar(t)."""
    out, (y, m) = [], a
    while (y, m) <= b:
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return tuple(out)


def wlabel(w):
    def one(o, m):
        return MON[m - 1] + ("(t)" if o == 0 else f"(t{o:+d})")
    return one(*w[0]) + "-" + one(*w[-1])


def shift(w, k):
    return tuple((o + k, m) for o, m in w)


# ---- country specs (fixed from the phenology note: main yield window, a lag term, persistence) -------------------
# feature tuple: (kind, window) with kind in rain | wet | frost | heat | oni ; ('ylag', None) = last year's change
# 'moist' is replaced by the global moisture metric (rain or wet) chosen by the rule below.
C = {
    "BR": dict(name="Brazil", my="Apr-Mar", m0=4, pts=("BR", "BRNE"),
               spec=[("moist", months((-1, 10), (0, 3))), ("rain", months((-1, 4), (-1, 9))), ("ylag", None)],
               pool=[("moist", months((-1, 10), (0, 3))), ("rain", months((-1, 4), (-1, 9))), ("frost", months((-1, 6), (-1, 8))),
                     ("heat", months((-1, 10), (0, 3))), ("oni", months((-1, 10), (0, 3))), ("moist", months((-2, 10), (-1, 3))), ("ylag", None)]),
    "IN": dict(name="India", my="Oct-Sep", m0=10, pts=("IN",),
               spec=[("moist", months((0, 6), (0, 9))), ("moist", months((-1, 6), (-1, 9))), ("ylag", None)]),
    "TH": dict(name="Thailand", my="Dec-Nov", m0=12, pts=("TH",),
               spec=[("moist", months((0, 5), (0, 10))), ("moist", months((-1, 5), (-1, 10))), ("ylag", None)]),
    "CH": dict(name="China", my="Oct-Sep", m0=10, pts=("CH",),
               spec=[("moist", months((0, 4), (0, 9))), ("frost", months((-1, 12), (0, 2))), ("ylag", None)]),
    "MX": dict(name="Mexico", my="Oct-Sep", m0=10, pts=("MX",),
               spec=[("moist", months((0, 6), (0, 10))), ("moist", months((-1, 6), (-1, 10))), ("ylag", None)]),
    "AS": dict(name="Australia", my="Jul-Jun", m0=7, pts=("AS",),
               spec=[("moist", months((-1, 12), (0, 3))), ("rain", months((-1, 6), (-1, 11))), ("ylag", None)]),
    "PK": dict(name="Pakistan", my="Oct-Sep", m0=10, pts=("PK",),
               spec=[("moist", months((0, 7), (0, 9))), ("heat", months((0, 5), (0, 6))), ("ylag", None)]),
    "GT": dict(name="Guatemala", my="Oct-Sep", m0=10, pts=("GT",),
               spec=[("moist", months((0, 5), (0, 10))), ("moist", months((-1, 5), (-1, 10))), ("ylag", None)]),
    "CO": dict(name="Colombia", my="Oct-Sep", m0=10, pts=("CO",),
               spec=[("moist", months((-1, 10), (0, 9))), ("oni", months((-1, 10), (0, 9))), ("ylag", None)]),
    "SF": dict(name="South Africa", my="May-Apr", m0=5, pts=("SF",),
               spec=[("moist", months((-1, 10), (0, 3))), ("moist", months((-2, 10), (-1, 3))), ("ylag", None)]),
    "RP": dict(name="Philippines", my="Dec-Nov", m0=12, pts=("RP",),
               spec=[("moist", months((0, 6), (0, 11))), ("moist", months((-1, 6), (-1, 11))), ("ylag", None)]),
    "ID": dict(name="Indonesia", my="May-Apr", m0=5, pts=("ID",),
               spec=[("moist", months((-1, 11), (0, 4))), ("moist", months((-2, 11), (-1, 4))), ("ylag", None)]),
    "AR": dict(name="Argentina", my="May-Apr", m0=5, pts=("AR",),
               spec=[("moist", months((-1, 11), (0, 3))), ("frost", months((-1, 6), (-1, 8))), ("ylag", None)]),
    "US": dict(name="United States (cane)", my="Oct-Sep", m0=10, pts=("US",),
               spec=[("moist", months((0, 4), (0, 9))), ("frost", months((-1, 12), (0, 2))), ("ylag", None)]),
    "EG": dict(name="Egypt (cane)", my="Oct-Sep", m0=10, pts=("EG",),
               spec=[("heat", months((0, 4), (0, 9))), ("ylag", None)]),
}
# a generic selection pool for the check variant (main window, its lag, frost, heat, ONI, persistence)
for cc, c in C.items():
    if "pool" not in c:
        main = next(w for k, w in c["spec"] if k in ("moist", "heat"))
        c["pool"] = [("moist", main), ("moist", shift(main, -1)), ("heat", main), ("oni", main),
                     ("frost", months((-1, 12), (0, 2)) if c["m0"] >= 10 else months((-1, 6), (-1, 8))), ("ylag", None)]
    c["early"] = [f for f in c["spec"] if f[0] == "ylag" or (f[1] and max(f[1])[0] <= -1)] + [("oni_aso", None)]
    # pre-window outlook: lag terms already observed + ONI Aug-Oct of t-1 (as of late in the year before the MY)


# ---- inputs ---------------------------------------------------------------------------------------------------------
def die(msg):
    print(f"cane_country: {msg}", file=sys.stderr)
    sys.exit(2)


def load():
    for p in (D / "psd_full.csv", D / "meta.json", D / "oni.csv"):
        if not p.exists():
            die(f"missing input {p.relative_to(ROOT)}")
    psd = pd.read_csv(D / "psd_full.csv")
    psd = psd[psd.Attribute_Description == "Cane Sugar Production"]
    P = psd.pivot_table(index="Market_Year", columns="Country_Code", values="Value", aggfunc="sum")
    pts = json.load(open(D / "meta.json"))["points"]
    oni = pd.read_csv(D / "oni.csv")
    # centre month of each 3-month season (DJF of year Y = Dec(Y-1)..Feb(Y), centred on Jan Y; NDJ centred on Dec Y)
    oni["m"] = oni.season.map({s: i + 1 for i, s in enumerate(SEASONS)})
    if oni.m.isna().any():
        die("unexpected ONI season labels")
    oni["date"] = [pd.Timestamp(int(y), int(m), 1) for y, m in zip(oni.year, oni.m)]
    oni = oni.set_index("date").anom.sort_index()
    mon, last = {}, None
    for pid, (cc, lab, lat, lon, w) in pts.items():
        f = D / "wx" / f"{pid}.csv.gz"
        if not f.exists():
            die(f"missing weather file {f.relative_to(ROOT)}")
        d = pd.read_csv(f, parse_dates=["date"]).set_index("date").sort_index()
        if d.empty or d[["rain", "tmax", "tmin", "gwr"]].isna().all().any():
            die(f"empty weather file {f.name}")
        last = d.index.max() if last is None else min(last, d.index.max())
        g = d.resample("MS")
        mon[pid] = pd.DataFrame({"rain": g.rain.mean(), "wet": g.gwr.mean(), "heat": g.tmax.apply(lambda s: (s > 35).mean()),
                                 "frost": g.tmin.apply(lambda s: (s <= 2).mean()), "n": g.rain.count()})
    for cc, c in C.items():
        if cc not in P.columns:
            die(f"PSD has no cane sugar series for {cc}")
        if not any(v[0] in c["pts"] for v in pts.values()):
            die(f"no weather points for {cc}")
    return P, pts, oni, mon, last


def country_monthly(cc, pts, mon):
    """Weighted mean of point monthly stats (daily means / fractions of days). Brazil = 0.9 Centre-South + 0.1 N-NE."""
    grp = C[cc]["pts"]
    share = {"BR": 0.9, "BRNE": 0.1} if cc == "BR" else {grp[0]: 1.0}
    acc, wt = None, 0.0
    for pid, (pc, lab, lat, lon, w) in pts.items():
        if pc not in grp:
            continue
        tot = sum(v[4] for v in pts.values() if v[0] == pc)
        ww = share[pc] * w / tot
        x = mon[pid][["rain", "wet", "heat", "frost"]] * ww
        acc = x if acc is None else acc.add(x, fill_value=0)
        wt += ww
        n = mon[pid]["n"]          # all points share the same date range
    acc = acc / wt
    acc["n"] = n
    return acc


def window_value(M, oni, kind, w, t, last):
    """Mean daily rate over the window for MY t, with the share of the window's days observed."""
    rows, days, obs = [], 0, 0
    if kind == "ylag":
        return np.nan, 1.0
    for o, m in w:
        ts = pd.Timestamp(t + o, m, 1)
        nd = ts.days_in_month
        days += nd
        if kind == "oni":
            if ts in oni.index:
                rows.append((oni[ts], nd)); obs += nd
            continue
        if ts in M.index and M.at[ts, "n"] > 0:
            rows.append((M.at[ts, kind], M.at[ts, "n"])); obs += M.at[ts, "n"]
    if not rows:
        return np.nan, 0.0
    v = sum(a * b for a, b in rows) / sum(b for a, b in rows)
    if kind in ("heat", "frost"):
        v *= days                  # share of days -> days in the window
    return v, obs / days


def build(cc, P, pts, oni, mon, last, moist):
    """Feature frame for years FIRST..2027 with observed-share columns, plus targets."""
    c = C[cc]
    M = country_monthly(cc, pts, mon)
    feats = {f for f in c["spec"] + c["pool"] + c["early"]}
    years = list(range(FIRST - 1, 2028))
    X, OBS = {}, {}
    for kind, w in feats:
        if kind == "ylag":
            continue
        key = name(kind, w, moist)
        vals, ob = [], []
        for t in years:
            if kind == "oni_aso":
                ts = pd.Timestamp(t - 1, 9, 1)
                v, o = (oni.get(ts, np.nan), 1.0 if ts in oni.index else 0.0)
            else:
                v, o = window_value(M, oni, moist if kind == "moist" else kind, w, t, last)
            vals.append(v if o >= OBS_MIN else np.nan); ob.append(o)
        s = pd.Series(vals, index=years, dtype=float)
        k = moist if kind == "moist" else kind
        if k == "rain":
            s = 100 * (s / s.loc[CLIM[0]:CLIM[1]].mean() - 1)    # % departure from the 1991-2020 normal
        elif k == "wet":
            s = 100 * (s - s.loc[CLIM[0]:CLIM[1]].mean())         # root-zone wetness anomaly, percentage points
        X[key], OBS[key] = s, pd.Series(ob, index=years)
    F = derive(pd.DataFrame(X), P[cc].reindex(range(1960, 2028)), years)
    return F, OBS


def derive(F, p, years):
    """Targets from a production series: yoy change, yoy minus trailing 15-yr drift, and causal trend deviation."""
    F = F.copy()
    lp = np.log(p.where(p > 0))
    y = lp.diff()
    F["y"] = y.reindex(years)
    F["ylag"] = y.shift(1).reindex(years)
    F["P"] = p.reindex(years)
    F["Plag"] = p.shift(1).reindex(years)
    F["drift"] = y.rolling(15, min_periods=8).mean().shift(1).reindex(years)
    F["yd"] = F["y"] - F["drift"]
    T, dev_lag = [], []
    for t in years:                                   # Theil-Sen trend on the 15 years before t
        hist = lp.loc[t - 15:t - 1].dropna()
        if len(hist) < 8:
            T.append(np.nan); dev_lag.append(np.nan); continue
        xs, vs = hist.index.values.astype(float), hist.values
        sl = np.median([(vs[j] - vs[i]) / (xs[j] - xs[i]) for i in range(len(xs)) for j in range(i + 1, len(xs))])
        ic = np.median(vs - sl * xs)
        T.append(ic + sl * t); dev_lag.append(lp.get(t - 1, np.nan) - (ic + sl * (t - 1)))
    F["trend"] = T
    F["dev"] = lp.reindex(years).values - F["trend"]
    F["devlag"] = dev_lag
    return F


TARGETS = {"yoy": "y", "yoyd": "yd", "trend": "dev"}


def level(target, r, yh):
    """Implied production level from a target-scale prediction (r = row with Plag, drift, trend)."""
    if target == "yoy":
        return r["Plag"] * np.exp(yh)
    if target == "yoyd":
        return r["Plag"] * np.exp(r["drift"] + yh)
    return np.exp(r["trend"] + yh)


def name(kind, w, moist="rain"):
    if kind == "ylag":
        return "ylag"
    if kind == "oni_aso":
        return "oni_ASO(t-1)"
    k = moist if kind == "moist" else kind
    return f"{k}_{wlabel(w)}"


PLAIN = {"rain": "rainfall", "wet": "root-zone soil moisture", "frost": "frost days", "heat": "heat days (>35°C)", "oni": "ENSO (ONI)"}


def plain(kind, w, moist):
    if kind == "ylag":
        return "previous season's crop change (ratoon / area persistence)"
    if kind == "oni_aso":
        return "ENSO (ONI, Aug-Oct of the year before)"
    yr = {0: "", -1: " previous year", -2: " two years before"}
    (o1, m1), (o2, m2) = w[0], w[-1]
    span = f"{MON[m1 - 1]}-{MON[m2 - 1]}{yr[o1]}" if o1 == o2 else f"{MON[m1 - 1]}{yr[o1]}-{MON[m2 - 1]}{yr[o2]}"
    k = moist if kind == "moist" else kind
    return f"{PLAIN[k]}, {span}"


# ---- regression and evaluation --------------------------------------------------------------------------------------
def ols(X, y):
    A = np.column_stack([np.ones(len(X)), X])
    b = np.linalg.lstsq(A, y, rcond=None)[0]
    return b


def pred(b, X):
    return np.column_stack([np.ones(len(X)), X]) @ b


def r2(y, yh, bench):
    y, yh, bench = map(np.asarray, (y, yh, bench))
    sst = np.sum((y - bench) ** 2)
    return float(1 - np.sum((y - yh) ** 2) / sst) if sst > 0 else float("nan")


def cols_for(spec, moist, target):
    out = []
    for k, w in spec:
        n = name(k, w, moist)
        out.append(("devlag" if target == "trend" else "ylag") if n == "ylag" else n)
    return out


def evaluate(F, cols, target, select_pool=None):
    tcol = TARGETS[target]
    D_ = F.loc[FIRST:LAST, list(dict.fromkeys(cols + [tcol, "P", "Plag", "trend", "drift"]))].dropna()
    yrs = D_.index.values
    X, y = D_[cols].values, D_[tcol].values
    b = ols(X, y)
    ins = r2(y, pred(b, X), np.full(len(y), y.mean()))
    # leave-one-year-out
    loo = np.array([pred(ols(np.delete(X, i, 0), np.delete(y, i)), X[i:i + 1])[0] for i in range(len(y))])
    r_loo = r2(y, loo, np.full(len(y), y.mean()))
    # expanding window
    rec = []
    for i, t in enumerate(yrs):
        if t < TEST0 or i < MIN_TRAIN:
            continue
        Xtr, ytr = X[:i], y[:i]
        use = list(range(len(cols)))
        if select_pool:
            use = select(Xtr, ytr)
        bt = ols(Xtr[:, use], ytr)
        yh = pred(bt, X[i:i + 1, use])[0]
        r = D_.iloc[i]
        Ph = level(target, r, yh)
        rec.append(dict(year=int(t), y=float(y[i]), yhat=float(yh), bench=float(ytr.mean()), P=float(r.P), Plag=float(r.Plag), Phat=float(Ph),
                        used=[cols[u] for u in use]))
    R = pd.DataFrame(rec)
    # yoy-equivalent OOS (comparable across targets): log(Phat/Plag) vs log(P/Plag), benchmark = train-mean drift
    yy = np.log(R.P / R.Plag); yyh = np.log(R.Phat / R.Plag)
    drift = [float(np.nanmean(np.log(F.P / F.Plag).loc[FIRST:t - 1])) for t in R.year]
    # intercept-only (expanding mean drift) benchmark on the level, to show what the weather terms add
    Pd = R.Plag * np.exp(R.bench) if target == "yoy" else None
    out = dict(n=int(len(y)), years=f"{int(yrs[0])}-{int(yrs[-1])}", in_sample_r2=ins, loo_r2=r_loo,
               level_oos_r2_drift_only=r2(R.P, Pd, R.Plag) if Pd is not None else None,
               oos_r2=r2(R.y, R.yhat, R.bench), oos_yoy_r2=r2(yy, yyh, drift),
               level_oos_r2_vs_naive=r2(R.P, R.Phat, R.Plag), n_test=int(len(R)),
               coef=dict(zip(["const"] + cols, map(float, b))), records=R)
    return out


def select(X, y, kmax=3):
    """Best subset of <= kmax columns by leave-one-out MSE on the training rows only (nested, honest)."""
    best, bset = np.inf, [len(X[0]) - 1]
    for k in range(1, kmax + 1):
        for s in combinations(range(X.shape[1]), k):
            Xs = X[:, s]
            e = [y[i] - pred(ols(np.delete(Xs, i, 0), np.delete(y, i)), Xs[i:i + 1])[0] for i in range(len(y))]
            m = np.mean(np.square(e))
            if m < best:
                best, bset = m, list(s)
    return bset


def forecast(F, cols, target, t, yhat_prev=None):
    tcol = TARGETS[target]
    D_ = F.loc[FIRST:LAST, list(dict.fromkeys(cols + [tcol, "trend", "drift"]))].dropna()
    b = ols(D_[cols].values, D_[tcol].values)
    x = F.loc[t, cols]
    if x.isna().any() or pd.isna(F.at[t, "Plag"]):
        return None, None
    yh = float(pred(b, x.values.reshape(1, -1).astype(float))[0])
    return float(level(target, F.loc[t], yh)), yh


def analogs(F, oni):
    """Crop change in strong El Nino onset years (ONI Aug-Oct >= 1.4) and in the crop year after them."""
    aso = {d.year: v for d, v in oni.items() if d.month == 9}
    onset = [yr for yr, v in aso.items() if v >= 1.4 and FIRST <= yr <= LAST - 1]
    y = F["y"]
    avg = float(y.loc[FIRST:LAST].mean())
    return dict(onset_years=onset, mean_change_all=avg,
                onset_crop={str(t): float(y.get(t)) for t in onset}, next_crop={str(t + 1): float(y.get(t + 1)) for t in onset},
                mean_onset=float(np.mean([y.get(t) for t in onset])), mean_next=float(np.mean([y.get(t + 1) for t in onset])))


def my_label(cc, t):
    c = C[cc]
    return f"{t}/{str(t + 1)[2:]} ({c['my']})" if c["m0"] > 1 else str(t)


# ---- main -----------------------------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab", help="also write full backtest statistics to this path (keep outside the repo)")
    a = ap.parse_args()
    P, pts, oni, mon, last = load()

    # global choices, same rule for every country: target (yoy change vs trend deviation) and moisture metric
    # (window rain vs root-zone wetness), picked by the median expanding-window level skill vs no-change.
    target, moist = TARGET, MOIST
    frames, grid = {}, {}
    for mo in (("rain", "wet") if a.lab else (moist,)):
        for cc in C:
            frames[(cc, mo)] = build(cc, P, pts, oni, mon, last, mo)
        if a.lab:
            for tg in TARGETS:
                sk = [evaluate(frames[(cc, mo)][0], cols_for(C[cc]["spec"], mo, tg), tg)["level_oos_r2_vs_naive"] for cc in C]
                grid[(tg, mo)] = float(np.median(sk))

    res, fc = {}, {}
    lab = {"choice": {"target": target, "moisture": moist, "grid_median_level_oos_r2": {f"{k[0]}/{k[1]}": v for k, v in grid.items()},
                      "grid_best": "/".join(max(grid, key=grid.get)) if grid else None}}
    for cc, c in C.items():
        F, OBS = frames[(cc, moist)]
        cols = cols_for(c["spec"], moist, target)
        ev = evaluate(F, cols, target)
        ecols = cols_for(c["early"], moist, target)
        if a.lab:                                 # checks: nested feature selection, pre-window outlook
            pool = list(dict.fromkeys(cols_for(c["pool"], moist, target)))
            sel = evaluate(F, pool, target, select_pool=True)
            ear = evaluate(F, ecols, target)
        # alternative moisture metric and target, as checks
        alt = {}
        for (tg, mo) in grid:
            Fx = frames[(cc, mo)][0]
            e = evaluate(Fx, cols_for(c["spec"], mo, tg), tg)
            alt[f"{tg}/{mo}"] = {k: e[k] for k in ("oos_r2", "oos_yoy_r2", "loo_r2", "level_oos_r2_vs_naive")}
        res[cc] = ev
        # forecasts
        p25, p26 = float(P.at[2025, cc]), float(P.at[2026, cc]) if 2026 in P.index else None
        m26, y26 = forecast(F, cols, target, 2026)
        m27 = o27 = y27 = ye = None
        if m26 is not None:                       # 2027 chains off the model's own 2026 crop, not USDA's
            p2 = P[cc].reindex(range(1960, 2028)).astype(float).copy()
            p2.loc[2026] = m26
            F27 = derive(F.drop(columns=["y", "ylag", "P", "Plag", "drift", "yd", "trend", "dev", "devlag"]), p2, list(F.index))
            m27, y27 = forecast(F27, cols, target, 2027)
            o27, ye = forecast(F27, ecols, target, 2027)
        obs27 = {k: round(float(OBS[k].get(2027, 0)), 2) for k in OBS if k in cols}
        fc[cc] = dict(name=c["name"], my_label_2026=my_label(cc, 2026), my_label_2027=my_label(cc, 2027),
                      usda_2025=round(p25), usda_2026=round(p26) if p26 is not None else None,
                      usda_2026_vs_2025_pct=round(100 * (p26 / p25 - 1), 1) if p26 else None,
                      model_2026=round(m26) if m26 is not None else None,
                      model_2026_vs_2025_pct=round(100 * (m26 / p25 - 1), 1) if m26 is not None else None,
                      change_vs_usda_pct=round(100 * (m26 / p26 - 1), 1) if (m26 is not None and p26) else None,
                      model_2027=round(m27) if m27 is not None else None,
                      variables_used=[plain(k, w, moist) for k, w in c["spec"]],
                      as_of=str(last.date()))
        if not a.lab:
            continue
        lab[cc] = dict(name=c["name"], my=c["my"], spec=cols, stats={k: v for k, v in ev.items() if k != "records"},
                       per_year=ev["records"].round(4).to_dict("records"),
                       selection_check={k: v for k, v in sel.items() if k not in ("records", "coef")} | {"picked": sel["records"].used.astype(str).value_counts().head(3).to_dict()},
                       early_outlook=dict(spec=ecols, **{k: v for k, v in ear.items() if k != "records"}),
                       alternatives=alt, enso_analogs=analogs(F, oni),
                       forecast=fc[cc] | {"outlook_2027_early": round(o27) if o27 is not None else None, "yhat_2026": y26, "yhat_2027": y27, "yhat_2027_early": ye, "obs_share_2027": obs27})

    # world (sum of modelled countries): expanding-window yoy skill
    R = pd.concat([res[cc]["records"].set_index("year")[["P", "Plag", "Phat"]].add_prefix(cc + "_") for cc in C], axis=1).dropna()
    Pw, Plw, Phw = (sum(R[f"{cc}_{s}"] for cc in C) for s in ("P", "Plag", "Phat"))
    yw, ywh = np.log(Pw / Plw), np.log(Phw / Plw)
    tot = sum(P[cc] for cc in C)
    drift = [float(np.log(tot / tot.shift(1)).loc[FIRST:t - 1].mean()) for t in R.index]
    share = {cc: float(P.loc[2015:2025, cc].mean()) for cc in C}
    wavg = sum(share[cc] * res[cc]["oos_r2"] for cc in C) / sum(share.values())
    world = dict(years=f"{R.index.min()}-{R.index.max()}", oos_yoy_r2_vs_drift=r2(yw, ywh, drift), oos_yoy_r2_vs_nochange=r2(yw, ywh, np.zeros(len(yw))),
                 level_oos_r2_vs_naive=r2(Pw, Phw, Plw), production_weighted_country_oos_r2=float(wavg),
                 per_year=pd.DataFrame({"y": yw, "yhat": ywh}).round(4).reset_index().rename(columns={"index": "year"}).to_dict("records"))
    lab["world"] = world
    s26 = [cc for cc in C if fc[cc]["model_2026"] is not None]
    fc_world = dict(usda_2025=round(sum(fc[cc]["usda_2025"] for cc in s26)), usda_2026=round(sum(fc[cc]["usda_2026"] for cc in s26)),
                    model_2026=round(sum(fc[cc]["model_2026"] for cc in s26)), countries=s26)
    fc_world["change_vs_usda_pct"] = round(100 * (fc_world["model_2026"] / fc_world["usda_2026"] - 1), 1)

    out = dict(built=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), units="1000 MT raw value, cane sugar",
               as_of=str(last.date()), countries=fc, total_modelled=fc_world)
    out["use"] = "Weather overlay to read against USDA, not a standalone production forecast."
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"wrote {OUT.relative_to(ROOT)}")
    if a.lab:
        lp = Path(a.lab).resolve()
        if ROOT in lp.parents:
            die("--lab path must be outside the repo")
        lp.parent.mkdir(parents=True, exist_ok=True)
        lab["built"] = out["built"]
        lp.write_text(json.dumps(lab, indent=1, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
        print(f"wrote {lp}")


if __name__ == "__main__":
    main()
