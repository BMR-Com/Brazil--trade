"""Brazil Centre-South cane model: half-monthly crush, sugar kg/t, ATR and sugar mix, plus the season outlook.

Inputs (all public, already collected by the desk):
  sugar/data/mapa_fortnight.csv            MAPA fortnightly cumulative cane, sugar, ethanol by state (2018/19 on)
  sugar/data/sugar.json -> parity          daily No.11 front and hydrous-ethanol export parity (¢/lb), 2012 on
  sugar/data/unica_reports.csv             UNICA reports (cane-only ATR and mix; corn ethanol)
  data/geo/weather_hist + recent, data/sugar/wx   daily ERA5 rain by cane state (models/sugar_world.py helpers)
  data/sugar/wx/ens_latest.json            ECMWF/GEFS ensemble rain (next 15 days)
  data/sugar/cane_model/{psd_full,oni}.csv, wx/  long history (pipelines/cane_model_data.py)

Writes data/sugar/cane_model/brazil_forecast.json with final outputs and the variables used only.
`python models/cane_model.py --lab PATH` also writes the backtests, coefficients and per-fortnight fits to PATH
(keep it outside the repo: the method belongs in the private Lab, not on the public site).
Exits non-zero when an input is missing or a backtest cannot be run.
"""
import argparse, json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "models"))
import sugar_world as W  # noqa: E402  (state rain series, stoppage rule)

OUT = ROOT / "data/sugar/cane_model/brazil_forecast.json"
ATR = {"sugar": 1.0495, "anh": 1.7651, "hyd": 1.6913, "eth_avg": 1.72}
# Corn ethanol in the Centre-South by season (bn litres, Apr-Mar). UNICA season totals as reported in the press for
# 2018/19-2021/22 and 2024/25 (to mid-Dec); 2022/23-2023/24 interpolated; 2025/26-2026/27 backed out of UNICA's
# accumulated cane-only mix against MAPA totals (Apr-Aug). Spread evenly by day. Used only to strip corn ethanol
# out of MAPA's ethanol so the mix and ATR are cane-only.
CORN_BNL = {"2018/2019": 0.79, "2019/2020": 1.6, "2020/2021": 2.58, "2021/2022": 3.45, "2022/2023": 4.4,
            "2023/2024": 6.3, "2024/2025": 8.2, "2025/2026": 9.8, "2026/2027": 10.6}
MIN_FN, MAX_FN = 3, 18          # crush model fitted May 1H .. Dec 2H (start/finish fortnights are mill decisions)
Q_FN = (3, 16)                  # mix / kg/t / ATR models fitted May 1H .. Nov 2H
CATCHUP = (0.3, 0.5, 0.7)       # share of crush lost to excess stoppage days in Sep-Oct recovered in Nov-Mar


def die(msg):
    print("cane_model:", msg, file=sys.stderr)
    sys.exit(2)


def r2(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def rd(x, n=2):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), n)


# ---------------------------------------------------------------- data
def fortnight_bounds(e):
    a = pd.Timestamp(e.year, e.month, 1) if e.day <= 15 else pd.Timestamp(e.year, e.month, 16)
    return a, e


def season_of(d):
    y = d.year if d.month >= 4 else d.year - 1
    return f"{y}/{y + 1}"


def fn_of(e):
    """Fortnight number in the Apr-Mar season: Apr 1H = 1 ... Mar 2H = 24."""
    k = (e.month - 4) % 12
    return 2 * k + (1 if e.day <= 15 else 2)


def load():
    for p in ["sugar/data/mapa_fortnight.csv", "sugar/data/sugar.json", "data/sugar/wx/ens_latest.json"]:
        if not (ROOT / p).exists():
            die(f"missing input {p}")
    m = W.mapa()
    rain = W.state_rain()
    if not rain:
        die("no state rain series")
    stops = {k: W.stop_series(v) for k, v in rain.items()}
    S = json.loads((ROOT / "sugar/data/sugar.json").read_text())["parity"]
    par = pd.DataFrame({"sb": S["sb"], "par": S["par"]}, index=pd.to_datetime(S["dates"]))
    par["prem"] = par.sb - par.par
    return m, rain, stops, par


def state_weights(m, safra):
    cs = m[(m.region == "Centro-Sul") & (m.uf != "TOTAL") & (m.safra == safra)]
    last = cs[cs.end == cs.end.max()]
    w = {uf: float(last[last.uf == uf].cane_t.sum()) for uf in W.STATES}
    t = sum(w.values()) or 1.0
    return {k: v / t for k, v in w.items()}


def wx_window(rain, stops, w, a, b):
    sd = sum(w[k] * stops[k].loc[a:b].sum() for k in stops if k in w)
    rn = sum(w[k] * rain[k].loc[a:b].sum() for k in rain if k in w)
    return float(sd), float(rn)


def frame(m, rain, stops, par):
    tot = m[(m.region == "Centro-Sul") & (m.uf == "TOTAL")]
    rows = []
    for sf, g in tot.groupby("safra"):
        g = g.sort_values("end")
        if len(g) < 10:
            continue
        w = state_weights(m, sf)
        v = g[["cane_t", "sugar_t", "anh_prod", "hyd_prod"]].values
        inc = np.vstack([v[0], np.diff(v, axis=0)])
        for i, e in enumerate(g.end):
            a, b = fortnight_bounds(e)
            if i > 0 and g.end.iloc[i - 1] < a - pd.Timedelta(days=1):   # a missing fortnight: spread over the gap
                a = g.end.iloc[i - 1] + pd.Timedelta(days=1)
            days = (b - a).days + 1
            sd, rn = wx_window(rain, stops, w, a, b)
            cane, sug, anh, hyd = inc[i]
            corn = CORN_BNL.get(sf, np.nan) * 1e6 * days / 365
            s_atr = sug * ATR["sugar"]
            e_atr = anh * ATR["anh"] + hyd * ATR["hyd"] - corn * ATR["eth_avg"]
            rows.append(dict(safra=sf, fn=fn_of(e), end=e, days=days, cane=cane, sugar=sug, sd=sd, rain=rn,
                             sfrac=sd / days, prem=par.prem.loc[a:b].mean(),
                             prem_l=par.prem.loc[a - pd.Timedelta(days=30):a - pd.Timedelta(days=1)].mean(),
                             kgt=1000 * sug / cane if cane > 0 else np.nan,
                             mix=100 * s_atr / (s_atr + e_atr) if cane > 0 else np.nan,
                             atr=1000 * (s_atr + e_atr) / cane if cane > 0 else np.nan))
    F = pd.DataFrame(rows)
    F["lr"] = np.log(F.cane.clip(lower=1) / F.days)
    return F


# ---------------------------------------------------------------- crush model
def crush_design(d, cols=None):
    X = pd.get_dummies(d.fn.astype(int).astype(str), prefix="f").astype(float)
    X["sfrac"] = d.sfrac.values
    return X if cols is None else X.reindex(columns=cols, fill_value=0.0)


def fit_crush(F):
    tr = F[(F.fn >= MIN_FN) & (F.fn <= MAX_FN)]
    X = crush_design(tr)
    co, *_ = np.linalg.lstsq(X.values, tr.lr.values, rcond=None)
    return pd.Series(co, X.columns)


def predict_crush(co, fn, sfrac, days):
    return float(np.exp(co.get(f"f_{fn}", np.nan) + co["sfrac"] * sfrac) * days)


def backtest_crush(F):
    full = [s for s in F.safra.unique() if F[F.safra == s].fn.max() >= MAX_FN]
    Y, P, B, rows = [], [], [], []
    for s in full:
        tr = F[F.safra != s]
        co = fit_crush(tr)
        prof = tr[(tr.fn >= MIN_FN) & (tr.fn <= MAX_FN)].groupby("fn").cane.mean()
        te = F[(F.safra == s) & (F.fn >= MIN_FN) & (F.fn <= MAX_FN)]
        for r in te.itertuples():
            p = predict_crush(co, r.fn, r.sfrac, r.days)
            Y.append(r.cane); P.append(p); B.append(prof.get(r.fn, np.nan) * r.days / 15.0)
            rows.append([s, int(r.fn), str(r.end.date()), round(r.cane / 1e6, 2), round(p / 1e6, 2), round(r.sd, 1)])
    Y, P, B = map(np.array, (Y, P, B))
    return {"seasons": full, "n": len(Y), "r2_crush": rd(r2(Y, P), 3), "r2_profile_only": rd(r2(Y, B), 3),
            "r2_of_deviation_from_profile": rd(r2(Y - B, P - B), 3), "mae_mt": rd(np.mean(np.abs(Y - P)) / 1e6, 2),
            "rows": rows}


# ---------------------------------------------------------------- quality models (mix, kg/t, ATR)
QFEATS = {"mix": ["prem_l", "rain"], "kgt": ["prem_l", "rain"], "atr": ["rain"]}


def q_fit(tr, tgt, feats):
    X = pd.get_dummies(tr.fn.astype(int).astype(str), prefix="f").astype(float)
    X = X.join(pd.get_dummies(tr.safra, prefix="s", drop_first=True).astype(float))
    for c in feats:
        X[c] = tr[c].values
    co, *_ = np.linalg.lstsq(X.values, tr[tgt].values, rcond=None)
    co = pd.Series(co, X.columns)
    co["_season_mean"] = np.mean([0.0] + [v for k, v in co.items() if k.startswith("s_")])
    return co


def q_base(co, fn, row, feats):
    return co.get(f"f_{fn}", np.nan) + sum(co[c] * row[c] for c in feats)


def q_level(co, resid):
    """Real-time season level: the season-to-date average residual, shrunk toward the average season by one fortnight."""
    se = co["_season_mean"]
    return se if not resid else (np.sum(resid) + se) / (len(resid) + 1)


def backtest_quality(F, tgt, feats):
    Q = F[(F.fn >= Q_FN[0]) & (F.fn <= Q_FN[1])].dropna(subset=[tgt] + feats)
    Y, P, P0 = [], [], []
    for s in sorted(Q.safra.unique()):
        tr, te = Q[Q.safra != s], Q[Q.safra == s].sort_values("fn")
        co, co0 = q_fit(tr, tgt, feats), q_fit(tr, tgt, [])
        res, res0 = [], []
        for _, r in te.iterrows():
            b, b0 = q_base(co, int(r.fn), r, feats), q_base(co0, int(r.fn), r, [])
            if r.fn >= 5:
                Y.append(r[tgt]); P.append(b + q_level(co, res)); P0.append(b0 + q_level(co0, res0))
            res.append(r[tgt] - b); res0.append(r[tgt] - b0)
    co = q_fit(Q, tgt, feats)
    return {"n": len(Y), "r2": rd(r2(Y, P), 3), "r2_without_weather_price": rd(r2(Y, P0), 3),
            "mae": rd(np.mean(np.abs(np.array(Y) - np.array(P))), 2), "coef": {c: rd(co[c], 3) for c in feats}}, co


# ---------------------------------------------------------------- current season
def ens_stop_days(rain, w, asof, d0, d1):
    """Ensemble-median Centre-South stoppage days for forecast days in [d0, d1] (after asof)."""
    ens = json.loads((ROOT / "data/sugar/wx/ens_latest.json").read_text())
    vals = []
    for model in ("ecmwf_ens", "gefs"):
        per = {}
        dates = None
        for uf, ids in W.STATES.items():
            mem = [ens["points"][i][model] for i in ids if i in ens.get("points", {}) and model in ens["points"][i]]
            if not mem:
                continue
            dates = mem[0]["dates"]
            n = min(len(x["members"]) for x in mem)
            per[uf] = np.nanmean(np.array([np.array(x["members"][:n], float) for x in mem]), axis=0)
        if not per:
            continue
        n = min(a.shape[0] for a in per.values())
        ws = sum(w.get(k, 0) for k in per) or 1
        csm = sum(per[k][:n] * w.get(k, 0) / ws for k in per)
        idx = [i for i, d in enumerate(dates) if asof < pd.Timestamp(d) <= d1 and pd.Timestamp(d) >= d0]
        if not idx:
            continue
        pre = [0.0, 0.0]
        for row in csm:
            vals.append(W.stop_days(np.r_[pre, row[idx]])[2:].sum())
        last_fc = pd.Timestamp(dates[idx[-1]])
    if not vals:
        return None, None
    return float(np.median(vals)), last_fc


def clim_stop_days(rain, stops, w, a, b, years):
    out = []
    for y in years:
        k = y - b.year
        try:
            aa, bb = a.replace(year=a.year + k), b.replace(year=b.year + k)
        except ValueError:
            continue
        sd, _ = wx_window(rain, stops, w, aa, bb)
        out.append(sd)
    return float(np.mean(out)) if out else 0.0


def next_fortnights(e, until_fn=24):
    out, d = [], e
    while True:
        a = d + pd.Timedelta(days=1)
        b = pd.Timestamp(a.year, a.month, 15) if a.day == 1 else a + pd.offsets.MonthEnd(0)
        if fn_of(b) == 1 or fn_of(b) > until_fn:
            break
        out.append((a, b))
        d = b
        if fn_of(b) == 24:
            break
    return out


def current_season(F, m, rain, stops, par, co_crush, qco):
    cur = F.safra.max()
    g = F[F.safra == cur].sort_values("fn")
    last = g.iloc[-1]
    w = state_weights(m, cur)
    years = list(range(2011, int(cur[:4])))
    asof = min(s.index.max() for s in rain.values())
    prof_all = F[F.safra != cur].groupby("fn").cane.mean()
    # excess-stoppage crush lost in Sep-Oct (fortnights 11-14): model crush at normal stoppage minus model at actual
    lost = 0.0
    for r in g[(g.fn >= 11) & (g.fn <= 14)].itertuples():
        a, b = fortnight_bounds(r.end)
        norm = clim_stop_days(rain, stops, w, a, b, years) / r.days
        lost += predict_crush(co_crush, r.fn, norm, r.days) - predict_crush(co_crush, r.fn, r.sfrac, r.days)
    # quality residuals so far this season (real-time level)
    resid = {t: [] for t in qco}
    for _, r in g[(g.fn >= Q_FN[0]) & (g.fn <= Q_FN[1])].iterrows():
        for t, (co, feats) in qco.items():
            if np.isfinite(r[t]):
                resid[t].append(r[t] - q_base(co, int(r.fn), r, feats))
    prem_now = float(par.prem.loc[par.index.max() - pd.Timedelta(days=29):].mean())
    out = []
    for a, b in next_fortnights(last.end):
        fn, days = fn_of(b), (b - a).days + 1
        obs_end = min(asof, b)
        sd_obs = wx_window(rain, stops, w, a, obs_end)[0] if obs_end >= a else 0.0
        src = "observed" if obs_end >= b else ("observed + forecast" if obs_end >= a else "forecast")
        sd_rest = 0.0
        if obs_end < b:
            fc, fc_end = ens_stop_days(rain, w, asof, max(a, asof + pd.Timedelta(days=1)), b)
            fc_end = fc_end if fc is not None else asof
            sd_rest = (fc or 0.0) + clim_stop_days(rain, stops, w, max(a, fc_end + pd.Timedelta(days=1)), b, years)
            if fc is None and src != "observed":
                src = src.replace("forecast", "normal")
        sd = sd_obs + sd_rest
        rn_obs = wx_window(rain, stops, w, a, obs_end)[1] if obs_end >= a else 0.0
        if fn <= MAX_FN:
            cane = predict_crush(co_crush, fn, sd / days, days)
        else:   # Jan-Mar: off-season average (crush there is mill choice, not weather)
            cane = float(prof_all.get(fn, 0.0)) * days / 15.0
        row = {"start": str(a.date()), "end": str(b.date()), "fn": fn, "weather": src,
               "stop_days": rd(sd, 1), "cane_mt": cane / 1e6}
        prem_l = float(par.prem.loc[a - pd.Timedelta(days=30):a - pd.Timedelta(days=1)].mean()) if a - pd.Timedelta(days=1) <= par.index.max() else prem_now
        if not np.isfinite(prem_l):
            prem_l = prem_now
        x = {"prem_l": prem_l, "rain": rn_obs if src == "observed" else rn_obs + 3.0 * sd_rest}
        for t, (co, feats) in qco.items():
            if fn <= Q_FN[1]:
                row[t] = rd(q_base(co, fn, x, feats) + q_level(co, resid[t]), 1)
            else:   # Dec-Mar: few mills run; use the last three seasons' cane-weighted value for that fortnight
                last3 = sorted(F.safra[F.safra != cur].unique())[-3:]
                pool = F[(F.fn == fn) if fn <= 18 else (F.fn >= 19)]
                h = pool[pool.safra.isin(last3) & (pool.cane > 1e5)]
                h = h[np.isfinite(h[t]) & (h[t] > 0) & (h[t] < 200)]
                row[t] = rd(np.average(h[t], weights=h.cane), 1) if len(h) else None
        row["sugar_mt"] = row["cane_mt"] * (row["kgt"] or 0) / 1000
        out.append(row)
    # Nov-Mar total: model fortnights + catch-up of cane left standing by the wet Sep-Oct
    base_tail = sum(r["cane_mt"] for r in out)
    kg_tail = np.average([r["kgt"] for r in out], weights=[r["cane_mt"] for r in out]) if base_tail else 0
    to_date = {"cane_mt": g.cane.sum() / 1e6, "sugar_mt": g.sugar.sum() / 1e6}
    scen = {}
    for k in CATCHUP:
        cane_tail = base_tail + k * lost / 1e6
        sug_tail = sum(r["sugar_mt"] for r in out) + k * lost / 1e6 * kg_tail / 1000
        scen[f"catchup_{int(k * 100)}"] = {"cane_mt": rd(to_date["cane_mt"] + cane_tail, 1),
                                           "sugar_mt": rd(to_date["sugar_mt"] + sug_tail, 2)}
    for r in out:
        r["cane_mt"], r["sugar_mt"] = rd(r["cane_mt"], 2), rd(r["sugar_mt"], 3)
    ly = F[F.safra == F.safra[F.safra != cur].max()]
    return {"season": cur, "mapa_last": str(last.end.date()), "weather_to": str(asof.date()),
            "to_date": {k: rd(v, 2) for k, v in to_date.items()},
            "to_date_last_year_same_date": {"cane_mt": rd(ly[ly.fn <= last.fn].cane.sum() / 1e6, 2),
                                            "sugar_mt": rd(ly[ly.fn <= last.fn].sugar.sum() / 1e6, 2)},
            "last_year_final": {"cane_mt": rd(ly.cane.sum() / 1e6, 1), "sugar_mt": rd(ly.sugar.sum() / 1e6, 2)},
            "sepoct_crush_lost_to_rain_mt": rd(lost / 1e6, 1), "sugar_premium_30d_c_lb": rd(prem_now, 2),
            "fortnights": out, "season_total": scen}


# ---------------------------------------------------------------- 2027/28 outlook (ENSO analogs, long history)
def outlook_next(F):
    """Analog read for next season from the long PSD and CS weather history (1981 on)."""
    base = ROOT / "data/sugar/cane_model"
    if not (base / "psd_full.csv").exists() or not (base / "oni.csv").exists():
        return None, None
    psd = pd.read_csv(base / "psd_full.csv")
    br = psd[(psd.Country_Code == "BR") & (psd.Attribute_Description == "Cane Sugar Production")].set_index("Market_Year").Value
    oni = pd.read_csv(base / "oni.csv")
    oni["anom"] = pd.to_numeric(oni.anom, errors="coerce")
    son = oni[oni.season == "SON"].set_index("year").anom
    aso = oni[oni.season == "ASO"].set_index("year").anom
    now = float(son.iloc[-1]) if son.index.max() == aso.index.max() else float(aso.iloc[-1])
    meta = json.loads((base / "meta.json").read_text())
    pts = {k: v for k, v in meta["points"].items() if v[0] == "BR"}
    rain = []
    for k, v in pts.items():
        p = base / "wx" / f"{k}.csv.gz"
        if p.exists():
            rain.append(pd.read_csv(p, index_col=0, parse_dates=True).rain * v[4])
    R = pd.concat(rain, axis=1).sum(axis=1) / sum(v[4] for k, v in pts.items() if (base / "wx" / f"{k}.csv.gz").exists())
    om = {}
    for y in range(1982, int(R.index.max().year) + 1):
        om[y] = R.loc[f"{y - 1}-10-01":f"{y}-03-31"].sum()
    om = pd.Series(om)
    norm = om.loc[1991:2020].mean()
    chg = np.log(br / br.shift(1)) * 100
    yrs = [y for y in son.index if y + 1 in chg.index and y + 1 <= 2025 and y >= 1981]
    strong = [y for y in yrs if son.get(y, np.nan) >= 1.0]
    lab = {"oni_now": rd(now, 2), "analog_years_el_nino_son_ge_1": strong,
           "br_sugar_chg_after_el_nino_pct": rd(chg.loc[[y + 1 for y in strong]].mean(), 1),
           "br_sugar_chg_all_years_pct": rd(chg.loc[[y + 1 for y in yrs]].mean(), 1),
           "cs_octmar_rain_el_nino_pct_normal": rd(100 * om.loc[[y + 1 for y in strong if y + 1 in om.index]].mean() / norm, 0),
           "cs_octmar_rain_others_pct_normal": rd(100 * om.loc[[y + 1 for y in yrs if y not in strong and y + 1 in om.index]].mean() / norm, 0)}
    corr = np.corrcoef(om.loc[[y for y in om.index if y in chg.index and y <= 2025]],
                       chg.loc[[y for y in om.index if y in chg.index and y <= 2025]])[0, 1]
    lab["corr_octmar_rain_vs_br_sugar_chg"] = rd(corr, 2)
    nxt = int(R.index.max().year) + (1 if R.index.max().month >= 4 else 0)
    obs = R.loc[f"{nxt - 1}-10-01":].sum()
    lab["octmar_observed_so_far_mm"] = rd(obs, 0)
    lab["octmar_normal_to_same_date_mm"] = rd(np.mean([R.loc[f"{y - 1}-10-01":f"{y - 1}-{R.index.max():%m-%d}"].sum() for y in range(1992, 2021)]), 0)
    pub = {"oni_latest": rd(now, 2), "el_nino_analogs": len(strong),
           "cs_rain_since_1_oct_pct_normal": rd(100 * obs / lab["octmar_normal_to_same_date_mm"], 0) if lab["octmar_normal_to_same_date_mm"] else None}
    return pub, lab


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab", default="")
    a = ap.parse_args()
    m, rain, stops, par = load()
    F = frame(m, rain, stops, par)
    if F.safra.nunique() < 6:
        die("too few MAPA seasons")
    bt_crush = backtest_crush(F)
    co_crush = fit_crush(F)
    qstats, qco = {}, {}
    for t, feats in QFEATS.items():
        qstats[t], co = backtest_quality(F, t, feats)
        qco[t] = (co, feats)
    cur = current_season(F, m, rain, stops, par, co_crush, qco)
    pub_next, lab_next = outlook_next(F)
    unica = pd.read_csv(ROOT / "sugar/data/unica_reports.csv") if (ROOT / "sugar/data/unica_reports.csv").exists() else None
    ulast = str(unica.position.max()) if unica is not None else None
    out = {
        "built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "region": "Brazil Centre-South",
        "unica_last_position": ulast,
        "current_season": cur,
        "next_season_signals": pub_next,
        "variables_used": ["MAPA fortnightly cane, sugar and ethanol by state", "daily rain by cane state (ERA5)",
                           "estimated harvest-stoppage days", "ECMWF and GEFS ensemble rain forecast",
                           "No. 11 front vs hydrous-ethanol export parity", "corn ethanol (UNICA)",
                           "ONI (NOAA)", "USDA PSD sugar history", "NASA POWER rain 1981 on"],
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print("crush R2", bt_crush["r2_crush"], "| mix", qstats["mix"]["r2"], "| kg/t", qstats["kgt"]["r2"], "| ATR", qstats["atr"]["r2"])
    for r in cur["fortnights"][:4]:
        print(r)
    print(cur["season_total"])
    if a.lab:
        lab = {"built": out["built"],
               "skill": {"crush_fortnight_r2": bt_crush["r2_crush"], "mix_fortnight_r2": qstats["mix"]["r2"],
                         "kgt_fortnight_r2": qstats["kgt"]["r2"], "atr_fortnight_r2": qstats["atr"]["r2"],
                         "seasons_tested": len(bt_crush["seasons"])},
               "crush": {k: v for k, v in bt_crush.items()},
               "crush_coef": {"stoppage_fraction": rd(co_crush["sfrac"], 3),
                              "profile_log_rate": {k: rd(v, 3) for k, v in co_crush.items() if k.startswith("f_")}},
               "quality": qstats, "corn_bnl_assumed": CORN_BNL, "next_season": lab_next,
               "frame": F.assign(end=F.end.astype(str)).round(3).to_dict(orient="records")}
        Path(a.lab).write_text(json.dumps(lab, indent=1, default=float))
        print("lab ->", a.lab)


if __name__ == "__main__":
    main()
