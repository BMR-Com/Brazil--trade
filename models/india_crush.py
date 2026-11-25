"""India crush tracker, season projection and import need (Sugar > India detail).

Inputs (all public, dated, with source URL):
  data/sugar/manual/india_crush_history.csv   season-to-date sugar by release date, all-India (IN) and Maharashtra (MH),
                                              Uttar Pradesh (UP), Karnataka (KA); mills; state cane/recovery where given
  data/sugar/manual/india_season_finals.csv   final production per season and Maharashtra's crushing start date
  data/sugar/manual/india_isma_estimates.csv  ISMA's first in-season estimate per season
  data/sugar/manual/india_balance_inputs.csv  opening stock, consumption, exports, closing-stock norm, TRQ
  data/sugar/manual/india.csv                 'production' rows ending 'to date' (added by hand from each release)
  data/sugar/india_crush_auto.csv             rows the collector (pipelines/india_crush.py) parsed from news of releases

build(parity) -> dict for world.json['india']['crush']; outputs and variable names only.
python models/india_crush.py --backtest prints the leave-one-out backtest (not written anywhere, not on the page).
"""
import math, re, sys
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MAN = ROOT / "data" / "sugar" / "manual"
AUTO = ROOT / "data" / "sugar" / "india_crush_auto.csv"
REG = {"IN": "All India", "MH": "Maharashtra", "UP": "Uttar Pradesh", "KA": "Karnataka"}
STATE_WORDS = {"maharashtra": "MH", "uttar pradesh": "UP", "karnataka": "KA", "all-india": "IN", "all india": "IN"}
Z80 = 1.2816


def rd(v, n=2):
    return None if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else round(float(v), n)


def season_of(d):
    d = pd.Timestamp(d)
    y = d.year if d.month >= 10 else d.year - 1
    return f"{y}/{(y + 1) % 100:02d}"


def season_start(season):
    return pd.Timestamp(f"{season[:4]}-10-01")


# ------------------------------------------------------------------ data
def load_history():
    H = pd.read_csv(MAN / "india_crush_history.csv", dtype={"season": str})
    H["origin"] = "manual"
    parts = [H]
    if AUTO.exists():
        A = pd.read_csv(AUTO, dtype={"season": str})
        if len(A):
            A["origin"] = "auto"
            parts.append(A)
    # rows typed into india.csv from each release ('... production 2026/27 to date', '... production to date')
    p = MAN / "india.csv"
    if p.exists():
        R = pd.read_csv(p, dtype=str).fillna("")
        rows = []
        for _, r in R.iterrows():
            it = r["item"].lower()
            if r["kind"] != "production" or "to date" not in it or r["unit"] != "lakh t":
                continue
            reg = next((v for k, v in STATE_WORDS.items() if it.startswith(k)), None)
            if not reg:
                continue
            mills = None
            m = re.match(r"\s*(\d+)\s+mills", r["note"])
            if m:
                mills = float(m.group(1))
            rows.append({"season": season_of(r["date"]), "as_of": r["date"], "region": reg, "sugar_lakh_t": float(r["value"]),
                         "mills": mills, "source": r["source"], "url": r["url"], "origin": "manual"})
        if rows:
            parts.append(pd.DataFrame(rows))
    H = pd.concat(parts, ignore_index=True)
    H["as_of"] = pd.to_datetime(H["as_of"])
    H["kind"] = np.where(H.get("cane_lakh_t").notna() if "cane_lakh_t" in H else False, "state", "isma")
    # manual beats auto; first manual row for a date/region wins
    H["rank"] = (H.origin != "manual").astype(int)
    H = H.sort_values(["rank"]).drop_duplicates(["season", "as_of", "region", "kind"]).drop(columns="rank")
    return H.sort_values(["season", "as_of", "region"]).reset_index(drop=True)


def load_finals():
    F = pd.read_csv(MAN / "india_season_finals.csv", dtype={"season": str})
    fin = {(r.season, r.region): float(r.final_lakh_t) for r in F.itertuples() if r.final_lakh_t == r.final_lakh_t}
    mh0 = {r.season: pd.Timestamp(r.mh_start) for r in F.itertuples() if r.region == "IN" and isinstance(r.mh_start, str)}
    return F, fin, mh0


def series(H, season, region):
    s = H[(H.season == season) & (H.region == region) & (H.kind == "isma")].set_index("as_of").sugar_lakh_t
    return s[~s.index.duplicated(keep="first")].sort_index()


def mills_at(H, season, region, d, tol=3):
    s = H[(H.season == season) & (H.region == region) & (H.kind == "isma") & H.mills.notna()]
    s = s[(s.as_of - d).abs() <= pd.Timedelta(days=tol)]
    return float(s.mills.iloc[0]) if len(s) else None


# ------------------------------------------------------------------ shares of final
def interp(points, x, origin_gap=None):
    """Linear interpolation on (x, y) points sorted by x; None outside the observed range. The first point may be the
    origin (0, 0); it is only used as a bracket when the first observed point is within origin_gap days of it."""
    pts = sorted(points)
    if not pts or x < pts[0][0] or x > pts[-1][0]:
        return None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            if x0 == 0 and y0 == 0 and origin_gap is not None and x1 > origin_gap:
                return None
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def mh_share(H, fin, mh0, s, tau):
    """Share of Maharashtra's final made tau days after the state's crushing start (removes start-date differences)."""
    f, st = fin.get((s, "MH")), mh0.get(s)
    if not f or st is None:
        return None
    m = series(H, s, "MH")
    pts = [(0, 0.0)] + [((d - st).days, v / f) for d, v in m.items() if (d - st).days >= 0]
    return interp(pts, tau, origin_gap=50) if len(pts) > 1 else None


def rest_share(H, fin, s, t, mills_now=None, adjust=True):
    """Share of the rest of India's final (all-India less Maharashtra) made t days after 1 October; while mills are
    still starting (to 31 Dec) scaled by mills operating now against mills operating then."""
    fi, fm = fin.get((s, "IN")), fin.get((s, "MH"))
    if not fi or not fm:
        return None
    a, m = series(H, s, "IN"), series(H, s, "MH")
    common = a.index.intersection(m.index)
    st = season_start(s)
    pts = [(0, 0.0)] + [((d - st).days, (a[d] - m[d]) / (fi - fm)) for d in common]
    sh = interp(pts, t, origin_gap=50) if len(pts) > 1 else None
    if sh is None or sh <= 0:
        return None
    if adjust and mills_now and t <= 92:
        same = st + pd.Timedelta(days=t)
        mi, mm = mills_at(H, s, "IN", same), mills_at(H, s, "MH", same)
        if mi and mm and mi > mm:
            sh = sh * float(np.clip(mills_now / (mi - mm), 0.75, 1.33))
    return sh


def all_share(H, fin, s, t):
    fi = fin.get((s, "IN"))
    if not fi:
        return None
    a = series(H, s, "IN")
    return interp([(0, 0.0)] + [((d - season_start(s)).days, v / fi) for d, v in a.items()], t, origin_gap=50)


def momentum(H, s, d):
    """Sugar made in the last fortnight as a share of the season to date (per 15 days)."""
    a = series(H, s, "IN")
    if d not in a.index:
        return None
    pr = a[(a.index <= d - pd.Timedelta(days=10)) & (a.index >= d - pd.Timedelta(days=20))]
    if not len(pr) or a[d] <= 0:
        return None
    return float((a[d] - pr.iloc[-1]) / (d - pr.index[-1]).days * 15 / a[d])


def near(H, s, reg, t, tol=2):
    a = series(H, s, reg)
    day = season_start(s) + pd.Timedelta(days=t)
    x = a[(a.index - day).map(abs) <= pd.Timedelta(days=tol)] if len(a) else a
    return (x.index[0], float(x.iloc[0])) if len(x) else (None, None)


STAGE_STATE_TO, STAGE_MOM_FROM = 92, 148      # days after 1 Oct: to 31 Dec state split; from about 26 Feb momentum


def pace(H, fin, mh0, season, d, exclude=(), adjust=True):
    """Pace estimate of the season's final production from the release at date d, using every other finished season.
    Start-up (to 31 Dec): Maharashtra by days since its crushing start + rest of India by date, mills-adjusted.
    Mid-season: all-India share of final reached by the same date. Late season: share predicted from the last
    fortnight's momentum across past seasons (a crush that is slowing early means a short season)."""
    a, m = series(H, season, "IN"), series(H, season, "MH")
    if d not in a.index:
        return None
    t = (d - season_start(season)).days
    past = sorted({s for s in fin_seasons(fin) if s != season and s not in exclude and fin.get((s, "IN"))})
    v = float(a[d])
    out = {"date": d, "all_india_to_date": v, "t": t}
    if t < STAGE_STATE_TO and d in m.index and mh0.get(season) is not None:
        mh_now, rest_now = float(m[d]), v - float(m[d])
        tau = (d - mh0[season]).days
        mi, mm = mills_at(H, season, "IN", d), mills_at(H, season, "MH", d)
        rest_mills = (mi - mm) if mi and mm else None
        mh_est = [mh_now / sh for s in past if (sh := mh_share(H, fin, mh0, s, tau)) and sh > 0.02]
        re_est = [rest_now / sh for s in past if (sh := rest_share(H, fin, s, t, rest_mills, adjust)) and sh > 0.01]
        if len(mh_est) >= 3 and len(re_est) >= 3:
            out.update({"method": "state", "mh": float(np.median(mh_est)), "rest": float(np.median(re_est)), "n": min(len(mh_est), len(re_est)),
                        "mh_now": mh_now, "rest_now": rest_now, "tau": tau})
            out["est"] = out["mh"] + out["rest"]
            out["lo"], out["hi"] = min(mh_est) + min(re_est), max(mh_est) + max(re_est)
            return out
    if t >= STAGE_MOM_FROM:
        r0 = momentum(H, season, d)
        pts = []
        for o in past:
            od, ov = near(H, o, "IN", t)
            if od is not None and (r := momentum(H, o, od)) is not None:
                pts.append((r, ov / fin[(o, "IN")]))
        if r0 is not None and len(pts) >= 4:
            xx, yy = np.array([q[0] for q in pts]), np.array([q[1] for q in pts])
            b, a0 = np.polyfit(xx, yy, 1)
            sh = float(np.clip(a0 + b * r0, yy.min() * 0.85, min(0.999, yy.max() * 1.15)))
            est = [v / y for y in yy]
            out.update({"method": "momentum", "est": v / sh, "lo": min(est), "hi": max(est), "n": len(pts), "momentum": r0})
            return out
    est = [v / sh for s in past if (sh := all_share(H, fin, s, t)) and sh > 0.02]
    if len(est) >= 3:
        out.update({"method": "all", "est": float(np.median(est)), "lo": float(np.min(est)), "hi": float(np.max(est)), "n": len(est)})
        return out
    return None


def fin_seasons(fin):
    return {s for (s, r) in fin if r == "IN"}


BUCKETS = [(10, 31), (11, 15), (11, 30), (12, 15), (12, 31), (1, 15), (1, 31), (2, 15), (2, 28), (3, 15), (3, 31), (4, 15), (4, 30)]


def bucket(d):
    d = pd.Timestamp(d)
    best = min(BUCKETS, key=lambda b: abs((pd.Timestamp(d.year, b[0], min(b[1], 28 if b[0] == 2 else b[1])) - d).days))
    return f"{best[0]:02d}-{best[1]:02d}"


def backtest(H, fin, mh0, adjust=True):
    rows = []
    for s in sorted(fin_seasons(fin)):
        if not fin.get((s, "IN")):
            continue
        for d in series(H, s, "IN").index:
            p = pace(H, fin, mh0, s, d, exclude=(s,), adjust=adjust)
            if not p:
                continue
            fi = fin[(s, "IN")]
            rows.append({"season": s, "date": d, "bucket": bucket(d), "method": p["method"], "est": p["est"], "final": fi,
                         "err_pct": 100 * (p["est"] / fi - 1), "inside": p["lo"] <= fi <= p["hi"]})
    return pd.DataFrame(rows)


def isma_error_pct():
    E = pd.read_csv(MAN / "india_isma_estimates.csv", dtype={"season": str})
    _, fin, _ = load_finals()
    e = [100 * (fin[(r.season, "IN")] / r.net_lakh_t - 1) for r in E.itertuples() if fin.get((r.season, "IN"))]
    return float(np.sqrt(np.mean(np.square(e)))) if e else 10.0, len(e)


# ------------------------------------------------------------------ public output
def build(parity=None):
    H = load_history()
    F, fin, mh0 = load_finals()
    isma_rows = H[(H.kind == "isma") & (H.region == "IN")]
    cur = isma_rows.season.max()
    a = series(H, cur, "IN")
    d = a.index.max()
    prev = f"{int(cur[:4]) - 1}/{int(cur[:4]) % 100:02d}"
    t = (d - season_start(cur)).days

    # ---- tracker: latest release by region vs same date last year
    def at(season, reg, day, tol=3):
        s = series(H, season, reg)
        s = s[(s.index - day).map(abs) <= pd.Timedelta(days=tol)] if len(s) else s
        return float(s.iloc[0]) if len(s) else None
    ly_day = d - pd.DateOffset(years=1)
    latest = []
    for reg in ("IN", "MH", "UP", "KA"):
        v = at(cur, reg, d, 0)
        if v is None:
            continue
        lyv = at(prev, reg, ly_day)
        latest.append({"region": REG[reg], "now": rd(v), "mills": mills_at(H, cur, reg, d, 0), "year_ago": rd(lyv),
                       "mills_year_ago": mills_at(H, prev, reg, ly_day), "final_last_season": rd(fin.get((prev, reg)))})
    src = H[(H.season == cur) & (H.as_of == d) & (H.region == "IN") & (H.kind == "isma")].iloc[0]

    # ---- chart: season to date at every release (days after 1 October), final production at 30 September
    seasons = sorted({s for s in H.season.unique() if s >= "2020/21"})
    def pts(season, reg="IN"):
        s = series(H, season, reg)
        st = season_start(season)
        p_ = [[(d - st).days, rd(v)] for d, v in s.items()]
        if fin.get((season, reg)):
            p_.append([364, rd(fin[(season, reg)])])
        return p_
    chart = {"points": {s: pts(s) for s in seasons}, "mh_points": {s: pts(s, "MH") for s in seasons}}

    # ---- history table: all-India and Maharashtra at the same point of past seasons, and finals
    same = []
    for s in sorted(fin_seasons(fin)):
        if s == cur:
            continue
        st = season_start(s)
        day = st + pd.Timedelta(days=t)
        same.append({"season": s, "all_india_same_date": rd(at(s, "IN", day, 2)), "mh_same_date": rd(at(s, "MH", day, 2)),
                     "final": rd(fin.get((s, "IN"))), "mh_final": rd(fin.get((s, "MH"))), "mh_start": str(mh0[s].date()) if s in mh0 else None})

    # ---- Maharashtra cane-crush rows (commissionerate / NFCSF style)
    st_rows = H[(H.kind == "state") & (H.season.isin([cur, prev]))].sort_values("as_of", ascending=False)
    mh_crush = [{"as_of": str(r.as_of.date()), "season": r.season, "mills": rd(r.mills, 0), "cane_lakh_t": rd(r.cane_lakh_t, 1),
                 "sugar_lakh_t": rd(r.sugar_lakh_t), "recovery_pct": rd(r.recovery_pct), "source": r.source, "url": r.url} for r in st_rows.itertuples()]

    # ---- projection
    p = pace(H, fin, mh0, cur, d)
    E = pd.read_csv(MAN / "india_isma_estimates.csv", dtype={"season": str})
    ie = E[E.season == cur].sort_values("release_date")
    isma = float(ie.net_lakh_t.iloc[-1]) if len(ie) else None
    isma_date = ie.release_date.iloc[-1] if len(ie) else None
    isma_mh = None
    R = pd.read_csv(MAN / "india.csv", dtype=str).fillna("")
    q = R[R.item.str.startswith("ISMA") & R.item.str.contains("estimate") & R.item.str.endswith("Maharashtra") & (R.date >= str(season_start(cur).date()))]
    if len(q):
        isma_mh = float(q.sort_values("date").value.iloc[-1])
    proj = None
    if p:
        bt = backtest(H, fin, mh0)
        b = bucket(d)
        e = bt[bt.bucket == b].err_pct
        sp = float(np.sqrt(np.mean(np.square(e)))) if len(e) >= 3 else 50.0
        si, _ = isma_error_pct()
        sig_p, sig_i = sp / 100 * p["est"], (si / 100 * isma) if isma else None
        if isma:
            w = sig_i ** 2 / (sig_i ** 2 + sig_p ** 2)
            mid = w * p["est"] + (1 - w) * isma
            sig = math.sqrt(1 / (1 / sig_i ** 2 + 1 / sig_p ** 2))
        else:
            mid, sig = p["est"], sig_p
        proj = {"as_of": str(d.date()), "to_date": rd(p["all_india_to_date"]), "low": rd(mid - Z80 * sig, 1), "mid": rd(mid, 1), "high": rd(mid + Z80 * sig, 1),
                "isma": rd(isma), "isma_date": isma_date, "vs_isma_pct": rd(100 * (mid / isma - 1), 1) if isma else None,
                "isma_mh": isma_mh,
                "mh_vs_isma": (None if not (p.get("mh") and isma_mh) else "above" if p["mh"] > 1.05 * isma_mh else "below" if p["mh"] < 0.95 * isma_mh else "in line"),
                "share_of_mid_made": rd(100 * p["all_india_to_date"] / mid, 1),
                "last_season_final": rd(fin.get((prev, "IN"))),
                "reliability": "low" if t < 75 else ("medium" if t < 135 else "high")}

    out = {"season": cur, "as_of": str(d.date()), "source": src.source, "url": src.url, "latest": latest, "chart": chart, "same_point": same,
           "days_into_season": t, "mh_start": str(mh0[cur].date()) if cur in mh0 else None, "mh_crush": mh_crush, "projection": proj,
           "variables": ["ISMA season-to-date sugar production, all-India and Maharashtra, at each release (2018/19 on)",
                         "Final production per season (ISMA; Maharashtra state figures)",
                         "Maharashtra crushing start date each season (state-fixed)",
                         "Mills operating at each release",
                         "ISMA's in-season estimates and how far past first estimates were from the final"]}
    out["balance"] = balance(proj, parity)
    return out


def balance(proj, parity):
    B = pd.read_csv(MAN / "india_balance_inputs.csv").set_index("item")
    g = lambda k, c="mid": float(B.loc[k, c])
    if not proj:
        return None
    prod = {"low": proj["low"], "mid": proj["mid"], "high": proj["high"]}
    op, ex = g("opening_stock"), g("exports")
    cons = {c: g("consumption", c) for c in ("low", "mid", "high")}
    norms = [1.5, 2.0, 2.5, 3.0]
    nm = g("closing_norm_months")
    need = lambda P, C, n: C + C * n / 12 + ex - op - P
    quota, used = g("trq_quota"), g("trq_used")
    left = quota - used
    main = need(prod["mid"], cons["mid"], nm)
    # widest sensible range: high production + low consumption + low norm, and the reverse
    lo = need(prod["high"], cons["low"], g("closing_norm_months", "low"))
    hi = need(prod["low"], cons["high"], g("closing_norm_months", "high"))
    grid = [{"case": k, "production": prod[k], "need": [rd(need(prod[k], cons["mid"], n), 1) for n in norms]} for k in ("high", "mid", "low")]
    close_trq = op + prod["mid"] + left - cons["mid"] - ex        # only the unused part of the quota arrives this season
    rows = [{"item": "Opening stock, 1 Oct 2026", "value": rd(op, 1), "note": B.loc["opening_stock", "note"], "source": B.loc["opening_stock", "source"], "url": B.loc["opening_stock", "url"]},
            {"item": "Production 2026/27 (desk projection, mid)", "value": rd(prod["mid"], 1), "note": f"range {prod['low']:.1f} to {prod['high']:.1f}; ISMA {proj['isma']}", "source": "Desk projection from ISMA releases", "url": ""},
            {"item": "Consumption", "value": rd(cons["mid"], 1), "note": B.loc["consumption", "note"], "source": B.loc["consumption", "source"], "url": B.loc["consumption", "url"]},
            {"item": "Exports", "value": rd(ex, 1), "note": B.loc["exports", "note"], "source": B.loc["exports", "source"], "url": B.loc["exports", "url"] if isinstance(B.loc["exports", "url"], str) else ""},
            {"item": f"Closing stock at the norm ({nm:g} months of consumption)", "value": rd(cons["mid"] * nm / 12, 1), "note": B.loc["closing_norm_months", "note"], "source": B.loc["closing_norm_months", "source"], "url": B.loc["closing_norm_months", "url"]},
            {"item": "Imports needed to reach the norm", "value": rd(main, 1), "note": "consumption + exports + closing stock − opening stock − production", "source": "Desk", "url": ""}]
    econ = None
    if parity and parity.get("raw_trq_rs_qtl") and parity.get("domestic"):
        dom = parity["domestic"]
        econ = {"raw_trq_rs_qtl": parity["raw_trq_rs_qtl"], "domestic_rs_qtl": dom["value"], "domestic_item": dom["item"], "domestic_date": dom["date"],
                "gap_rs_qtl": rd(dom["value"] - parity["raw_trq_rs_qtl"], 0), "raw_usd_t": parity.get("raw_usd_t"),
                "white_full_duty_rs_qtl": parity.get("white_full_duty_rs_qtl")}
    return {"rows": rows, "need_mid": rd(main, 1), "need_low": rd(lo, 1), "need_high": rd(hi, 1), "norms": norms, "grid": grid,
            "trq_quota": quota, "trq_used": used, "trq_left": rd(left, 1), "need_vs_trq_left": rd(main - left, 1),
            "closing_if_trq_only": rd(close_trq, 1), "closing_if_trq_only_months": rd(12 * close_trq / cons["mid"], 1),
            "trq_used_date": B.loc["trq_used", "as_of"], "trq_url": B.loc["trq_quota", "url"], "economics": econ,
            "next_season": {"status": "not yet",
                            "text": ("No 2027/28 production view yet: the first public read is ISMA's satellite cane-area assessment (usually July) and the monsoon. "
                                     f"What is known: if only the unused part of the duty-free quota (about {left:.1f} lakh t) arrives this season, India starts 2027/28 with about {close_trq:.0f} lakh t "
                                     f"({12 * close_trq / cons['mid']:.1f} months of consumption), so any shortfall in the 2027/28 crop goes straight to imports.")}}


if __name__ == "__main__":
    H = load_history()
    F, fin, mh0 = load_finals()
    if "--backtest" in sys.argv:
        for adj in (True, False):
            bt = backtest(H, fin, mh0, adjust=adj)
            print(f"\n=== pace backtest, mills adjustment {'ON' if adj else 'OFF'} (leave-one-season-out) ===")
            g = bt.groupby("bucket").agg(n=("err_pct", "size"), mean=("err_pct", "mean"), rmse=("err_pct", lambda x: np.sqrt(np.mean(x ** 2))),
                                         maxabs=("err_pct", lambda x: x.abs().max()), inside=("inside", "mean"))
            order = [f"{m:02d}-{d:02d}" for m, d in BUCKETS]
            print(g.reindex([o for o in order if o in g.index]).round(1).to_string())
            if adj:
                print(bt.assign(date=bt.date.dt.date).round(1).to_string())
        si, n = isma_error_pct()
        print(f"\nISMA first-estimate RMS error {si:.1f}% over {n} seasons")
    else:
        import json
        print(json.dumps(build(), default=str, indent=1)[:4000])
