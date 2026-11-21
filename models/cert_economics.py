"""Cost to put up certs (cotton, coffee, cocoa) and the front spread into first notice -> data/derived/cert_economics.json.

Reads only files in this repo:
  data/cotton/ref/ice_tariffs_2026-27.csv   ICE Cotton No. 2 warehouse tariffs (cents per bale)
  data/cotton/ice/warehouse_*.csv           ICE cotton certificated stock by warehouse (weekly)
  data/cotton/ice/stock_*.csv               ICE cotton certificated stock by delivery point
  data/coffee/ref/grading_fees.csv          ICE coffee grading fees
  data/coffee/ref/kc_rule_params.json       bag weights by origin
  data/coffee/ice_certs_daily_detail.csv    daily coffee certs, passed and failed grading by origin and port
  data/coffee/ice_certs.csv                 daily coffee certs (automatic feed)
  data/coffee/ice_certs_eom_by_port.csv     month-end coffee certs, 1996 on
  data/cocoa/ref/grading_fees.csv           ICE cocoa grading fees by chops per sample
  data/cocoa/ice_grading_monthly.csv        ICE cocoa grading results by month, port, origin, initial/regrade
  data/cocoa/ice_certs_daily.csv            daily cocoa certs (from Oct 2026)
  data/contracts/{CT,KC,CC}.csv (+ _pre2006) settlements by contract
  data/specs/calendar.json                  first notice days of live contracts
The page shows results only. Any missing main input raises.
"""
import glob
import json
import math
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "models"))
from softs_spreads_history import BD, HOL  # noqa: E402

OUT = os.path.join(ROOT, "data", "derived", "cert_economics.json")
LB_KG = 2.20462
MC = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6, "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}
MN = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WIN = 21                                    # trading days before first notice
CFG = {"CT": {"nbd": 5, "months": "HKNZ", "unit": "¢/lb", "dp": 2},
       "KC": {"nbd": 7, "months": "HKNUZ", "unit": "¢/lb", "dp": 2},
       "CC": {"nbd": 10, "months": "HKNUZ", "unit": "$/t", "dp": 0}}
TODAY = pd.Timestamp(date.today())


def P(*a):
    return os.path.join(ROOT, *a)


def need(p):
    if not os.path.exists(p):
        raise SystemExit(f"missing input: {os.path.relpath(p, ROOT)}")
    return p


def rd(v, n=2):
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(v, n) if math.isfinite(v) else None


def lab(c):
    return f"{MN[MC[c[-5]]]} {c[-2:]}"


# ---------------------------------------------------------------- A. cost to put up certs
def cotton_cost():
    T = pd.read_csv(need(P("data/cotton/ref/ice_tariffs_2026-27.csv")), dtype={"code": str}).set_index("code")
    files = sorted(glob.glob(P("data/cotton/ice/warehouse_*.csv")))
    if not files:
        raise SystemExit("missing input: data/cotton/ice/warehouse_*.csv")
    W = {}
    for f in files:
        w = pd.read_csv(f, dtype={"Warehouse Number": str})
        W[os.path.basename(f)[10:20]] = w.set_index("Warehouse Number")
    ds = sorted(W)
    cur, d1 = W[ds[-1]], ds[-1]
    prev, d0 = (W[ds[-2]], ds[-2]) if len(ds) > 1 else (None, None)
    rows, n_new, usd_new, unmatched, ex_lo = [], 0, 0.0, 0, 0.0
    for code, r in cur.iterrows():
        b = float(r.Receipt or 0)
        b0 = float(prev.Receipt.get(code, 0) or 0) if prev is not None else 0.0
        ch = b - b0
        if code not in T.index:
            unmatched += max(ch, 0)
            continue
        t = T.loc[code]
        if b == 0 and b0 == 0:
            continue
        new = max(ch, 0)
        rows.append({"warehouse": str(r.Warehouse).strip(), "point": t.delivery_point, "bales": int(b), "change": int(ch),
                     "new": int(new), "cost_c_bale": int(t.total_to_certificate_c), "cost_c_lb": rd(t.total_to_certificate_c / 500, 2),
                     "new_usd": rd(new * t.total_to_certificate_c / 100, 0)})
        ex_lo += b * (t.total_to_certificate_c - t.load_out_c)
        n_new += new
        usd_new += new * t.total_to_certificate_c / 100
    rows.sort(key=lambda x: (-x["new"], -x["bales"]))
    tot_b = sum(x["bales"] for x in rows)
    tot_usd = sum(x["bales"] * x["cost_c_bale"] / 100 for x in rows)
    rng = (rd(T.total_to_certificate_c.min() / 500, 2), rd(T.total_to_certificate_c.max() / 500, 2))
    comp = {k: rd(T[k].median(), 0) for k in ["receiving_weighing_sampling_c", "exchange_inspection_c", "usda_classing_c", "load_out_c", "total_to_certificate_c"]}
    # front spread for the replacement-cost line: live front vs next (October skipped)
    sp = None
    try:
        S = front_now("CT")
        if S:
            sp = S
    except Exception:
        sp = None
    stock_c_lb = tot_usd * 100 / tot_b / 500 if tot_b else None
    new_c_lb = usd_new * 100 / n_new / 500 if n_new else None
    return {"report": d1, "prev_report": d0, "rows": rows, "new_bales": int(n_new), "new_usd": rd(usd_new, 0),
            "new_c_lb": rd(new_c_lb, 2), "stock_bales": int(tot_b), "stock_usd": rd(tot_usd, 0), "stock_c_lb": rd(stock_c_lb, 2),
            "stock_ex_loadout_c_lb": rd(ex_lo / tot_b / 500, 2) if tot_b else None,
            "range_c_lb": rng, "range_c_bale": (int(T.total_to_certificate_c.min()), int(T.total_to_certificate_c.max())),
            "median_components_c_bale": comp, "unmatched_new_bales": int(unmatched), "spread": sp}


def coffee_cost():
    F = pd.read_csv(need(P("data/coffee/ref/grading_fees.csv")))
    fee = float(F[F.item == "grading"].sort_values("effective_from").usd.iloc[-1])
    mn = float(F[F.item == "minimum_per_receipt"].usd.iloc[-1])
    K = json.load(open(need(P("data/coffee/ref/kc_rule_params.json"))))["bag_kg_by_origin"]
    D = pd.read_csv(need(P("data/coffee/ice_certs_daily_detail.csv")))
    D["graded"] = D.passed + D.failed
    D["lb"] = D.origin.map(lambda o: K.get(o, K["default"]) * LB_KG)
    g = D[D.graded > 0]
    if g.empty:
        return None
    last = g.date.max()

    def by_port(x):
        o = []
        for p, y in x.groupby("port"):
            gb, pb = y.graded.sum(), y.passed.sum()
            lbs_g, lbs_p = (y.graded * y.lb).sum(), (y.passed * y.lb).sum()
            usd = gb * fee
            o.append({"port": p, "graded": int(gb), "passed": int(pb), "failed": int(y.failed.sum()), "fee_usd": rd(usd, 0),
                      "c_lb_graded": rd(usd * 100 / lbs_g, 2) if lbs_g else None, "c_lb_passed": rd(usd * 100 / lbs_p, 2) if lbs_p else None})
        o.sort(key=lambda r: -r["graded"])
        gb, pb = x.graded.sum(), x.passed.sum()
        lbs_g, lbs_p = (x.graded * x.lb).sum(), (x.passed * x.lb).sum()
        return o, {"graded": int(gb), "passed": int(pb), "fee_usd": rd(gb * fee, 0),
                   "c_lb_graded": rd(gb * fee * 100 / lbs_g, 2) if lbs_g else None, "c_lb_passed": rd(gb * fee * 100 / lbs_p, 2) if lbs_p else None}
    day_rows, day_tot = by_port(g[g.date == last])
    since = (pd.Timestamp(last) - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    m_rows, m_tot = by_port(g[g.date > since])
    return {"date": last, "rows": day_rows, "total": day_tot, "d30_from": since, "rows_30d": m_rows, "total_30d": m_tot,
            "fee_usd_bag": fee, "min_usd_receipt": mn, "c_lb_60kg": rd(fee * 100 / (60 * LB_KG), 2),
            "min_binds_below_bags": int(math.ceil(mn / fee)), "warehouse_in_charges": None}


def cocoa_fee(chops_per_lot, F):
    c = max(1, int(round(chops_per_lot)))
    hit = F[(F.chops_min <= c) & (F.chops_max >= c)]
    return float(hit.usd_per_sample.iloc[0]) if len(hit) else float(F.usd_per_sample.max())


def cocoa_cost():
    F = pd.read_csv(need(P("data/cocoa/ref/grading_fees.csv")))
    G = pd.read_csv(need(P("data/cocoa/ice_grading_monthly.csv")))
    G = G[G.month >= "2025-01"]
    last = G.month.max()
    PORT = {"DR": "Delaware River", "NY": "New York", "BA": "Baltimore", "HR": "Hampton Roads", "AL": "Albany"}

    def cost(x):
        o = []
        for (p, gt), y in x.groupby(["port", "grade_type"]):
            lots = max(1, int(round(y.tonnes.sum() / 10)))
            cpl = y.chops.sum() / lots
            per = cocoa_fee(cpl, F)
            usd = per * lots
            o.append({"port": PORT.get(p, p), "type": "first grading" if gt == "initial" else "regrade", "lots": lots, "tonnes": rd(y.tonnes.sum(), 0),
                      "chops_per_lot": rd(cpl, 1), "fee_per_lot": per, "fee_usd": rd(usd, 0), "usd_t": rd(usd / y.tonnes.sum(), 2)})
        o.sort(key=lambda r: (r["type"], -r["tonnes"]))
        t = sum(r["tonnes"] for r in o)
        u = sum(r["fee_usd"] for r in o)
        return o, {"tonnes": rd(t, 0), "lots": sum(r["lots"] for r in o), "fee_usd": rd(u, 0), "usd_t": rd(u / t, 2) if t else None}
    rows, tot = cost(G[G.month == last])
    m12 = sorted(G.month.unique())[-12:]
    r12, t12 = cost(G[G.month.isin(m12)])
    return {"month": last, "rows": rows, "total": tot, "rows_12m": r12, "total_12m": t12, "from_12m": m12[0],
            "fee_table": F[["chops_min", "chops_max", "usd_per_sample"]].to_dict("records"), "min_usd_t": rd(F.usd_per_sample.min() / 10, 1),
            "warehouse_handling": None}


# ---------------------------------------------------------------- B. front spread into first notice
def prices(sym):
    parts = [pd.read_csv(need(P("data", "contracts", f"{sym}.csv")))]
    old = P("data", "contracts", f"{sym}_pre2006.csv")
    if os.path.exists(old):
        parts.insert(0, pd.read_csv(old))
    d = pd.concat(parts).drop_duplicates(["contract", "date"], keep="last")
    d["date"] = pd.to_datetime(d.date)
    return d.pivot_table(index="date", columns="contract", values="close").sort_index()


def fnd_of(c, nbd, cal):
    if c in cal:
        return pd.Timestamp(cal[c])
    y, m = int(c[-4:]), MC[c[-5]]
    first = pd.Timestamp(y, m, 1)
    while first.weekday() >= 5 or first in HOL:
        first += pd.Timedelta(days=1)
    return first - nbd * BD


def cal_fnd(sym):
    try:
        J = json.load(open(P("data/specs/calendar.json")))
        return {c["contract"]: c["fnd"] for c in J["markets"][sym]["contracts"] if c.get("fnd")}
    except Exception:
        return {}


def pairs(sym, px):
    m = CFG[sym]["months"]
    cons = sorted([c for c in px.columns if c[-5] in m], key=lambda c: (int(c[-4:]), MC[c[-5]]))
    return [(a, b) for a, b in zip(cons, cons[1:])]


def asof(s, d, tol=3):
    s = s.dropna()
    s = s[s.index <= d]
    if s.empty or (d - s.index[-1]).days > tol + 3:
        return None, None
    return float(s.iloc[-1]), s.index[-1]


def cert_series(sym):
    """(date -> certified stock) points, and for cocoa a monthly first-grading series."""
    if sym == "CT":
        pts = {}
        for f in glob.glob(P("data/cotton/ice/stock_*.csv")):
            w = pd.read_csv(f)
            col = [c for c in w.columns if c.startswith("Current Stock")]
            if col:
                pts[pd.Timestamp(os.path.basename(f)[6:16])] = float(pd.to_numeric(w[col[0]], errors="coerce").sum())
        for f in glob.glob(P("data/cotton/ice/warehouse_*.csv")):
            pts[pd.Timestamp(os.path.basename(f)[10:20])] = float(pd.read_csv(f).Receipt.sum())
        return pd.Series(pts).sort_index(), "bales", None
    if sym == "KC":
        e = pd.read_csv(need(P("data/coffee/ice_certs_eom_by_port.csv")))
        e = e[e.port == "TOTAL"].dropna()
        s = pd.Series(e.bags.values, index=pd.to_datetime(e.date))
        k = pd.read_csv(need(P("data/coffee/ice_certs.csv")))
        k = k[k.section == "certified"].groupby("date").bags.sum()
        d = pd.read_csv(need(P("data/coffee/ice_certs_daily_detail.csv"))).groupby("date").certified.sum()
        for x in (k, d):
            x.index = pd.to_datetime(x.index)
            s = pd.concat([s[~s.index.isin(x.index)], x.astype(float)])
        return s.sort_index(), "bags", None
    c = pd.read_csv(need(P("data/cocoa/ice_certs_daily.csv")))
    c = c[c.section == "certified"].groupby("date").lots.sum() * 10
    c.index = pd.to_datetime(c.index)
    g = pd.read_csv(need(P("data/cocoa/ice_grading_monthly.csv")))
    gi = g[g.grade_type == "initial"].groupby("month").tonnes.sum()
    return c.sort_index().astype(float), "t", gi


def interp(s, d, gap=45):
    if s.empty:
        return None
    if d in s.index:
        return float(s.loc[d])
    a, b = s[s.index < d], s[s.index > d]
    if len(a) and len(b) and (d - a.index[-1]).days <= gap and (b.index[0] - d).days <= gap:
        x0, x1 = a.index[-1], b.index[0]
        w = (d - x0).days / (x1 - x0).days
        return float(a.iloc[-1] + w * (b.iloc[0] - a.iloc[-1]))
    if len(a) and not len(b) and (d - a.index[-1]).days <= 7:
        return float(a.iloc[-1])
    return None


def gradings_in(gi, d0, d1):
    """first-grading tonnes in (d0, d1], monthly totals spread evenly over the days of each month."""
    if gi is None or gi.empty:
        return None
    tot, cover = 0.0, 0
    for m in pd.period_range(d0, d1, freq="M"):
        ms, me = m.start_time, m.end_time.normalize()
        a, b = max(ms, d0 + pd.Timedelta(days=1)), min(me, d1)
        if b < a:
            continue
        k = str(m)
        if k not in gi.index:
            return None
        tot += gi[k] * ((b - a).days + 1) / ((me - ms).days + 1)
        cover += 1
    return tot if cover else None


def contract_rows(sym):
    px = prices(sym)
    cal = cal_fnd(sym)
    certs, cu, gi = cert_series(sym)
    nbd = CFG[sym]["nbd"]
    out = []
    for f, n in pairs(sym, px):
        F = fnd_of(f, nbd, cal)
        S0 = F - WIN * BD
        if F > TODAY + pd.Timedelta(days=400):
            continue
        a0, d0 = asof(px[f], S0)
        b0, _ = asof(px[n], S0)
        a1, d1 = asof(px[f], F)
        b1, _ = asof(px[n], F)
        r = {"front": f, "next": n, "pair": f"{lab(f)}/{lab(n)}", "fnd": F.strftime("%Y-%m-%d"), "start": S0.strftime("%Y-%m-%d"),
             "s_start": None if a0 is None or b0 is None else a0 - b0, "s_fnd": None if a1 is None or b1 is None or F > TODAY else a1 - b1,
             "px_start": a0}
        r["chg"] = r["s_fnd"] - r["s_start"] if r["s_fnd"] is not None and r["s_start"] is not None else None
        c0, c1 = interp(certs, S0), interp(certs, F) if F <= TODAY else None
        r["certs_start"], r["certs_fnd"] = c0, c1
        r["cert_chg"] = c1 - c0 if c0 is not None and c1 is not None else None
        r["gradings"] = gradings_in(gi, S0, F) if gi is not None and F <= TODAY else None
        out.append(r)
    return out, cu, px, certs, cal


def front_now(sym):
    px = prices(sym)
    cal = cal_fnd(sym)
    nbd = CFG[sym]["nbd"]
    for f, n in pairs(sym, px):
        F = fnd_of(f, nbd, cal)
        if F >= TODAY.normalize():
            a, d = asof(px[f], TODAY, tol=7)
            b, _ = asof(px[n], TODAY, tol=7)
            if a is None or b is None:
                return None
            return {"front": f, "next": n, "pair": f"{lab(f)}/{lab(n)}", "spread": rd(a - b, CFG[sym]["dp"] + 1), "date": d.strftime("%Y-%m-%d"),
                    "fnd": F.strftime("%Y-%m-%d")}
    return None


def fnd_block(sym):
    rows, cu, px, certs, cal = contract_rows(sym)
    dp = CFG[sym]["dp"]
    done = [r for r in rows if pd.Timestamp(r["fnd"]) <= TODAY and r["chg"] is not None]
    tbl = [{"pair": r["pair"], "fnd": r["fnd"], "s_start": rd(r["s_start"], dp), "s_fnd": rd(r["s_fnd"], dp), "chg": rd(r["chg"], dp),
            "cert_chg": rd(r["cert_chg"], 0), "gradings": rd(r["gradings"], 0)} for r in done[-8:]][::-1]
    cur = None
    nb = front_now(sym)
    if nb:
        live = next(r for r in rows if r["front"] == nb["front"])
        S0 = pd.Timestamp(live["start"])
        opened = TODAY >= S0
        cur = {"pair": nb["pair"], "fnd": nb["fnd"], "start": live["start"], "opened": bool(opened), "spread": nb["spread"], "date": nb["date"],
               "s_start": rd(live["s_start"], dp) if opened else None,
               "chg": rd(nb["spread"] - live["s_start"], dp) if opened and live["s_start"] is not None else None}
        if opened:
            c0 = interp(certs, S0)
            last = certs.dropna()
            if c0 is None and len(last[last.index >= S0]):   # history starts inside the window
                first = last[last.index >= S0]
                cur["cert_from"] = first.index[0].strftime("%Y-%m-%d")
                c0 = float(first.iloc[0])
            if len(last) and c0 is not None:
                cur["cert_chg"] = rd(float(last.iloc[-1]) - c0, 0)
                cur["cert_to"] = last.index[-1].strftime("%Y-%m-%d")
    return {"unit": CFG[sym]["unit"], "cert_unit": cu, "rows": tbl, "current": cur, "window_days": WIN}


def main():
    out = {"built": date.today().isoformat(), "markets": {}}
    for sym, fn in (("CT", cotton_cost), ("KC", coffee_cost), ("CC", cocoa_cost)):
        out["markets"][sym] = {"cost": fn(), "fnd": fnd_block(sym)}
    out["sources"] = {
        "CT": ["ICE Futures U.S. Cotton No. 2 warehouse tariffs 2026-27", "ICE certificated stock reports (by warehouse)"],
        "KC": ["ICE Coffee Grading Fee Schedule (PDF)", "ICE notice on 2025 grading fees", "ICE daily certified stock report (coffee)",
               "ICE Coffee \"C\" storage and handling rates"],
        "CC": ["ICE notice on 2025 grading fees (cocoa)", "ICE Rulebook Chapter 9 Cocoa (Rule 9.18)", "ICE cocoa grading results"],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), separators=(",", ":"), allow_nan=False)
    for s, m in out["markets"].items():
        c = m["fnd"]["current"]
        print(s, "rows", len(m["fnd"]["rows"]), "current", c and (c["pair"], c.get("chg"), c.get("cert_chg")))
    print("->", os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    main()
