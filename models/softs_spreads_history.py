"""Daily calendar-spread history for coffee (KC) and cocoa (CC) from the stored per-contract closes.

Inputs : data/contracts/KC.csv, CC.csv (2006 contracts on) and, if present, KC_pre2006.csv / CC_pre2006.csv
         (1996-2005 contracts, filled by pipelines/contracts.py in the softs-contracts workflow).
Outputs: data/coffee/kc_spreads_history.csv, data/cocoa/cc_spreads_history.csv
         columns: date, front, second, third, f1, f2, f3, s12, s23, pair12, pair23, bd_to_fnd
         s12 = front minus second (KC c/lb, CC $/t); negative = carry, positive = inversion.
         "front" rolls on the first notice day: KC 7 business days, CC 10 business days before the first business day
         of the delivery month. pair12 names the spread (e.g. 'Z/H').
Any missing main input raises.
"""
import os
import sys

import pandas as pd
from pandas.tseries.holiday import (AbstractHolidayCalendar, GoodFriday, Holiday, USLaborDay, USMartinLutherKingJr,
                                    USMemorialDay, USPresidentsDay, USThanksgivingDay, nearest_workday)
from pandas.tseries.offsets import CustomBusinessDay


class ICEUSCal(AbstractHolidayCalendar):          # ICE Futures U.S. softs holidays (approximation of the exchange calendar)
    rules = [Holiday("NewYear", month=1, day=1, observance=nearest_workday), USMartinLutherKingJr, USPresidentsDay, GoodFriday,
             USMemorialDay, Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
             Holiday("July4", month=7, day=4, observance=nearest_workday), USLaborDay, USThanksgivingDay,
             Holiday("Christmas", month=12, day=25, observance=nearest_workday)]


BD = CustomBusinessDay(calendar=ICEUSCal())
HOL = set(ICEUSCal().holidays("1990-01-01", "2035-12-31"))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MC = {"H": 3, "K": 5, "N": 7, "U": 9, "Z": 12}
CFG = {"KC": (7, os.path.join(ROOT, "data", "coffee", "kc_spreads_history.csv")),
       "CC": (10, os.path.join(ROOT, "data", "cocoa", "cc_spreads_history.csv"))}


def fnd(code, nbd):
    y, m = int(code[-4:]), MC[code[-5]]
    first = pd.Timestamp(y, m, 1)
    while first.weekday() >= 5 or first in HOL:
        first += pd.Timedelta(days=1)
    return first - nbd * BD


def build(sym):
    nbd, out = CFG[sym]
    p = os.path.join(ROOT, "data", "contracts", f"{sym}.csv")
    if not os.path.exists(p):
        raise SystemExit(f"missing input: {p}")
    parts = [pd.read_csv(p)]
    old = os.path.join(ROOT, "data", "contracts", f"{sym}_pre2006.csv")
    if os.path.exists(old):
        parts.insert(0, pd.read_csv(old))
    d = pd.concat(parts).drop_duplicates(["contract", "date"], keep="last")
    d = d[d.contract.str[-5].isin(list(MC))]
    d["date"] = pd.to_datetime(d.date)
    px = d.pivot_table(index="date", columns="contract", values="close").sort_index()
    cons = sorted(px.columns, key=lambda c: (int(c[-4:]), MC[c[-5]]))
    F = {c: fnd(c, nbd) for c in cons}
    rows = []
    for dt, r in px.iterrows():
        live = [c for c in cons if F[c] > dt and pd.notna(r.get(c))]
        if len(live) < 2:
            continue
        f1, f2 = live[0], live[1]
        f3 = live[2] if len(live) > 2 else None
        # require the front to be the true nearest contract (no gap from a missing series)
        rows.append({"date": dt.strftime("%Y-%m-%d"), "front": f1, "second": f2, "third": f3 or "",
                     "f1": r[f1], "f2": r[f2], "f3": r[f3] if f3 else None,
                     "s12": round(r[f1] - r[f2], 4), "s23": round(r[f2] - r[f3], 4) if f3 else None,
                     "pair12": f"{f1[-5]}/{f2[-5]}", "pair23": f"{f2[-5]}/{f3[-5]}" if f3 else "",
                     "bd_to_fnd": int(len(pd.date_range(dt, F[f1], freq=BD)) - 1)})
    S = pd.DataFrame(rows)
    if len(S) < 1000:
        raise SystemExit(f"{sym}: only {len(S)} spread rows")
    S.to_csv(out, index=False)
    print(f"{sym}: {len(S)} days {S.date.iloc[0]} to {S.date.iloc[-1]} -> {os.path.relpath(out, ROOT)}")
    return S


def gaps(S):
    """Calendar gaps over 10 days in the daily spread series (for the report)."""
    t = pd.to_datetime(S.date)
    g = t.diff().dt.days
    return [(t.iloc[i - 1].date().isoformat(), t.iloc[i].date().isoformat()) for i in g[g > 10].index]


if __name__ == "__main__":
    for s in (sys.argv[1:] or CFG):
        S = build(s)
        print("  gaps > 10 days:", gaps(S)[:10])
