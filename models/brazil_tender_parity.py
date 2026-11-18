"""Brazil tender parity: cost of putting a blended Brazil lot on the ICE "C" exchange in Antwerp vs what the exchange pays.

Trader logic (Ma, 18 Nov 2026): certs are rarely pure semi-washed. Exporters blend fine cup / good cup with semi-washed in the
share that passes grading. Brazil prices are about FOB, so freight, grading and warehouse costs are added to get tender
parity; the exchange pays a fixed differential (Brazil -6c, Antwerp -1.25c). The wider good cup trades over semi-washed, the
more a passing blend is worth on the exchange against its value in the physical market.

Prices (US cents/lb, Brazil origin, treated as FOB-equivalent per Ma):
  semi-washed (cereja descascado), co-op average      data/coffee/brazil_physical_history.csv  cd_usc_lb  (Notícias Agrícolas, 2018 on)
  fine/good cup: CEPEA tipo 6 bebida dura para melhor  cepea_usc_lb (Ma's CEPEA download, 1996 on) + premium (FC_ADJ)
  alternative good cup: B3 4/5 front future (ICF1!)   icf_usc_lb (TradingView, 1999 on; trades above semi-washed, see below)
Blend cost = w x semi-washed + (1 - w) x fine/good cup (CEPEA tipo 6 + a fine-cup premium), w = semi-washed share: 15-30%, base 30%
  (Ma's trading experience: about 70% fine cup / 30% semi-washed or less). All-in shipping to the Antwerp warehouse 8-10c (Ma).
Cost to tender (each item: base, low, high, source or "assumption") -> COSTS below.
Exchange value = ICE KC 2nd position (the contract a lot shipped now can be tendered against) + Brazil origin differential
  (-9c Mar 2013 - Apr 2016, -6c from May 2016) + Antwerp port differential (-1.25c); fresh coffee, no age discount.
  EUDR: from 30 Dec 2026 new EU-port gradings need validated due-diligence data, so a new tender must be EUDR-compliant coffee
  (the Appendix VIII transition discount from Mar 2027 applies to older non-DDI stock, not to a new compliant lot).
Margin = exchange value - cost to tender. Expected failure cost = (1 - p) / p x loss on a failed lot, p = Brazil pass rate
  (ICE monthly grading files, last 3 months, Oct 2022 on; median before).
Output: data/coffee/tender_parity.json (page), data/coffee/tender_parity_history.csv. --lab PATH writes the lead / price tests.
"""
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data", "coffee")
OUT = os.path.join(D, "tender_parity.json")
HIST = os.path.join(D, "tender_parity_history.csv")
LB_BAG = 132.277
LOT_BAGS = 37500 / LB_BAG                       # 60-kg bags per 37,500-lb lot (283.5)
W_RANGE = (0.15, 0.3)                          # semi-washed share of the blend (Ma: about 30% or less; base 30%)
W_BASE = 0.3


def need(p):
    q = os.path.join(ROOT, p)
    if not os.path.exists(q):
        raise SystemExit(f"missing input: {p}")
    return q


def rd(v, n=2):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), n)


# ------------------------------------------------------------------ inputs
H = pd.read_csv(need("data/coffee/brazil_physical_history.csv"), parse_dates=["date"]).set_index("date").sort_index()
KC = pd.read_csv(need("data/coffee/kc_spreads_history.csv"), parse_dates=["date"]).set_index("date").sort_index()
PC = pd.read_csv(need("coffee/data/prices_cont.csv"), parse_dates=["date"])
US3M = PC[PC.symbol == "US03MY"].set_index("date").close.sort_index()
RC1 = PC[PC.symbol == "RC1!"].set_index("date").close.sort_index()
KC1 = PC[PC.symbol == "KC1!"].set_index("date").close.sort_index()
ICF = PC[PC.symbol == "ICF1!"].set_index("date").close.sort_index() / LB_BAG * 100
WR = pd.read_csv(need("data/coffee/ref/warehouse_rates.csv"))
WR = WR[(WR.port == "ANTWERP")]
WR = WR[WR.effective_from == WR.effective_from.max()]
STOR_BAG = float(WR.storage_usd_bag_month.mean())
GR = pd.read_csv(need("data/coffee/ice_grading_monthly.csv"))
GB = GR[(GR.scope == "month") & (GR.row_type == "origin") & (GR.stage == "original") & (GR.name == "Brazil")].set_index("month")[["passed", "failed"]]
GB["pass"] = GB.passed / (GB.passed + GB.failed)
GB["sub_bags"] = (GB.passed + GB.failed) * LOT_BAGS
GB["pass_bags"] = GB.passed * LOT_BAGS
P_MED = float(GB["pass"].median())
EOM = pd.read_csv(need("data/coffee/ice_certs_eom_by_port.csv"), parse_dates=["date"])
ANT = EOM[EOM.port == "ANTWERP"].set_index("date").bags.sort_index()
TOT = EOM[EOM.port == "TOTAL"].set_index("date").bags.sort_index()
DC = pd.read_csv(need("data/coffee/ice_certs.csv"), parse_dates=["date"])
PEND_BR = DC[(DC.section == "pending") & (DC.origin == "Brazil")].groupby("date").bags.sum().sort_index()
CERT_BR = DC[(DC.section == "certified") & (DC.origin == "Brazil")].groupby("date").bags.sum().sort_index()

# ------------------------------------------------------------------ cost items (US cents/lb unless computed)
COSTS = [
    # key, label, base, low, high, source
    ("fob", "Origin to FOB Santos (inland, fobbing, export papers)", 0.0, 0.0, 2.0,
     "assumption: Ma treats the co-op and B3 prices as about FOB; up to 2c if they are ex-warehouse Minas / São Paulo"),
    ("freight", "All-in shipping Santos to the Antwerp warehouse (ocean freight, port, devanning, drayage)", 9.0, 8.0, 10.0,
     "Ma's trading experience (8-10c); no free public index for the Santos-North Europe lane"),
    ("in_charge", "Warehouse in-charge (receiving, weighing, sampling)", 0.5, 0.3, 1.0,
     "assumption: in-charges are not in the ICE warehouse rate file (data/coffee/ref/warehouse_rates.csv has storage, load-out, rebagging only)"),
    ("grading", "ICE grading and sampling fees", 0.5, 0.3, 1.0, "assumption (about 1c fees and grading together with the in-charge)"),
    ("eudr", "EUDR-compliant coffee premium (needed for EU gradings from 30 Dec 2026)", 0.0, 0.0, 3.0,
     "assumption: no public price for compliant vs non-compliant Brazil; ICE Appendix VIII"),
]
FAIL_LOSS = (5.0, 3.0, 10.0)                    # c/lb lost on a lot that fails (resold in Europe as physical); assumption
FIN_DAYS = (75, 60, 100)                        # shipment ~25 days + grading ~3 weeks + to first notice; assumption
FIN_SPREAD = 2.0                                # % over US 3-month bill; assumption
INS = (0.15, 0.10, 0.30)                        # % of cargo value, marine insurance; assumption
STOR_M = (1.0, 0.5, 2.0)                        # months of Antwerp storage paid before first notice; assumption


def origin_diff(d):
    return -9.0 if d < pd.Timestamp("2016-05-01") else -6.0


PORT_ANT = -1.25


def pass_rate_at(d):
    """Brazil pass rate over the last 3 published months (file month + 7 days), else the median."""
    ms = [m for m in GB.index if pd.Timestamp(m + "-01") + pd.offsets.MonthEnd(0) + pd.Timedelta(days=7) <= d]
    if len(ms) >= 1:
        g = GB.loc[ms[-3:]]
        return float(g.passed.sum() / (g.passed + g.failed).sum()), True
    return P_MED, False


FC_ADJ = (5.0, 0.0, 18.0)                       # fine/good cup over CEPEA tipo 6, c/lb (SAFRAS check Oct 2025: good cup R$30-130/bag over CEPEA)


def stack(d, price, kc2, case=1, w=None):
    """Cost items and exchange value at date d for a lot costing `price` c/lb at origin. case 1 = base, 0 = low, 2 = high.
    w = semi-washed share when the price is a blend with CEPEA as the fine-cup leg (adds the fine-cup premium over CEPEA)."""
    it = {c[0]: [c[3], c[2], c[4]][case] for c in COSTS}          # c = (key, label, base, low, high, source)
    if w is not None:
        it["fc_adj"] = (1 - w) * [FC_ADJ[1], FC_ADJ[0], FC_ADJ[2]][case]
    r = float(US3M[US3M.index <= d].iloc[-1]) if (US3M.index <= d).any() else 2.0
    it["finance"] = price * (r + FIN_SPREAD) / 100 * [FIN_DAYS[1], FIN_DAYS[0], FIN_DAYS[2]][case] / 365
    it["insurance"] = price * [INS[1], INS[0], INS[2]][case] / 100
    it["storage"] = STOR_BAG * [STOR_M[1], STOR_M[0], STOR_M[2]][case] / LB_BAG * 100
    p, _ = pass_rate_at(d)
    it["fail"] = (1 - p) / max(p, 0.05) * [FAIL_LOSS[1], FAIL_LOSS[0], FAIL_LOSS[2]][case]
    cost = sum(it.values())
    exv = kc2 + origin_diff(d) + PORT_ANT
    return it, cost, exv, p


# ------------------------------------------------------------------ history at each co-op quote date
# fine cup / good cup proxy: CEPEA tipo 6 bebida dura para melhor (domestic hard cup or better). Since 2018 co-op semi-washed has
# traded a median ~11c over it, in line with Ma's ~10c normal semi-washed premium over fine cup, and CEPEA sits within a few cents
# of the public SAFRAS good-cup quotes (data/coffee/manual/brazil_export_diffs.csv). B3 4/5 (ICF1!) is kept as an alternative:
# a futures price with carry and front-month squeezes, it trades ABOVE semi-washed (median -6c), which contradicts that normal.
q = H[H.cd_usc_lb.notna() & H.cepea_usc_lb.notna()].copy()
k = KC.reindex(q.index, method="ffill", tolerance=pd.Timedelta(days=4))
q["kc2"] = k.f2
q["kc2_contract"] = k.second
q["kc1"] = k.f1
q = q.dropna(subset=["kc2"])
rows = []
for d, r in q.iterrows():
    e = {"date": d, "sw": r.cd_usc_lb, "fc": r.cepea_usc_lb, "gc_b3": r.icf_usc_lb, "t6": r.t6_coop_usc_lb, "kc2": r.kc2, "kc1": r.kc1,
         "sw_minus_fc": r.cd_usc_lb - r.cepea_usc_lb, "sw_minus_b3": r.cd_usc_lb - r.icf_usc_lb}
    for w in W_RANGE:
        blend = w * r.cd_usc_lb + (1 - w) * r.cepea_usc_lb
        it, cost, exv, p = stack(d, blend, r.kc2, w=w)
        e[f"margin_w{int(w * 100)}"] = exv - blend - cost
        if r.icf_usc_lb == r.icf_usc_lb:
            b2 = w * r.cd_usc_lb + (1 - w) * r.icf_usc_lb
            e[f"margin_b3_w{int(w * 100)}"] = exv - b2 - stack(d, b2, r.kc2)[1]
    e["exchange_value"] = exv
    e["pass_rate"] = p
    # value of semi-washed itself on the exchange against its physical price (pure SW lot, w = 1)
    e["margin_sw_only"] = exv - r.cd_usc_lb - stack(d, r.cd_usc_lb, r.kc2)[1]
    rows.append(e)
T = pd.DataFrame(rows).set_index("date")
T.round(3).to_csv(HIST, date_format="%Y-%m-%d")

# daily CEPEA margin since Brazil became deliverable (CEPEA daily from 1996; costs at base, failure cost from pass rates)
cep = H.cepea_usc_lb.dropna()
cep = cep[cep.index >= "2013-01-01"]
kd = KC.reindex(cep.index, method="ffill", tolerance=pd.Timedelta(days=4))
CM = pd.Series({d: (kd.at[d, "f2"] + origin_diff(d) + PORT_ANT - v - sum(stack(d, v, kd.at[d, "f2"])[0].values()))
                for d, v in cep.items() if kd.at[d, "f2"] == kd.at[d, "f2"]}).sort_index()
# daily good-cup (B3) margin since 2013
gcd = ICF[ICF.index >= "2013-01-01"]
kg = KC.reindex(gcd.index, method="ffill", tolerance=pd.Timedelta(days=4))
GM = pd.Series({d: (kg.at[d, "f2"] + origin_diff(d) + PORT_ANT - v - sum(stack(d, v, kg.at[d, "f2"])[0].values()))
                for d, v in gcd.items() if kg.at[d, "f2"] == kg.at[d, "f2"]}).sort_index()

# ------------------------------------------------------------------ today
last = T.index[-1]
r = q.loc[last]
now = {"date": last.strftime("%Y-%m-%d"), "sw": rd(r.cd_usc_lb, 1), "fc": rd(r.cepea_usc_lb, 1), "gc_b3": rd(r.icf_usc_lb, 1), "t6": rd(r.t6_coop_usc_lb, 1),
       "kc2": rd(r.kc2, 2), "kc2_contract": r.kc2_contract, "sw_minus_fc": rd(r.cd_usc_lb - r.cepea_usc_lb, 1), "sw_minus_b3": rd(r.cd_usc_lb - r.icf_usc_lb, 1),
       "fc_vs_kc2": rd(r.cepea_usc_lb - r.kc2, 1), "sw_vs_kc2": rd(r.cd_usc_lb - r.kc2, 1)}
gs = T.sw_minus_fc
now["sw_frozen"] = True    # co-op semi-washed quotes stopped (Notícias Agrícolas blocks runners): the card is as of the last co-op date
now["sw_minus_fc_pct_all"] = rd((gs <= gs.iloc[-1]).mean() * 100, 0)
g5 = gs[gs.index >= last - pd.DateOffset(years=5)]
now["sw_minus_fc_pct5y"] = rd((g5 <= gs.iloc[-1]).mean() * 100, 0)
now["sw_minus_fc_median"] = rd(gs.median(), 1)
now["ma_normal"] = 10.0
stk = {}
for w in W_RANGE:
    blend = w * r.cd_usc_lb + (1 - w) * r.cepea_usc_lb
    cases = [stack(last, blend, r.kc2, c, w=w) for c in (0, 1, 2)]
    it, cost, exv, p = cases[1]
    stk[f"w{int(w * 100)}"] = {"w": w, "blend": rd(blend, 1), "costs": {a: rd(b, 2) for a, b in it.items()}, "cost_items_total": rd(cost, 1),
                               "cost_total": rd(blend + cost, 1), "exchange_value": rd(exv, 1), "margin": rd(exv - blend - cost, 1),
                               "margin_low_cost": rd(exv - blend - cases[0][1], 1), "margin_high_cost": rd(exv - blend - cases[2][1], 1)}
p_now, p_live = pass_rate_at(last)
labels = {c[0]: c[1] for c in COSTS}
labels["fc_adj"] = "Fine/good cup premium over CEPEA tipo 6, on the fine-cup share"
labels.update(finance=f"Finance, {FIN_DAYS[0]} days at US 3-month + {FIN_SPREAD:.0f}%", insurance=f"Marine insurance, {INS[0]}% of value",
              storage=f"Antwerp storage to first notice, {STOR_M[0]:.0f} month at US${STOR_BAG:.2f}/bag",
              fail="Expected grading-failure cost: (1 - pass rate) / pass rate x loss on a failed lot")
srcs = {c[0]: {"base": c[2], "low": c[3], "high": c[4], "source": c[5]} for c in COSTS}
srcs["fc_adj"] = {"base": FC_ADJ[0], "low": FC_ADJ[1], "high": FC_ADJ[2],
                  "source": "calibration: SAFRAS & Mercado good cup Sul de Minas R$2,240-2,340 (20 Oct 2025) vs CEPEA ~R$2,210 = 4-18c over CEPEA; base 5c (assumption). Co-op semi-washed has traded a median 11c over CEPEA since 2018, close to Ma's ~10c normal over fine cup"}
srcs.update(finance={"base": f"{FIN_DAYS[0]} days", "low": FIN_DAYS[1], "high": FIN_DAYS[2], "source": "assumption on days; rate = US 3-month bill (TradingView US03MY) + 2% (assumption)"},
            insurance={"base": INS[0], "low": INS[1], "high": INS[2], "source": "assumption, % of cargo value"},
            storage={"base": STOR_M[0], "low": STOR_M[1], "high": STOR_M[2], "source": f"ICE posted Antwerp storage rates (data/coffee/ref/warehouse_rates.csv, average US${STOR_BAG:.2f}/bag/month); months assumed"},
            fail={"base": FAIL_LOSS[0], "low": FAIL_LOSS[1], "high": FAIL_LOSS[2],
                  "source": f"Brazil pass rate {p_now * 100:.0f}% ({'ICE grading files, last 3 months' if p_live else 'median of the grading files'}); loss on a failed lot assumed (c/lb)"})
mid = stk["w30"]
wide = now["sw_minus_fc"] - now["ma_normal"]
reading = [f"Semi-washed trades {now['sw_minus_fc']:+.1f}¢ over fine/good cup (co-op cereja descascado vs CEPEA tipo 6, {now['date']}), against a normal of about +10¢ "
           f"(median since 2018 {now['sw_minus_fc_median']:+.1f}¢; {now['sw_minus_fc_pct5y']:.0f}th percentile of 5 years): "
           f"{'wide, so blending a little semi-washed into fine cup and tendering is attractive' if wide > 3 else 'narrow, little extra reason to blend' if wide < -3 else 'about normal'}.",
           f"A 15-30% semi-washed blend costs {stk['w15']['cost_total']:.0f}-{stk['w30']['cost_total']:.0f}¢ in the Antwerp warehouse against an exchange value of "
           f"{mid['exchange_value']:.0f}¢ ({now['kc2_contract']} − 6¢ Brazil − 1.25¢ Antwerp): tender margin {stk['w30']['margin']:+.0f} to {stk['w15']['margin']:+.0f}¢ "
           f"({min(v['margin_high_cost'] for v in stk.values()):+.0f} to {max(v['margin_low_cost'] for v in stk.values()):+.0f}¢ across the cost ranges); "
           f"{'tendering pays, so expect more Brazil coffee to be submitted for grading' if mid['margin'] > 0 else 'tendering does not pay at these costs'}."]
# live margin on CEPEA (co-op semi-washed quotes stopped 11 Nov 2026): semi-washed proxied as CEPEA + Ma's normal 10c premium
SW_NORMAL = 10.0
cl = cep.index[-1]
kcl = KC[KC.index <= cl].iloc[-1]
live = {"date": cl.strftime("%Y-%m-%d"), "cepea": rd(cep.iloc[-1], 1), "kc2": rd(kcl.f2, 2), "kc2_contract": kcl.get("second", now["kc2_contract"]),
        "sw_proxy_note": f"semi-washed taken as CEPEA + {SW_NORMAL:.0f}¢ (Ma's normal premium over fine cup)", "stack": {}}
for w in W_RANGE:
    blend = cep.iloc[-1] + w * SW_NORMAL
    cases = [stack(cl, blend, kcl.f2, c, w=w) for c in (0, 1, 2)]
    it, cost, exv, p = cases[1]
    live["stack"][f"w{int(w * 100)}"] = {"blend": rd(blend, 1), "cost_total": rd(blend + cost, 1), "exchange_value": rd(exv, 1),
                                         "margin": rd(exv - blend - cost, 1), "margin_low_cost": rd(exv - blend - cases[0][1], 1),
                                         "margin_high_cost": rd(exv - blend - cases[2][1], 1)}
lm = live["stack"]
reading.insert(0, f"Live, on CEPEA ({live['date']}, {live['cepea']:.1f}¢; semi-washed taken at CEPEA + {SW_NORMAL:.0f}¢): a 15-30% semi-washed blend in the "
                  f"Antwerp warehouse costs {lm['w15']['cost_total']:.0f}-{lm['w30']['cost_total']:.0f}¢ against {lm['w30']['exchange_value']:.0f}¢ from the exchange "
                  f"→ tender margin {lm['w30']['margin']:+.0f} to {lm['w15']['margin']:+.0f}¢ "
                  f"({min(v['margin_high_cost'] for v in lm.values()):+.0f} to {max(v['margin_low_cost'] for v in lm.values()):+.0f}¢ across cost ranges). "
                  f"The lines below use the last co-op semi-washed quote ({now['date']}).")
hist_w = T.resample("W-FRI").last().dropna(subset=["sw_minus_fc"])
OUTJ = {"built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "now": now, "stack": stk, "cost_labels": labels, "cost_sources": srcs,
        "w_base": W_BASE, "pass_rate": rd(p_now * 100, 0), "pass_rate_source": "ICE monthly grading files, Brazil, last 3 months" if p_live else "median",
        "exchange_rule": {"origin_brazil_c": origin_diff(last), "port_antwerp_c": PORT_ANT, "contract": now["kc2_contract"],
                          "eudr": "new EU-port gradings from 30 Dec 2026 need validated EUDR due-diligence data (ICE Appendix VIII); the transition discount from Mar 2027 applies to older non-compliant stock"},
        "history": {"dates": [d.strftime("%Y-%m-%d") for d in hist_w.index], "sw_minus_fc": [rd(v, 1) for v in hist_w.sw_minus_fc],
                    "margin_w15": [rd(v, 1) for v in hist_w.margin_w15], "margin_w30": [rd(v, 1) for v in hist_w.margin_w30]},
        "reading": reading, "live_cepea": live,
        "inputs": {"semi_washed": "co-op cereja descascado average (Notícias Agrícolas), R$/bag at BCB PTAX",
                   "fine_cup": "CEPEA/ESALQ arabica index, tipo 6 bebida dura para melhor (proxy for fine/good cup; calibration in data/coffee/manual/brazil_export_diffs.csv)",
                   "kc": "ICE KC 2nd position settlement", "pass_rate": "ICE monthly grading summary (upload)", "storage": "ICE Antwerp warehouse rates (upload)",
                   "parameters": "blend share and all-in shipping 8-10c from Ma's trading experience; other cost items as listed"}}
json.dump(OUTJ, open(OUT, "w"), indent=1, ensure_ascii=False)
print(f"tender parity {now['date']}: SW-FC {now['sw_minus_fc']:+.1f}c ({now['sw_minus_fc_pct5y']:.0f} pct 5y); margin w15/30 "
      f"{stk['w15']['margin']:+.1f}/{stk['w30']['margin']:+.1f}c; exchange {mid['exchange_value']:.1f}; costs {mid['cost_items_total']}")

# ------------------------------------------------------------------ research (--lab PATH): leads, implied certs, price
if "--lab" not in sys.argv:
    sys.exit(0)
LABP = sys.argv[sys.argv.index("--lab") + 1]
mk = lambda s: s.groupby(s.index.to_period("M")).mean()
M = pd.DataFrame({"m30": mk(T.margin_w30), "swfc": mk(T.sw_minus_fc), "mcep": mk(CM), "mgc": mk(GM),
                  "cepb": mk(H.cepea_basis_2nd3rd.dropna())})
M.index = M.index.astype(str)
antm = ANT.groupby(ANT.index.to_period("M")).last(); antm.index = antm.index.astype(str)
totm = TOT.groupby(TOT.index.to_period("M")).last(); totm.index = totm.index.astype(str)
pbm = PEND_BR.groupby(PEND_BR.index.to_period("M")).mean(); pbm.index = pbm.index.astype(str)
cbm = CERT_BR.groupby(CERT_BR.index.to_period("M")).last(); cbm.index = cbm.index.astype(str)
Y = pd.DataFrame({"dant": antm.diff(), "dtot": totm.diff(), "sub_br": GB.sub_bags, "pass_br": GB.pass_bags, "pend_br": pbm, "dcert_br": cbm.diff()})
ALL = M.join(Y, how="outer").sort_index()
for c_ in ("dant", "dtot"):                              # forward sums: certs built over the next 1-4 months
    for h in (2, 3, 4):
        ALL[f"{c_}_f{h}"] = sum(ALL[c_].shift(-j) for j in range(1, h + 1))
LAB = {"built": OUTJ["built"], "n_months": {c: int(ALL[c].notna().sum()) for c in ALL.columns}, "lead": {}, "oos": {}, "slope": {}, "price": {}}
XS_ = {"m30": "tender margin, 30% semi-washed + 70% CEPEA fine/good cup (2018 on)", "swfc": "semi-washed minus fine/good cup (CEPEA)",
       "mcep": "tender margin on CEPEA tipo 6 (2013 on)", "mgc": "tender margin on B3 good cup alone (2013 on)", "cepb": "CEPEA minus KC 2nd/3rd"}
TG = {"dant": "Antwerp certs change", "dtot": "total certs change", "sub_br": "Brazil bags submitted for grading", "pass_br": "Brazil bags passed",
      "pend_br": "Brazil bags pending (avg)", "dcert_br": "Brazil-origin certs change"}
for x in XS_:
    for t in TG:
        cs = []
        for L in range(0, 5):
            z = pd.concat([ALL[x].shift(L), ALL[t]], axis=1).dropna()
            cs.append([rd(z.iloc[:, 0].rank().corr(z.iloc[:, 1].rank()), 2), len(z)] if len(z) >= 12 else None)
        LAB["lead"].setdefault(x, {})[t] = cs


def wf_month(x, t, L, start="2021-01", min_n=24):
    """Walk-forward OLS of target(m) on x(m - L) using only months before m; MAE vs the training mean and vs zero."""
    z = pd.concat([ALL[x].shift(L).rename("x"), ALL[t].rename("y")], axis=1).dropna()
    em, e0, ez, out = [], [], [], []
    for m in z.index:
        if m < start:
            continue
        tr = z[z.index < m]
        # target known only once the month is over: training rows must end before m - L as well
        if len(tr) < min_n:
            continue
        b = np.polyfit(tr.x, tr.y, 1)
        p = np.polyval(b, z.at[m, "x"])
        em.append(abs(z.at[m, "y"] - p)); e0.append(abs(z.at[m, "y"] - tr.y.mean())); ez.append(abs(z.at[m, "y"]))
        out.append((m, z.at[m, "y"], p))
    if not em:
        return None
    return {"n": len(em), "mae": rd(np.mean(em), 0), "mae_mean": rd(np.mean(e0), 0), "mae_zero": rd(np.mean(ez), 0),
            "skill_vs_mean": rd(1 - np.mean(em) / np.mean(e0), 3)}


for x in XS_:
    for t in ("dant", "dtot", "sub_br", "pass_br", "dcert_br"):
        for L in (1, 2, 3, 4):
            st = "2023-06" if t in ("sub_br", "pass_br", "dcert_br") else "2021-01"
            mn = 12 if t in ("sub_br", "pass_br", "dcert_br") else 24
            res = wf_month(x, t, L, start=st, min_n=mn)
            if res:
                LAB["oos"].setdefault(x, {})[f"{t} lag {L}"] = res
    for t in ("dant_f3", "dtot_f3", "dant_f4"):
        res = wf_month(x, t, 0, start="2021-01", min_n=24)
        if res:
            LAB["oos"].setdefault(x, {})[f"{t} (next months, from this month)"] = res
# bags per cent of margin: full-sample slope of the next-3-month Antwerp / total build on this month's margin, by period
for x in ("m30", "swfc", "mcep", "mgc", "cepb"):
    for t in ("dant_f3", "dtot_f3"):
        for pn, (a, b) in {"2018 on": ("2018-01", "2099"), "2018-Nov 2023": ("2018-01", "2023-11"), "Dec 2023 on": ("2023-12", "2099"),
                           "2013 on": ("2013-01", "2099")}.items():
            z = ALL[[x, t]].dropna()
            z = z[(z.index >= a) & (z.index <= b)]
            if len(z) >= 12:
                bb = np.polyfit(z[x], z[t], 1)
                LAB["slope"].setdefault(x, {}).setdefault(t, {})[pn] = {"n": len(z), "bags_per_c": rd(bb[0], 0), "intercept": rd(bb[1], 0),
                                                                       "rho": rd(z[x].rank().corr(z[t].rank()), 2)}
# implied build to the Mar 27 first notice (Feb 2027; about 3 months of month-end changes from the Nov 2026 month-end)
cur = {x: float(ALL[x].dropna().iloc[-1]) for x in ("m30", "swfc", "mcep", "mgc", "cepb")}
LAB["current"] = {x: rd(v, 1) for x, v in cur.items()}
imp = {}
for x in ("m30", "swfc", "mcep", "mgc", "cepb"):
    for t in ("dant_f3", "dtot_f3"):
        s = (LAB["slope"].get(x, {}).get(t, {}).get("2018 on")) or {}
        if s:
            imp[f"{x} -> {t}"] = rd(s["intercept"] + s["bags_per_c"] * cur[x], 0)
LAB["implied_build_3m"] = imp

# ------------------------------------------------------------------ price / structure: 1-3 month direction
KCc = pd.read_csv(need("data/contracts/KC.csv"), parse_dates=["date"])
KCc = pd.concat([pd.read_csv(need("data/contracts/KC_pre2006.csv"), parse_dates=["date"]), KCc]).drop_duplicates(["contract", "date"], keep="last")
piv = KCc.pivot_table(index="date", columns="contract", values="close").sort_index()
me = KC.groupby(KC.index.to_period("M")).tail(1)                      # month-end rows
rows = []
for d, r_ in me.iterrows():
    m = str(d.to_period("M"))
    e = {"m": m}
    for h in (1, 2, 3):
        d2 = d + pd.DateOffset(months=h)
        sec = r_.second                                                 # hold the 2nd contract: no roll in the return
        s2 = piv[sec].loc[(piv.index > d2 - pd.Timedelta(days=6)) & (piv.index <= d2)].dropna() if sec in piv else pd.Series(dtype=float)
        e[f"ret{h}"] = (math.log(s2.iloc[-1] / r_.f2) * 100) if len(s2) and r_.f2 > 0 else np.nan
        fut = KC[(KC.index > d2 - pd.Timedelta(days=6)) & (KC.index <= d2)]
        e[f"dspr{h}"] = (fut.s12.iloc[-1] / fut.f1.iloc[-1] * 100 - r_.s12 / r_.f1 * 100) if len(fut) else np.nan
        # arbs: KC2 minus B3 good cup (c/lb), KC1! x 22.0462 minus RC1! ($/t), change over h months
        def lv(s, dd):
            v = s[(s.index > dd - pd.Timedelta(days=6)) & (s.index <= dd)]
            return float(v.iloc[-1]) if len(v) else np.nan
        e[f"dkcb3_{h}"] = (lv(KC.f2, d2) - lv(ICF, d2)) - (lv(KC.f2, d) - lv(ICF, d))
        e[f"dkcrc_{h}"] = (lv(KC1, d2) * 22.0462 - lv(RC1, d2)) - (lv(KC1, d) * 22.0462 - lv(RC1, d))
    rows.append(e)
PR = pd.DataFrame(rows).set_index("m")
PR = PR[~PR.index.duplicated(keep="last")]
Z = M.join(PR, how="inner")


def wf_dir(x, t, start, min_n=36):
    z = Z[[x, t]].dropna()
    hit, hit_mom, hit_up, e, e0 = [], [], [], [], []
    h = int(t[-1])
    for i, m in enumerate(z.index):
        if m < start:
            continue
        # training rows whose outcome window has closed before m (h months)
        tr = z[z.index < str(pd.Period(m, "M") - h)]
        if len(tr) < min_n:
            continue
        b = np.polyfit(tr[x], tr[t], 1)
        p = np.polyval(b, z.at[m, x])
        a = z.at[m, t]
        if abs(a) < 1e-9:
            continue
        hit.append(np.sign(p) == np.sign(a)); hit_up.append(np.sign(tr[t].mean()) == np.sign(a))
        prev = tr[t].iloc[-1]
        hit_mom.append(np.sign(prev) == np.sign(a))
        e.append(abs(a - p)); e0.append(abs(a - tr[t].mean()))
    if not e:
        return None
    return {"n": len(e), "hit": rd(np.mean(hit) * 100, 0), "hit_train_mean_sign": rd(np.mean(hit_up) * 100, 0), "hit_last_value": rd(np.mean(hit_mom) * 100, 0),
            "mae": rd(np.mean(e), 3), "mae_mean": rd(np.mean(e0), 3), "skill_vs_mean": rd(1 - np.mean(e) / np.mean(e0), 3)}


for x, st in (("cepb", "2005-01"), ("mcep", "2018-01"), ("mgc", "2018-01"), ("m30", "2021-01"), ("swfc", "2021-01")):
    for t in [f"{a}{h}" for a in ("ret", "dspr") for h in (1, 2, 3)] + [f"dkcb3_{h}" for h in (1, 3)] + [f"dkcrc_{h}" for h in (1, 3)]:
        res = wf_dir(x, t, st, min_n=24 if x in ("m30", "swfc") else 36)
        if res:
            LAB["price"].setdefault(x, {})[t] = res
json.dump(LAB, open(LABP, "w"), indent=1, default=str)
print("lab ->", LABP)
