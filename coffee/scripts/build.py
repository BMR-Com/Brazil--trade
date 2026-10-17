"""Build coffee/data/coffee.json for the Coffee desk tab."""
import os, json, math
from datetime import date, timedelta
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.environ.get("COFFEE_DATA", os.path.join(ROOT, "data"))
TRADE = os.environ.get("TRADE_DATA", os.path.join(ROOT, "..", "data"))
LB_T = 22.0462           # c/lb -> $/t factor (2204.62 lb / 100)
LB_BAG = 132.276         # lb per 60-kg bag
COL_LB_CARGA = 125 * 70 / 94 * 2.20462   # 125 kg parchment -> green excelso at factor 94, in lb


def rd(x, n=2):
    try:
        if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
            return None
        return round(float(x), n)
    except Exception:
        return None


def read(name, **kw):
    p = os.path.join(DATA, name)
    return pd.read_csv(p, **kw) if os.path.exists(p) else None


def series(idx, vals, n=2):
    return {"dates": [str(x)[:10] for x in idx], "v": [rd(v, n) for v in vals]}


def prices():
    p = read("prices_cont.csv")
    p["date"] = pd.to_datetime(p["date"])
    w = p.pivot_table(index="date", columns="symbol", values="close").sort_index().ffill(limit=5)
    snap = {}
    for c in w.columns:
        s = w[c].dropna()
        if s.empty:
            continue
        v = s.iloc[-1]
        def chg(days):
            t = s[s.index <= s.index[-1] - timedelta(days=days)]
            return rd((v / t.iloc[-1] - 1) * 100, 1) if len(t) else None
        ytd = s[s.index < pd.Timestamp(s.index[-1].year, 1, 1)]
        snap[c] = {"last": rd(v, 4), "date": str(s.index[-1])[:10], "w1": chg(7), "m1": chg(30),
                   "ytd": rd((v / ytd.iloc[-1] - 1) * 100, 1) if len(ytd) else None}
    return w, snap


def arb(w):
    q = w[["KC1!", "RC1!"]].dropna()
    q = q[q.index >= "2012-01-01"]
    a = q["KC1!"] * LB_T - q["RC1!"]
    ratio = q["KC1!"] / (q["RC1!"] / LB_T)
    x = a.resample("W-FRI").last(); r = ratio.resample("W-FRI").last()
    pr = (a[a.index >= a.index[-1] - timedelta(days=5 * 365)] <= a.iloc[-1]).mean() * 100
    return {"dates": [str(i)[:10] for i in x.index], "arb": [rd(v, 0) for v in x], "ratio": [rd(v, 2) for v in r],
            "now": {"arb": rd(a.iloc[-1], 0), "ratio": rd(ratio.iloc[-1], 2), "pct5y": rd(pr, 0), "date": str(a.index[-1])[:10]}}


MON = {"F": 1, "H": 3, "K": 5, "N": 7, "U": 9, "V": 10, "X": 11, "Z": 12}


def curves():
    c = read("prices_curve.csv")
    if c is None:
        return None
    c["date"] = pd.to_datetime(c["date"])
    last = c.date.max()
    out = {}
    for mk in ["KC", "RC"]:
        g = c[c.symbol.str.startswith(mk)]
        live = []
        for s, h in g.groupby("symbol"):
            h = h.sort_values("date")
            if h.date.max() < last - timedelta(days=4):
                continue
            m, y = s[len(mk)], int(s[len(mk) + 1:])
            prev = h[h.date <= last - timedelta(days=7)]
            live.append({"sym": s, "label": f"{['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][MON[m]]} {str(y)[2:]}",
                         "key": y * 100 + MON[m], "px": rd(h.close.iloc[-1], 2), "px_1w": rd(prev.close.iloc[-1], 2) if len(prev) else None,
                         "vol": rd(h.volume.iloc[-1], 0)})
        live.sort(key=lambda x: x["key"])
        out[mk] = live[:8]
    return out


def brazil(w):
    b = read("br_physical.csv")
    if b is None or b.empty:
        return None
    b["date"] = pd.to_datetime(b["date"])
    fx = w["USDBRL"]
    out = {}
    ca = b[b.series == "cepea_arabica"].groupby("date").brl_bag.mean()
    cc = b[b.series == "cepea_conillon"].groupby("date").brl_bag.mean()
    j = pd.concat([ca.rename("ara"), cc.rename("con"), fx.rename("fx"), w["KC1!"].rename("kc"), w["RC1!"].rename("rc")], axis=1, sort=True).ffill(limit=3)
    ja = j.dropna(subset=["ara", "fx", "kc"])
    ara_c = ja.ara / ja.fx / LB_BAG * 100
    out["arabica"] = {"dates": [str(i)[:10] for i in ja.index], "brl": [rd(v, 2) for v in ja.ara], "c_lb": [rd(v, 2) for v in ara_c],
                      "kc": [rd(v, 2) for v in ja.kc], "basis": [rd(v, 2) for v in ara_c - ja.kc]}
    jc = j.dropna(subset=["con", "fx", "rc"])
    con_t = jc.con / jc.fx / 0.06
    out["conillon"] = {"dates": [str(i)[:10] for i in jc.index], "brl": [rd(v, 2) for v in jc.con], "usd_t": [rd(v, 0) for v in con_t],
                       "rc": [rd(v, 0) for v in jc.rc], "basis": [rd(v, 0) for v in con_t - jc.rc]}
    # latest co-op and Vitória quotes
    tabs = {}
    for sname in ["coop_cd", "coop_arabica", "vitoria_conillon"]:
        g = b[b.series == sname]
        if g.empty:
            continue
        d = g.date.max(); cur = g[g.date == d]
        prev = g[g.date == g[g.date < d - timedelta(days=5)].date.max()] if (g.date < d - timedelta(days=5)).any() else g.iloc[0:0]
        f = fx[fx.index <= d].iloc[-1]
        rows = []
        for _, r in cur.iterrows():
            pv = prev[prev.place == r.place].brl_bag
            rows.append({"place": r.place, "brl": rd(r.brl_bag, 0), "brl_1w": rd(pv.iloc[0], 0) if len(pv) else None,
                         "usd": rd(r.brl_bag / f / LB_BAG * 100, 1) if sname != "vitoria_conillon" else rd(r.brl_bag / f / 0.06, 0)})
        tabs[sname] = {"date": str(d)[:10], "rows": rows}
    out["quotes"] = tabs
    # Basis ladder by quality. B3 arabica (ICF) is type 4/5 "hard cup or better" (good cup) in US$/bag;
    # cereja descascado (CD) = semi-washed; tipo 6 duro and 6/7 = lower grades; CEPEA = type 6 hard cup.
    kc = w["KC1!"]
    lad = {"icf": (w["ICF1!"] / LB_BAG * 100) if "ICF1!" in w else None}
    for key, ser in [("cd", "coop_cd"), ("t6", "coop_arabica"), ("t67", "coop_67"), ("cepea", "cepea_arabica")]:
        g = b[b.series == ser].groupby("date").brl_bag.mean()
        if len(g):
            f = fx.reindex(g.index, method="ffill")
            lad[key] = g / f / LB_BAG * 100
    frame = pd.concat({k: v for k, v in lad.items() if v is not None}, axis=1, sort=True)
    frame["kc"] = kc.reindex(frame.index, method="ffill")
    bas = frame.drop(columns="kc").sub(frame.kc, axis=0)
    wk = bas.resample("W-FRI").mean()
    wk = wk[wk.index >= "2018-01-01"]
    out["ladder_hist"] = {"dates": [str(i)[:10] for i in wk.index], **{c: [rd(v, 1) for v in wk[c]] for c in wk.columns}}
    names = {"icf": "B3 arabica 4/5 — good cup (front future)", "cd": "Semi-washed (cereja descascado), co-op avg",
             "t6": "Tipo 6 bebida dura, co-op avg", "t67": "Tipo 6/7, co-op avg", "cepea": "CEPEA/ESALQ tipo 6 bebida dura (SP)"}
    ladder = []
    for c in ["icf", "cd", "t6", "t67", "cepea"]:
        if c not in frame or frame[c].dropna().empty:
            continue
        sr = frame[c].dropna(); d = sr.index[-1]
        kcv = kc[kc.index <= d].iloc[-1]
        hist = bas[c].dropna(); h1y = hist[hist.index >= d - timedelta(days=365)]
        ladder.append({"key": c, "name": names[c], "date": str(d)[:10], "c_lb": rd(sr.iloc[-1], 1), "basis": rd(sr.iloc[-1] - kcv, 1),
                       "avg1y": rd(h1y.mean(), 1), "pct": rd((hist[hist.index >= d - timedelta(days=1826)] <= hist.iloc[-1]).mean() * 100, 0)})
    out["ladder"] = ladder
    return out


def colombia(w):
    d = read("col_internal_daily.csv")
    m = read("col_monthly.csv")
    e = read("col_exports.csv")
    out = {}
    if d is not None:
        d["date"] = pd.to_datetime(d["date"]); d = d[d.date <= pd.Timestamp(date.today())].groupby("date").cop_125kg.last()
        j = pd.concat([d.rename("cop"), w["USDCOP"].rename("fx"), w["KC1!"].rename("kc")], axis=1, sort=True).ffill(limit=5).dropna()
        j = j[j.index >= "2015-01-01"]
        c_lb = j.cop / j.fx / COL_LB_CARGA * 100
        jw = pd.concat([c_lb.rename("c"), j.kc, j.cop], axis=1).resample("W-FRI").last()
        out["internal"] = {"dates": [str(i)[:10] for i in jw.index], "cop": [rd(v, 0) for v in jw.cop], "c_lb": [rd(v, 1) for v in jw.c],
                           "kc": [rd(v, 1) for v in jw.kc], "diff": [rd(v, 1) for v in jw.c - jw.kc],
                           "now": {"date": str(j.index[-1])[:10], "cop": rd(j.cop.iloc[-1], 0), "fx": rd(j.fx.iloc[-1], 0), "c_lb": rd(c_lb.iloc[-1], 1), "kc": rd(j.kc.iloc[-1], 2)}}
    if m is not None:
        m = m[m.month >= "2012-01"]
        kcm = w["KC1!"].resample("MS").mean(); kcm.index = kcm.index.strftime("%Y-%m")
        m["kc"] = m.month.map(kcm)
        out["monthly"] = {"month": m.month.tolist(), "exdock": [rd(v, 1) for v in m.exdock_c_lb], "kc": [rd(v, 1) for v in m.kc],
                          "diff": [rd(a - b, 1) if a == a and b == b else None for a, b in zip(m.exdock_c_lb, m.kc)],
                          "prod": [rd(v, 0) for v in m.prod_k_bags]}
        # coffee-year (Oct–Sep) production, cumulative
        p = m.dropna(subset=["prod_k_bags"]).copy()
        p["cy"] = [int(x[:4]) if int(x[5:]) >= 10 else int(x[:4]) - 1 for x in p.month]
        p["mi"] = [(int(x[5:]) - 10) % 12 for x in p.month]
        cy = {}
        for y, g in p.groupby("cy"):
            g = g.sort_values("mi")
            cy[str(y)] = {"cum": [rd(v / 1000, 2) for v in g.prod_k_bags.cumsum()], "total": rd(g.prod_k_bags.sum() / 1000, 2), "n": len(g)}
        out["prod_cy"] = cy
    if e is not None:
        e = e[e.month >= "2015-01"]
        out["exports"] = {"month": e.month.tolist(), "k_bags": [rd(v, 0) for v in e.exports_k_bags]}
    return out


def vietnam(w):
    v = read("vn_physical.csv")
    if v is None or v.empty:
        return None
    v["date"] = pd.to_datetime(v["date"]); v = v.groupby("date").vnd_kg.last()
    j = pd.concat([v.rename("vnd"), w["USDVND"].rename("fx"), w["RC1!"].rename("rc")], axis=1, sort=True).ffill(limit=7).dropna()
    j = j[j.index.isin(v.index)]
    usd = j.vnd * 1000 / j.fx
    return {"dates": [str(i)[:10] for i in j.index], "vnd": [rd(x, 0) for x in j.vnd], "usd_t": [rd(x, 0) for x in usd],
            "rc": [rd(x, 0) for x in j.rc], "diff": [rd(x, 0) for x in usd - j.rc],
            "now": {"date": str(j.index[-1])[:10], "vnd": rd(j.vnd.iloc[-1], 0), "fx": rd(j.fx.iloc[-1], 0), "usd_t": rd(usd.iloc[-1], 0), "rc": rd(j.rc.iloc[-1], 0)}}


def ico(w):
    g = read("ico_groups_monthly.csv")
    out = {}
    if g is not None:
        g = g[g.month >= "2012-01"]
        kcm = w["KC1!"].resample("MS").mean(); kcm.index = kcm.index.strftime("%Y-%m")
        rcm = (w["RC1!"] / LB_T).resample("MS").mean(); rcm.index = rcm.index.strftime("%Y-%m")
        k = g.month.map(kcm); r = g.month.map(rcm)
        out["groups"] = {"month": g.month.tolist(), "composite": [rd(v, 1) for v in g.composite],
                         "col": [rd(v, 1) for v in g.col_w], "oth": [rd(v, 1) for v in g.oth_w], "bra": [rd(v, 1) for v in g.bra_w],
                         "rob": [rd(v, 1) for v in g.get("rob_w", g.get("rob_eu"))],
                         "col_d": [rd(a - b, 1) for a, b in zip(g.col_w, k)], "oth_d": [rd(a - b, 1) for a, b in zip(g.oth_w, k)],
                         "bra_d": [rd(a - b, 1) for a, b in zip(g.bra_w, k)],
                         "rob_d": [rd(a - b, 1) for a, b in zip(g.get("rob_w", g.get("rob_eu")), r)]}
    s = read("ico_certified_stocks.csv")
    if s is not None:
        s = s.sort_values(["stock_month", "report_period"]).drop_duplicates("stock_month", keep="last")
        out["stocks"] = {"month": s.stock_month.tolist(), "ny": s.new_york_bags_millions.tolist(), "ldn": s.london_bags_millions.tolist()}
    e = read("ico_exports.csv")
    if e is not None:
        e = e.sort_values("export_month")
        e["cy"] = [int(x[:4]) if int(x[5:]) >= 10 else int(x[:4]) - 1 for x in e.export_month]
        roll = e.set_index("export_month")[["total", "arabicas", "robustas"]].rolling(12).sum().dropna()
        out["exports"] = {"month": e.export_month.tolist(), "total": e.total.tolist(), "arabicas": e.arabicas.tolist(), "robustas": e.robustas.tolist(),
                          "roll12": {"month": roll.index.tolist(), "total": [rd(v / 1000, 2) for v in roll.total],
                                     "arabicas": [rd(v / 1000, 2) for v in roll.arabicas], "robustas": [rd(v / 1000, 2) for v in roll.robustas]}}
    return out


def brazil_exports():
    frames = []
    for fn in ["exports_pre2015.csv", "exports_2015on.csv"]:
        p = os.path.join(TRADE, fn)
        if os.path.exists(p):
            x = pd.read_csv(p, dtype={"ncm": str}, usecols=["year", "month", "ncm", "commodity", "country_name", "kg_net", "fob_usd"])
            x = x[x.commodity == "coffee"].copy()
            # Secex NCM does not split arabica from conilon: 0901.1x green, 0901.2x roasted, 2101 soluble/extracts
            x["subtype"] = ["green" if n.startswith("09011") else "roasted" if n.startswith("0901") else "soluble" for n in x.ncm]
            frames.append(x)
    if not frames:
        return None
    d = pd.concat(frames)
    d["bags"] = d.kg_net / 60
    d = d[d.year >= 2012]
    d["cy"] = np.where(d.month >= 7, d.year, d.year - 1); d["mi"] = (d.month - 7) % 12
    m = d.pivot_table(index=["year", "month"], columns="subtype", values="bags", aggfunc="sum").fillna(0).reset_index()
    fob = d.groupby(["year", "month"]).fob_usd.sum().values
    m["usd_bag"] = fob / m[[c for c in m.columns if c not in ("year", "month")]].sum(axis=1)
    tot = d.groupby(["cy", "mi"]).bags.sum().reset_index()
    cy = {}
    for y, g in tot.groupby("cy"):
        g = g.sort_values("mi")
        cy[str(y)] = {"cum": [rd(v / 1e6, 3) for v in g.bags.cumsum()], "total": rd(g.bags.sum() / 1e6, 2), "n": len(g)}
    ly, lm = int(m.year.iloc[-1]), int(m.month.iloc[-1])
    k = (lm - 7) % 12; cur = ly if lm >= 7 else ly - 1
    cur_d = d[(d.cy == cur) & (d.mi <= k)].groupby("country_name").bags.sum()
    prv_d = d[(d.cy == cur - 1) & (d.mi <= k)].groupby("country_name").bags.sum()
    dest = [{"country": c, "bags": rd(v / 1e6, 3), "prev": rd(prv_d.get(c, 0) / 1e6, 3)} for c, v in cur_d.sort_values(ascending=False).head(12).items()]
    sub = {s: [rd(v / 1e6, 3) for v in m.tail(36).get(s, pd.Series([0] * 36))] for s in ["green", "roasted", "soluble"]}
    # Belgium (Antwerp hosts ICE certified warehouses): unusual green-coffee flows there can precede certification
    gb = d[(d.subtype == "green") & (d.country_name == "Belgium")].groupby(["year", "month"]).bags.sum()
    gt = d[d.subtype == "green"].groupby(["year", "month"]).bags.sum()
    bel = pd.DataFrame({"bel": gb, "tot": gt}).fillna(0).reset_index()
    bel["ym"] = [f"{a}-{b:02d}" for a, b in zip(bel.year, bel.month)]
    bel["avg3"] = [bel[(bel.month == m) & (bel.year.between(y - 3, y - 1))].bel.mean() for y, m in zip(bel.year, bel.month)]
    bel = bel[bel.year >= 2018]
    cs = read("ico_certified_stocks.csv")
    certs = {}
    if cs is not None:
        cs = cs.sort_values(["stock_month", "report_period"]).drop_duplicates("stock_month", keep="last")
        certs = dict(zip(cs.stock_month, cs.new_york_bags_millions))
    last3 = bel.tail(3)
    belgium = {"ym": bel.ym.tolist(), "bags": [rd(v / 1e3, 0) for v in bel.bel], "avg3": [rd(v / 1e3, 0) for v in bel.avg3],
               "share": [rd(a / b * 100, 1) if b else None for a, b in zip(bel.bel, bel.tot)], "certs_ny": [certs.get(m) for m in bel.ym],
               "now": {"last3": rd(last3.bel.sum() / 1e3, 0), "avg3_last3": rd(last3.avg3.sum() / 1e3, 0),
                       "vs_avg": rd((last3.bel.sum() / last3.avg3.sum() - 1) * 100, 0) if last3.avg3.sum() else None,
                       "share": rd(last3.bel.sum() / last3.tot.sum() * 100, 1), "months": f"{last3.ym.iloc[0]} to {last3.ym.iloc[-1]}"}}
    return {"belgium": belgium, "last": f"{ly}-{lm:02d}", "cur_cy": cur, "k": k, "cy": cy, "dest": dest,
            "monthly": {"ym": [f"{a}-{b:02d}" for a, b in zip(m.year.tail(36), m.month.tail(36))], **sub, "usd_bag": [rd(v, 0) for v in m.usd_bag.tail(36)]}}


def psd():
    d = read("psd_coffee.csv")
    if d is None:
        return None
    d = d[d.Market_Year >= 2008]
    attrs = {"Production": "prod", "Arabica Production": "ara", "Robusta Production": "rob", "Bean Exports": "exp",
             "Domestic Consumption": "cons", "Ending Stocks": "end"}
    out = {}
    for cc, name in [("BR", "Brazil"), ("VM", "Vietnam"), ("CO", "Colombia"), ("ID", "Indonesia"), ("ET", "Ethiopia"), ("HO", "Honduras"), ("UG", "Uganda"), ("IN", "India")]:
        g = d[d.Country_Code == cc]
        if g.empty:
            continue
        p = g.pivot_table(index="Market_Year", columns="Attribute_Description", values="Value")
        out[name] = {"years": p.index.tolist(), **{k: [rd(v / 1000, 2) for v in p.get(a, pd.Series(index=p.index, dtype=float))] for a, k in attrs.items()}}
    wsum = d.groupby(["Market_Year", "Attribute_Description"]).Value.sum().unstack()
    out["World"] = {"years": wsum.index.tolist(), **{k: [rd(v / 1000, 2) for v in wsum.get(a, pd.Series(index=wsum.index, dtype=float))] for a, k in attrs.items()}}
    return out


def structure(w):
    """Front KC spread (inversion) vs certified stocks and vs the cost of carrying coffee for one roll (~2 months)."""
    q = w[["KC1!", "KC2!"]].dropna()
    q = q[q.index >= "2012-01-01"]
    rate = w["US03MY"].reindex(q.index).ffill().fillna(4.0) if "US03MY" in w else pd.Series(4.0, index=q.index)
    spread = q["KC1!"] - q["KC2!"]                         # + = front over second (inversion)
    carry = q["KC1!"] * rate / 100 * 61 / 360              # financing one 2-month roll, ¢/lb
    wk = pd.concat([spread.rename("sp"), carry.rename("carry"), rate.rename("r")], axis=1).resample("W-FRI").last()
    out = {"dates": [str(i)[:10] for i in wk.index], "spread": [rd(v, 2) for v in wk.sp], "carry": [rd(v, 2) for v in wk.carry],
           "now": {"spread": rd(spread.iloc[-1], 2), "carry": rd(carry.iloc[-1], 2), "rate": rd(rate.iloc[-1], 2), "date": str(q.index[-1])[:10],
                   "pct5y": rd((spread[spread.index >= spread.index[-1] - timedelta(days=1826)] <= spread.iloc[-1]).mean() * 100, 0)}}
    s = read("ico_certified_stocks.csv")
    if s is not None:
        s = s.sort_values(["stock_month", "report_period"]).drop_duplicates("stock_month", keep="last")
        ms = spread.resample("MS").mean(); ms.index = ms.index.strftime("%Y-%m")
        pts = [{"x": rd(r.new_york_bags_millions, 2), "y": rd(ms.get(r.stock_month), 2), "m": r.stock_month}
               for r in s.itertuples() if r.stock_month in ms.index]
        out["vs_certs"] = pts
    return out


def cot():
    c = read("cot_coffee.csv")
    if c is None or c.empty:
        return None
    c = c.sort_values("date"); c = c[c.date >= "2015-01-01"]
    net = c.managed_money_net
    pct = (net.tail(260) <= net.iloc[-1]).mean() * 100
    pms = c.prod_merc_short
    pm5 = pms.rolling(260, min_periods=100).mean()
    return {"pm_short": pms.tolist(), "pm_short_5y": [rd(v, 0) for v in pm5],
            "pm_now": {"short": int(pms.iloc[-1]), "avg5y": rd(pm5.iloc[-1], 0)},
            "dates": c.date.tolist(), "mm_net": c.managed_money_net.tolist(), "mm_long": c.managed_money_long.tolist(),
            "mm_short": c.managed_money_short.tolist(), "pm_net": c.prod_merc_net.tolist(), "oi": c.open_interest.tolist(),
            "now": {"date": c.date.iloc[-1], "mm_net": int(net.iloc[-1]), "chg": int(net.iloc[-1] - net.iloc[-2]), "pct5y": rd(pct, 0),
                    "oi": int(c.open_interest.iloc[-1])}}


def main():
    w, snap = prices()
    res = {"built": str(date.today()), "snapshot": snap, "arb": arb(w), "curves": curves(), "brazil": brazil(w),
           "colombia": colombia(w), "vietnam": vietnam(w), "ico": ico(w), "br_exports": brazil_exports(), "psd": psd(), "cot": cot(), "structure": structure(w),
           "constants": {"lb_t": LB_T, "lb_bag": LB_BAG, "col_lb_carga": rd(COL_LB_CARGA, 2)}}
    est = os.path.join(DATA, "estimates.json")
    res["estimates"] = json.load(open(est)) if os.path.exists(est) else []
    with open(os.path.join(DATA, "coffee.json"), "w") as fh:
        json.dump(res, fh, separators=(",", ":"))
    print("built coffee.json", os.path.getsize(os.path.join(DATA, "coffee.json")) // 1024, "KB")


if __name__ == "__main__":
    main()
