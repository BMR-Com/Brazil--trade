"""Sugar market signals from public data: fund positioning, sugar in reais per tonne, ethanol parity premium and
market depth (fund lots per point of price). Writes data/sugar/signals.json with current readings and weekly history.

Inputs: CFTC disaggregated COT (data/cot/SB_fut.csv), ICE No. 11 front and USD/BRL (sugar/data/prices_cont.csv),
hydrous ethanol parity (sugar/data/sugar.json).
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sugar" / "signals.json"


def pctile(s, n):
    return s.rolling(n, min_periods=int(n * 2 / 3)).apply(lambda x: (x[:-1] < x[-1]).mean() * 100, raw=True)


def main():
    cot = pd.read_csv(ROOT / "data/cot/SB_fut.csv", parse_dates=["report_date_as_yyyy_mm_dd"]).set_index("report_date_as_yyyy_mm_dd").sort_index()
    net = cot.m_money_positions_long_all - cot.m_money_positions_short_all
    mm = net / cot.open_interest_all * 100
    pm = cot.prod_merc_positions_short / cot.open_interest_all * 100
    con = pd.read_csv(ROOT / "sugar/data/prices_cont.csv", parse_dates=["date"])
    sb = con[con.symbol == "ICEUS:SB1!"].set_index("date").close.sort_index()
    fx = con[con.symbol == "FX_IDC:USDBRL"].set_index("date").close.sort_index()
    brl_t = (sb * fx * 22.0462).dropna().resample("W-TUE").last()
    P = json.loads((ROOT / "sugar/data/sugar.json").read_text())["parity"]
    prem = (pd.Series(P["sb"], index=pd.to_datetime(P["dates"])) - pd.Series(P["par"], index=pd.to_datetime(P["dates"]))).resample("W-TUE").last()
    px_w = sb.resample("W-TUE").last().reindex(cot.index, method="ffill")
    dpx = px_w.diff() * 100
    lpp = (net.diff() / dpx).where(dpx.abs() > 10).abs()
    H = pd.DataFrame({"mm_pct_oi": mm, "mm_pctile_3y": pctile(mm, 156), "pm_short_pct_oi": pm}).join(
        pd.DataFrame({"brl_t": brl_t, "brl_t_pctile_5y": pctile(brl_t, 260), "parity_premium": prem}), how="outer")
    H = H[H.index >= "2016-01-01"].round(2)
    last = lambda c: (None if H[c].dropna().empty else float(H[c].dropna().iloc[-1]))
    out = {"generated": date.today().isoformat(), "cot_date": str(cot.index[-1].date()),
           "now": {"mm_net": int(net.iloc[-1]), "mm_pct_oi": last("mm_pct_oi"), "mm_pctile_3y": last("mm_pctile_3y"), "mm_chg_1w": int(net.diff().iloc[-1]),
                   "pm_short_pct_oi": last("pm_short_pct_oi"), "brl_t": last("brl_t"), "brl_t_pctile_5y": last("brl_t_pctile_5y"),
                   "parity_premium": last("parity_premium"), "lots_per_point_median": round(float(lpp[lpp.index >= "2021-01-01"].median()), 0),
                   "lots_per_point_last": None if pd.isna(lpp.iloc[-1]) else round(float(lpp.iloc[-1]), 0)},
           "history": {"dates": [d.strftime("%Y-%m-%d") for d in H.index], **{c: [None if pd.isna(v) else v for v in H[c]] for c in H.columns}}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out))
    print("sugar signals", out["cot_date"], out["now"])


if __name__ == "__main__":
    main()
