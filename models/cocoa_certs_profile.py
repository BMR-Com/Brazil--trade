"""ICE Cocoa (US) certified-stock profile and delivery value -> data/cocoa/certs_profile.json.

Reads only files in this repo:
  data/cocoa/ice_certs_daily.csv        ICE daily certified stock by origin, growth group and port (from Oct 2026)
  data/cocoa/ice_grading_monthly.csv    ICE grading results per month, port, origin, class, initial/regrade (2016 on)
  data/cocoa/ref/cc_rule_params.json    ICE cocoa rule values (group premiums, grade/count/slate rules)
  data/cocoa/ref/rule_changes.csv       dated rule-change timeline with sources
  data/contracts/CC.csv                 CC settlements by contract
  data/cocoa/cc_spreads_history.csv     daily front/second spreads (models/softs_spreads_history.py)

Delivery value of a certified lot against the futures ($/t) = growth-group premium (from the class on ICE's daily
report) - weight discount (count and waste, % of invoice weight x futures) - slate discount, the last two taken as the
tonnage-weighted average of ICE's grading results for that origin and port over the last 12 months. There is no port
differential in cocoa. Age since first grading is estimated (newest initial gradings fill the stock first).
Any missing input or failed check raises, so the workflow step fails.
"""
import json
import math
import os
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CO = os.path.join(ROOT, "data", "cocoa")
OUT = os.path.join(CO, "certs_profile.json")
PORT = {"DR": "Delaware River", "NY": "New York", "BA": "Baltimore", "HR": "Hampton Roads", "AL": "Albany"}
MC = {"H": 3, "K": 5, "N": 7, "U": 9, "Z": 12}
AGE = [(0, 182, "under 6 m"), (183, 365, "6–12 m"), (366, 730, "1–2 yrs"), (731, 1095, "2–3 yrs"), (1096, 99999, "over 3 yrs")]


def rd(v, n=2):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), n)


def need(path):
    p = os.path.join(ROOT, path)
    if not os.path.exists(p):
        raise SystemExit(f"missing input: {path}")
    return p


P = json.load(open(need("data/cocoa/ref/cc_rule_params.json")))
daily = pd.read_csv(need("data/cocoa/ice_certs_daily.csv"), parse_dates=["date"])
grad = pd.read_csv(need("data/cocoa/ice_grading_monthly.csv")).dropna(subset=["origin"])
rules = pd.read_csv(need("data/cocoa/ref/rule_changes.csv")).fillna("")
cc = pd.read_csv(need("data/contracts/CC.csv"), parse_dates=["date"])
spr = pd.read_csv(need("data/cocoa/cc_spreads_history.csv"), parse_dates=["date"])
out = {"built": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
ckey = lambda c: (int(c[-4:]), MC[c[-5]])

# --------------------------------------------------------------------------------------------- current stock
D = daily.date.max()
cur = daily[(daily.date == D) & (daily.section == "certified")].copy()
cur = cur[cur.bags > 0]
if cur.empty:
    raise SystemExit("no certified rows on the latest date")
cur["t"] = cur.lots * P["lot_t"]
cur["kg_bag"] = cur.t * 1000 / cur.bags
tot_bags, tot_lots = float(cur.bags.sum()), float(cur.lots.sum())
pend = daily[(daily.date == D) & (daily.section == "pending_grading")]
passed = daily[(daily.date == D) & (daily.section == "passed_grading")]
wh = daily[(daily.date == D) & (daily.section == "warehouse_total")]

# futures: delivery month in progress and the next contract
px = cc.pivot_table(index="date", columns="contract", values="close")
fdate = px.index.max()
live = sorted([c for c in px.columns if px[c].dropna().index.max() == fdate], key=ckey)
nxt = spr[spr.date == spr.date.max()].iloc[0]
front, second = nxt.front, nxt.second                         # front after the first-notice roll (e.g. Mar 27)
spot = live[0]                                                 # contract still trading (may be in its delivery period)
F = float(px[front].dropna().iloc[-1])
Fs = float(px[spot].dropna().iloc[-1])

# grading-based discounts, last 12 months, by origin x port (fallback origin, then all)
g12 = grad[grad.month > (pd.Timestamp(grad.month.max() + "-01") - pd.DateOffset(months=12)).strftime("%Y-%m")]
w = lambda d, c: float((d[c].fillna(0) * d.tonnes).sum() / d.tonnes.sum()) if d.tonnes.sum() > 0 else float("nan")


def disc(o, p):
    for d, lev in [(g12[(g12.origin == o) & (g12.port == p)], "origin and port"), (g12[g12.origin == o], "origin, all ports"),
                   (grad[grad.origin == o], "origin, since 2016"), (g12, "all cocoa graded")]:
        if d.tonnes.sum() >= 50:
            return w(d, "avg_weight_disc_pct"), w(d, "avg_slate_disc_usd_t"), lev, float(d.tonnes.sum())
    return 0.0, 0.0, "none", 0.0


rows = []
for r in cur.itertuples():
    wt, sl, lev, base = disc(r.origin, r.port)
    prem = P["group_premium_usd_t"].get(str(r.growth_group), 0)
    v = prem - wt / 100 * F + sl
    rows.append({"origin": r.origin, "port": PORT.get(r.port, r.port), "port_code": r.port, "group": r.growth_group, "bags": float(r.bags),
                 "lots": float(r.lots), "t": float(r.t), "kg_bag": float(r.kg_bag), "premium": prem, "weight_pct": wt,
                 "weight_usd": -wt / 100 * F, "slate": sl, "value": v, "value_spot": prem - wt / 100 * Fs + sl, "disc_basis": lev, "disc_tonnes": base})
X = pd.DataFrame(rows)
if abs(X.bags.sum() - tot_bags) > 1:
    raise SystemExit("rows do not add to the certified total")

# estimated age since first grading: newest initial gradings (origin x port) fill the stock first
ini = grad[grad.grade_type == "initial"].groupby(["origin", "port", "month"]).tonnes.sum()
age_rows = []
for r in X.itertuples():
    left = r.t
    try:
        s = ini.loc[(r.origin, r.port_code)].sort_index(ascending=False)
    except KeyError:
        s = pd.Series(dtype=float)
    for m, t in s.items():
        if left <= 0:
            break
        take = min(left, t)
        age_rows.append((r.origin, r.port, (D - pd.Timestamp(m + "-15")).days, take))
        left -= take
    if left > 0:
        age_rows.append((r.origin, r.port, 99999, left))       # older than the grading file (before 2016)
AG = pd.DataFrame(age_rows, columns=["origin", "port", "days", "t"])
AG["grp"] = pd.cut(AG.days, [-1] + [a[1] for a in AGE], labels=[a[2] for a in AGE])
age_tab = AG.pivot_table(index="origin", columns="grp", values="t", aggfunc="sum", observed=False).fillna(0)
age_port = AG.pivot_table(index="port", columns="grp", values="t", aggfunc="sum", observed=False).fillna(0)
known = AG[AG.days < 99999]
avg_age = float((known.days * known.t).sum() / known.t.sum()) if len(known) else None
regr12 = float(g12[g12.grade_type == "regrade"].tonnes.sum())

# ------------------------------------------------ grade validity (Rule 9.18(d)(ii)), regrade, weight allowance (9.23(b))
DM = [3, 5, 7, 9, 12]


def dperiods_after(y, m, k):
    """k-th delivery month strictly after (y, m)."""
    out = []
    while len(out) < k:
        m += 1
        if m > 12:
            y, m = y + 1, 1
        if m in DM:
            out.append((y, m))
    return out[-1]


def valid_through(d):
    """Grade validity of a certificate issued on date d: issued in a delivery month -> rest of it and the next delivery
    period; issued outside -> the next two delivery periods. The delivery period is taken as the delivery month."""
    y, m = d.year, d.month
    yy, mm = dperiods_after(y, m, 1 if m in DM else 2)
    return f"{yy}-{mm:02d}"


# grading events (initial and regrade) by origin x port: monthly file, then daily passes after the last monthly period
ev = grad.assign(d=pd.to_datetime(grad.period_end)).groupby(["origin", "port", "d"]).tonnes.sum().reset_index()
last_m = pd.to_datetime(grad.period_end).max()
pp = daily[daily.section == "passed_grading"].pivot_table(index="date", columns="origin", values="lots", aggfunc="sum").fillna(0).sort_index()
pp = pp[pp.index >= last_m]
dpass = pp.diff().clip(lower=0).iloc[1:] * P["lot_t"] if len(pp) > 1 else pd.DataFrame()
port_share = (cur.groupby(["origin", "port"]).t.sum() / cur.groupby("origin").t.sum()).to_dict()
extra = []
for dt, r in dpass.iterrows():
    for o, t in r.items():
        if t > 0:
            for (oo, pt), sh in port_share.items():
                if oo == o:
                    extra.append({"origin": o, "port": pt, "d": dt, "tonnes": t * sh})
ev = pd.concat([ev, pd.DataFrame(extra)]) if extra else ev
evg = ev.groupby(["origin", "port", "d"]).tonnes.sum()
nxt_m = f"{front[-4:]}-{MC[front[-5]]:02d}"
after_m = f"{second[-4:]}-{MC[second[-5]]:02d}"
vrows = []
for r in X.itertuples():
    left = r.t
    try:
        es = evg.loc[(r.origin, r.port_code)].sort_index(ascending=False)
    except KeyError:
        es = pd.Series(dtype=float)
    for d, t in es.items():
        if left <= 0:
            break
        take = min(left, t)
        vrows.append((r.origin, r.port, valid_through(d), d.strftime("%Y-%m"), take))
        left -= take
    if left > 0:
        vrows.append((r.origin, r.port, "unknown (older)", "before file", left))
V = pd.DataFrame(vrows, columns=["origin", "port", "valid_through", "graded", "t"])
V["needs_regrade_front"] = V.valid_through < nxt_m
V["needs_regrade_second"] = V.valid_through < after_m

# regrade outcome: discount change on regrade vs first grading, same origin (last 3 years), and how much of the
# lapsing stock comes back as regrades (cohort survival) by delivery period
g3 = grad[grad.month >= (pd.Timestamp(grad.month.max() + "-01") - pd.DateOffset(years=3)).strftime("%Y-%m")]
def chg(o):
    d = g3[g3.origin == o] if g3[g3.origin == o].tonnes.sum() > 200 else g3
    a, b = d[d.grade_type == "initial"], d[d.grade_type == "regrade"]
    if a.tonnes.sum() == 0 or b.tonnes.sum() == 0:
        d = g3; a, b = d[d.grade_type == "initial"], d[d.grade_type == "regrade"]
    return (w(b, "avg_weight_disc_pct") - w(a, "avg_weight_disc_pct"), w(b, "group_premium_usd_t") - w(a, "group_premium_usd_t"))


ge = grad.assign(d=pd.to_datetime(grad.period_end))
ge["vt"] = ge.d.map(valid_through)
periods = sorted({f"{y}-{m:02d}" for y in range(2016, 2028) for m in DM})
surv = []
for i in range(1, len(periods)):
    prev, cur_p = periods[i - 1], periods[i]
    lapsing = float(ge[ge.vt == prev].tonnes.sum())
    win = ge[(ge.grade_type == "regrade") & (ge.month > prev) & (ge.month <= cur_p)]
    if lapsing > 500 and cur_p <= grad.month.max():
        surv.append({"period": cur_p, "lapsing_t": rd(lapsing, 0), "regraded_t": rd(float(win.tonnes.sum()), 0),
                     "share": rd(float(win.tonnes.sum()) / lapsing * 100, 0)})
sv = pd.DataFrame(surv)
surv_med = float(sv.share.tail(8).clip(upper=100).median()) / 100 if len(sv) else float("nan")   # last 8 delivery periods

days_to = (pd.Timestamp(nxt_m + "-15") - D).days
wa = []
for r in X.itertuples():
    a = AG[(AG.origin == r.origin) & (AG.port == r.port)]
    dd = a.days.where(a.days < 99999, 1200) + days_to             # days from the weight date (first grading) to delivery
    pct = (0.25 * np.ceil(dd / 30) * a.t).sum() / a.t.sum() if a.t.sum() else 0.0
    vv = V[(V.origin == r.origin) & (V.port == r.port)]
    need = float(vv[vv.needs_regrade_front].t.sum() / vv.t.sum()) if vv.t.sum() else 0.0
    dw, dprem = chg(r.origin)
    rg = (dprem - dw / 100 * F) * need                               # expected value change for the share that must be regraded
    wa.append((pct, -pct / 100 * F, need, rg))
X["allow_pct"], X["allow_usd"], X["regrade_share"], X["regrade_usd"] = zip(*wa)
X["value_before_allow"] = X.value
X["value"] = X.value + X.allow_usd + X.regrade_usd
validity = {
    "front_month": nxt_m, "second_month": after_m, "days_to_front": days_to,
    "by_cell": [{"origin": o, "port": pt, "valid_through": vt, "lots": rd(t / P["lot_t"], 0)}
                for (o, pt, vt), t in V.groupby(["origin", "port", "valid_through"]).t.sum().items()],
    "by_valid": {vt: rd(t / P["lot_t"], 0) for vt, t in V.groupby("valid_through").t.sum().items()},
    "need_front_lots": rd(float(V[V.needs_regrade_front].t.sum()) / P["lot_t"], 0),
    "need_second_lots": rd(float(V[V.needs_regrade_second].t.sum()) / P["lot_t"], 0),
    "survival": surv, "survival_median_pct": rd(surv_med * 100, 0), "survival_basis": "median of the last 8 delivery periods",
    "survival_range_last8": [rd(float(sv.share.tail(8).min()), 0), rd(float(sv.share.tail(8).max()), 0)],
    "at_risk_lots": rd(float(V[V.needs_regrade_front].t.sum()) / P["lot_t"] * (1 - min(1.0, surv_med)), 0),
    "regrade_change": {o: {"weight_pct": rd(chg(o)[0], 2), "premium": rd(chg(o)[1], 1)} for o in sorted(X.origin.unique())},
}

# cheapest to deliver order (lowest value first)
X = X.sort_values("value").reset_index(drop=True)
X["cum_lots"] = X.lots.cumsum()
wl = lambda d, c: float((d[c] * d.lots).sum() / d.lots.sum())
ctd = []
for n in [500, 1000, 2500]:
    if X.lots.sum() > n:
        k = X[X.cum_lots - X.lots < n].copy()
        k.loc[k.index[-1], "lots"] -= k.cum_lots.iloc[-1] - n
        ctd.append({"lots": n, "avg": rd(wl(k, "value"), 1), "worst": rd(k.value.min(), 1), "best": rd(k.value.max(), 1)})
ctd.append({"lots": "all", "avg": rd(wl(X, "value"), 1), "worst": rd(X.value.min(), 1), "best": rd(X.value.max(), 1)})

by_origin = []
for o, d in X.groupby("origin"):
    by_origin.append({"origin": o, "bags": rd(d.bags.sum(), 0), "lots": rd(d.lots.sum(), 0), "t": rd(d.t.sum(), 0),
                      "premium": rd(wl(d, "premium"), 0), "weight_pct": rd(wl(d, "weight_pct"), 2), "weight_usd": rd(wl(d, "weight_usd"), 1),
                      "slate": rd(wl(d, "slate"), 1), "allow_pct": rd(wl(d, "allow_pct"), 2), "allow_usd": rd(wl(d, "allow_usd"), 1),
                      "regrade_share": rd(wl(d, "regrade_share") * 100, 0), "regrade_usd": rd(wl(d, "regrade_usd"), 1),
                      "value_before_allow": rd(wl(d, "value_before_allow"), 1), "value": rd(wl(d, "value"), 1),
                      "pending_bags": rd(float(pend[pend.origin == o].bags.sum()), 0),
                      "age": {a[2]: rd(float(age_tab.loc[o, a[2]]) if o in age_tab.index else 0, 0) for a in AGE},
                      "older_than_file_t": rd(float(AG[(AG.origin == o) & (AG.days == 99999)].t.sum()), 0)})
by_origin.sort(key=lambda r: -r["lots"])

# --------------------------------------------------------------------------------------------------- history
daily_c = daily[daily.section == "certified"]
dh = daily_c.pivot_table(index="date", columns="origin", values="lots", aggfunc="sum").fillna(0)
top = list(dh.sum().sort_values(ascending=False).index[:6])
dh["Other"] = dh.drop(columns=top).sum(axis=1)
grad["grp"] = grad["class"].fillna("?")
gm = grad.pivot_table(index="month", columns=["grade_type"], values="tonnes", aggfunc="sum").fillna(0)
gg = grad[grad.grade_type == "initial"].pivot_table(index="month", columns="grp", values="tonnes", aggfunc="sum").fillna(0)
months = sorted(gm.index)
# front-month average futures per month for the value of new gradings
cc["m"] = cc.date.dt.strftime("%Y-%m")
sp_m = spr.assign(m=spr.date.dt.strftime("%Y-%m")).groupby("m").f1.mean()
gval = []
for m in months:
    d = grad[(grad.month == m) & (grad.grade_type == "initial")]
    f = sp_m.get(m)
    if d.tonnes.sum() <= 0 or f is None:
        gval.append(None)
        continue
    gval.append(rd(w(d, "group_premium_usd_t") - w(d, "avg_weight_disc_pct") / 100 * f + w(d, "avg_slate_disc_usd_t"), 1))
out["history"] = {
    "daily": {"dates": [d.strftime("%Y-%m-%d") for d in dh.index], "series": {c: [rd(v, 0) for v in dh[c]] for c in top + ["Other"]},
              "total_lots": [rd(v, 0) for v in daily_c.groupby("date").lots.sum()]},
    "grading": {"months": months, "initial_t": [rd(gm.loc[m].get("initial", 0), 0) for m in months],
                "regrade_t": [rd(gm.loc[m].get("regrade", 0), 0) for m in months],
                "initial_by_class": {c: [rd(gg.loc[m, c], 0) if m in gg.index else 0 for m in months] for c in ["A", "B", "C"] if c in gg},
                "value_new": gval},
    "yearly": [{"year": y, "initial_t": rd(gm[gm.index.str[:4] == y].get("initial", pd.Series(dtype=float)).sum(), 0),
                "regrade_t": rd(gm[gm.index.str[:4] == y].get("regrade", pd.Series(dtype=float)).sum(), 0)} for y in sorted({m[:4] for m in months})],
    "markers": [{"date": r.effective_date[:7], "label": r.short} for r in rules.itertuples() if r.effective_date >= "2016"],
}

# spreads vs history with rule markers
s = spr[spr.date >= "2004-01-01"]
sm = s.assign(m=s.date.dt.strftime("%Y-%m")).groupby("m").agg(s12=("s12", "mean"), f1=("f1", "mean"))
pair = nxt.pair12
same = spr[(spr.pair12 == pair) & ((spr.bd_to_fnd - int(nxt.bd_to_fnd)).abs() <= 2)]
same = same.assign(y=same.front.str[-4:]).groupby("y").agg(s12=("s12", "mean"), f1=("f1", "mean")).reset_index()
same["pct"] = same.s12 / same.f1 * 100
out["spreads"] = {"months": list(sm.index), "s12": [rd(v, 0) for v in sm.s12], "s12_pct": [rd(v, 2) for v in sm.s12 / sm.f1 * 100],
                  "now": {"date": nxt.date.strftime("%Y-%m-%d"), "pair": pair, "front": front, "second": second, "s12": rd(nxt.s12, 0),
                          "pct": rd(nxt.s12 / nxt.f1 * 100, 2), "bd_to_fnd": int(nxt.bd_to_fnd), "s23": rd(nxt.s23, 0), "pair23": nxt.pair23},
                  "same_point": [{"year": r.y, "s12": rd(r.s12, 0), "pct": rd(r.pct, 2)} for r in same.itertuples()],
                  "first": s.date.min().strftime("%Y-%m-%d")}

out["current"] = {"date": D.strftime("%Y-%m-%d"), "bags": rd(tot_bags, 0), "lots": rd(tot_lots, 0), "tonnes": rd(tot_lots * P["lot_t"], 0),
                  "first_report": daily_c.date.min().strftime("%Y-%m-%d"),
                  "first_lots": rd(float(daily_c[daily_c.date == daily_c.date.min()].lots.sum()), 0),
                  "pending_bags": rd(float(pend.bags.sum()), 0), "pending_lots": rd(float(pend.lots.sum()), 0),
                  "warehouse_bags": {PORT.get(r.port, r.port): rd(r.bags, 0) for r in wh.itertuples()},
                  "by_port": {PORT.get(p, p): rd(float(d.lots.sum()), 0) for p, d in cur.groupby("port")},
                  "by_group": {str(g): rd(float(d.lots.sum()), 0) for g, d in cur.groupby("growth_group")},
                  "avg_age_days_known": rd(avg_age, 0), "older_than_file_t": rd(float(AG[AG.days == 99999].t.sum()), 0),
                  "regrade_12m_t": rd(regr12, 0), "initial_12m_t": rd(float(g12[g12.grade_type == "initial"].tonnes.sum()), 0),
                  "age_groups": [a[2] for a in AGE],
                  "age_by_port": [{"port": p, "t": [rd(age_port.loc[p, a[2]], 0) for a in AGE]} for p in age_port.index]}
out["economics"] = {
    "futures": {"front": front, "front_settle": rd(F, 0), "spot": spot, "spot_settle": rd(Fs, 0), "date": fdate.strftime("%Y-%m-%d"),
                "second": second, "second_settle": rd(float(px[second].dropna().iloc[-1]), 0)},
    "all": {"value": rd(wl(X, "value"), 1), "premium": rd(wl(X, "premium"), 1), "weight_usd": rd(wl(X, "weight_usd"), 1),
            "weight_pct": rd(wl(X, "weight_pct"), 2), "slate": rd(wl(X, "slate"), 1), "value_spot": rd(wl(X, "value_spot"), 1),
            "allow_usd": rd(wl(X, "allow_usd"), 1), "allow_pct": rd(wl(X, "allow_pct"), 2), "regrade_usd": rd(wl(X, "regrade_usd"), 1),
            "value_before_allow": rd(wl(X, "value_before_allow"), 1)},
    "validity": validity,
    "ctd": ctd, "by_origin": by_origin,
    "cells": [{"origin": r.origin, "port": r.port, "group": r.group, "lots": rd(r.lots, 0), "cum_lots": rd(r.cum_lots, 0),
               "premium": r.premium, "weight_pct": rd(r.weight_pct, 2), "weight_usd": rd(r.weight_usd, 1), "slate": rd(r.slate, 1),
               "allow_usd": rd(r.allow_usd, 1), "regrade_usd": rd(r.regrade_usd, 1), "regrade_share": rd(r.regrade_share * 100, 0),
               "value": rd(r.value, 1), "basis": r.disc_basis} for r in X.itertuples()],
}
# physical comparison: what is defensible from public data
out["physical"] = {
    "lid_usd_t": P["lid_usd_t"], "group_a": P["group_premium_usd_t"]["A"],
    "west_africa_gap": P["lid_usd_t"] - P["group_premium_usd_t"]["A"],
    "note": "No public, dated series of physical cocoa differentials (Ivory Coast, Ghana, Ecuador, Nigeria vs London/NY) was found; "
            "ICCO's daily price is an average of London and New York futures, not a differential, and farmgate prices are not "
            "differentials. Only the fixed Living Income Differential on Ivorian and Ghanaian forward sales is a public physical premium.",
    "confidence": "low",
}
out["rules"] = {"source": P["source_url"], "read_on": P["read_on"], "premiums": P["group_premium_usd_t"], "groups": P["groups"],
                "count_classes": P["count_classes"], "count_disc_pct": P["count_disc_pct"], "slate": P["slate"], "defects": P["defects"],
                "waste": P["waste"], "certificate_validity": P["certificate_validity"], "grade_validity_rule": P["grade_validity_rule"], "weight_loss_allowance": P["weight_loss_allowance"],
                "weight": P["weight"], "customs": P["customs"], "eudr": P["eudr"], "port_note": P["port_note"], "load_out": P["load_out"],
                "changes": rules.to_dict("records")}
out["variables"] = ["ICE daily cocoa certified stock by origin, growth group and port (from Oct 2026)",
                    "ICE monthly grading results by port, origin and class: tonnes, group premium, weight (count and waste) discount, slate discount, initial vs regrade (2016 on)",
                    "ICE Cocoa rulebook: group premiums, count classes, slate, waste and weight rules, certificate validity",
                    "CC settlements by contract (2004 on) and daily front/second spreads",
                    "Living Income Differential (Côte d'Ivoire, Ghana)"]
out["checks"] = {"rows_bags": rd(X.bags.sum(), 0), "certified_bags": rd(tot_bags, 0), "age_t": rd(AG.t.sum(), 0), "stock_t": rd(X.t.sum(), 0)}
if abs(AG.t.sum() - X.t.sum()) > 1:
    raise SystemExit("age split does not add to the stock")
json.dump(out, open(OUT, "w"), separators=(",", ":"), allow_nan=False)
print(f"cocoa certs profile: {tot_lots:,.0f} lots on {D.date()}, avg delivery value {wl(X, 'value'):+.0f} $/t vs {front} {F:.0f}")
