#!/usr/bin/env python3
"""Sugar: Brazil export vs hydrous ethanol parity, one read for the Ethanol parity tab, the alerts and the overview.

Ethanol price: CEPEA/ESALQ hydrous ethanol (sugar/data/cepea_hydrous.csv, R$/m³) when that file has a price no older
than 5 business days, else the B3 hydrous ethanol futures front month (sugar/data/prices_cont.csv, ETH1!, R$/m³).
FX: USD/BRL from the same file. Sugar: No. 11 front settlement from data/contracts/SB.csv.
Conversion (public CONSECANA constants, the same as the parity chart in sugar/scripts/build.py):
  parity ¢/lb = (ethanol R$/m³ × 1.0495 / 1.6913 + FOB logistics R$/t) / USDBRL / 22.0462 / (1 + 4.05% polarisation premium)
Writes data/sugar/parity_read.json.
"""
from datetime import datetime, timezone

import pandas as pd

from watch_common import ROOT, J, rd, label, last_settled, load_px, front_series, bd_between, write_json

S = J("sugar/data/sugar.json", {}) or {}
K = S.get("constants") or {"atr": {"sugar": 1.0495, "hyd": 1.6913}, "pol": 0.0405, "logistics_brl": 190.0, "lb_t": 22.0462}


def parity(eth, fx):
    return (eth * K["atr"]["sugar"] / K["atr"]["hyd"] + K["logistics_brl"]) / fx / K["lb_t"] / (1 + K["pol"])


def last_change(s):
    """Date the series last moved (a carried-forward price is not a new price)."""
    s = s.dropna()
    ch = s[s.diff().fillna(1) != 0]
    return ch.index[-1] if len(ch) else s.index[-1]


def main():
    asof = last_settled()
    p = pd.read_csv(ROOT / "sugar" / "data" / "prices_cont.csv", parse_dates=["date"])
    w = p.pivot_table(index="date", columns="symbol", values="close").sort_index()
    w.columns = [c.split(":")[1] for c in w.columns]
    eth_src, eth = None, None
    cp = ROOT / "sugar" / "data" / "cepea_hydrous.csv"
    if cp.exists():
        c = pd.read_csv(cp, parse_dates=["date"]).dropna(subset=["brl_m3"]).sort_values("date")
        if len(c) and bd_between(c.date.iloc[-1], asof) <= 5:
            eth, eth_date, eth_src = float(c.brl_m3.iloc[-1]), c.date.iloc[-1], "CEPEA/ESALQ hydrous ethanol indicator, R$/m³"
    if eth is None:
        e = w["ETH1!"][w["ETH1!"] > 0].dropna()
        eth_date = last_change(e)
        eth, eth_src = float(e.loc[eth_date]), "B3 hydrous ethanol futures, front month, R$/m³ (cash-settled on the CEPEA/ESALQ Paulínia index)"
    fxs = w["USDBRL"].dropna()
    fx_date = fxs.index[-1]
    fx = float(fxs.iloc[-1])
    sb = load_px("SB", asof)
    fs = front_series("SB", sb)
    L = fs.iloc[-1]
    par = parity(eth, fx)
    # mix: latest UNICA month and the MAPA-implied fortnight
    U = S.get("unica") or {}
    mix = {}
    try:
        mix["unica"] = {"month": U["month"], "mix_sugar": U["monthly"]["mix_sugar"][-1], "mix_sugar_ly": U["monthly"]["mix_sugar"][0],
                        "season": U["seasons"][-1], "src": "UNICA Centre-South, monthly"}
        im = U["implied_mix"][-1]
        mix["fortnight"] = {"end": im["end"], "mix_sugar": im["mix"], "src": "implied from MAPA fortnightly sugar and ethanol" + (", corn ethanol estimated" if im.get("corn_est") else "")}
    except Exception:
        pass
    # sensitivity: R$/m³ of ethanol that would equal today's No. 11 (the ethanol price at which mills are indifferent)
    eth_be = (L.px * K["lb_t"] * (1 + K["pol"]) * fx - K["logistics_brl"]) * K["atr"]["hyd"] / K["atr"]["sugar"]
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
           "now": {"date": str(L.name.date()), "contract": L.front, "contract_label": label(L.front), "sb": rd(L.px, 2),
                   "eth": rd(eth, 1), "eth_date": str(eth_date.date()), "eth_src": eth_src, "fx": rd(fx, 4), "fx_date": str(fx_date.date()),
                   "parity": rd(par, 2), "gap": rd(L.px - par, 2), "sugar_pays": bool(L.px > par),
                   "sb_level_ethanol_equal": rd(par, 2), "eth_level_sugar_equal": rd(eth_be, 0),
                   "eth_age_bd": bd_between(eth_date, asof)},
           "mix": mix,
           "constants": {"atr_kg_per_kg_sugar": K["atr"]["sugar"], "atr_kg_per_litre_hydrous": K["atr"]["hyd"], "pol_premium": K["pol"],
                         "fob_logistics_brl_t": K["logistics_brl"], "lb_per_tonne_over_100": K["lb_t"]},
           "cepea_file": cp.exists()}
    write_json("data/sugar/parity_read.json", out)
    n = out["now"]
    print(f"No.11 {n['contract_label']} {n['sb']} ¢/lb ({n['date']}) vs parity {n['parity']} ({n['eth_src'][:30]} R${n['eth']} on {n['eth_date']}, "
          f"USDBRL {n['fx']} {n['fx_date']}); gap {n['gap']:+} ¢/lb; ethanol would need R${n['eth_level_sugar_equal']}/m³ to match sugar; mix {mix}")


if __name__ == "__main__":
    main()
