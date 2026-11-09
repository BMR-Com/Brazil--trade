"""ICE Cotton No. 2 quality premiums and discounts (tenderable differences), from USDA AMS Daily Spot Cotton Quotations
(MARS report 3804, sections "Tenderable Differences - CLS" and "- Str"). These are the averages of the designated spot
markets that ICE applies to delivered bales (the same table as AMS MP_CN051), in points (100 = 1 c/lb) against base
41-4-34. Needs AMS_API_KEY. Stores data/cotton/ice_diffs.csv and writes data/cotton/ice_diffs.json for the desk.
"""
import json
import os
import time
from datetime import date, timedelta

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "cotton")
CSV = os.path.join(OUT, "ice_diffs.csv")
KEY = (os.getenv("AMS_API_KEY") or "").strip()
B = "https://marsapi.ams.usda.gov/services/v1.2/reports/3804"
START = date(2023, 1, 1)
KEYCELLS = [("41", "4", "34"), ("41", "3", "35"), ("31", "3", "35"), ("31", "3", "36"), ("21", "2", "36"), ("11", "2", "37"), ("41", "5", "34"), ("51", "4", "34")]


def section(name, a, b):
    q = f"report_begin_date={a:%m/%d/%Y}:{b:%m/%d/%Y}"
    for i in range(3):
        try:
            r = requests.get(f"{B}/{name}", params={"q": q}, auth=(KEY, ""), timeout=(30, 300))
            if r.status_code == 200:
                j = r.json()
                return j.get("results", j) if isinstance(j, dict) else j
        except Exception as e:
            print("mars", name, a, e)
        time.sleep(5)
    return []


def fetch(a, b):
    rows = []
    for x in section("Tenderable Differences - CLS", a, b):
        rows.append({"date": pd.to_datetime(x.get("report_Begin_Date") or x.get("report_begin_date")).date(), "kind": "cls",
                     "color": str(x.get("color")), "leaf": str(x.get("leaf")), "staple": str(x.get("staple")), "points": int(float(x.get("difference")))})
    for x in section("Tenderable Differences - Str", a, b):
        rows.append({"date": pd.to_datetime(x.get("report_Begin_Date") or x.get("report_begin_date")).date(), "kind": "str",
                     "color": "", "leaf": "", "staple": str(x.get("strength")), "points": int(float(x.get("difference")))})
    return rows


BASIS = os.path.join(OUT, "spot_basis.csv")
MKT = ["East Texas - South Texas", "West Texas - Kansas - Oklahoma", "North Delta", "South Delta", "Southeast", "Desert Southwest", "San Joaquin Valley", "US Average"]


def basis_rows(a, b):
    out = []
    for x in section("Basis and Bales", a, b):
        if x.get("commodity") != "Upland":
            continue
        d = pd.to_datetime(x.get("report_Begin_Date") or x.get("report_begin_date")).date()
        g = lambda k: x.get(k) if x.get(k) not in (None, "N/A", "") else None
        out.append({"date": str(d), "market": x.get("spotMarket"), "basis_month": g("basis_Month"), "basis_41_4_34": g("basis_41_4_34"),
                    "base_41_4_34": g("41_4_34_Base_Price"), "basis_31_3_36": g("basis_31_3_36"), "base_31_3_36": g("31_3_36_Base_Price"), "bales": g("bales_Reported")})
    return out


def market_grids(day):
    """Commercial grade/leaf/staple differences by spot market on one day (points vs 41-4-34; micronaire etc. ignored)."""
    g = {}
    for x in section("Daily Spot Quotations Differences", day, day):
        if x.get("commod") != "Upland" or x.get("mike") not in (None, "N/A") or x.get("strength") not in (None, "N/A"):
            continue
        m, c, l, st = x.get("market"), str(x.get("color")), str(x.get("leaf")), str(x.get("staple"))
        if m and c not in ("N/A", "None") and l not in ("N/A", "None") and st not in ("N/A", "None"):
            try:
                # the base cell (41-4-34) carries the base price in this field, not a difference
                g.setdefault(m, {})[f"{c}|{l}|{st}"] = 0 if (c, l, st) == ("41", "4", "34") else int(float(x.get("difference")))
            except (TypeError, ValueError):
                pass
    return g


def main():
    if not KEY:
        print("cotton diffs: no AMS_API_KEY"); return
    os.makedirs(OUT, exist_ok=True)
    old = pd.read_csv(CSV, dtype=str) if os.path.exists(CSV) else pd.DataFrame(columns=["date", "kind", "color", "leaf", "staple", "points"])
    last = pd.to_datetime(old.date).max().date() if len(old) else START - timedelta(days=1)
    rows, a, today = [], last + timedelta(days=1), date.today()
    while a <= today:
        b = min(a + timedelta(days=30), today)
        got = fetch(a, b); rows += got
        print("cotton diffs", a, b, len(got))
        a = b + timedelta(days=1)
    # spot basis history (same chunks)
    ob = pd.read_csv(BASIS, dtype=str) if os.path.exists(BASIS) else pd.DataFrame()
    lastb = pd.to_datetime(ob.date).max().date() if len(ob) else START - timedelta(days=1)
    br, a = [], lastb + timedelta(days=1)
    while a <= today:
        b = min(a + timedelta(days=30), today); br += basis_rows(a, b); a = b + timedelta(days=1)
    if br:
        nb = pd.concat([ob, pd.DataFrame(br).astype(str)]).drop_duplicates(["date", "market"], keep="last").sort_values(["date", "market"])
        nb.to_csv(BASIS, index=False); print("spot basis rows", len(br))
    if rows:
        new = pd.DataFrame(rows).astype({"date": str})
        allr = pd.concat([old.astype(str), new.astype(str)]).drop_duplicates(["date", "kind", "color", "leaf", "staple"], keep="last")
        allr.sort_values(["date", "kind", "color", "leaf", "staple"]).to_csv(CSV, index=False)
    d = pd.read_csv(CSV, dtype=str); d["points"] = d.points.astype(int)
    if d.empty:
        return
    cls, st = d[d.kind == "cls"], d[d.kind == "str"]
    lastd = cls.date.max()
    L = cls[cls.date == lastd]
    grid = {f"{r.color}|{r.leaf}|{r.staple}": int(r.points) for r in L.itertuples()}

    def cell(c, l, s):
        return [r for r in L.itertuples() if r.color == c and r.staple == s and (r.leaf == l or (l in ("1", "2") and r.leaf == "1 & 2"))]
    hist = {}
    for c, l, s in KEYCELLS:
        lk = "1 & 2" if l in ("1", "2") else l
        h = cls[(cls.color == c) & (cls.leaf == lk) & (cls.staple == s)].sort_values("date")
        hist[f"{c}-{l}-{s}"] = {"dates": h.date.tolist(), "points": h.points.tolist()}

    def ago(days):
        ds = sorted(cls.date.unique()); t = str(pd.to_datetime(lastd).date() - timedelta(days=days))
        prev = [x for x in ds if x <= t]
        return prev[-1] if prev else None
    chg = {}
    for lab, days in (("1w", 7), ("1m", 30), ("1y", 365)):
        p = ago(days)
        if p:
            P = cls[cls.date == p]
            chg[lab] = {"date": p, "grid": {f"{r.color}|{r.leaf}|{r.staple}": int(r.points) for r in P.itertuples()}}
    stl = st[st.date == st.date.max()]
    out = {"date": lastd, "grid": grid, "colors": sorted(L.color.unique(), key=lambda x: (x[1], x[0])), "leaves": sorted(L.leaf.unique()),
           "staples": sorted(L.staple.unique()), "strength": [{"range": r.staple, "points": int(r.points)} for r in stl.itertuples()],
           "history": hist, "prev": chg, "source": "USDA AMS Daily Spot Cotton Quotations, tenderable differences (ICE Cotton No. 2)"}
    try:
        mg = market_grids(pd.to_datetime(lastd).date())
        out["markets"] = {"date": lastd, "grids": mg}
    except Exception as e:
        print("market grids failed", e)
    if os.path.exists(BASIS):
        bb = pd.read_csv(BASIS, dtype=str); bl = bb[bb.date == bb.date.max()]
        out["basis"] = {"date": bb.date.max(), "markets": {r.market: {"basis_month": r.basis_month, "basis_41_4_34": float(r.basis_41_4_34) if r.basis_41_4_34 not in ("nan", "None") else None,
                        "basis_31_3_36": float(r.basis_31_3_36) if r.basis_31_3_36 not in ("nan", "None") else None, "base_41_4_34": float(r.base_41_4_34) if r.base_41_4_34 not in ("nan", "None") else None}
                        for r in bl.itertuples()}}
    json.dump(out, open(os.path.join(OUT, "ice_diffs.json"), "w"), separators=(",", ":"))
    print("cotton diffs: latest", lastd, len(grid), "cells; history days", cls.date.nunique())


if __name__ == "__main__":
    main()
