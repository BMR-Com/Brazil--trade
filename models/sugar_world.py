"""Public-data sugar panels for the Sugar tab: Brazil cane weather and harvest stoppage, Centre-South fortnight scorecard
and season range, India, Europe, expiry deliveries, agency revisions and Brazil fuel policy.

Inputs (all in the repo):
  sugar/data/mapa_fortnight.csv, sugar/data/sugar.json, sugar/data/prices_contracts.csv, sugar/data/prices_cont.csv (sugar workflow)
  data/geo/weather_hist/<id>.csv.gz and recent/ (geo_weather), data/sugar/wx/* (pipelines/sugar_wx.py), data/geo/wx_ensemble.json
  data/markets/closes.csv (Yahoo FX), data/sugar/manual/*.csv (hand-entered from dated public releases, with URLs)
Writes data/sugar/world.json. Only results go to the page; the rain-to-stoppage rule lives here.
"""
import json, math
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
GEO = ROOT / "data" / "geo" / "weather_hist"
WX = ROOT / "data" / "sugar" / "wx"
MAN = ROOT / "data" / "sugar" / "manual"
OUT = ROOT / "data" / "sugar" / "world.json"
LB_T = 22.0462
ATR = {"sugar": 1.0495, "anh": 1.7651, "hyd": 1.6913}

STATES = {"SP": ["br_sp", "br_spw", "su_pi"], "GO": ["br_gos"], "MG": ["br_mgc"], "MS": ["br_ms"], "PR": ["br_prs"]}
STATE_NAME = {"SP": "São Paulo", "GO": "Goiás", "MG": "Minas Gerais (Triângulo)", "MS": "Mato Grosso do Sul", "PR": "Paraná"}
# Harvest-stoppage rule (rainfall only). Chosen by fitting fortnightly MAPA crush by state (2014-2025, May-Oct) on rain-day counts
# for a grid of thresholds; this one fit as well as the best while using a conventional threshold.
WET, HEAVY, HEAVY2 = 5.0, 10.0, 20.0   # mm: stop on a day >= WET; the day after >= HEAVY; two days after >= HEAVY2
BEET_IDS = ["eu_fr_b", "su_fr_ce", "su_de_ns", "su_de_ma", "su_pl_ku", "su_nl_fl", "su_be_ti", "su_cz_ha"]


def rd(x, n=1):
    if x is None:
        return None
    try:
        if isinstance(x, (float, np.floating)) and (math.isnan(x) or math.isinf(x)):
            return None
        return round(float(x), n)
    except Exception:
        return None


def jl(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return None


# ---------------------------------------------------------------- weather series
def series(pid):
    parts = []
    for base in (GEO, WX / "hist"):
        p = base / f"{pid}.csv.gz"
        if p.exists():
            parts.append(pd.read_csv(p, index_col=0, parse_dates=True))
            break
    for base in (GEO / "recent", WX / "recent"):
        p = base / f"{pid}.csv.gz"
        if p.exists():
            parts.append(pd.read_csv(p, index_col=0, parse_dates=True))
            break
    if not parts:
        return None
    d = pd.concat(parts)
    d = d[~d.index.duplicated(keep="last")].sort_index()
    return d


def stop_days(rain):
    a = np.nan_to_num(np.asarray(rain, dtype=float))
    out = np.zeros(len(a))
    for i, x in enumerate(a):
        if x >= WET or (i > 0 and a[i - 1] >= HEAVY) or (i > 1 and a[i - 2] >= HEAVY2):
            out[i] = 1
    return out


def stop_series(rain):
    return pd.Series(stop_days(rain.values), index=rain.index)


def state_rain():
    st = {}
    for uf, ids in STATES.items():
        ss = [s["rain"] for s in (series(i) for i in ids) if s is not None]
        if ss:
            st[uf] = pd.concat(ss, axis=1).mean(axis=1)
    return st


def mapa():
    """MAPA fortnights by region/state. Region totals missing in MAPA's sheet are rebuilt from the states, and a
    Centre-South fortnight MAPA skipped (15 Nov 2022) is interpolated from its neighbours (column 'interp'), so that
    fortnight increments are never two fortnights booked as one."""
    import sys
    sys.path.insert(0, str(ROOT / "sugar" / "scripts"))
    import mapa as mp
    m = pd.read_csv(ROOT / "sugar/data/mapa_fortnight.csv", parse_dates=["start", "end"])
    m = mp.fill_totals(m)
    cs = mp.cs_clean(m)
    rest = m[~((m.region == "Centro-Sul") & (m.uf == "TOTAL"))].assign(interp=False)
    return pd.concat([rest, cs], ignore_index=True).sort_values(["end", "region", "uf"]).reset_index(drop=True)


def weights(m):
    cur = m.safra.max()
    last = m[(m.safra == cur) & (m.region == "Centro-Sul")]
    last = last[last.end == last.end.max()]
    w = {uf: float(last[last.uf == uf].cane_t.sum()) for uf in STATES}
    tot = sum(w.values())
    return {k: v / tot for k, v in w.items()}, str(last.end.max().date())


def same_dates(s, d0, d1, years):
    """Sum of s over the same calendar window (d0..d1, shifted whole years) in each past year."""
    out = {}
    for y in years:
        k = y - d1.year
        try:
            a, b = pd.Timestamp(d0.replace(year=d0.year + k)), pd.Timestamp(d1.replace(year=y))
        except ValueError:
            continue
        v = s.loc[a:b]
        if len(v) >= ((b - a).days + 1) * 0.9:
            out[y] = float(v.sum())
    return out


def stats(cur, hist, ly):
    arr = list(hist.values())
    if not arr:
        return {"now": rd(cur)}
    pct = 100 * (np.sum(np.array(arr) < cur) + 0.5 * np.sum(np.array(arr) == cur)) / len(arr)
    return {"now": rd(cur), "avg": rd(np.mean(arr)), "ly": rd(hist.get(ly)), "pct": rd(pct, 0), "vs_avg_pct": rd(100 * (cur / np.mean(arr) - 1), 0) if np.mean(arr) else None}


def cane_weather(m):
    w, wdate = weights(m)
    st = state_rain()
    if not st:
        return None
    asof = min(s.dropna().index.max() for s in st.values())
    st = {k: v.loc[:asof] for k, v in st.items()}
    cs = sum(st[k].reindex(st["SP"].index).fillna(0) * w[k] for k in st)
    years = list(range(2011, 2026))
    ly = asof.year - 1
    d1 = asof.date()
    mstart, astart = d1.replace(day=1), date(d1.year, 4, 1)
    rows = []
    for name, s in [(k, st[k]) for k in STATES if k in st] + [("CS", cs)]:
        sd = stop_series(s)
        r = {"id": name, "name": STATE_NAME.get(name, "Centre-South, weighted by cane crushed"), "weight": rd(100 * w.get(name, 1), 1) if name != "CS" else 100.0}
        for key, d0 in (("mtd", mstart), ("atd", astart)):
            cur = float(s.loc[pd.Timestamp(d0):pd.Timestamp(d1)].sum())
            r[f"rain_{key}"] = stats(cur, same_dates(s, d0, d1, years), ly)
            cur = float(sd.loc[pd.Timestamp(d0):pd.Timestamp(d1)].sum())
            r[f"stop_{key}"] = stats(cur, same_dates(sd, d0, d1, years), ly)
        rows.append(r)
    # forecast: per-member stoppage days from the ensembles (data/sugar/wx/ens_latest.json)
    ens = jl(WX / "ens_latest.json")
    fc = {"available": False}
    if ens and ens.get("points"):
        fc = {"available": True, "generated": ens["generated"], "models": {}}
        for model in ("ecmwf_ens", "gefs"):
            per_state = {}
            dates = None
            for uf, ids in STATES.items():
                mem = [ens["points"][i][model] for i in ids if i in ens["points"] and model in ens["points"][i]]
                if not mem:
                    continue
                dates = mem[0]["dates"]
                n = min(len(x["members"]) for x in mem)
                arr = np.nanmean(np.array([np.array(x["members"][:n], dtype=float) for x in mem]), axis=0)   # members x days
                per_state[uf] = arr
            if not per_state or dates is None:
                continue
            n = min(a.shape[0] for a in per_state.values())
            wsum = sum(w[k] for k in per_state)
            csm = sum(per_state[k][:n] * w[k] / wsum for k in per_state)
            fut = [d for d in dates if d > str(d1)]
            k0 = len(dates) - len(fut)
            pre = cs.loc[:asof].iloc[-2:].values    # last two observed days carry into day 1
            stops = [stop_days(np.r_[pre, mrow[k0:]])[2:].sum() for mrow in csm]
            rains = [np.nansum(mrow[k0:]) for mrow in csm]
            f0, f1 = pd.Timestamp(fut[0]), pd.Timestamp(fut[-1])
            norm_r = same_dates(cs, f0.date(), f1.date(), years)
            norm_s = same_dates(stop_series(cs), f0.date(), f1.date(), years)
            fc["models"][model] = {"from": fut[0], "to": fut[-1], "days": len(fut), "members": int(n),
                                   "rain_p10": rd(np.percentile(rains, 10)), "rain_p50": rd(np.percentile(rains, 50)), "rain_p90": rd(np.percentile(rains, 90)),
                                   "rain_normal": rd(np.mean(list(norm_r.values()))) if norm_r else None,
                                   "stop_p10": rd(np.percentile(stops, 10)), "stop_p50": rd(np.percentile(stops, 50)), "stop_p90": rd(np.percentile(stops, 90)),
                                   "stop_normal": rd(np.mean(list(norm_s.values()))) if norm_s else None}
        # run history for "change vs previous forecast"
        hp = WX / "ens_runs.jsonl"
        runs = [json.loads(x) for x in hp.read_text().splitlines() if x.strip()] if hp.exists() else []
        rec = {"generated": ens["generated"], "cs": {k: {kk: v[kk] for kk in ("from", "to", "rain_p50", "stop_p50")} for k, v in fc["models"].items()}}
        if not runs or runs[-1]["generated"] != rec["generated"]:
            runs.append(rec)
            hp.write_text("\n".join(json.dumps(r) for r in runs[-120:]) + "\n")
        prev = [r for r in runs if r["generated"] != ens["generated"]]
        if prev:
            fc["previous"] = prev[-1]
    else:   # fallback: rain only, from the desk's ensemble summary
        E = jl(ROOT / "data/geo/wx_ensemble.json") or {}
        R = E.get("regions", {})
        tot = n = 0.0
        normal = 0.0
        for uf, ids in STATES.items():
            vals = [R[i]["next15"]["ecmwf_ens"] for i in ids if i in R and "ecmwf_ens" in R[i].get("next15", {})]
            if vals:
                tot += w[uf] * np.mean([v["rain_p50"] for v in vals]); normal += w[uf] * np.mean([v["rain_normal"] for v in vals]); n += w[uf]
        if n:
            v0 = next(iter(R.values()))["next15"]["ecmwf_ens"]
            fc = {"available": False, "fallback": {"generated": E.get("generated"), "rain_p50": rd(tot / n), "rain_normal": rd(normal / n), "from": v0["from"], "to": v0["to"]}}
    # daily chart for the CS-weighted month: cumulative this month vs average and last year
    days = pd.date_range(pd.Timestamp(mstart), pd.Timestamp(d1))
    chart = {"days": [str(x.date()) for x in days], "cur": [rd(x) for x in cs.loc[days[0]:days[-1]].cumsum().tolist()]}
    acc = []
    for y in years:
        a = pd.Timestamp(mstart.replace(year=y)); b = pd.Timestamp(d1.replace(year=y))
        v = cs.loc[a:b]
        if len(v) == len(days):
            acc.append(v.cumsum().values)
    if acc:
        chart["avg"] = [rd(x) for x in np.mean(acc, axis=0)]
        chart["ly"] = [rd(x) for x in acc[-1]] if years[-1] == ly else None
    return {"asof": str(d1), "weights_from": f"MAPA cane crushed 1 Apr–{wdate}", "rows": rows, "forecast": fc, "chart": chart,
            "rule": "Estimated stoppage day: rain of 5 mm or more, the day after 10 mm or more, or the second day after 20 mm or more (daily ERA5 rain at one or more points per state).",
            "_cs": cs, "_years": years}


# ---------------------------------------------------------------- MAPA scorecard and range
def cs_table(m):
    t = m[(m.region == "Centro-Sul") & (m.uf == "TOTAL")].copy().sort_values("end")
    out = []
    for sf, g in t.groupby("safra"):
        g = g.sort_values("end")
        inc = g[["cane_t", "sugar_t", "ethanol_m3", "anh_prod", "hyd_prod"]].diff()
        inc.iloc[0] = g[["cane_t", "sugar_t", "ethanol_m3", "anh_prod", "hyd_prod"]].iloc[0]
        for (_, r), (_, i) in zip(g.iterrows(), inc.iterrows()):
            out.append({"safra": sf, "end": r.end, "cum_cane": r.cane_t, "cum_sugar": r.sugar_t, "cum_eth": r.ethanol_m3,
                        "cane": i.cane_t, "sugar": i.sugar_t, "eth": i.ethanol_m3, "anh": i.anh_prod, "hyd": i.hyd_prod})
    return pd.DataFrame(out)


def raw_mix(sugar, anh, hyd):
    s, e = sugar * ATR["sugar"], anh * ATR["anh"] + hyd * ATR["hyd"]
    return 100 * s / (s + e) if s + e > 0 else None


def scorecard(t, S):
    cur = t.safra.max()
    g = t[t.safra == cur].sort_values("end")
    last = g.iloc[-1]
    E = last.end
    def pick(y):
        x = t[(t.end == E.replace(year=E.year - y))]
        return x.iloc[0] if len(x) else None
    prev = [pick(y) for y in range(1, 6)]
    prev = [p for p in prev if p is not None]
    def blk(fn):
        now = fn(last); ly = fn(prev[0]) if prev else None
        av = np.mean([fn(p) for p in prev]) if prev else None
        return {"now": rd(now, 2), "ly": rd(ly, 2), "avg5": rd(av, 2)}
    fort = {
        "cane_mt": blk(lambda r: r.cane / 1e6), "sugar_mt": blk(lambda r: r.sugar / 1e6), "eth_bnl": blk(lambda r: r.eth / 1e6),
        "kgt": blk(lambda r: 1000 * r.sugar / r.cane if r.cane else None),
        "mix_raw": blk(lambda r: raw_mix(r.sugar, r.anh, r.hyd))}
    cum = {"cane_mt": blk(lambda r: r.cum_cane / 1e6), "sugar_mt": blk(lambda r: r.cum_sugar / 1e6), "eth_bnl": blk(lambda r: r.cum_eth / 1e6),
           "kgt": blk(lambda r: 1000 * r.cum_sugar / r.cum_cane)}
    mix = (S.get("unica") or {}).get("implied_mix") or []
    mx = next((x for x in mix if x["end"] == str(E.date())), None)
    U = S.get("unica") or {}
    uc = jl(ROOT / "data/sugar/unica_check.json") or {}
    return {"unica_last_published": uc.get("latest_position") or U.get("position"), "unica_checked": uc.get("checked"), "end": str(E.date()), "start": str((pd.Timestamp(E.year, E.month, 16) if E.day > 15 else pd.Timestamp(E.year, E.month, 1)).date()), "season": cur,
            "fortnight": fort, "cumulative": cum, "mix_corn_adjusted": mx["mix"] if mx else None,
            "seasons_in_avg": [p.safra for p in prev], "unica_position": U.get("position"),
            "note": "MAPA fortnightly data for all Centre-South mills. Ethanol includes corn ethanol; 'sugar share of ATR' uses all ethanol, so it understates the cane mix as corn ethanol grows; the desk's corn-adjusted mix is shown for this season only."}


def fit_beta(t, cs):
    """Share of a normal day's crush lost per estimated stoppage day: Centre-South fortnights May-Dec, 2014-2025,
    daily crush relative to that season's 90th-percentile fortnight."""
    sd = stop_series(cs)
    xs, ys = [], []
    for sf, g in t.groupby("safra"):
        g = g.sort_values("end")
        g = g.assign(days=(g.end - g.end.shift(1)).dt.days.fillna(15))
        g = g[(g.end.dt.month >= 5) & (g.end.dt.month <= 12) & (g.end <= cs.index.max())]
        if len(g) < 10:
            continue
        cap = (g.cane / g.days).quantile(0.9)
        for r in g.itertuples():
            a = r.end - pd.Timedelta(days=int(r.days) - 1)
            xs.append(float(sd.loc[a:r.end].sum()) / r.days); ys.append(r.cane / r.days / cap)
    if len(xs) < 50:
        return 0.75
    return float(np.clip(-np.polyfit(xs, ys, 1)[0], 0.3, 1.0))


def fortnights_after(E):
    out, d = [], E
    while True:
        a = d + pd.Timedelta(days=1)
        b = pd.Timestamp(a.year, a.month, 15) if a.day == 1 else (a + pd.offsets.MonthEnd(0))
        out.append((a, b))
        d = b
        if b.month == 3 and b.day == 31:
            return out


def season_range(t, W, S):
    cs, years = W["_cs"], W["_years"]
    asof = pd.Timestamp(W["asof"])
    cur = t.safra.max()
    g = t[t.safra == cur].sort_values("end")
    E = g.end.max()
    last = g.iloc[-1]
    sd = stop_series(cs)
    beta = fit_beta(t, cs)
    fns = fortnights_after(E)
    # pace path: each later fortnight's crush relative to the fortnight ending on E's date, median of past seasons
    paths, kgr = [], []
    for sf, h in t.groupby("safra"):
        if sf == cur:
            continue
        k = int(cur[:4]) - int(sf[:4])
        h = h.set_index("end")
        e = E.replace(year=E.year - k)
        if e not in h.index:
            continue
        base = h.loc[e, "cane"]
        row = []
        for (a, b) in fns:
            bb = b.replace(year=b.year - k) if not (b.month == 2 and b.day == 29) else b
            row.append(h.loc[bb, "cane"] / base if bb in h.index else np.nan)
        if not np.isnan(row).all():
            paths.append(row)
        fin = h[(h.index > e) & (h.index.month <= 3)]
        rest = h[h.index > e]
        if len(rest) and rest.cane.sum() > 0:
            kgr.append((rest.sugar.sum() / rest.cane.sum()) / (h.loc[e, "sugar"] / base))
    P = np.nanmedian(np.array(paths, dtype=float), axis=0)
    P = np.nan_to_num(P)
    fcm = (W["forecast"].get("models") or {}).get("ecmwf_ens") or (W["forecast"].get("models") or {}).get("gefs")
    f_from = pd.Timestamp(fcm["from"]) if fcm else None
    f_to = pd.Timestamp(fcm["to"]) if fcm else asof
    kgt_now = last.sugar / last.cane * 1000
    kr = float(np.median(kgr)) if kgr else 0.85
    cases = {}
    for name, fq, cq in (("dry", "stop_p10", 20), ("base", "stop_p50", 50), ("wet", "stop_p90", 80)):
        tot_rem = 0.0; jm = 0.0; sdays = 0.0; per = []
        for (a, b), p in zip(fns, P):
            days = (b - a).days + 1
            norm = np.mean(list(same_dates(sd, a.date(), b.date(), years).values()) or [0])
            # this fortnight's stoppage days: observed part + forecast part + climatology for the rest
            o_end = min(b, asof)
            obs = float(sd.loc[a:o_end].sum()) if a <= asof else 0.0
            f_part = 0.0
            if fcm and b >= f_from and a <= f_to:
                lo, hi = max(a, f_from), min(b, f_to)
                share = ((hi - lo).days + 1) / fcm["days"]
                f_part = fcm[fq] * share
            c0 = max(a, (f_to if fcm else asof) + pd.Timedelta(days=1))
            clim = 0.0
            if c0 <= b:
                vals = list(same_dates(sd, c0.date(), b.date(), years).values()) or [0]
                clim = float(np.percentile(vals, cq)) if b <= pd.Timestamp(E.year, 12, 31) else float(np.mean(vals))
            sdj = obs + f_part + clim
            sdays += sdj if b <= pd.Timestamp(E.year, 12, 31) else 0
            cane = last.cane * p * max(0.0, 1 - beta * (sdj - norm) / days)
            tot_rem += cane
            if a.year > E.year:
                jm += cane
            per.append({"to": str(b.date()), "cane_mt": rd(cane / 1e6, 2), "stop_days": rd(sdj), "normal_stop_days": rd(norm)})
        rem = tot_rem / 1e6
        kg = kgt_now * kr
        cases[name] = {"stop_days_to_dec31": rd(sdays), "remaining_cane_mt": rd(rem), "season_cane_mt": rd(last.cum_cane / 1e6 + rem),
                       "remaining_sugar_mt": rd(rem * kg / 1000, 2), "season_sugar_mt": rd(last.cum_sugar / 1e6 + rem * kg / 1000, 2),
                       "jan_mar_cane_mt": rd(jm / 1e6), "fortnights": per[:6]}
    grid_k = [round(kgt_now * kr * f, 1) for f in (0.75, 0.85, 0.95, 1.0, 1.1)]
    grid = [{"case": c, "remaining_cane_mt": cases[c]["remaining_cane_mt"],
             "season_sugar": [rd(last.cum_sugar / 1e6 + cases[c]["remaining_cane_mt"] * k / 1000, 2) for k in grid_k]} for c in ("wet", "base", "dry")]
    Pj = (S.get("crush") or {}).get("projection") or {}
    m = mapa()
    prevs = sorted(m.safra.unique())[-2]
    lp = m[(m.safra == prevs)]
    lp = lp[lp.end == lp.end.max()]
    cs_share = float(lp[(lp.region == "Centro-Sul") & (lp.uf == "TOTAL")].cane_t.sum() / lp[lp.uf == "TOTAL"].cane_t.sum())
    rev = pd.read_csv(MAN / "agency_revisions.csv")
    conab = rev[rev.agency == "Conab"].iloc[0] if (rev.agency == "Conab").any() else None
    checks = {"desk_pace_projection_cane": (Pj.get("cane") or {}).get("mid"), "desk_pace_projection_sugar": (Pj.get("sugar") or {}).get("mid"),
              "cs_share_of_brazil_cane": rd(100 * cs_share, 1), "cs_share_season": prevs}
    if conab is not None:
        checks.update({"conab_brazil_cane": float(conab.value), "conab_date": conab.release_date, "conab_cs_implied": rd(float(conab.value) * cs_share), "conab_url": conab.url})
    return {"from_fortnight": str(E.date()), "so_far": {"cane_mt": rd(last.cum_cane / 1e6), "sugar_mt": rd(last.cum_sugar / 1e6, 2)},
            "last_fortnight": {"cane_mt": rd(last.cane / 1e6, 2), "kgt": rd(kgt_now), "kgt_remaining": rd(kgt_now * kr)},
            "observed_to": W["asof"], "forecast_model": ("ECMWF ENS" if (W["forecast"].get("models") or {}).get("ecmwf_ens") else "GEFS") if fcm else None,
            "cases": cases, "grid_kgt": grid_k, "grid": grid, "checks": checks, "n_seasons": len(paths),
            "assumptions": ["Each fortnight to 31 March: last fortnight's crush × the median path of past seasons from the same date (MAPA, 2014/15 on).",
                            "Adjusted by rain: estimated stoppage days in that fortnight above or below the 2011–2025 normal for the same dates reduce or add to the crush, at the rate seen in past fortnights.",
                            "Stoppage days: observed to the latest ERA5 day, then the ensemble forecast (10th / 50th / 90th percentile member for dry / base / wet), then 2011–2025 climatology to 31 December (20th / 50th / 80th percentile); January–March at normal.",
                            "Sugar per tonne of the remaining cane = last fortnight's kg/t × the median ratio of later-season to same-fortnight kg/t in past seasons (mix and ATR both fall late in the season).",
                            "Mills' end dates follow past seasons; if more mills stop early than usual the outcome falls below the wet case."]}


# ---------------------------------------------------------------- prices and FX
def settle(sym, d):
    p = pd.read_csv(ROOT / "sugar/data/prices_contracts.csv")
    p = p[(p.symbol == sym)]
    p = p[p.date <= str(d)].sort_values("date")
    return (float(p.close.iloc[-1]), p.date.iloc[-1]) if len(p) else (None, None)


def fx(col, d):
    c = pd.read_csv(ROOT / "data/markets/closes.csv", index_col=0, parse_dates=True)
    s = c[col].dropna()
    s = s[s.index <= pd.Timestamp(d)]
    return (float(s.iloc[-1]), str(s.index[-1].date())) if len(s) else (None, None)


def last_friday(today=None):
    t = today or date.today()
    return t - timedelta(days=(t.weekday() - 4) % 7)


def india(fri):
    rows = pd.read_csv(MAN / "india.csv", dtype=str).fillna("")
    sb, sbd = settle("SBH2027", fri)
    wh, whd = settle("WH2027", fri)
    inr, inrd = fx("INR=X", fri)
    duty = next((float(r.value) for _, r in rows.iterrows() if r["item"].startswith("Normal import duty")), None)
    price = [r for _, r in rows.iterrows() if r.kind == "price"]
    par = {"date": str(fri), "inputs": {"sb_mar27_c_lb": sb, "sb_date": sbd, "w_mar27_usd_t": wh, "w_date": whd, "usd_inr": rd(inr, 3), "inr_date": inrd, "duty_full_pct": duty}}
    if sb and inr:
        raw_t = sb * LB_T
        par["raw_trq_rs_qtl"] = rd(raw_t * inr / 10, 0)
        par["raw_usd_t"] = rd(raw_t, 1)
    if wh and inr:
        par["white_zero_duty_rs_qtl"] = rd(wh * inr / 10, 0)
        if duty is not None:
            par["white_full_duty_rs_qtl"] = rd(wh * inr * (1 + duty / 100) / 10, 0)
    prices = None
    pp = ROOT / "data/sugar/india_prices.csv"
    if pp.exists():
        q = pd.read_csv(pp)
        q = q[q.date <= str(fri)]
        if len(q):
            last = q.date.max()
            lq = q[q.date == last]
            prices = {"date": last, "url": lq.url.iloc[0], "source": "ChiniMandi daily sugar market update (Vizzie), ex-mill excl. GST",
                      "latest": lq[["state", "grade", "lo", "hi"]].to_dict("records"),
                      "series": {f"{st} {g}": {"dates": list(h.date), "mid": [rd((a + b) / 2, 0) for a, b in zip(h.lo, h.hi)]}
                                 for (st, g), h in q[q.date >= str(pd.Timestamp(fri) - pd.Timedelta(days=90))].groupby(["state", "grade"])
                                 if (st, g) in (("Maharashtra", "S/30"), ("Uttar Pradesh", "M/30"))}}
            mh = lq[(lq.state == "Maharashtra") & (lq.grade == "S/30")]
            if len(mh):
                par["domestic"] = {"item": "Ex-mill price Maharashtra S/30", "value": float(mh.lo.iloc[0]), "date": last, "url": mh.url.iloc[0], "source": "ChiniMandi"}
    st = jl(ROOT / "data/sugar/india_prices_status.json")
    if "domestic" not in par and price:
        p = price[0]
        par["domestic"] = {"item": p["item"], "value": float(p["value"]), "date": p["date"], "url": p["url"], "source": p["source"] + " (manual fallback)"}
    par["note"] = ("All parities are ex-freight and ex-port/handling (no public freight series); the raw parity is also before refining cost. "
                   "Raws under the duty-free TRQ (to 31 Mar 2027) must be refined and sold in India.")
    crush = None
    try:
        import india_crush
        crush = india_crush.build(par)
        crush["collector"] = jl(ROOT / "data/sugar/india_crush_status.json")
    except Exception as e:                      # the rest of the India panel still builds
        print("india crush tracker failed:", repr(e))
    return {"releases": rows.to_dict("records"), "parity": par, "prices": prices, "collector": st, "history": india_history(), "crush": crush}


def india_history():
    """Indian ex-mill prices (ChiniMandi, Rs/quintal excl. GST) in US cents per lb next to ICE No. 11 and London No. 5
    front months, every date the collector has a quote for. ¢/lb = Rs/qtl ÷ INR per USD ÷ 220.462 lb × 100."""
    pp = ROOT / "data/sugar/india_prices.csv"
    if not pp.exists():
        return None
    q = pd.read_csv(pp)
    if q.empty:
        return None
    q["mid"] = (q.lo + q.hi) / 2
    keys = {"mh_s30": ("Maharashtra", "S/30"), "up_m30": ("Uttar Pradesh", "M/30")}
    piv = {k: q[(q.state == st) & (q.grade == g)].groupby("date").mid.mean() for k, (st, g) in keys.items()}
    D = pd.DataFrame(piv)
    D.index = pd.to_datetime(D.index)
    D = D.sort_index()
    # USD/INR: Yahoo INR=X, daily since 2016 (india workflow) and the desk's closes file
    fx = []
    for f, col in ((ROOT / "data/india/raw/fx_ct.csv", "INR=X"), (ROOT / "data/markets/closes.csv", "INR=X")):
        if f.exists():
            c = pd.read_csv(f, index_col=0, parse_dates=True)
            if col in c:
                fx.append(c[col].dropna())
    if not fx:
        return None
    inr = pd.concat(fx).groupby(level=0).last().sort_index()
    inr = inr[(inr > 40) & (inr < 200)]
    pc = pd.read_csv(ROOT / "sugar/data/prices_cont.csv", parse_dates=["date"])
    sb = pc[pc.symbol == "ICEUS:SB1!"].set_index("date").close.sort_index()
    wh = pc[pc.symbol == "ICEEUR:W1!"].set_index("date").close.sort_index()
    asof = lambda s, d: (float(s.loc[:d].iloc[-1]), str(s.loc[:d].index[-1].date())) if len(s.loc[:d]) and (d - s.loc[:d].index[-1]).days <= 7 else (None, None)
    out = []
    for d, r in D.iterrows():
        x, xd = asof(inr, d)
        if not x:
            continue
        s11, _ = asof(sb, d)
        w5, _ = asof(wh, d)
        c = lambda v: rd(v / x / 220.462 * 100, 2) if v == v and v is not None else None
        rec = {"date": str(d.date()), "inr": rd(x, 2), "mh_rs": rd(r.mh_s30, 0) if r.mh_s30 == r.mh_s30 else None, "up_rs": rd(r.up_m30, 0) if r.up_m30 == r.up_m30 else None,
               "mh_c": c(r.mh_s30), "up_c": c(r.up_m30), "sb_c": rd(s11, 2), "w5_c": rd(w5 / LB_T, 2) if w5 else None, "w5_usd_t": rd(w5, 1)}
        rec["gap_w5"] = rd(rec["mh_c"] - rec["w5_c"], 2) if rec["mh_c"] is not None and rec["w5_c"] is not None else None
        rec["gap_sb"] = rd(rec["mh_c"] - rec["sb_c"], 2) if rec["mh_c"] is not None and rec["sb_c"] is not None else None
        out.append(rec)
    if not out:
        return None
    # one row a week (last quote of each week) for the table
    wk = pd.DataFrame(out)
    wk["w"] = pd.to_datetime(wk.date).dt.to_period("W-FRI")
    weekly = wk.groupby("w").tail(1).drop(columns="w").to_dict("records")
    return {"rows": out, "weekly": weekly, "first": out[0]["date"], "last": out[-1]["date"], "n": len(out),
            "sources": "ChiniMandi daily sugar market update (ex-mill, excl. GST); USD/INR Yahoo INR=X; ICE No. 11 and London No. 5 front month (TradingView continuous)"}


def europe(fri):
    out = {}
    rows = []
    years = list(range(2011, 2026))
    for pid in BEET_IDS:
        s = series(pid)
        if s is None:
            continue
        s = s.loc[:pd.Timestamp(fri)]
        lastd = s.dropna(subset=["rain"]).index.max()
        r = {"id": pid}
        def mon(y, col, how):
            v = s.loc[f"{y}-10-01":f"{y}-10-31", col].dropna()
            if len(v) < 28:
                return None
            return float(v.sum() if how == "sum" else v.mean())
        for col, how in (("rain", "sum"), ("sm100", "mean"), ("sm7", "mean")):
            if col not in s:
                continue
            vals = {y: mon(y, col, how) for y in range(2011, 2027)}
            r[col] = {"oct_2026": rd(vals.get(2026), 3 if col != "rain" else 0), "oct_2025": rd(vals.get(2025), 3 if col != "rain" else 0),
                      "avg_2021_25": rd(np.mean([vals[y] for y in range(2021, 2026) if vals.get(y) is not None]), 3 if col != "rain" else 0) if any(vals.get(y) is not None for y in range(2021, 2026)) else None,
                      "avg_2011_25": rd(np.mean([vals[y] for y in years if vals.get(y) is not None]), 3 if col != "rain" else 0) if any(vals.get(y) is not None for y in years) else None}
        # last 30 days rain vs same dates
        e = lastd
        cur = float(s.loc[e - pd.Timedelta(days=29):e, "rain"].sum())
        hh = [float(s.loc[e.replace(year=y) - pd.Timedelta(days=29):e.replace(year=y), "rain"].sum()) for y in years if e.replace(year=y) <= s.index.max()]
        r["rain30"] = {"now": rd(cur, 0), "avg_2011_25": rd(np.mean(hh), 0) if hh else None, "to": str(e.date())}
        rows.append(r)
    meta = jl(WX / "meta.json") or {}
    names = {"eu_fr_b": "Picardie / Hauts-de-France (Amiens)", **(meta.get("beet") or {})}
    for r in rows:
        r["name"] = names.get(r["id"], r["id"])
    out["beet_weather"] = rows
    # EU price (EC price reporting) vs London No. 5 in euros for the same month
    ep = pd.read_csv(MAN / "eu_price.csv") if (MAN / "eu_price.csv").exists() else None
    if ep is not None and len(ep):
        pc = pd.read_csv(ROOT / "sugar/data/prices_cont.csv")
        pc = pc[pc.symbol == "ICEEUR:W1!"]; pc["date"] = pd.to_datetime(pc.date)
        c = pd.read_csv(ROOT / "data/markets/closes.csv", index_col=0, parse_dates=True)["EURUSD=X"].dropna()
        lst = []
        for _, r in ep.iterrows():
            mth = str(r.month)
            w = pc[pc.date.dt.strftime("%Y-%m") == mth].close
            e = c[c.index.strftime("%Y-%m") == mth]
            n5 = float(w.mean() / e.mean()) if len(w) and len(e) else None
            lst.append({"month": mth, "eu_avg": r.eu_avg, "r1": r.r1, "r2": r.r2, "r3": r.r3, "no5_eur": rd(n5, 0),
                        "premium_eur": rd(r.eu_avg - n5, 0) if n5 else None, "source": r.source, "url": r.url, "released": r.released})
        out["prices"] = lst
    rev = pd.read_csv(MAN / "agency_revisions.csv").fillna("")
    out["ec"] = [r for r in rev.to_dict("records") if r["agency"] == "European Commission"]
    return out


def csv_records(name):
    p = MAN / name
    return pd.read_csv(p, dtype=str).fillna("").to_dict("records") if p.exists() else []


def fuel_sensitivity(S):
    now = (S.get("parity") or {}).get("now") or {}
    fxv = now.get("fx")
    if not fxv:
        return None
    per_real = 1000 * ATR["sugar"] / ATR["hyd"] / fxv / LB_T / (1 + 0.0405)    # ¢/lb per R$1/litre of hydrous at the mill
    return {"fx": fxv, "date": now.get("date"), "c_lb_per_real_litre": rd(per_real, 2), "subsidy_r_l": 0.428, "subsidy_c_lb": rd(per_real * 0.428, 2),
            "parity_now": now.get("parity"), "sb_now": now.get("sb"),
            "note": "Sugar-equivalent value of R$1 per litre of hydrous ethanol at the mill, at today's real (same formula as the parity chart)."}


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, list):
        return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if math.isnan(o) or math.isinf(o) else round(float(o), 4)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, pd.Timestamp):
        return str(o.date())
    return o


def main():
    S = jl(ROOT / "sugar/data/sugar.json") or {}
    m = mapa()
    t = cs_table(m)
    fri = last_friday()
    W = cane_weather(m)
    res = {"built": str(date.today()), "week_ending": str(fri), "cane_weather": W, "scorecard": scorecard(t, S)}
    if W:
        res["range"] = season_range(t, W, S)
    res["india"] = india(fri)
    res["europe"] = europe(fri)
    res["deliveries"] = csv_records("deliveries.csv")
    res["revisions"] = csv_records("agency_revisions.csv")
    res["fuel_policy"] = csv_records("fuel_policy.csv")
    res["fuel_sensitivity"] = fuel_sensitivity(S)
    OUT.write_text(json.dumps(clean(res), ensure_ascii=False, separators=(",", ":")))
    print("wrote", OUT, OUT.stat().st_size)


if __name__ == "__main__":
    main()
