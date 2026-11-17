"""ICE Coffee "C" certified-stock profile and delivery economics -> data/coffee/certs_profile.json.

Reads only files in this repo:
  data/coffee/ice_certs_eom_by_port.csv   month-end certs by port, 1996 on
  data/coffee/ice_aging_history.csv       monthly aging by port and 30-day age bucket, 2016 on (ages to the next delivery)
  data/coffee/ice_certs_daily_detail.csv  daily certs by origin and port, with passes, pending and EUDR transition bags
  data/coffee/ice_certs.csv               daily certs by origin and port (automatic feed, sparse before Sep 2026)
  data/coffee/ice_grading_monthly.csv     monthly grading passes by origin (lots), Oct 2022 on
  data/coffee/ref/kc_rule_params.json     ICE rule parameters by version (origin, port, age, weight, OCA/RCA, EUDR)
  data/coffee/ref/rule_changes.csv        dated rule-change timeline
  data/coffee/ref/warehouse_rates.csv     storage / load-out / OCA / RCA by warehouse (owner names are never written out)
  data/contracts/KC.csv                   KC settlements by contract
  coffee/data/ico_groups_monthly.csv      ICO group indicator prices by market (EU / NY) and the ICO New York average
  coffee/data/ico_prices.csv
  coffee/data/coffee.json                 Brazil basis ladder (export qualities)

Any missing input or failed check raises, so the workflow step fails.
"""
import json
import math
import os
import sys
from datetime import date, datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CF = os.path.join(ROOT, "data", "coffee")
OUT = os.path.join(CF, "certs_profile.json")
LB_KG = 2.20462
SHORT = {"ANT": "ANTWERP", "HA/BR": "HAMBURG / BREMEN", "BAR": "BARCELONA", "HOU": "HOUSTON", "NOLA": "NEW ORLEANS",
         "MIAMI": "MIAMI", "NY": "NEW YORK", "VA": "VIRGINIA"}
PORT_LABEL = {"ANTWERP": "Antwerp", "HAMBURG / BREMEN": "Hamburg/Bremen", "BARCELONA": "Barcelona", "HOUSTON": "Houston",
              "NEW ORLEANS": "New Orleans", "MIAMI": "Miami", "NEW YORK": "New York", "VIRGINIA": "Virginia"}
EU = {"ANTWERP", "HAMBURG / BREMEN", "BARCELONA"}
AGE_GROUPS = [(0, 120, "0–120 d"), (121, 360, "121–360 d"), (361, 720, "1–2 yrs"), (721, 1080, "2–3 yrs"), (1081, 99999, "over 3 yrs")]
ICO_GROUP = {"Colombia": "col", "Brazil": "bra"}           # everything else -> Other Milds ("oth")
ICO_NAME = {"col": "Colombian Milds", "oth": "Other Milds", "bra": "Brazilian Naturals"}
MCODE = {3: "H", 5: "K", 7: "N", 9: "U", 12: "Z"}


def rd(v, n=2):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), n)


def need(path):
    p = os.path.join(ROOT, path)
    if not os.path.exists(p):
        raise SystemExit(f"missing input: {path}")
    return p


P = json.load(open(need("data/coffee/ref/kc_rule_params.json")))


def version(key, delivery):
    """Rule version in force for a delivery month 'YYYY-MM'."""
    vs = [v for v in P[key] if v["from_delivery"] <= delivery]
    if not vs:
        raise SystemExit(f"no {key} for {delivery}")
    return vs[-1]


def age_pts(days, delivery):
    v = version("age_discount_versions", delivery)
    if days <= v["first_free_days"]:
        return 0.0
    if days <= 150:
        return float(v["first_step_pts"])
    for lo, hi, base, step in v["bands"]:
        if days <= hi:
            return float(base + step * math.ceil((days - lo) / 30))
    lo, hi, base, step = v["bands"][-1]
    return float(base + step * math.ceil((days - lo) / 30))


def bag_lb(origin):
    k = P["bag_kg_by_origin"]
    return k.get(origin, k["default"]) * LB_KG


def weight_pct(age_days):
    """Appendix V (14): 0.5% for the 2nd calendar month after weighing + 0.125% per further month. Weighing taken as
    ~15 days before the grading certificate."""
    m = math.ceil((age_days + 15) / 30.44)
    w = P["weight_allowance"]
    return 0.0 if m < 2 else w["second_month_pct"] + w["per_month_after_pct"] * (m - 2)


# ----------------------------------------------------------------------------------------------------------- inputs
eom = pd.read_csv(need("data/coffee/ice_certs_eom_by_port.csv"), parse_dates=["date"])
aging = pd.read_csv(need("data/coffee/ice_aging_history.csv"), parse_dates=["date", "delivery"])
det = pd.read_csv(need("data/coffee/ice_certs_daily_detail.csv"), parse_dates=["date"])
grad = pd.read_csv(need("data/coffee/ice_grading_monthly.csv"))
rules = pd.read_csv(need("data/coffee/ref/rule_changes.csv"))
rates = pd.read_csv(need("data/coffee/ref/warehouse_rates.csv"))
kc = pd.read_csv(need("data/contracts/KC.csv"), parse_dates=["date"])
icog = pd.read_csv(need("coffee/data/ico_groups_monthly.csv"))
icop = pd.read_csv(need("coffee/data/ico_prices.csv"))
cj = json.load(open(need("coffee/data/coffee.json")))
det["port"] = det.port.map(lambda s: SHORT.get(s, s))
aging["dlv"] = aging.delivery.dt.strftime("%Y-%m")

out = {"built": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}

# ----------------------------------------------------------------------------------------------- 1. history panels
e = eom[eom.port != "TOTAL"].pivot_table(index="date", columns="port", values="bags", aggfunc="sum")
tot = eom[eom.port == "TOTAL"].set_index("date").bags
e = e.reindex(tot.index)
months = [d.strftime("%Y-%m") for d in tot.index]
ports_hist = [p for p in ["ANTWERP", "HAMBURG / BREMEN", "BARCELONA", "NEW YORK", "VIRGINIA", "NEW ORLEANS", "HOUSTON", "MIAMI"] if p in e]
out["history"] = {
    "months": months, "total": [rd(v, 0) for v in tot],
    "by_port": {PORT_LABEL[p]: [rd(v, 0) for v in e[p]] for p in ports_hist if e[p].fillna(0).sum() > 0},
    "markers": [{"date": r.effective_date[:7], "label": r.short, "text": r.plain_english} for r in rules.itertuples()
                if "2005" <= r.effective_date <= date.today().isoformat() and r.short not in ("Rent cost adjustment", "Origin schedule 2005", "Schedule restated")],
}
# age profile, all ports combined
aging["grp"] = pd.cut(aging.age_max, [-1] + [g[1] for g in AGE_GROUPS], labels=[g[2] for g in AGE_GROUPS])
ag = aging.pivot_table(index="date", columns="grp", values="bags", aggfunc="sum", observed=False).fillna(0)
atot = ag.sum(axis=1)
over1y = aging[aging.age_min > 365].groupby("date").bags.sum().reindex(ag.index).fillna(0)
wavg_age = aging.assign(mid=(aging.age_min + aging.age_max) / 2 * aging.bags).groupby("date").mid.sum() / atot


pc = pd.read_csv(need("coffee/data/prices_cont.csv"), parse_dates=["date"])
kc1 = pc[pc.symbol == "KC1!"].set_index("date").close.sort_index()


def hist_val(rows, today_rules):
    dl = rows.dlv.iloc[0]
    dl_rules = max(P["port_diff_versions"][-1]["from_delivery"], P["age_discount_versions"][-1]["from_delivery"]) if today_rules else dl
    pv = version("port_diff_versions", dl_rules)["pts"]
    agep = -rows.age_max.map(lambda d: age_pts(d, dl_rules))
    pts = rows.port.map(pv).fillna(0) + agep
    w = rows.bags
    f = float(kc1[kc1.index <= rows.date.iloc[0]].iloc[-1]) if (kc1.index <= rows.date.iloc[0]).any() else float("nan")
    wt = -rows.apply(lambda r: weight_pct((r.age_min + r.age_max) / 2 if r.age_min > 0 else 60), axis=1) / 100 * f * 100
    return (pts * w).sum() / w.sum() / 100, (agep * w).sum() / w.sum() / 100, ((pts + wt) * w).sum() / w.sum() / 100


hv = {d: hist_val(g, False) for d, g in aging.groupby("date")}
hv_now = {d: hist_val(g, True) for d, g in aging.groupby("date")}
out["age_hist"] = {
    "months": [d.strftime("%Y-%m") for d in ag.index], "groups": [g[2] for g in AGE_GROUPS],
    "bags": {g[2]: [rd(v, 0) for v in ag[g[2]]] for g in AGE_GROUPS},
    "share_over_1y": [rd(v * 100, 1) for v in over1y / atot], "avg_age_days": [rd(v, 0) for v in wavg_age],
    "delivery": [aging[aging.date == d].delivery.iloc[0].strftime("%Y-%m") for d in ag.index],
    "port_age_disc": [rd(hv[d][0], 2) for d in ag.index], "age_disc": [rd(hv[d][1], 2) for d in ag.index],
    "port_age_disc_today_rules": [rd(hv_now[d][0], 2) for d in ag.index],
    "port_age_weight": [rd(hv[d][2], 2) for d in ag.index],
}
# seasonal: the latest month vs the same month in earlier years
lm = tot.index[-1]
same = tot[tot.index.month == lm.month]
out["seasonal"] = {"month": lm.strftime("%b"), "latest": lm.strftime("%Y-%m"),
                   "years": [d.year for d in same.index], "bags": [rd(v, 0) for v in same],
                   "rank_low": int((same < same.iloc[-1]).sum()) + 1, "n": int(same.notna().sum()),
                   "avg10": rd(same.iloc[-11:-1].mean(), 0), "min10": rd(same.iloc[-11:-1].min(), 0), "max10": rd(same.iloc[-11:-1].max(), 0)}

# ---------------------------------------------------------------------------- 2. current stock: origin x port x age
A_DATE = aging.date.max()
la = aging[aging.date == A_DATE]
DLV = la.delivery.iloc[0]
DLV_M = DLV.strftime("%Y-%m")
buckets = la[["age_days", "age_min", "age_max"]].drop_duplicates().sort_values("age_min")
B = list(buckets.age_days)
bmax = dict(zip(buckets.age_days, buckets.age_max)); bmin = dict(zip(buckets.age_days, buckets.age_min))
port_age = la.pivot_table(index="port", columns="age_days", values="bags", aggfunc="sum").reindex(columns=B).fillna(0)

d0 = det[det.date == A_DATE]
if d0.empty:
    raise SystemExit(f"no daily detail on the aging date {A_DATE.date()}")
op0 = d0.groupby(["origin", "port"]).certified.sum()
op0 = op0[op0 > 0]
chk = op0.groupby(level=1).sum().reindex(port_age.index).fillna(0) - port_age.sum(axis=1)
if chk.abs().max() > 50:
    raise SystemExit(f"daily detail and aging file disagree by port on {A_DATE.date()}: {chk.to_dict()}")


def bucket_of(age):
    for b in B:
        if bmin[b] <= age <= bmax[b]:
            return b
    return B[0] if age < bmin[B[0]] else B[-1]


# dated inflows by origin: grading passes (lots -> bags) before the daily detail starts, daily passes after
lots_bags = {o: P["lot_lb"] / bag_lb(o) for o in op0.index.get_level_values(0).unique()}
g = grad[(grad.scope == "month") & (grad.row_type == "origin")].groupby(["month", "name"]).passed.sum()
det_start = det.date.min()
inflow = {}                                                  # (origin, port) -> list of (age_at_delivery, bags)
for (o, p), s in op0.items():
    share = s / op0.loc[o].sum()
    L = []
    for (m, oo), lots in g.items():
        if oo != o or lots <= 0 or pd.Timestamp(m + "-15") >= det_start:
            continue
        L.append(((DLV - pd.Timestamp(m + "-15")).days, lots * lots_bags.get(o, 283.5) * share))
    dp = det[(det.origin == o) & (det.port == p) & (det.passed > 0) & (det.date <= A_DATE)]
    L += [((DLV - r.date).days, float(r.passed)) for r in dp.itertuples()]
    inflow[(o, p)] = sorted(L)                               # youngest first

prior = {}
for p in port_age.index:
    os_ = [o for (o, pp) in op0.index if pp == p]
    M = pd.DataFrame(0.0, index=os_, columns=B)
    for o in os_:
        left = op0[(o, p)]
        oldest = 0
        for age, b in inflow.get((o, p), []):                # newest-first fill (oldest coffee has left first)
            take = min(left, b)
            if take <= 0:
                break
            M.loc[o, bucket_of(age)] += take; left -= take; oldest = age
        if left > 0:                                         # older than the dated inflows: the port's own old profile
            old = port_age.loc[p][[b for b in B if bmax[b] > oldest]]
            old = old if old.sum() > 0 else port_age.loc[p]
            M.loc[o] += left * old / old.sum()
    prior[p] = M


def ipf(M, rows, cols, it=500):
    X = M.values + 1e-6 * max(1.0, M.values.sum()) / M.size
    X = X * (X.sum() and 1)
    r, c = rows.values.astype(float), cols.values.astype(float)
    for _ in range(it):
        X *= (r / np.where(X.sum(1) == 0, 1, X.sum(1)))[:, None]
        X *= (c / np.where(X.sum(0) == 0, 1, X.sum(0)))[None, :]
        if np.abs(X.sum(1) - r).max() < 0.5:
            break
    return pd.DataFrame(X, index=M.index, columns=M.columns)


est = {}
for p, M in prior.items():
    rows = op0.xs(p, level=1).reindex(M.index)
    est[p] = ipf(M, rows, port_age.loc[p])

# roll forward to the latest daily report: passes enter the youngest bucket, other falls come out pro rata
D_DATE = det.date.max()
dl = det[det.date == D_DATE].groupby(["origin", "port"])[["certified", "transition"]].sum()
dl = dl[dl.certified > 0]
passes = det[(det.date > A_DATE) & (det.date <= D_DATE)].groupby(["origin", "port"]).passed.sum()
roll = []
for (o, p) in sorted(set(dl.index) | set(op0.index)):
    now = float(dl.certified.get((o, p), 0.0)); was = float(op0.get((o, p), 0.0))
    if p not in est:
        est[p] = pd.DataFrame(0.0, index=[], columns=B)
    if o not in est[p].index:
        est[p].loc[o] = 0.0
    add = float(passes.get((o, p), 0.0)); rem = add - (now - was)
    if rem < 0:
        add -= rem; rem = 0.0
    v = est[p].loc[o].clip(lower=0)
    if rem > 0 and v.sum() > 0:
        v = v * max(0.0, 1 - rem / v.sum())
    v[B[0]] += add
    est[p].loc[o] = v
    roll.append({"origin": o, "port": PORT_LABEL.get(p, p), "was": rd(was, 0), "passed": rd(add, 0), "removed": rd(rem, 0), "now": rd(now, 0)})

cells = []                                                   # origin, port, bucket, bags
for p, M in est.items():
    for o in M.index:
        for b in B:
            if M.loc[o, b] >= 0.5:
                cells.append((o, p, b, float(M.loc[o, b])))
C = pd.DataFrame(cells, columns=["origin", "port", "bucket", "bags"])
tot_now = float(dl.certified.sum())
if abs(C.bags.sum() - tot_now) > 50:
    raise SystemExit(f"estimated cells {C.bags.sum():.0f} != certified {tot_now:.0f}")

# ------------------------------------------------------------------------------------------- 3. delivery economics
px = kc.pivot_table(index="date", columns="contract", values="close")
fdate = px.index.max()
dcode = f"KC{MCODE[DLV.month]}{DLV.year}"
if dcode not in px:
    raise SystemExit(f"no settlement for {dcode}")
F = float(px[dcode].dropna().iloc[-1])
nxt = sorted([c for c in px.columns if px[c].dropna().index.max() == fdate],
             key=lambda c: (int(c[-4:]), "HKNUZ".index(c[2])))
nxt = [c for c in nxt if (int(c[-4:]), "HKNUZ".index(c[2])) > (DLV.year, "HKNUZ".index(MCODE[DLV.month]))]
N1 = nxt[0]
N1_M = f"{N1[-4:]}-{[k for k, v in MCODE.items() if v == N1[2]][0]:02d}"

rates["port"] = rates.port.str.replace("HAMBURG/BREMEN", "HAMBURG / BREMEN")
rt = rates[(rates.effective_from <= date.today().isoformat())].groupby("port")[["oca_usd_bag", "rca_usd_bag", "storage_usd_bag_month", "load_out_usd_bag"]].mean()


def components(o, p, age_days, dmonth, transition_share=0.0, fut=F):
    od = version("origin_diff_versions", dmonth)["pts"].get(o)
    if od is None:
        od = float("nan")
    pdp = version("port_diff_versions", dmonth)["pts"].get(p, 0)
    ap = age_pts(age_days, dmonth)
    wa = -weight_pct(age_days) / 100 * fut * 100            # points
    lb = bag_lb(o)
    oca = rt.oca_usd_bag.get(p, 0.0) / lb * 1e4 if p in rt.index else 0.0
    mult = P["rca"]["mult"].get(str(int(dmonth[5:])), 2)
    rca = rt.rca_usd_bag.get(p, 0.0) * mult / lb * 1e4 if p in rt.index else 0.0
    eu = P["eudr_transition"]; tr = 0.0
    if p in EU and dmonth >= eu["from_contract"] and transition_share > 0:
        y, m = int(dmonth[:4]), int(dmonth[5:])
        tr = -(eu["pts_per_month_2027"] * (m if y == 2027 else 12) if y == 2027 else eu["pts_2028_base"] + eu["pts_per_month_2028"] * ((y - 2028) * 12 + m)) * transition_share
    return {"odiff": od, "pdiff": pdp, "age": -ap, "weight": wa, "oca": oca, "rca": rca, "eudr": tr}


trans_share = (dl.transition / dl.certified).to_dict()
rows = []
for r in C.itertuples():
    mid = (bmin[r.bucket] + bmax[r.bucket]) / 2 if r.bucket != B[0] else 60
    age_for_disc = bmax[r.bucket]
    c = components(r.origin, r.port, age_for_disc, DLV_M, 0.0)
    c["weight"] = -weight_pct(mid) / 100 * F * 100
    days_n1 = (pd.Timestamp(N1_M + "-01") - DLV).days
    c1 = components(r.origin, r.port, age_for_disc + days_n1, N1_M, trans_share.get((r.origin, r.port), 0.0))
    c1["weight"] = -weight_pct(mid + days_n1) / 100 * F * 100
    lots = r.bags * bag_lb(r.origin) / P["lot_lb"]
    rows.append({"origin": r.origin, "port": r.port, "bucket": r.bucket, "age_max": bmax[r.bucket], "bags": r.bags, "lots": lots,
                 **{k: v / 100 for k, v in c.items()}, "total": sum(c.values()) / 100, "total_n1": sum(c1.values()) / 100,
                 "eudr_n1": c1["eudr"] / 100})
X = pd.DataFrame(rows)
bad = X[X["odiff"].isna()]
if len(bad):
    raise SystemExit(f"origin without an ICE differential: {sorted(bad.origin.unique())}")
X["lb"] = X.lots * P["lot_lb"]
wavg = lambda d, col: float((d[col] * d.lb).sum() / d.lb.sum())

# physical differentials (ICO group prices by market, vs ICO New York = 2nd/3rd position average), restated vs the delivery contract
gm = icog.month.max()
ico_row = icog[icog.month == gm].iloc[0]
ny = float(icop[icop.price_month == gm].new_york_ice.iloc[0])
mstart, mend = pd.Timestamp(gm + "-01"), pd.Timestamp(gm + "-01") + pd.offsets.MonthEnd(0)
pm = px[(px.index >= mstart) & (px.index <= mend)]
cons = sorted([c for c in px.columns if pm[c].notna().any()], key=lambda c: (int(c[-4:]), "HKNUZ".index(c[2])))
dlv_avg = float(pm[dcode].mean())
second_third = [c for c in cons if (int(c[-4:]), "HKNUZ".index(c[2])) > (DLV.year, "HKNUZ".index(MCODE[DLV.month]))][:2]
st_avg = float(pm[second_third].mean().mean())
roll_adj = st_avg - dlv_avg                                 # add to a diff vs 2nd/3rd to restate it vs the delivery contract
phys = {}
for gk in ["col", "oth", "bra"]:
    for mk, ports in [("eu", "Europe"), ("ny", "United States")]:
        v = float(ico_row[f"{gk}_{mk}"])
        phys[(gk, mk)] = {"group": ICO_NAME[gk], "market": ports, "price": rd(v, 2), "vs_ico_ny": rd(v - ny, 2), "vs_delivery": rd(v - ny + roll_adj, 2)}


def phys_of(o, p):
    return phys[(ICO_GROUP.get(o, "oth"), "eu" if p in EU else "ny")]


def summ(d):
    return {"bags": rd(d.bags.sum(), 0), "lots": rd(d.lots.sum(), 0), "odiff": rd(wavg(d, "odiff"), 2), "pdiff": rd(wavg(d, "pdiff"), 2),
            "age": rd(wavg(d, "age"), 2), "weight": rd(wavg(d, "weight"), 2), "oca_rca": rd(wavg(d, "oca") + wavg(d, "rca"), 2),
            "total": rd(wavg(d, "total"), 2), "total_n1": rd(wavg(d, "total_n1"), 2),
            "avg_age": rd(float((d.age_max * d.bags).sum() / d.bags.sum()), 0)}


by_op = []
for (o, p), d in X.groupby(["origin", "port"]):
    s = summ(d); ph = phys_of(o, p)
    fresh = components(o, p, 60, DLV_M); fresh["weight"] = -weight_pct(60) / 100 * F * 100
    fr = sum(fresh.values()) / 100
    by_op.append({"origin": o, "port": PORT_LABEL.get(p, p), **s, "fresh": rd(fr, 2), "phys_group": ph["group"],
                  "phys": ph["vs_delivery"], "gap": rd(ph["vs_delivery"] - s["total"], 2), "gap_fresh": rd(ph["vs_delivery"] - fr, 2),
                  "transition": rd(float(dl.transition.get((o, p), 0)), 0)})
by_op.sort(key=lambda r: -r["bags"])

grid = X.assign(g=pd.cut(X.age_max, [-1] + [g[1] for g in AGE_GROUPS], labels=[g[2] for g in AGE_GROUPS]))
pa = grid.pivot_table(index="port", columns="g", values="bags", aggfunc="sum", observed=False).fillna(0)
oa = grid.pivot_table(index="origin", columns="g", values="bags", aggfunc="sum", observed=False).fillna(0)

# cheapest to deliver: the deliverer hands over the lots worth least on the invoice first
X = X.sort_values("total").reset_index(drop=True)
X["cum_lots"] = X.lots.cumsum()
ctd_n = []
for n in [100, 250, 500]:
    if X.lots.sum() > n:
        k = X[X.cum_lots - X.lots < n].copy()
        k.loc[k.index[-1], "lb"] -= (k.cum_lots.iloc[-1] - n) * P["lot_lb"]
        ctd_n.append({"lots": n, "avg": rd(wavg(k, "total"), 2), "worst": rd(float(k.total.min()), 2), "best": rd(float(k.total.max()), 2)})
ctd_n.append({"lots": "all", "avg": rd(wavg(X, "total"), 2), "worst": rd(float(X.total.min()), 2), "best": rd(float(X.total.max()), 2)})
step = max(1, len(X) // 120)
curve = [{"cum_lots": rd(r.cum_lots, 1), "diff": rd(r.total, 2), "origin": r.origin, "port": PORT_LABEL.get(r.port, r.port), "age": r.bucket}
         for r in X.iloc[::step].itertuples()] + [{"cum_lots": rd(X.cum_lots.iloc[-1], 1), "diff": rd(X.total.iloc[-1], 2)}]
k100 = X[X.cum_lots - X.lots < 100]
ctd_top = [{"origin": o, "port": PORT_LABEL.get(p, p), "lots": rd(d.lots.sum(), 1), "diff_from": rd(d.total.min(), 2), "diff_to": rd(d.total.max(), 2),
            "age_from": int(d.age_max.min()) - 29, "age_to": int(d.age_max.max())}
           for (o, p), d in k100.groupby(["origin", "port"])]
ctd_top.sort(key=lambda r: -r["lots"])
ctd_top = ctd_top[:8]
S = summ(X)
dist = np.percentile(np.repeat(X.total.values, np.maximum(1, np.round(X.lots.values * 10).astype(int))), [10, 25, 50, 75, 90])
out["current"] = {
    "daily_date": D_DATE.strftime("%Y-%m-%d"), "aging_date": A_DATE.strftime("%Y-%m-%d"), "delivery": DLV_M,
    "delivery_contract": dcode, "next_contract": N1, "next_delivery": N1_M, "first_notice": P["first_notice"].get(DLV_M),
    "total_bags": rd(tot_now, 0), "total_lots": S["lots"], "pending": rd(float(det[det.date == D_DATE].pending.sum()), 0),
    "transition": rd(float(dl.transition.sum()), 0),
    "port_age": {"groups": [g[2] for g in AGE_GROUPS], "rows": [{"port": PORT_LABEL.get(p, p), "bags": [rd(v, 0) for v in pa.loc[p]], "total": rd(pa.loc[p].sum(), 0)} for p in pa.sum(1).sort_values(ascending=False).index]},
    "origin_age": {"groups": [g[2] for g in AGE_GROUPS], "rows": [{"origin": o, "bags": [rd(v, 0) for v in oa.loc[o]], "total": rd(oa.loc[o].sum(), 0)} for o in oa.sum(1).sort_values(ascending=False).index]},
    "roll": roll, "reported_port_age_date": A_DATE.strftime("%Y-%m-%d"),
}
out["economics"] = {
    "futures": {"contract": dcode, "settle": rd(F, 2), "date": fdate.strftime("%Y-%m-%d"), "next": N1, "next_settle": rd(float(px[N1].dropna().iloc[-1]), 2)},
    "all": S, "dist": {"p10": rd(dist[0]), "p25": rd(dist[1]), "p50": rd(dist[2]), "p75": rd(dist[3]), "p90": rd(dist[4])},
    "ctd_n": ctd_n, "ctd_curve": curve, "ctd_top": ctd_top, "by_origin_port": by_op,
    "eudr_n1": rd(wavg(X, "eudr_n1"), 2),
}
out["physical"] = {
    "ico_month": gm, "ico_ny": rd(ny, 2), "roll_adj": rd(roll_adj, 2), "delivery_avg": rd(dlv_avg, 2), "second_third": second_third,
    "second_third_avg": rd(st_avg, 2), "groups": list(phys.values()),
    "brazil_ladder": [{"name": l["name"], "date": l["date"], "basis": l["basis"]} for l in (cj.get("brazil") or {}).get("ladder", []) if l["key"] in ("icf", "cd", "t6")],
}
# exchange vs physical by ICO group (fresh 0-120 d coffee and the stock as it is)
grp = []
for gk in ["col", "oth", "bra"]:
    for mk, pset in [("eu", EU), ("ny", None)]:
        d = X[X.origin.map(lambda o: ICO_GROUP.get(o, "oth")) == gk]
        d = d[d.port.isin(EU)] if mk == "eu" else d[~d.port.isin(EU)]
        if d.empty:
            continue
        ph = phys[(gk, mk)]
        fr = d[d.bucket == B[0]]
        grp.append({"group": ICO_NAME[gk], "market": ph["market"], "bags": rd(d.bags.sum(), 0), "exchange": rd(wavg(d, "total"), 2),
                    "exchange_fresh": rd(wavg(fr, "total"), 2) if len(fr) else None, "physical": ph["vs_delivery"],
                    "gap": rd(ph["vs_delivery"] - wavg(d, "total"), 2), "gap_fresh": rd(ph["vs_delivery"] - wavg(fr, "total"), 2) if len(fr) else None})
out["physical"]["vs_exchange"] = grp

# ------------------------------------------------- 4b. exchange vs ICO, measured against its own history (by delivery)
# ICO group prices by market (US / Europe) from the desk's ICO feed, with the ICE 2nd/3rd-position average computed here.
kcm = kc.assign(m=kc.date.dt.strftime("%Y-%m"))
cavg = kcm.groupby(["contract", "m"]).close.mean()
cexp = kc.groupby("contract").date.max()
ckey = lambda c: (int(c[-4:]), "HKNUZ".index(c[2]))


def positions(m):
    mid = pd.Timestamp(m + "-15")
    live = sorted([c for c in cexp.index if cexp[c] >= mid and (c, m) in cavg.index], key=ckey)
    return live


hist_rows = []
pub_ny = icop.set_index("price_month").new_york_ice
for r in icog.itertuples():
    pos = positions(r.month)
    ny_calc = float(np.mean([cavg[(c, r.month)] for c in pos[1:3]])) if len(pos) >= 3 else float("nan")
    hist_rows.append({"month": r.month, "col_us": r.col_ny, "col_eu": r.col_eu, "col_w": r.col_w, "oth_us": r.oth_ny, "oth_eu": r.oth_eu, "oth_w": r.oth_w,
                      "bra_us": r.bra_ny, "bra_eu": r.bra_eu, "bra_w": r.bra_w, "ico_new_york_published": pub_ny.get(r.month, np.nan),
                      "kc_2nd_3rd_avg_calc": ny_calc, "kc_2nd": pos[1] if len(pos) > 1 else "", "kc_3rd": pos[2] if len(pos) > 2 else "",
                      "source": "ICO monthly group indicator prices (USA and Europe ex-dock, US cents/lb), via the FNC 'OIC mensual' table; KC averages from ICE settlements"})
IH = pd.DataFrame(hist_rows)
IH.round(3).to_csv(os.path.join(CF, "ico_groups_history.csv"), index=False)
chkny = IH.dropna(subset=["ico_new_york_published", "kc_2nd_3rd_avg_calc"])
ny_err = float((chkny.ico_new_york_published - chkny.kc_2nd_3rd_avg_calc).abs().median()) if len(chkny) else None
IHi = IH.set_index("month")

certs_od = pd.read_csv(need("data/coffee/ice_certs.csv"), parse_dates=["date"])
certs_od = certs_od[certs_od.section == "certified"]
certs_od["port"] = certs_od.port.map(lambda s: SHORT.get(s, s))
eomt = tot.copy(); eomt.index = eomt.index.strftime("%Y-%m")
GRP = {"col": ["Colombia"], "bra": ["Brazil"]}


def fnd(dm):
    first = pd.Timestamp(dm + "-01")
    while first.weekday() >= 5:
        first += pd.Timedelta(days=1)
    return first - pd.offsets.BDay(7)


gap_hist = []
for R, g0 in aging.groupby("date"):
    D = g0.delivery.iloc[0]; dm = D.strftime("%Y-%m"); M = R.strftime("%Y-%m")
    if (D.year * 12 + D.month) - (R.year * 12 + R.month) != 2:
        continue                                             # one observation per delivery: the report two months before
    dc = f"KC{MCODE[D.month]}{D.year}"
    if (dc, M) not in cavg.index or M not in IHi.index:
        continue
    Fm = float(cavg[(dc, M)])
    pv = version("port_diff_versions", dm)["pts"]
    g0 = g0.assign(pd_=g0.port.map(pv).fillna(0) / 100, ad=-g0.age_max.map(lambda d: age_pts(d, dm)) / 100,
                   wt=-g0.apply(lambda r: weight_pct((r.age_min + r.age_max) / 2 if r.age_min > 0 else 60), axis=1) / 100 * Fm)
    g0["paw"] = g0.pd_ + g0.ad + g0.wt
    w = g0.bags; paw = float((g0.paw * w).sum() / w.sum())
    eu_sh = float(g0[g0.port.isin(EU)].bags.sum() / w.sum())
    port_paw = g0.groupby("port").apply(lambda d: (d.paw * d.bags).sum() / d.bags.sum(), include_groups=False)
    od = version("origin_diff_versions", dm)["pts"]
    # origin x port snapshot near the report date, where the automatic feed has one
    near = certs_od[(certs_od.date - R).abs() <= pd.Timedelta(days=35)]
    snap = near[near.date == near.date.iloc[(near.date - R).abs().argmin()]] if len(near) else None
    if R >= det.date.min() and (det.date <= R).any():
        dd = det[det.date == det[det.date <= R].date.max()]
        snap = dd.rename(columns={"certified": "bags"})[["date", "origin", "port", "bags"]]
    rec = {"delivery": dm, "contract": dc, "report": R.strftime("%Y-%m-%d"), "ico_month": M, "first_notice": fnd(dm).strftime("%Y-%m-%d"),
           "pool_bags": rd(float(w.sum()), 0), "pool_lots": rd(float(w.sum()) / 265, 0), "eu_share": rd(eu_sh * 100, 0), "kc": rd(Fm, 2),
           "pool_paw": rd(paw, 2), "regime": "post" if dm >= "2024-03" else "pre", "groups": {}}
    for gk in ["oth", "bra", "col"]:
        o_d = 0.0 if gk == "oth" else od.get(GRP[gk][0])
        if o_d is None:
            continue
        o_d = o_d / 100
        phys = eu_sh * IHi.loc[M, f"{gk}_eu"] + (1 - eu_sh) * IHi.loc[M, f"{gk}_us"] - Fm
        inv = o_d + paw
        e = {"ico": rd(phys, 2), "invoice": rd(inv, 2), "gap": rd(phys - inv, 2)}
        if snap is not None and len(snap):
            sg = snap[snap.origin.isin(GRP[gk])] if gk != "oth" else snap[~snap.origin.isin(GRP["col"] + GRP["bra"])]
            sg = sg.groupby(["origin", "port"]).bags.sum()
            sg = sg[sg > 0]
            if sg.sum() > 0:
                odv = np.array([(od.get(o, 0) or 0) / 100 for o, _ in sg.index])
                ppv = np.array([port_paw.get(p, paw) for _, p in sg.index])
                inv_b = float(((odv + ppv) * sg.values).sum() / sg.sum())
                eu_b = float(sg[[p in EU for _, p in sg.index]].sum() / sg.sum())
                phys_b = eu_b * IHi.loc[M, f"{gk}_eu"] + (1 - eu_b) * IHi.loc[M, f"{gk}_us"] - Fm
                e.update({"bags_b": rd(float(sg.sum()), 0), "invoice_b": rd(inv_b, 2), "ico_b": rd(phys_b, 2), "gap_b": rd(phys_b - inv_b, 2),
                          "snap": str(snap.date.iloc[0])[:10]})
        rec["groups"][gk] = e
    # outcomes (used in the Lab only): certs change through the delivery month, front spread into first notice
    after = (D + pd.offsets.MonthEnd(0)).strftime("%Y-%m")
    rec["certs_chg_pct"] = rd((eomt.get(after) / eomt.get(M) - 1) * 100, 1) if eomt.get(after) and eomt.get(M) else None
    nxt_c = [c for c in cexp.index if ckey(c) > ckey(dc)]
    if nxt_c:
        n1 = sorted(nxt_c, key=ckey)[0]
        sp = (px[dc] - px[n1]).dropna() if dc in px and n1 in px else pd.Series(dtype=float)
        f_d = fnd(dm)
        a, b = sp[sp.index <= pd.Timestamp(M + "-01") + pd.offsets.MonthEnd(0)], sp[sp.index <= f_d]
        rec["spread_month"] = rd(float(a.iloc[-1]), 2) if len(a) else None
        rec["spread_fnd"] = rd(float(b.iloc[-1]), 2) if len(b) else None
        rec["spread_chg"] = rd(float(b.iloc[-1] - a.iloc[-1]), 2) if len(a) and len(b) else None
    gap_hist.append(rec)

if len(gap_hist) < 10:
    raise SystemExit(f"only {len(gap_hist)} past deliveries for the gap history")
cur, prev = gap_hist[-1], gap_hist[-2]
norm = {}
for gk, nm in ICO_NAME.items():
    for reg in ["post", "pre", "all"]:
        v = np.array([h["groups"][gk]["gap"] for h in gap_hist[:-1] if gk in h["groups"] and (reg == "all" or h["regime"] == reg)])
        if len(v) == 0:
            continue
        norm.setdefault(gk, {})[reg] = {"n": int(len(v)), "median": rd(np.median(v)), "p10": rd(np.percentile(v, 10)), "p90": rd(np.percentile(v, 90)),
                                        "mean": rd(v.mean())}
sig = []
for gk, nm in ICO_NAME.items():
    if gk not in cur["groups"] or gk not in norm:
        continue
    pre, post = norm[gk].get("pre"), norm[gk].get("post")
    shift = (post and pre and abs(post["median"] - pre["median"]) > max(5.0, 0.5 * ((pre["p90"] - pre["p10"]) / 2)))
    use = "post" if shift and post and post["n"] >= 5 else "all"
    nrm = norm[gk][use]
    g_now = cur["groups"][gk]["gap"]
    rank = float(np.mean([h["groups"][gk]["gap"] <= g_now for h in gap_hist[:-1] if gk in h["groups"] and (use == "all" or h["regime"] == use)]) * 100)
    sig.append({"group": nm, "key": gk, "now": cur["groups"][gk], "prev": prev["groups"].get(gk), "normal": nrm, "basis": use,
                "regime_shift": bool(shift), "pre": pre, "post": post, "adjusted": rd(g_now - nrm["median"]), "pctile": rd(rank, 0)})
out["gap"] = {"deliveries": gap_hist, "signal": sig, "current": cur["delivery"], "previous": prev["delivery"], "n": len(gap_hist) - 1,
              "first": gap_hist[0]["delivery"], "ico_ny_check_median_abs_err": rd(ny_err, 2),
              "ico_note": "ICO group indicators: daily ex-dock prompt-shipment prices for named current-crop export grades in the USA and Europe (Germany, France), built as futures plus trade differentials, US cents/lb; the group price weights the two markets by export share. ICO's 'New York' is the average of the ICE 2nd and 3rd positions."}
out["rules"] = {
    "source": P["source_url"], "read_on": P["read_on"],
    "origin_now": version("origin_diff_versions", DLV_M), "origin_next": version("origin_diff_versions", "2027-05"),
    "port_now": version("port_diff_versions", DLV_M), "age_bands": version("age_discount_versions", DLV_M),
    "changes": rules.fillna("").to_dict("records"),
}
out["variables"] = [
    "ICE month-end certified stocks by port (1996 on)", "ICE monthly aging report by port and 30-day age bucket (2016 on)",
    "ICE daily certified-stock report by origin and port (certified, pending, passed, EUDR transition bags)",
    "ICE monthly grading results by origin (lots passed)", "ICE Coffee \"C\" rulebook: origin and port differentials, age discount, weight allowance, OCA/RCA, EUDR transition discount",
    "ICE warehouse storage and load-out rates (2026-27)", "KC settlements by contract", "ICO group indicator prices by market (Europe / US) and the ICO New York average, monthly since 2000", "Past delivery pools: aging report two months before each KC delivery (2016 on) and origin-by-port snapshots where available (2024 on)",
    "Brazil export-quality prices (B3 arabica 4/5 good cup, co-op semi-washed, tipo 6)"]
out["checks"] = {"cells_sum": rd(C.bags.sum(), 0), "certified": rd(tot_now, 0), "aging_total": rd(float(port_age.values.sum()), 0)}

json.dump(out, open(OUT, "w"), separators=(",", ":"), allow_nan=False)
print(f"certs profile: {tot_now:,.0f} bags ({S['lots']:,.0f} lots) on {D_DATE.date()}, avg invoice diff {S['total']:+.2f} c/lb vs {dcode} {F:.2f}")
