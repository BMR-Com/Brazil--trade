"""KC (ICE arabica) front calendar spread against certified stocks: fair spread by contract, deliverable cover, similar past deliveries.

Target : front minus second at 30 and 10 business days before first notice and on the last day before it (bd 1), as % of
         the front price and in c/lb; and the change from 21 business days before first notice to bd 1 (the month into notice).
Drivers, each as of the target date (no look-ahead):
         ICE certified stocks at the last month-end before the date (log bags; vs their own 5-year average; 1- and 3-month change;
         European-port share), cover = certified lots / total KC futures open interest (CFTC, last report at least 3 days old),
         age of the pile (share over one year, bag-weighted age; ICE aging report, month-end at least 7 days old, 2016 on),
         ICO Brazilian naturals and other milds minus the ICE 2nd/3rd average (month at least 10 days complete),
         Brazil green exports (MDIC, NCM 0901.11.10) to Belgium / Germany / Netherlands vs the same months of the 3 years
         before, ICE gradings passed and bags leaving the pile (monthly grading files, Oct 2022 on), bags pending grading x
         the recent pass rate ("certs to come"; grading run-rate where no pending series), whole-pool delivery value from
         the certs profile, CFTC managed-money net and spreading (% of OI), rule regimes (May 2019, Dec 2023).
Model  : ordinary least squares of the spread on the candidate specifications in SPECS; the one with the lowest walk-forward
         error (by delivery, 2021 on) is used. Fair range = fit +/- the 20th-80th percentile of its walk-forward errors.
         Nearest past deliveries on standardised cover, age and 3-month change.
Output : data/coffee/spread_model.json (page outputs only). With --lab PATH it also writes the regime tests and
         out-of-sample statistics to PATH (kept out of the repo; they go into the private Lab).
Inputs : data/coffee/kc_spreads_history.csv, ice_certs_eom_by_port.csv, ice_aging_history.csv, ice_certs.csv,
         ice_grading_monthly.csv, ico_groups_history.csv, data/cot/KC_fut.csv, coffee/data/coffee.json (Brazil-Belgium),
         data/contracts/KC.csv (curve), data/options/roll.json (front-month OI now).
Any missing input or failed check exits non-zero.
"""
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from softs_spreads_history import BD, fnd as fnd_of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "coffee", "spread_model.json")
BAGS_PER_LOT = 265.0                      # 37,500 lb at the desk's average bag weight (same as the certs profile)
EU = {"ANTWERP", "HAMBURG / BREMEN", "BARCELONA"}
KS = [30, 10, 1]
MC = {"H": 3, "K": 5, "N": 7, "U": 9, "Z": 12}
MN = {3: "Mar", 5: "May", 7: "Jul", 9: "Sep", 12: "Dec"}
R19, R23 = pd.Timestamp("2019-05-01"), pd.Timestamp("2023-12-01")
LAB_MODE = "--lab" in sys.argv


def rd(v, n=2):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), n)


def need(rel):
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        raise SystemExit(f"missing input: {rel}")
    return p


def lab(code):                             # KCH2027 -> Mar 27
    return f"{MN[MC[code[-5]]]} {code[-2:]}"


# ------------------------------------------------------------------ inputs
spr = pd.read_csv(need("data/coffee/kc_spreads_history.csv"), parse_dates=["date"])
eom = pd.read_csv(need("data/coffee/ice_certs_eom_by_port.csv"), parse_dates=["date"])
tot = eom[eom.port == "TOTAL"].set_index("date").bags.dropna().sort_index()
tot = tot[tot > 0]
eu = eom[eom.port.isin(EU)].groupby("date").bags.sum().reindex(tot.index)
ant = eom[eom.port == "ANTWERP"].set_index("date").bags.reindex(tot.index)
aging = pd.read_csv(need("data/coffee/ice_aging_history.csv"), parse_dates=["date"])
aging["mid"] = np.where(aging.age_min > 0, (aging.age_min + aging.age_max) / 2, 60)
ag = aging.groupby("date").apply(lambda d: pd.Series({"over1y": d.bags[d.age_min > 360].sum() / d.bags.sum() * 100,
                                                       "avg_age": (d.mid * d.bags).sum() / d.bags.sum()}), include_groups=False)
daily = pd.read_csv(need("data/coffee/ice_certs.csv"), parse_dates=["date"])
dcert = daily[daily.section == "certified"].groupby("date").bags.sum()
dbra = daily[(daily.section == "certified") & (daily.origin == "Brazil")].groupby("date").bags.sum().reindex(dcert.index).fillna(0)
det = pd.read_csv(need("data/coffee/ice_certs_daily_detail.csv"), parse_dates=["date"])
PEND = daily[daily.section == "pending"].groupby("date").bags.sum()
PEND = pd.concat([PEND[PEND.index < det.date.min()], det.groupby("date").pending.sum()]).sort_index()
grd = pd.read_csv(need("data/coffee/ice_grading_monthly.csv"))
grd = grd[(grd.scope == "month") & (grd.row_type == "total") & (grd.stage == "original")].set_index("month")[["passed", "failed"]]
ico = pd.read_csv(need("data/coffee/ico_groups_history.csv")).set_index("month")
ico_bra = (ico.bra_w - ico.kc_2nd_3rd_avg_calc).dropna()
ico_oth = (ico.oth_w - ico.kc_2nd_3rd_avg_calc).dropna()
cot = pd.read_csv(need("data/cot/KC_fut.csv"), usecols=["report_date_as_yyyy_mm_dd", "open_interest_all", "m_money_positions_long_all",
                                                         "m_money_positions_short_all", "m_money_positions_spread"])
cot["date"] = pd.to_datetime(cot.report_date_as_yyyy_mm_dd.str[:10])
cot = cot.set_index("date").sort_index()
PRM = json.load(open(need("data/coffee/ref/kc_rule_params.json")))
# Brazil green coffee exports by destination (MDIC Comex Stat, NCM 0901.11.10, 60-kg bags), 1997 on
ex = pd.concat([pd.read_csv(need(f), dtype={"ncm": str}, usecols=["year", "month", "ncm", "country_name", "kg_net"])
                for f in ("data/exports_pre2015.csv", "data/exports_2015on.csv")])
ex = ex[ex.ncm == "09011110"]
ex["m"] = ex.year.astype(str) + "-" + ex.month.astype(int).map("{:02d}".format)
EXP = ex.pivot_table(index="m", columns="country_name", values="kg_net", aggfunc="sum").sort_index() / 60
for c_ in ("Belgium", "Germany", "Netherlands"):
    if c_ not in EXP or EXP[c_].notna().sum() < 120:
        raise SystemExit(f"Brazil exports to {c_} missing")
EXP = EXP[["Belgium", "Germany", "Netherlands"]].fillna(0)
EXP_ALL = ex.groupby("m").kg_net.sum().sort_index() / 60
curve = pd.read_csv(need("data/contracts/KC.csv"), parse_dates=["date"])
roll = (json.load(open(need("data/options/roll.json"))).get("markets") or {}).get("KC") or {}
for nm, s_ in [("spreads", spr), ("certs month-end", tot), ("aging", ag), ("COT", cot), ("ICO", ico_bra)]:
    if len(s_) < 10:
        raise SystemExit(f"input too short: {nm}")

# ------------------------------------------------------------------ monthly flows: cert changes, gradings, Brazil -> Europe lead
FLOW_FROM = "2020-10"        # Brazil semi-washed entered the certified pile in size from late 2020
mk = lambda ts: ts.strftime("%Y-%m")
MF = pd.DataFrame({"tot": tot.values, "ant": ant.values}, index=[mk(t) for t in tot.index])
MF = MF[~MF.index.duplicated(keep="last")]
MF["dtot"] = MF.tot.diff()
MF["dant"] = MF.ant.diff()
mlist = list(MF.index)


def mshift(m, n):
    t = pd.Period(m, "M") + n
    return str(t)


def excess(s):
    """Shipments minus the average of the same calendar month in the 3 years before (bags)."""
    base = sum(s.shift(12 * y) for y in (1, 2, 3)) / 3
    return s - base


EXX = pd.DataFrame({c_: excess(EXP[c_]) for c_ in EXP})
EXX["all"] = excess(EXP_ALL)
# gradings: passed and failed lots by origin -> bags (origin bag weight), Oct 2022 on
go = pd.read_csv(need("data/coffee/ice_grading_monthly.csv"))
go = go[(go.scope == "month") & (go.row_type == "origin") & (go.stage == "original")]
bkg = PRM["bag_kg_by_origin"]
go["bags_per_lot"] = go.name.map(lambda o: PRM["lot_lb"] / (bkg.get(o, bkg["default"]) * 2.20462))
GR = pd.DataFrame({"pass_bags": (go.passed * go.bags_per_lot).groupby(go.month).sum(),
                   "fail_bags": (go.failed * go.bags_per_lot).groupby(go.month).sum()})
GR["pass_rate"] = GR.pass_bags / (GR.pass_bags + GR.fail_bags)
MF = MF.join(GR, how="left")
MF["out_bags"] = MF.pass_bags - MF.dtot           # bags that left the pile (de-certified, aged out, delivered and taken out)


def lead_fit(target, L, until, since=FLOW_FROM, xcols=("Belgium",)):
    """OLS of a monthly cert change on Brazil shipments excess L months earlier, months since..until (inclusive)."""
    ms = [m for m in mlist if since <= m <= until]
    rows_ = []
    for m in ms:
        x = [EXX[c_].get(mshift(m, -L), np.nan) for c_ in xcols]
        y = MF.at[m, target]
        if not np.isnan(x).any() and y == y:
            rows_.append([1.0] + x + [y])
    if len(rows_) < 12:
        return None
    A = np.array(rows_)
    b, *_ = np.linalg.lstsq(A[:, :-1], A[:, -1], rcond=None)
    return b


LEAD = {"xcorr": {}, "oos": {}, "spread": {}}
PERIODS = {"1999-2012 (Brazil not deliverable)": ("1999-01", "2012-12"), "2013-Sep 2020 (deliverable, rarely certified)": ("2013-01", "2020-09"),
           "Oct 2020 on (Brazil in the pile)": ("2020-10", "2099-12")}
for tgt in ("dant", "dtot"):
    for c_ in ("Belgium", "Germany", "Netherlands", "all"):
        for pn, (a_, b_) in PERIODS.items():
            cs = []
            for L in range(0, 7):
                z = pd.concat([EXX[c_].shift(L), MF[tgt]], axis=1, join="inner").dropna()
                z = z[(z.index >= a_) & (z.index <= b_)]
                cs.append(rd(z.corr().iloc[0, 1], 2) if len(z) > 12 else None)
            LEAD["xcorr"].setdefault(tgt, {}).setdefault(c_, {})[pn] = cs
# walk-forward: predict each month's Antwerp / total cert change from shipments L months before (L >= 1: the MDIC month is
# published in the first days of the next month, so L = 0 is not known in time), months from Jan 2022, trained from Oct 2020
for tgt in ("dant", "dtot"):
    for xc in (("Belgium",), ("Germany",), ("Belgium", "Germany"), ("all",)):
        for L in range(1, 7):
            e_m, e_0, e_mean = [], [], []
            for m in [m for m in mlist if m >= "2022-01"]:
                b = lead_fit(tgt, L, mshift(m, -1), xcols=xc)
                x = [EXX[c_].get(mshift(m, -L), np.nan) for c_ in xc]
                y = MF.at[m, tgt]
                if b is None or np.isnan(x).any() or y != y:
                    continue
                tr = MF.loc[[k for k in mlist if FLOW_FROM <= k < m], tgt].dropna()
                e_m.append(abs(y - (b[0] + np.dot(b[1:], x)))); e_0.append(abs(y)); e_mean.append(abs(y - tr.mean()))
            if e_m:
                LEAD["oos"].setdefault(tgt, {})[f"{'+'.join(xc)} lag {L}"] = {"n": len(e_m), "mae": rd(np.mean(e_m), 0), "mae_zero": rd(np.mean(e_0), 0),
                                                                            "mae_mean": rd(np.mean(e_mean), 0),
                                                                            "skill_vs_mean": rd(1 - np.mean(e_m) / np.mean(e_mean), 3)}
bel_oos = {k: v for k, v in LEAD["oos"]["dant"].items() if k.startswith("Belgium lag")}
BEST_L = int(min(bel_oos, key=lambda k: bel_oos[k]["mae"]).split()[-1])
BEST_SKILL = bel_oos[f"Belgium lag {BEST_L}"]["skill_vs_mean"]
LEAD["best_lag"] = BEST_L
LEAD["best_skill"] = BEST_SKILL
LEAD["coef_full"] = [rd(v, 3) for v in lead_fit("dant", BEST_L, mlist[-1])]


def asof(s, d, lag_days=0):
    s = s[s.index <= d - pd.Timedelta(days=lag_days)]
    return (s.index[-1], s.iloc[-1]) if len(s) else (None, np.nan)


def month_asof(s, d, lag_days):
    """Monthly series keyed 'YYYY-MM': last month that ended at least lag_days before d."""
    ok = [m for m in s.index if pd.Timestamp(m + "-01") + pd.offsets.MonthEnd(0) + pd.Timedelta(days=lag_days) <= d]
    return (ok[-1], s[ok[-1]]) if ok else (None, np.nan)


LEADC = {}


def features(d, certs_override=None, fnd_d=None):
    """Everything known on date d. certs_override = (date, bags, eu_share) from the daily report for the live reading."""
    f = {}
    t0, c = asof(tot, d - pd.Timedelta(days=1))
    if t0 is None:
        return None
    eus = eu.get(t0, np.nan) / c
    if certs_override is not None:
        t0, c, eus = certs_override
    f["certs_date"] = t0
    f["certs"] = c
    f["lc"] = math.log(c)
    past = tot[(tot.index <= t0) & (tot.index > t0 - pd.DateOffset(years=5))]
    f["rel5"] = math.log(c / past.mean()) if len(past) >= 36 else np.nan
    for n in (1, 3):
        _, p = asof(tot, t0 - pd.DateOffset(months=n) + pd.Timedelta(days=3))
        f[f"d{n}"] = math.log(c / p) if p and p > 0 else np.nan
    f["eu_share"] = eus * 100 if eus == eus else np.nan
    cd, oi = asof(cot.open_interest_all, d, 3)
    f["oi"] = oi
    f["cover"] = c / BAGS_PER_LOT / oi * 100 if oi == oi and oi else np.nan          # certified lots as % of all futures OI
    f["lcover"] = math.log(f["cover"]) if f["cover"] == f["cover"] else np.nan
    if cd is not None:
        r = cot.loc[cd]
        f["mm_net"] = (r.m_money_positions_long_all - r.m_money_positions_short_all) / r.open_interest_all * 100
        f["mm_spread"] = r.m_money_positions_spread / r.open_interest_all * 100
    else:
        f["mm_net"] = f["mm_spread"] = np.nan
    a0, _ = asof(ag.over1y, d, 7)
    f["over1y"] = ag.over1y.get(a0, np.nan) if a0 is not None and (d - a0).days < 70 else np.nan
    f["avg_age"] = ag.avg_age.get(a0, np.nan) if a0 is not None and (d - a0).days < 70 else np.nan
    f["ico_bra"] = month_asof(ico_bra, d, 10)[1]
    f["ico_oth"] = month_asof(ico_oth, d, 10)[1]
    # flows: net change in the pile over 1-3 months (log and bags), gradings passed and bags that left (Oct 2022 on)
    cm = mk(t0)
    for n in (1, 2, 3):
        _, p = asof(tot, t0 - pd.DateOffset(months=n) + pd.Timedelta(days=3))
        f[f"db{n}"] = c - p if p == p else np.nan
    f["d2"] = math.log(c / (c - f["db2"])) if f["db2"] == f["db2"] and c - f["db2"] > 0 else np.nan
    prev2 = [mshift(cm, -1), cm] if certs_override is None else [mshift(cm, -2), mshift(cm, -1)]
    pb = [MF.pass_bags.get(m) for m in prev2]
    ob = [MF.out_bags.get(m) for m in prev2]
    f["pass2"] = sum(pb) / c * 100 if all(v == v and v is not None for v in pb) else np.nan
    f["out2"] = sum(ob) / c * 100 if all(v == v and v is not None for v in ob) else np.nan
    # Brazil -> Belgium: shipments excess over the last 3 published months (MDIC month published ~1 week after month end)
    known = [m for m in EXX.index if pd.Timestamp(m + "-01") + pd.offsets.MonthEnd(0) + pd.Timedelta(days=7) <= d]
    lk = known[-1] if known else None
    if lk:
        f["bel_x3"] = float(EXX.Belgium.loc[known[-3:]].sum())
        base3 = float(EXP.Belgium.loc[known[-3:]].sum() - f["bel_x3"])
        f["bel"] = (f["bel_x3"] / base3 * 100) if base3 > 0 else np.nan
        f["bel_x3_pile"] = f["bel_x3"] / c * 100
        f["bel_month"] = lk
    else:
        f["bel"] = f["bel_x3"] = f["bel_x3_pile"] = np.nan
    # expected certs at first notice: pile + walk-forward lead model of the monthly total change (drift + shipments BEST_L months
    # before; shipments not yet published count as normal), Oct 2020 on
    f["exp_certs"] = f["lexp"] = f["exp_add"] = np.nan
    if fnd_d is not None and lk and cm >= "2021-10":
        b = LEADC.get(cm)
        if b is None:
            b = LEADC[cm] = lead_fit("dtot", BEST_L, cm, xcols=("Belgium",))
        if b is not None:
            nmo = max(1, int(round((fnd_d - t0).days / 30.4)))
            add = 0.0
            for j in range(1, nmo + 1):
                xm = mshift(cm, j - BEST_L)
                x = float(EXX.Belgium.get(xm, np.nan)) if xm <= lk else 0.0
                add += b[0] + b[1] * (x if x == x else 0.0)
            f["exp_add"] = add
            f["exp_certs"] = max(c + add, 0.25 * c)
            f["lexp"] = math.log(f["exp_certs"])
    # pending grading (ICE daily report, Jun 2024 on, irregular): bags waiting x recent pass rate = certs to come
    pend = PEND[(PEND.index <= d) & (PEND.index >= d - pd.Timedelta(days=6))]
    f["pending"] = float(pend.iloc[-1]) if len(pend) else np.nan
    pr = MF.pass_rate.loc[[m for m in MF.index if m < mk(d)]].dropna().tail(3)
    f["pass_rate"] = float(pr.mean()) if len(pr) else np.nan
    f["pend_add"] = f["pending"] * f["pass_rate"] if f["pending"] == f["pending"] and f["pass_rate"] == f["pass_rate"] else np.nan
    f["lpend"] = math.log(c + f["pend_add"]) if f["pend_add"] == f["pend_add"] else np.nan
    # where there is no pending series: the monthly grading files (Oct 2022 on). Run-rate of bags passed (new certs) and of bags
    # leaving the pile over the last 3 published months, carried to first notice
    gm = [m for m in MF.index if pd.Timestamp(m + "-01") + pd.offsets.MonthEnd(0) + pd.Timedelta(days=7) <= d and MF.pass_bags.get(m) == MF.pass_bags.get(m)]
    f["grade_add"] = f["grade_net"] = np.nan
    if len(gm) >= 3 and fnd_d is not None:
        nmo = max(1, int(round((fnd_d - t0).days / 30.4)))
        pa = float(MF.loc[gm[-3:], "pass_bags"].mean())
        ou = float(MF.loc[gm[-3:], "out_bags"].mean())
        f["grade_add"] = pa * nmo
        f["grade_net"] = (pa - ou) * nmo
        f["sub_bags"] = float((MF.loc[gm[-3:], "pass_bags"] + MF.loc[gm[-3:], "fail_bags"]).mean())
    f["lgrade"] = math.log(c + f["grade_add"]) if f["grade_add"] == f["grade_add"] else np.nan
    f["lgnet"] = math.log(max(c + f["grade_net"], .25 * c)) if f["grade_net"] == f["grade_net"] else np.nan
    f["lexpf"] = f["lexp"] if f["lexp"] == f["lexp"] else f["lc"]
    # certs to come: pending x pass rate where the daily series has it, else the grading run-rate, else nothing
    f["lpendf"] = f["lpend"] if f["lpend"] == f["lpend"] else (f["lgrade"] if f["lgrade"] == f["lgrade"] else f["lc"])
    f["lgnetf"] = f["lgnet"] if f["lgnet"] == f["lgnet"] else f["lc"]
    f["r19"] = float(d >= R19)
    f["r23"] = float(d >= R23)
    return f


# ------------------------------------------------------------------ one row per delivery
rows = []
for code, g in spr.groupby("front"):
    g = g.set_index("bd_to_fnd")
    g = g[~g.index.duplicated(keep="last")]
    if 1 not in g.index or 21 not in g.index:
        continue
    F = fnd_of(code, 7)
    rec = {"contract": code, "label": lab(code), "fnd": F, "second": g.loc[1, "second"]}
    for k in KS + [21]:
        kk = min(g.index, key=lambda x: abs(x - k))
        if abs(kk - k) > 2:
            continue
        r = g.loc[kk]
        rec[f"date{k}"] = r.date
        rec[f"c{k}"] = r.s12
        rec[f"p{k}"] = r.s12 / r.f1 * 100
        rec[f"f{k}"] = r.f1
    if "p1" not in rec or "p21" not in rec:
        continue
    rec["chg_c"] = rec["c1"] - rec["c21"]
    lm = g[(g.index >= 1) & (g.index <= 21)]
    rec["avg_c"] = float(lm.s12.mean())
    rec["avg_p"] = float((lm.s12 / lm.f1 * 100).mean())
    rec["chg_p"] = rec["p1"] - rec["p21"]
    for k in KS + [21]:
        if f"date{k}" in rec:
            fe = features(rec[f"date{k}"], fnd_d=F)
            if fe:
                rec.update({f"{a}@{k}": b for a, b in fe.items()})
    rows.append(rec)
H = pd.DataFrame(rows).sort_values("fnd").reset_index(drop=True)
H = H[H["lc@10"].notna()].reset_index(drop=True)
if len(H) < 80:
    raise SystemExit(f"only {len(H)} deliveries with certs")
CPJ = json.load(open(need("data/coffee/certs_profile.json")))
POOL = {}
for g_ in CPJ["gap"]["deliveries"]:
    gb = g_["groups"]
    full = None
    if all("bags_b" in v for v in gb.values()):
        full = sum(v["invoice_b"] * v["bags_b"] for v in gb.values()) / sum(v["bags_b"] for v in gb.values())
    POOL[g_["contract"]] = {"paw": g_["pool_paw"], "inv_full": full, "pool_report": pd.Timestamp(g_["report"])}
H["paw"] = H.contract.map(lambda c: (POOL.get(c) or {}).get("paw"))
H["inv_full"] = H.contract.map(lambda c: (POOL.get(c) or {}).get("inv_full"))
# known at a date only once the aging report is out (about a week after month-end): bd 10 and bd 1 qualify, bd 21/30 do not
for k in (10, 1):
    H[f"paw@{k}"] = [r.paw if c_ in POOL and r[f"date{k}"] >= POOL[c_]["pool_report"] + pd.Timedelta(days=7) else np.nan
                     for c_, (_, r) in zip(H.contract, H.iterrows())]
H["reg"] = np.where(H.fnd >= R23, "post23", np.where(H.fnd >= R19, "r19_23", "pre19"))


# ------------------------------------------------------------------ model machinery
def design(df, k, xs, regs):
    X = [np.ones(len(df))]
    for x in xs:
        X.append(df[f"{x}@{k}"].values if f"{x}@{k}" in df else np.full(len(df), np.nan))
    for r in regs:
        X.append(df[f"{r}@{k}"].values)
    return np.column_stack(X)


def fit(df, k, xs, regs, y):
    X = design(df, k, xs, regs)
    ok = ~np.isnan(X).any(1) & ~np.isnan(df[y].values)
    b, *_ = np.linalg.lstsq(X[ok], df[y].values[ok], rcond=None)
    return b, ok


def walk(df, k, xs, regs, y, since=None, min_n=8, eval_from="2021-01-01"):
    """Walk-forward by delivery: each contract predicted from contracts whose first notice came before its target date."""
    out = []
    for i, r in df.iterrows():
        if r.fnd < pd.Timestamp(eval_from) or pd.isna(r.get(f"date{k}")):
            continue
        tr = df[(df.fnd < r[f"date{k}"])]
        if since is not None:
            tr = tr[tr.fnd >= since]
        X = design(tr, k, xs, regs)
        ok = ~np.isnan(X).any(1) & ~np.isnan(tr[y].values)
        if ok.sum() < max(min_n, X.shape[1] + 4):
            continue
        # a regime dummy that is constant in the training window cannot be estimated
        keep = [0] + [j for j in range(1, X.shape[1]) if np.ptp(X[ok][:, j]) > 0]
        b, *_ = np.linalg.lstsq(X[ok][:, keep], tr[y].values[ok], rcond=None)
        x = design(df.loc[[i]], k, xs, regs)[0][keep]
        if np.isnan(x).any() or pd.isna(r[y]):
            continue
        out.append({"contract": r.contract, "fnd": r.fnd, "pred": float(x @ b), "act": float(r[y]), "n": int(ok.sum())})
    return pd.DataFrame(out)


def score(w):
    if w.empty:
        return {"n": 0}
    e = w.act - w.pred
    return {"n": int(len(w)), "mae": rd(e.abs().mean(), 3), "rmse": rd(math.sqrt((e ** 2).mean()), 3), "bias": rd(e.mean(), 3),
            "first": w.contract.iloc[0], "last": w.contract.iloc[-1]}


def naive_score(df, k, y, eval_from="2021-01-01"):
    """Benchmark: previous delivery's value at the same point."""
    out = []
    for i, r in df.iterrows():
        if r.fnd < pd.Timestamp(eval_from):
            continue
        tr = df[df.fnd < r[f"date{k}"]]
        if len(tr) and not pd.isna(r[y]):
            out.append({"contract": r.contract, "fnd": r.fnd, "pred": float(tr[y].iloc[-1]), "act": float(r[y])})
    return pd.DataFrame(out)


SPECS = {
    "certs, no regimes, full sample": (["lc"], [], None),
    "certs + regime levels, full sample": (["lc"], ["r19", "r23"], None),
    "certs, from May 2019": (["lc"], ["r23"], R19),
    "certs, from Dec 2023 only": (["lc"], [], R23),
    "cover, no regimes, 2006 on": (["lcover"], [], None),
    "cover + regime levels, 2006 on": (["lcover"], ["r19", "r23"], None),
    "cover, from May 2019": (["lcover"], ["r23"], R19),
    "cover, from May 2019, no 2023 step": (["lcover"], [], R19),
    "cover, from Dec 2023 only": (["lcover"], [], R23),
    "cover + age, from May 2019": (["lcover", "over1y"], ["r23"], R19),
    "cover + age + regimes, 2016 on": (["lcover", "over1y"], ["r19", "r23"], None),
    "certs + 1-month change + regimes": (["lc", "d1"], ["r19", "r23"], None),
    "certs + 3-month change + regimes": (["lc", "d3"], ["r19", "r23"], None),
    "certs + age + regimes, 2016 on": (["lc", "over1y"], ["r19", "r23"], None),
    "expected certs at notice (Belgium lead) + regimes": (["lexpf"], ["r19", "r23"], None),
    "expected certs (pending, else grading run-rate) + regimes": (["lpendf"], ["r19", "r23"], None),
    "certs + Belgium excess (% of pile) + regimes, 2018 on": (["lc", "bel_x3_pile"], ["r19", "r23"], None),
    "expected certs (pending, else grading run-rate) + age + regimes, 2016 on": (["lpendf", "over1y"], ["r19", "r23"], None),
}
SPECS["certs + pool invoice diff + age + regimes, 2016 on"] = (["lc", "over1y", "paw"], ["r19", "r23"], None)
SPECS["expected certs + age + regimes + ICO other milds premium, 2016 on"] = (["lpendf", "over1y", "ico_oth"], ["r19", "r23"], None)
SPECS["certs + regimes + ICO other milds premium (2000 on)"] = (["lc", "ico_oth"], ["r19", "r23"], None)
SPECS["certs + pool invoice diff + regimes, 2016 on"] = (["lc", "paw"], ["r19", "r23"], None)
SPECS["certs + grading net run-rate + age + regimes"] = (["lgnetf", "over1y"], ["r19", "r23"], None)
FLOWSPECS = {"certs + 1-month change + regimes", "certs + 3-month change + regimes", "expected certs at notice (Belgium lead) + regimes",
             "expected certs (lead + pending) + regimes", "certs + Belgium excess (% of pile) + regimes, 2018 on", "certs + age + regimes, 2016 on"}
LAB = {"built": None, "specs": {}, "naive": {}, "break_scan": {}, "drivers": {}, "change": {}, "nn": {}, "depth": {}}

for k in KS:
    y = f"p{k}"
    LAB["naive"][k] = score(naive_score(H, k, y))
    for nm, (xs, regs, since) in SPECS.items():
        w = walk(H, k, xs, regs, y, since)
        LAB["specs"].setdefault(nm, {})[k] = score(w)
        # common evaluation window: deliveries from Mar 2025 (where every spec, incl. post-2023-only, can predict)
        wc = w[w.fnd >= "2025-02-01"] if len(w) else w
        LAB["specs"][nm][f"{k}_from2025"] = score(wc)

# choose the spec: lowest mean walk-forward MAE at bd 10 and bd 1 over the common window (2021+), among specs with full coverage
cands = {}
for nm, s in LAB["specs"].items():
    if all(s[k].get("n", 0) >= 20 for k in (10, 1)):
        cands[nm] = np.mean([s[k]["mae"] for k in (10, 1)])
CHOSEN = min(cands, key=cands.get)
XS, REGS, SINCE = SPECS[CHOSEN]
LAB["chosen"] = CHOSEN
LAB["cands"] = {a: rd(b, 3) for a, b in cands.items()}

# structural break scan: spread% at bd 10 on log certs, one intercept+slope break, 1997-2026 (F statistic by break date)
def ssr(df, k, y, xs, brk=None):
    X = design(df, k, xs, [])
    if brk is not None:
        dmy = (df.fnd >= brk).values.astype(float)
        X = np.column_stack([X, dmy] + [X[:, j] * dmy for j in range(1, X.shape[1])])
    ok = ~np.isnan(X).any(1) & ~np.isnan(df[y].values)
    b, *_ = np.linalg.lstsq(X[ok], df[y].values[ok], rcond=None)
    e = df[y].values[ok] - X[ok] @ b
    return float(e @ e), int(ok.sum()), X.shape[1]


for k in (10, 1):
    y = f"p{k}"
    for xs, tag in [(["lc"], "certs 1997-2026"), (["lcover"], "cover 2006-2026")]:
        s0, n, p0 = ssr(H, k, y, xs)
        scan = []
        for brk in H.fnd[(H.fnd >= "2012-01-01") & (H.fnd <= "2025-06-01")]:
            s1, n1, p1 = ssr(H, k, y, xs, brk)
            F = ((s0 - s1) / (p1 - p0)) / (s1 / (n1 - p1))
            scan.append((brk.strftime("%Y-%m"), rd(F, 2)))
        best = max(scan, key=lambda t: t[1])
        f19 = dict(scan).get(min([m for m, _ in scan if m >= "2019-04"]))
        f23 = dict(scan).get(min([m for m, _ in scan if m >= "2023-12"]))
        # two-break model vs each single break (BIC)
        def bic(brks):
            X = design(H, k, xs, [])
            cols = [X]
            for b_ in brks:
                dmy = (H.fnd >= b_).values.astype(float)
                cols += [dmy[:, None], (X[:, 1] * dmy)[:, None]]
            X2 = np.column_stack(cols)
            ok = ~np.isnan(X2).any(1) & ~np.isnan(H[y].values)
            b, *_ = np.linalg.lstsq(X2[ok], H[y].values[ok], rcond=None)
            e = H[y].values[ok] - X2[ok] @ b
            return rd(ok.sum() * math.log(e @ e / ok.sum()) + X2.shape[1] * math.log(ok.sum()), 1)
        LAB["break_scan"][f"{tag} @bd{k}"] = {"n": n, "best": best, "F_at_2019_05": f19, "F_at_2023_12": f23,
                                              "top5": sorted(scan, key=lambda t: -t[1])[:5],
                                              "bic": {"none": bic([]), "2019": bic([R19]), "2023": bic([R23]), "both": bic([R19, R23])}}

# drivers: rank correlation with the spread at bd 10 and with the month-into-notice change, within the chosen sample
SUB = H if SINCE is None else H[H.fnd >= SINCE]
DRV = {"lc": "log certified stocks", "rel5": "certs vs own 5-yr average", "lcover": "cover (certs / futures OI)", "d1": "certs change 1 month",
       "d3": "certs change 3 months", "eu_share": "European-port share", "over1y": "share over 1 year old", "avg_age": "bag-weighted age",
       "ico_bra": "ICO Brazil naturals minus ICE 2nd/3rd", "ico_oth": "ICO other milds minus ICE 2nd/3rd",
       "bel": "Brazil exports to Belgium, last 3 months vs normal", "bel_x3_pile": "Brazil-Belgium excess, % of pile",
       "d2": "certs change 2 months", "pass2": "gradings passed, 2 months, % of pile", "out2": "bags leaving the pile, 2 months, % of pile",
       "lexp": "expected certs at notice (lead model)", "lpend": "certs + pending x pass rate",
       "mm_net": "managed money net % OI", "mm_spread": "managed money spreading % OI"}


def spear(a, b):
    m = a.notna() & b.notna()
    if m.sum() < 8:
        return None, int(m.sum())
    return rd(a[m].rank().corr(b[m].rank()), 2), int(m.sum())


for scope, D_ in [("chosen sample", SUB), ("all", H), ("from Dec 2023", H[H.fnd >= R23])]:
    for x, nm in DRV.items():
        c10, n10 = spear(D_[f"{x}@10"], D_["p10"])
        c1, n1 = spear(D_[f"{x}@1"], D_["p1"]) if f"{x}@1" in D_ else (None, 0)
        cc, nc = spear(D_[f"{x}@21"], D_["chg_p"])
        # partial: correlation with the residual of the cover model
        LAB["drivers"].setdefault(scope, {})[nm] = {"level_bd10": c10, "n10": n10, "level_bd1": c1, "chg": cc, "n_chg": nc}
# residual correlations (does a driver add anything after cover?) in the chosen sample
b10, ok10 = fit(SUB, 10, XS, REGS, "p10")
res10 = pd.Series(np.nan, index=SUB.index)
res10[ok10] = SUB["p10"].values[ok10] - design(SUB, 10, XS, REGS)[ok10] @ b10
for x, nm in DRV.items():
    LAB["drivers"]["chosen sample"][nm]["vs_resid_bd10"] = spear(SUB[f"{x}@10"], res10)[0]

# month-into-notice change: predicted change = fair at bd 1 (features at bd 21) minus the spread at bd 21
def walk_change(df, since):
    out = []
    for i, r in df.iterrows():
        if r.fnd < pd.Timestamp("2021-01-01") or pd.isna(r.get("date21")):
            continue
        tr = df[df.fnd < r["date21"]]
        if since is not None:
            tr = tr[tr.fnd >= since]
        X = design(tr, 1, XS, REGS)
        ok = ~np.isnan(X).any(1) & ~np.isnan(tr["p1"].values)
        if ok.sum() < X.shape[1] + 4:
            continue
        keep = [0] + [j for j in range(1, X.shape[1]) if np.ptp(X[ok][:, j]) > 0]
        b, *_ = np.linalg.lstsq(X[ok][:, keep], tr["p1"].values[ok], rcond=None)
        x = np.array([1.0] + [r[f"{v}@21"] for v in XS] + [r[f"{v}@21"] for v in REGS])[keep]
        if np.isnan(x).any():
            continue
        out.append({"contract": r.contract, "pred": float(x @ b - r.p21), "act": float(r.chg_p), "trend": float(tr.chg_p.iloc[-1])})
    return pd.DataFrame(out)


wc = walk_change(H, SINCE)
if len(wc):
    nz = wc[wc.act.abs() > 0.05]
    LAB["change"] = {"n": int(len(wc)), "hit": rd((np.sign(nz.pred) == np.sign(nz.act)).mean() * 100, 0), "n_nonflat": int(len(nz)),
                     "hit_naive_last": rd((np.sign(nz.trend) == np.sign(nz.act)).mean() * 100, 0),
                     "hit_always_down": rd((nz.act < 0).mean() * 100, 0), "mae": rd((wc.act - wc.pred).abs().mean(), 3),
                     "mae_zero": rd(wc.act.abs().mean(), 3), "corr": rd(wc.pred.corr(wc.act), 2),
                     "big_moves_hit": rd((np.sign(nz[nz.pred.abs() > 1].pred) == np.sign(nz[nz.pred.abs() > 1].act)).mean() * 100, 0)
                     if (nz.pred.abs() > 1).sum() else None, "n_big": int((nz.pred.abs() > 1).sum())}



def walk_change2(df, xs, regs, since=None):
    """Month into notice, direct regression: change ~ spread at bd 21 + drivers at bd 21 (walk-forward)."""
    out = []
    for i, r in df.iterrows():
        if r.fnd < pd.Timestamp("2021-01-01"):
            continue
        tr = df[df.fnd < r["date21"]]
        if since is not None:
            tr = tr[tr.fnd >= since]
        X = np.column_stack([np.ones(len(tr)), tr.p21.values] + [tr[f"{v}@21"].values for v in xs + regs])
        ok = ~np.isnan(X).any(1) & ~np.isnan(tr.chg_p.values)
        if ok.sum() < X.shape[1] + 6:
            continue
        keep = [0] + [j for j in range(1, X.shape[1]) if np.ptp(X[ok][:, j]) > 0]
        b, *_ = np.linalg.lstsq(X[ok][:, keep], tr.chg_p.values[ok], rcond=None)
        x = np.array([1.0, r.p21] + [r[f"{v}@21"] for v in xs + regs])[keep]
        if np.isnan(x).any():
            continue
        out.append({"pred": float(x @ b), "act": float(r.chg_p)})
    w = pd.DataFrame(out)
    if w.empty:
        return {"n": 0}
    nz = w[w.act.abs() > 0.05]
    return {"n": int(len(w)), "hit": rd((np.sign(nz.pred) == np.sign(nz.act)).mean() * 100, 0), "mae": rd((w.act - w.pred).abs().mean(), 3),
            "mae_zero": rd(w.act.abs().mean(), 3), "corr": rd(w.pred.corr(w.act), 2)}


LAB["change2"] = {nm: walk_change2(H, xs, regs, since) for nm, (xs, regs, since) in {
    "spread + certs + regimes": (["lc"], ["r19", "r23"], None),
    "spread + certs + 1m change + regimes": (["lc", "d1"], ["r19", "r23"], None),
    "spread + expected certs (lead) + regimes": (["lexpf"], ["r19", "r23"], None),
    "spread + expected certs (lead+pending) + regimes": (["lpendf"], ["r19", "r23"], None),
    "spread + certs + Belgium excess + regimes": (["lc", "bel_x3_pile"], ["r19", "r23"], None),
    "spread + certs + age + regimes, 2016 on": (["lc", "over1y"], ["r19", "r23"], None),
    "spread + certs + MM spreading + regimes": (["lc", "mm_spread"], ["r19", "r23"], None),
    "spread only": ([], [], None)}.items()}
# Brazil -> Belgium lead on the spread itself: monthly average front spread (% of price), change month on month, vs shipments excess
spm = spr.assign(m=spr.date.dt.strftime("%Y-%m"), pct=spr.s12 / spr.f1 * 100).groupby("m").pct.mean()
for pn, (a_, b_) in PERIODS.items():
    cs = []
    for L in range(0, 7):
        z = pd.concat([EXX.Belgium.shift(L) / MF.tot.reindex(EXX.index).shift(L) * 100, spm.diff()], axis=1, join="inner").dropna()
        z = z[(z.index >= a_) & (z.index <= b_)]
        cs.append(rd(z.corr().iloc[0, 1], 2) if len(z) > 12 else None)
    LEAD["spread"][pn] = cs
LAB["lead"] = LEAD

if LAB_MODE:                                  # research only: written to the --lab file, not to the page
    # whole-pool delivery value (bag-weighted port + age + weight allowance; origin added where the origin snapshot exists) against the
    # AVERAGE front spread over the last month before first notice (bd 21 to bd 1)
    PL = {}
    Hp = H[H.paw.notna()]
    for pn, D_ in [("2016 on", Hp), ("2016-Apr 2019", Hp[Hp.fnd < R19]), ("May 2019-Nov 2023", Hp[(Hp.fnd >= R19) & (Hp.fnd < R23)]),
                   ("Dec 2023 on", Hp[Hp.fnd >= R23])]:
        e = {"n": int(len(D_))}
        for yv in ("avg_c", "avg_p"):
            e[f"rho_{yv}"] = spear(D_.paw, D_[yv])[0]
            if len(D_) >= 6:
                bb = np.polyfit(D_.paw, D_[yv], 1)
                e[f"slope_{yv}"] = rd(bb[0], 3)
                e[f"r2_{yv}"] = rd(np.corrcoef(D_.paw, D_[yv])[0, 1] ** 2, 2)
        # does it add after the certs level? rank correlation with the residual of avg_p on log certs (at bd 21) + regimes
        if len(D_) >= 10:
            Xr = np.column_stack([np.ones(len(D_)), D_["lc@21"].values] + ([D_["r23@21"].values] if np.ptp(D_["r23@21"].values) > 0 else []))
            br, *_ = np.linalg.lstsq(Xr, D_.avg_p.values, rcond=None)
            e["rho_resid_after_certs"] = spear(D_.paw, pd.Series(D_.avg_p.values - Xr @ br, index=D_.index))[0]
            e["rho_paw_certs"] = spear(D_.paw, D_["lc@21"])[0]
        PL[pn] = e
    Hf = H[H.inv_full.notna()]
    PL["full invoice incl. origin (snapshot era)"] = {"n": int(len(Hf)), "rho_avg_p": spear(Hf.inv_full, Hf.avg_p)[0] if len(Hf) >= 8 else None,
                                                       "contracts": list(Hf.label)}
    # walk-forward: average last-month spread (% of price) from the pool value alone, certs alone, both
    def walk_avg(xs, since=None):
        out = []
        for i, r in Hp.iterrows():
            if r.fnd < pd.Timestamp("2021-01-01"):
                continue
            tr = Hp[Hp.fnd < r.date21 - pd.Timedelta(days=60)] if False else Hp[Hp.fnd < r.date21]
            X = np.column_stack([np.ones(len(tr))] + [tr[x].values for x in xs])
            ok = ~np.isnan(X).any(1)
            if ok.sum() < X.shape[1] + 6:
                continue
            b, *_ = np.linalg.lstsq(X[ok], tr.avg_p.values[ok], rcond=None)
            x = np.array([1.0] + [r[x] for x in xs])
            if np.isnan(x).any():
                continue
            out.append(abs(r.avg_p - x @ b))
        return {"n": len(out), "mae": rd(np.mean(out), 3) if out else None}
    PL["walk_avg"] = {"mean only": walk_avg([]), "pool invoice": walk_avg(["paw"]), "certs (bd 21)": walk_avg(["lc@21"]),
                      "certs + age (bd 21)": walk_avg(["lc@21", "over1y@21"]), "certs + age + pool": walk_avg(["lc@21", "over1y@21", "paw"]),
                      "certs + age + regimes + pool": walk_avg(["lc@21", "over1y@21", "r23@21", "paw"]), "certs + age + regimes": walk_avg(["lc@21", "over1y@21", "r23@21"])}
    LAB["pool"] = PL
    # grading files: reconcile month-end cert changes with bags passed (implied outflow = passed - change; negative = inconsistency)
    rc = MF.dropna(subset=["pass_bags", "dtot"])
    LAB["grading_reconcile"] = {"months": int(len(rc)), "first": rc.index[0], "neg_outflow_months": int((rc.out_bags < 0).sum()),
                                "neg_outflow_list": [(m, rd(v, 0)) for m, v in rc.out_bags[rc.out_bags < 0].items()],
                                "corr_pass_vs_change": rd(rc.pass_bags.corr(rc.dtot), 2), "pass_mean": rd(rc.pass_bags.mean(), 0),
                                "out_mean": rd(rc.out_bags.mean(), 0), "out_median": rd(rc.out_bags.median(), 0)}
    dd = det.assign(m=det.date.dt.strftime("%Y-%m")).groupby("m")[["passed", "failed"]].sum()
    LAB["grading_reconcile"]["daily_vs_monthly"] = {m: {"daily_passed_bags": rd(dd.at[m, "passed"], 0), "monthly_pass_bags": rd(MF.pass_bags.get(m), 0)}
                                                   for m in dd.index}

    # ------------------------------------------------------------------ extra driver tests (Ma, 18 Nov): spot-month limit, poison pill, fundamentals
    SPOT_LIMIT = 500                              # lots: most one account may hold into the spot month (no exemption)
    for k in (30, 21, 10, 1):
        H[f"stop@{k}"] = np.exp(H[f"lc@{k}"]) / BAGS_PER_LOT / SPOT_LIMIT
    REG3 = [("before May 2019", H.fnd < R19), ("May 2019 - Nov 2023", (H.fnd >= R19) & (H.fnd < R23)), ("Dec 2023 on", H.fnd >= R23)]


    def wf(cols, y, base_from=None, eval_from="2021-01-01", min_extra=6):
        """Walk-forward OLS by delivery on explicit H columns (features dated at or before the target's start)."""
        out = []
        for i, r in H.iterrows():
            if r.fnd < pd.Timestamp(eval_from) or pd.isna(r[y]):
                continue
            tr = H[H.fnd < r.date21]
            if base_from is not None:
                tr = tr[tr.fnd >= base_from]
            X = np.column_stack([np.ones(len(tr))] + [tr[c].values.astype(float) for c in cols])
            ok = ~np.isnan(X).any(1) & tr[y].notna().values
            if ok.sum() < X.shape[1] + min_extra:
                continue
            keep = [0] + [j for j in range(1, X.shape[1]) if np.ptp(X[ok][:, j]) > 0]
            b, *_ = np.linalg.lstsq(X[ok][:, keep], tr[y].values[ok], rcond=None)
            x = np.array([1.0] + [float(r[c]) for c in cols])[keep]
            if np.isnan(x).any():
                continue
            out.append((float(r[y]), float(x @ b)))
        if not out:
            return {"n": 0}
        a = np.array(out)
        nz = np.abs(a[:, 0]) > .05
        return {"n": len(a), "mae": rd(np.mean(np.abs(a[:, 0] - a[:, 1])), 3), "hit": rd(np.mean(np.sign(a[nz, 0]) == np.sign(a[nz, 1])) * 100, 0)}


    BASE = ["lpendf@21", "over1y@21", "r19@21", "r23@21"]       # the chosen model's drivers, dated at bd 21
    # 1. spot-month limit: the pile measured in maximum-size stoppers
    X1 = {}
    H["stop_le2@21"] = (H["stop@21"] <= 2).astype(float)
    H["stop_le2@10"] = (H["stop@10"] <= 2).astype(float)
    bins = [(0, 1, "within 1 stopper"), (1, 2, "1-2 stoppers"), (2, 5, "2-5 stoppers"), (5, 1e9, "over 5 stoppers")]
    for rn, m in REG3 + [("all", H.fnd > "1900")]:
        D_ = H[m]
        X1[rn] = {lb: {"n": int(((D_["stop@10"] > lo) & (D_["stop@10"] <= hi)).sum()),
                       "p10_med": rd(D_.loc[(D_["stop@10"] > lo) & (D_["stop@10"] <= hi), "p10"].median(), 2),
                       "p1_med": rd(D_.loc[(D_["stop@10"] > lo) & (D_["stop@10"] <= hi), "p1"].median(), 2),
                       "avg_med": rd(D_.loc[(D_["stop@10"] > lo) & (D_["stop@10"] <= hi), "avg_p"].median(), 2),
                       "chg_med": rd(D_.loc[(D_["stop@10"] > lo) & (D_["stop@10"] <= hi), "chg_p"].median(), 2),
                       "chg_up_pct": rd((D_.loc[(D_["stop@10"] > lo) & (D_["stop@10"] <= hi), "chg_p"] > 0).mean() * 100, 0)}
                  for lo, hi, lb in bins}
    # residual of the chosen bd-10 fit by stopper bucket (does a tiny pile squeeze more than its log size implies?)
    b10_, ok10_ = fit(H[H.fnd >= "2016-01-01"], 10, XS, REGS, "p10")
    H16 = H[H.fnd >= "2016-01-01"]
    res = pd.Series(H16["p10"].values - design(H16, 10, XS, REGS) @ b10_, index=H16.index)
    X1["resid_bd10_by_bucket_2016on"] = {lb: {"n": int(((H16["stop@10"] > lo) & (H16["stop@10"] <= hi)).sum()),
                                              "mean_resid": rd(res[(H16["stop@10"] > lo) & (H16["stop@10"] <= hi)].mean(), 2)} for lo, hi, lb in bins}
    X1["oos"] = {"avg last month: chosen drivers": wf(BASE, "avg_p"), "avg last month: + pile within 2 stoppers": wf(BASE + ["stop_le2@21"], "avg_p"),
                 "change into notice: spread + chosen drivers": wf(["p21"] + BASE, "chg_p"),
                 "change into notice: + pile within 2 stoppers": wf(["p21"] + BASE + ["stop_le2@21"], "chg_p")}
    LAB["spot_limit"] = X1

    # 2. poison pill: exchange invoice vs ICO physical. gap = ICO group ex-dock price - (futures + pool invoice diff), per delivery from
    # the certs profile (2016 on, report at the start of the notice month); adjusted = gap minus the median of the same rule regime
    # so far (expanding, no look-ahead). Longer proxy back to 2000: ICO other milds minus the ICE 2nd/3rd average (physical premium).
    gapd = {g_["contract"]: g_["groups"].get("oth", {}).get("gap") for g_ in CPJ["gap"]["deliveries"]}
    H["gap"] = H.contract.map(gapd)
    adj = []
    for i, r in H.iterrows():
        if pd.isna(r.gap):
            adj.append(np.nan); continue
        same = H[(H.fnd < r.fnd) & (H.reg == r.reg) & H.gap.notna()]
        adj.append(r.gap - same.gap.median() if len(same) >= 3 else np.nan)
    H["gap_adj"] = adj
    X2 = {}
    for rn, m in REG3 + [("2016 on", H.fnd >= "2016-01-01")]:
        D_ = H[m]
        X2[rn] = {"n_gap": int(D_.gap.notna().sum()), "gap_vs_avg": spear(D_.gap, D_.avg_p)[0], "gap_vs_chg": spear(D_.gap, D_.chg_p)[0],
                  "gapadj_vs_avg": spear(D_.gap_adj, D_.avg_p)[0], "gapadj_vs_chg": spear(D_.gap_adj, D_.chg_p)[0],
                  "n_ico": int(D_["ico_oth@21"].notna().sum()), "ico_vs_avg": spear(D_["ico_oth@21"], D_.avg_p)[0],
                  "ico_vs_chg": spear(D_["ico_oth@21"], D_.chg_p)[0]}
        # after certs: residual of avg_p on log certs at bd 21 within the period
        Dq = D_.dropna(subset=["lc@21", "avg_p"])
        if len(Dq) >= 8:
            bq = np.polyfit(Dq["lc@21"], Dq.avg_p, 1)
            rq = Dq.avg_p - np.polyval(bq, Dq["lc@21"])
            X2[rn]["ico_vs_resid"] = spear(Dq["ico_oth@21"], rq)[0]
            X2[rn]["gap_vs_resid"] = spear(Dq.gap, rq)[0]
    X2["oos"] = {"avg: chosen drivers": wf(BASE, "avg_p"), "avg: + pool gap": wf(BASE + ["gap"], "avg_p"),
                 "avg: + ICO other milds premium": wf(BASE + ["ico_oth@21"], "avg_p"),
                 "change: spread + chosen": wf(["p21"] + BASE, "chg_p"), "change: + pool gap": wf(["p21"] + BASE + ["gap"], "chg_p"),
                 "change: + ICO premium": wf(["p21"] + BASE + ["ico_oth@21"], "chg_p")}
    X2["oos_full_history_certs_only"] = {"avg: certs + regimes": wf(["lc@21", "r19@21", "r23@21"], "avg_p", eval_from="2010-01-01"),
                                         "avg: + ICO premium": wf(["lc@21", "r19@21", "r23@21", "ico_oth@21"], "avg_p", eval_from="2010-01-01"),
                                         "change: spread + certs + regimes": wf(["p21", "lc@21", "r19@21", "r23@21"], "chg_p", eval_from="2010-01-01"),
                                         "change: + ICO premium": wf(["p21", "lc@21", "r19@21", "r23@21", "ico_oth@21"], "chg_p", eval_from="2010-01-01")}
    LAB["poison_pill"] = X2

    # 3. fundamentals: USDA PSD (final estimates, i.e. with hindsight) by marketing year; Brazil MY Y runs Jul Y - Jun Y+1
    psd = pd.read_csv(need("coffee/data/psd_coffee.csv"))
    pw = psd.groupby(["Market_Year", "Attribute_Description"]).Value.sum().unstack()
    pb = psd[psd.Country_Name == "Brazil"].pivot_table(index="Market_Year", columns="Attribute_Description", values="Value")
    FY = pd.DataFrame({"world_prod": pw["Production"], "world_cons": pw["Domestic Consumption"], "world_end": pw["Ending Stocks"],
                       "br_arabica": pb["Arabica Production"], "br_total": pb["Production"]}) / 1000
    FY = FY[FY.index >= 2002]                        # consumption of the big importers is only in PSD from MY 2002
    FY["balance"] = FY.world_prod - FY.world_cons
    FY["su"] = FY.world_end / FY.world_cons * 100
    FY["br_ar_chg"] = FY.br_arabica.pct_change() * 100
    cy = lambda d: d.year if d.month >= 7 else d.year - 1
    H["cy"] = H["date10"].map(cy)
    for c_ in ("balance", "su", "br_arabica", "br_ar_chg"):
        H[c_] = H.cy.map(FY[c_])
        H[f"{c_}_prev"] = (H.cy - 1).map(FY[c_])
    # certs 12 months on from the start of the crop year
    H["lc_chg12@10"] = [r["lc@10"] - math.log(asof(tot, r.date10 - pd.DateOffset(months=12))[1]) if asof(tot, r.date10 - pd.DateOffset(months=12))[0] is not None else np.nan
                        for _, r in H.iterrows()]
    X3 = {}
    for rn, m in [("2002 on", H.cy >= 2002), ("from May 2019", H.fnd >= R19), ("from Dec 2023", H.fnd >= R23)]:
        D_ = H[m]
        e = {"n": int(D_.balance.notna().sum()), "crop_years": int(D_.cy[D_.balance.notna()].nunique())}
        for x in ("balance", "su", "br_arabica", "br_ar_chg", "balance_prev"):
            e[x] = {"certs": spear(D_[x], D_["lc@10"])[0], "certs_chg12": spear(D_[x], D_["lc_chg12@10"])[0],
                    "spread_bd10": spear(D_[x], D_.p10)[0], "avg_last_month": spear(D_[x], D_.avg_p)[0]}
        Dq = D_.dropna(subset=["lc@10", "p10", "balance"])
        if len(Dq) >= 8:
            bq = np.polyfit(Dq["lc@10"], Dq.p10, 1)
            rq = Dq.p10 - np.polyval(bq, Dq["lc@10"])
            e["after_certs_resid_bd10"] = {x: spear(Dq[x], rq)[0] for x in ("balance", "su", "br_arabica", "br_ar_chg")}
        X3[rn] = e
    # crop-year table (one row per crop year: Brazil arabica, world balance, stocks/use, certs and spreads over that year's deliveries)
    for c_ in ("balance", "su", "br_arabica"):
        H[f"{c_}@10"] = H[c_]
    X3["oos"] = {"bd10: chosen": wf(["lpendf@10", "over1y@10", "r19@10", "r23@10"], "p10"),
                 "bd10: + world balance": wf(["lpendf@10", "over1y@10", "r19@10", "r23@10", "balance@10"], "p10"),
                 "bd10: + stocks/use": wf(["lpendf@10", "over1y@10", "r19@10", "r23@10", "su@10"], "p10"),
                 "bd10: + Brazil arabica crop": wf(["lpendf@10", "over1y@10", "r19@10", "r23@10", "br_arabica@10"], "p10"),
                 "bd10: certs + regimes (2002 on)": wf(["lc@10", "r19@10", "r23@10"], "p10", eval_from="2010-01-01"),
                 "bd10: + world balance (2002 on)": wf(["lc@10", "r19@10", "r23@10", "balance@10"], "p10", eval_from="2010-01-01"),
                 "bd10: balance + regimes, no certs (2002 on)": wf(["balance@10", "r19@10", "r23@10"], "p10", eval_from="2010-01-01"),
                 "certs: balance -> log certs (2002 on)": wf(["balance@10"], "lc@10", eval_from="2010-01-01"),
                 "certs: mean only": wf([], "lc@10", eval_from="2010-01-01")}
    LAB["fundamentals"] = X3
    CROP = []
    for y_ in sorted(FY.index):
        D_ = H[H.cy == y_]
        if y_ < 2012:
            continue
        CROP.append({"cy": f"{y_}/{str(y_ + 1)[-2:]}", "br_arabica": rd(FY.at[y_, "br_arabica"], 1), "balance": rd(FY.at[y_, "balance"], 1),
                     "su": rd(FY.at[y_, "su"], 0), "n": int(len(D_)),
                     "certs_m": rd(np.exp(D_["lc@10"]).median() / 1e6, 2) if len(D_) else None,
                     "stoppers": rd(D_["stop@10"].median(), 1) if len(D_) else None,
                     "p10_med": rd(D_.p10.median(), 2) if len(D_) else None, "avg_med": rd(D_.avg_p.median(), 2) if len(D_) else None,
                     "reg": D_.reg.iloc[-1] if len(D_) else ("post23" if y_ >= 2023 else "r19_23" if y_ >= 2019 else "pre19")})

LAB["depth"] = {"deliveries": int(len(H)), "first": H.contract.iloc[0], "cover_from": H[H["lcover@10"].notna()].contract.iloc[0],
                "age_from": H[H["over1y@10"].notna()].contract.iloc[0], "post19": int((H.fnd >= R19).sum()), "post23": int((H.fnd >= R23).sum()),
                "bel_from": H[H["bel@10"].notna()].contract.iloc[0] if H["bel@10"].notna().any() else None,
                "flows_from": H[H["pass2@10"].notna()].contract.iloc[0] if H["pass2@10"].notna().any() else None,
                "lexp_from": H[H["lexp@10"].notna()].contract.iloc[0] if H["lexp@10"].notna().any() else None,
                "pending_n": {k: int(H[f"pending@{k}"].notna().sum()) for k in (30, 10, 21, 1)}}

# ------------------------------------------------------------------ final fits (chosen spec, all deliveries in its sample)
FIT = {}
for k in KS:
    b, ok = fit(SUB, k, XS, REGS, f"p{k}")
    w = walk(H, k, XS, REGS, f"p{k}", SINCE)
    e = (w.act - w.pred) if len(w) else pd.Series([0.0])
    FIT[k] = {"b": b, "q20": float(e.quantile(.2)), "q80": float(e.quantile(.8)), "q10": float(e.quantile(.1)), "q90": float(e.quantile(.9)),
              "n": int(ok.sum())}
    if len(w) < 15:
        raise SystemExit(f"walk-forward too short at bd {k}: {len(w)}")


def fair(fe, k):
    x = np.array([1.0] + [fe[v] for v in XS] + [fe[v] for v in REGS])
    if np.isnan(x).any():
        return None
    m = float(x @ FIT[k]["b"])
    return {"mid": m, "lo": m + FIT[k]["q20"], "hi": m + FIT[k]["q80"], "lo90": m + FIT[k]["q10"], "hi90": m + FIT[k]["q90"]}


# ------------------------------------------------------------------ live reading
today = max(spr.date.max(), curve.date.max())
last_daily = dcert.index.max()
eu_now = daily[(daily.section == "certified") & (daily.date == last_daily) & (daily.port.isin(["ANT", "HA/BR", "BAR"]))].bags.sum() / dcert.iloc[-1]
POOL_NOW = CPJ["gap"]["deliveries"][-1]["pool_paw"]
LIVE_OV = (last_daily, float(dcert.iloc[-1]), eu_now)
live = features(today + pd.Timedelta(days=1), LIVE_OV, fnd_d=fnd_of(sorted([c for c in curve[curve.date == curve.date.max()].contract
                                                                            if fnd_of(c, 7) > today], key=lambda c: fnd_of(c, 7))[0], 7))
live_eom = features(today + pd.Timedelta(days=1))
if live is None or live["cover"] != live["cover"]:
    raise SystemExit("live features incomplete")
px = curve[curve.date == curve.date.max()].set_index("contract").close
cons = sorted([c for c in px.index if c[-5] in MC], key=lambda c: (int(c[-4:]), MC[c[-5]]))
upcoming = []
for i, c in enumerate(cons[:-1]):
    F = fnd_of(c, 7)
    if F <= today:
        continue
    n = cons[i + 1]
    s = float(px[c] - px[n])
    bd_left = len(pd.date_range(today, F, freq=BD)) - 1
    rec = {"contract": lab(c), "code": c, "pair": f"{lab(c)}/{lab(n)}", "first_notice": F.strftime("%Y-%m-%d"), "bd_to_fnd": int(bd_left),
           "front": rd(px[c], 2), "spread_c": rd(s, 2), "spread_pct": rd(s / px[c] * 100, 2), "fair": {}}
    lv = features(today + pd.Timedelta(days=1), LIVE_OV, fnd_d=F)
    lv["paw"] = POOL_NOW
    rec["exp_certs"] = rd(lv["exp_certs"], 0)
    rec["exp_pend"] = rd(lv["certs"] + lv["pend_add"], 0) if lv["pend_add"] == lv["pend_add"] else None
    for k in KS:
        fr = fair(lv, k)
        if fr:
            rec["fair"][str(k)] = {"pct": {a: rd(v, 2) for a, v in fr.items()}, "c": {a: rd(v * px[c] / 100, 2) for a, v in fr.items()}}
        # the same model on today's pile alone (nothing added for bags in the grading queue)
        lv2 = dict(lv)
        for v in ("lexpf", "lpendf", "lgnetf"):
            lv2[v] = lv["lc"]
        fr2 = fair(lv2, k)
        if fr2:
            rec.setdefault("fair_pile", {})[str(k)] = {"pct": {a: rd(v, 2) for a, v in fr2.items()}, "c": {a: rd(v * px[c] / 100, 2) for a, v in fr2.items()}}
    # compare the market with the fair value at the nearest fixed point not yet passed
    kk = min([k for k in KS if k <= max(bd_left, 1)] or [1], key=lambda k: abs(k - bd_left)) if bd_left <= 30 else 30
    rec["compare_at"] = kk
    fr = rec["fair"].get(str(kk))
    if fr:
        lo, hi = fr["pct"]["lo"], fr["pct"]["hi"]
        rec["gap_pct"] = rd(rec["spread_pct"] - fr["pct"]["mid"], 2)
        rec["gap_c"] = rd(s - fr["c"]["mid"], 2)
        rec["read"] = "rich" if rec["spread_pct"] > hi else "cheap" if rec["spread_pct"] < lo else "in range"
    upcoming.append(rec)
    if len(upcoming) >= 3:
        break
if not upcoming:
    raise SystemExit("no upcoming contract on the curve")

# cover reading against history (at bd 10 of past deliveries)
hc = H["cover@10"].dropna()
hs = SUB["cover@10"].dropna()
cover_now = live["cover"]
front_oi = float(roll["oi"]) if roll.get("oi") else None
cover_front = (live["certs"] / BAGS_PER_LOT / front_oi * 100) if front_oi else None

# nearest past deliveries (chosen sample): standardised log cover, age share, 3-month change
NNV = [v for v in ["lcover", "over1y", "d3"] if live.get(v) == live.get(v)]
P10 = SUB[list(dict.fromkeys([f"{v}@10" for v in NNV] + ["contract", "label", "p10", "p1", "chg_p", "c10", "c1", "cover@10", "over1y@10", "fnd"]))].dropna()
Z = P10[[f"{v}@10" for v in NNV]]
mu, sd = Z.mean(), Z.std()
dz = (((Z - mu) / sd) - ((pd.Series({f"{v}@10": live[v] for v in NNV}) - mu) / sd)).pow(2).sum(1).pow(.5)
nn = P10.assign(dist=dz).nsmallest(6, "dist")
nn_out = [{"contract": r.label + (" (" + str(r.fnd.year) + ")" if False else ""), "code": r.contract, "cover": rd(r["cover@10"], 1),
           "over1y": rd(r["over1y@10"], 0), "p10": rd(r.p10, 2), "p1": rd(r.p1, 2), "chg": rd(r.chg_p, 2), "c10": rd(r.c10, 2), "c1": rd(r.c1, 2)}
          for _, r in nn.iterrows()]
LAB["nn"] = {"vars": NNV, "rows": nn_out}

# scatter: spread % against cover at the fixed point of the nearest contract, every delivery with cover, by regime;
# fitted line at today's open interest, age and rules
m0 = upcoming[0]
SK = m0["compare_at"]
sc = H[H[f"cover@{SK}"].notna()]
hk = sc[f"cover@{SK}"]
grid = np.exp(np.linspace(math.log(max(min(hk.min(), cover_now) * .9, .2)), math.log(hk.max()), 30))
line = []
for g in grid:
    fe = dict(live); fe["lcover"] = math.log(g)
    for v in ("lc", "lexpf", "lpendf", "lgnetf"):
        fe[v] = math.log(g / 100 * live["oi"] * BAGS_PER_LOT)
    fr = fair(fe, SK)
    if fr:
        line.append({"x": rd(g, 2), "y": rd(fr["mid"], 2), "lo": rd(fr["lo"], 2), "hi": rd(fr["hi"], 2)})
REGL = {"pre19": "Before May 2019", "r19_23": "May 2019 – Nov 2023", "post23": "Dec 2023 on (re-grading barred)"}
KNAME = {30: "30 business days before first notice", 10: "10 business days before first notice", 1: "the day before first notice"}

# plain-English brief
nxt = next((u for u in upcoming if u["bd_to_fnd"] > 10), None)
pct_hist = rd((hc <= cover_now).mean() * 100, 0)
pct_reg = rd((hs <= cover_now).mean() * 100, 0)
pending_now = float(det[det.date == det.date.max()].pending.sum()) if det.date.max() >= last_daily else float(PEND.iloc[-1])
pr_now = live["pass_rate"]
exp_pend = m0.get("exp_pend")
low_txt = f"lower than at {100 - pct_hist:.0f}% of past deliveries since 2006" if pct_hist < 50 else f"higher than at {pct_hist:.0f}% of past deliveries since 2006"
brief = [f"ICE certified stocks are {live['certs']:,.0f} bags ({live['certs'] / BAGS_PER_LOT:,.0f} lots, {last_daily:%d %b %Y}), "
         f"{cover_now:.1f}% of KC futures open interest: {low_txt}. "
         + (f"Another {pending_now:,.0f} bags are waiting to be graded; at the recent pass rate ({pr_now * 100:.0f}%) that would take the pile to about {exp_pend:,.0f} bags."
            if exp_pend else "")]
for u in [m0] + ([nxt] if nxt and nxt is not m0 else []):
    f_ = u["fair"][str(u["compare_at"])]
    fp = (u.get("fair_pile") or {}).get(str(u["compare_at"]))
    when = KNAME[u["compare_at"]]
    word = {"cheap": "below", "rich": "above", "in range": "inside"}[u["read"]]
    brief.append(f"{u['pair']} at {u['spread_c']:+.2f}¢ ({u['spread_pct']:+.2f}% of price, {u['bd_to_fnd']} business days before first notice) is {word} "
                 f"the model's fair range for {when}, {f_['c']['lo']:+.1f} to {f_['c']['hi']:+.1f}¢, which counts the pending bags at the recent pass rate"
                 + (f" ({fp['c']['lo']:+.1f} to {fp['c']['hi']:+.1f}¢ on today's pile alone)." if fp else "."))
sim = pd.DataFrame(nn_out)
bk = FIT[10]["b"]
sl = bk[1]
brief.append(f"Past deliveries with a similar pile ({', '.join(sim.contract.head(4))}) traded {sim.p10.min():+.1f} to {sim.p10.max():+.1f}% ten days before notice. "
             f"What would change the reading: each 10% more certified coffee lowers the fair spread by about {abs(sl * math.log(1.1)):.2f} points of price "
             f"({abs(sl * math.log(1.1)) * m0['front'] / 100:.1f}¢); the pending queue passing grading would add to the pile, and a smaller premium of physical washed coffee over the exchange "
             f"(now {live['ico_oth']:.0f}¢, against a median of {float(ico_oth.median()):.0f}¢ since 2000) would lower the fair spread.")

# spot-month limit reading: pile in maximum-size stoppers (500 lots), and past deliveries with a pile this small
SPOT_LIMIT = 500                              # lots: most one account may hold into the spot month (no exemption)
stop_now = live["certs"] / BAGS_PER_LOT / SPOT_LIMIT
SPOT_OUT = {"limit": SPOT_LIMIT, "now": rd(stop_now, 2), "with_pending": rd(exp_pend / BAGS_PER_LOT / SPOT_LIMIT, 2) if exp_pend else None}
VARS = ["KC front minus second at 30 and 10 business days before first notice and on the day before it (% of the front price and ¢/lb; ICE settlements per contract)",
        "ICE certified arabica stocks (month-end since 1996; latest daily report for today)",
        "Bags pending grading x the recent pass rate (ICE daily report and monthly grading summary)",
        "Age of the certified pile: share over one year old (ICE aging report)",
        "ICO other milds ex-dock price minus the ICE 2nd/3rd position average (physical washed premium over the exchange)",
        "Rule periods: May 2019 port and rent rules, December 2023 re-grading ban",
        "Certified lots as % of all KC futures open interest (CFTC) and against the 500-lot spot-month limit (readings and chart only)"]
OUTJ = {
    "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "asof": today.strftime("%Y-%m-%d"), "certs_date": last_daily.strftime("%Y-%m-%d"),
    "basis": {"since": SINCE.strftime("%Y-%m") if SINCE is not None else H.fnd.min().strftime("%Y-%m"), "n": FIT[10]["n"]},
    "now": {"certs": rd(live["certs"], 0), "lots": rd(live["certs"] / BAGS_PER_LOT, 0), "oi": rd(live["oi"], 0),
            "cover": rd(cover_now, 2), "cover_pct_all": pct_hist, "cover_pct_regime": pct_reg, "cover_median_all": rd(hc.median(), 2),
            "cover_median_regime": rd(hs.median(), 2), "front_oi": front_oi, "front_oi_date": roll.get("asof"),
            "front_contract": roll.get("label"), "cover_front": rd(cover_front, 1), "over1y": rd(live["over1y"], 1),
            "avg_age": rd(live["avg_age"], 0), "d1": rd(live["d1"] * 100, 1) if live["d1"] == live["d1"] else None,
            "d3": rd(live["d3"] * 100, 1) if live["d3"] == live["d3"] else None, "pending": rd(pending_now, 0),
            "pass_rate": rd(pr_now * 100, 0), "exp_pend": rd(exp_pend, 0), "pending_date": det.date.max().strftime("%Y-%m-%d"),
            "ico_oth": rd(live["ico_oth"], 1), "ico_month": month_asof(ico_oth, today + pd.Timedelta(days=1), 10)[0],
            "ico_oth_median": rd(float(ico_oth.median()), 1),
            "eom_certs": rd(live_eom["certs"], 0) if live_eom else None, "eom_date": live_eom["certs_date"].strftime("%Y-%m-%d") if live_eom else None},
    "upcoming": upcoming,
    "scatter": {"k": SK, "k_name": KNAME[SK], "points": [{"x": rd(r[f"cover@{SK}"], 2), "y": rd(r[f"p{SK}"], 2), "c": r.label, "reg": r.reg, "yr": int(r.fnd.year)} for _, r in sc.iterrows()],
                "regimes": REGL, "line": line, "line_label": "Fair spread at today's open interest, age and rules",
                "today": {"x": rd(cover_now, 2), "y": rd(m0["spread_pct"], 2), "label": f"{m0['pair']} now"},
                "today_exp": {"x": rd(exp_pend / BAGS_PER_LOT / live["oi"] * 100, 2) if exp_pend else None, "y": rd(m0["spread_pct"], 2)}},
    "spot": SPOT_OUT,
    "similar": nn_out,
    "brief": brief,
    "variables": [v for v in VARS if v],
}
json.dump(OUTJ, open(OUT, "w"), separators=(",", ":"), allow_nan=False)

if "--lab" in sys.argv:
    LAB["built"] = OUTJ["built"]
    LAB["coef"] = {k: [rd(v, 4) for v in FIT[k]["b"]] for k in KS}
    LAB["coef_names"] = ["const"] + XS + REGS
    LAB["live"] = {a: (rd(v, 4) if isinstance(v, (int, float)) else str(v)) for a, v in live.items()}
    p = sys.argv[sys.argv.index("--lab") + 1]
    json.dump(LAB, open(p, "w"), indent=1, default=str)
print(f"KC spread model ({CHOSEN}; n={FIT[10]['n']}): cover {cover_now:.2f}% ({pct_hist:.0f}th pct since 2006); "
      + "; ".join(f"{u['pair']} {u['spread_pct']:+.2f}% vs fair {u['fair'].get(str(u['compare_at']), {}).get('pct', {}).get('mid')}% @bd{u['compare_at']} [{u.get('read')}]" for u in upcoming))
