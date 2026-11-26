"""Build the page data for the consumer-side tabs: data/consumers/{coffee,cocoa,cotton,producers}.json.

Inputs: data/consumers/auto/* (consumers_fetch.py), data/consumers/manual/* (hand-kept extracts of public filings and
association releases, refreshed after each results season / release), coffee/data/ico_certified_stocks.csv,
data/cocoa/ice_certs_daily.csv.
Stale rule: a monthly series whose last point is more than 75 days older than its expected release is left off the page;
quarterly series (grinds, company filings) carry their period-end dates.
"""
import csv, json, math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "consumers"
M, A = D / "manual", D / "auto"
TODAY = date.today()


def rcsv(p):
    p = Path(p)
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []


def num(x):
    try:
        v = float(str(x).replace(",", ""))
        return None if math.isnan(v) else v
    except Exception:
        return None


def pct_rank(cur, hist):
    """share of historical values below the current one (0-100); None with fewer than 3 comparisons"""
    h = [x for x in hist if x is not None]
    if cur is None or len(h) < 3:
        return None
    return round(100 * (sum(1 for x in h if x < cur) + 0.5 * sum(1 for x in h if x == cur)) / len(h))


def monthly_block(key, name, unit, months, vals, src, release_lag_days=60, note=""):
    """seasonal block: months 'YYYY-MM' -> values. Percentile vs the same month in earlier years and vs all history."""
    pts = sorted((m, v) for m, v in zip(months, vals) if v is not None)
    if not pts:
        return None
    months, vals = [p[0] for p in pts], [p[1] for p in pts]
    by = {m: v for m, v in pts}
    lm, lv = months[-1], vals[-1]
    y, mm = int(lm[:4]), int(lm[5:])
    prev = by.get(f"{y - 1}-{mm:02d}")
    same = [by[f"{yy}-{mm:02d}"] for yy in range(y - 30, y) if f"{yy}-{mm:02d}" in by]
    last5 = [by[f"{yy}-{mm:02d}"] for yy in range(y - 5, y) if f"{yy}-{mm:02d}" in by]
    exp = date(y, mm, 28) + timedelta(days=release_lag_days)
    stale = (TODAY - exp).days > 75
    return {"key": key, "name": name, "unit": unit, "source": src, "note": note, "months": months, "vals": vals,
            "latest": {"month": lm, "val": lv, "yoy_pct": round(100 * (lv / prev - 1), 1) if prev else None,
                       "vs5y_pct": round(100 * (lv / (sum(last5) / len(last5)) - 1), 1) if last5 else None,
                       "pct_season": pct_rank(lv, same), "n_season": len(same), "pct_all": pct_rank(lv, vals[:-1]), "n_all": len(vals) - 1},
            "stale": stale}


# ------------------------------------------------------------ company quarterly series
def sec_companies(group):
    inv = defaultdict(dict)
    for r in rcsv(A / "sec_inventory.csv"):
        if r["group"] == group:
            inv[r["ticker"]][r["end"]] = num(r["inventory"])
    sal = defaultdict(dict)
    names = {}
    for r in rcsv(A / "sec_sales.csv"):
        if r["group"] == group:
            sal[r["ticker"]][r["end"]] = num(r["sales"])
            names[r["ticker"]] = r["name"]
    for r in rcsv(A / "sec_inventory.csv"):
        names.setdefault(r["ticker"], r["name"])
    out = []
    for tk in sorted(set(inv) | set(sal)):
        out.append(company_series(tk, names.get(tk, tk), "USD", inv.get(tk, {}), sal.get(tk, {}), "SEC EDGAR XBRL (10-Q/10-K)"))
    return [c for c in out if c]


def near(dct, d0, tol=20):
    t = date.fromisoformat(d0)
    best = None
    for k in dct:
        dd = abs((date.fromisoformat(k) - t).days)
        if dd <= tol and (best is None or dd < best[0]):
            best = (dd, k)
    return dct[best[1]] if best else None


def company_series(tk, name, ccy, inv, sal, src, sales_is_quarterly=True):
    ends = sorted(set(inv) & set(sal)) if sal else sorted(inv)
    if not ends:
        return None
    rows = []
    for e in ends:
        i, s = inv.get(e), sal.get(e)
        ly = (date.fromisoformat(e) - timedelta(days=364)).isoformat()
        i0, s0 = near(inv, ly), near(sal, ly) if sal else None
        rows.append({"end": e, "inventory": i, "sales": s,
                     "inv_yoy": round(100 * (i / i0 - 1), 1) if i and i0 else None,
                     "sales_yoy": round(100 * (s / s0 - 1), 1) if s and s0 else None,
                     "ratio": round(i / s, 3) if i and s else None})
    for r in rows:
        r["gap"] = round(r["inv_yoy"] - r["sales_yoy"], 1) if r["inv_yoy"] is not None and r["sales_yoy"] is not None else None
        # ratio percentile against the same fiscal quarter in earlier years (anniversaries within 25 days)
        t = date.fromisoformat(r["end"])
        same = [x["ratio"] for x in rows if x["end"] < r["end"] and x["ratio"] is not None
                and min(abs((date(t.year - k, t.month, min(t.day, 28)) - date.fromisoformat(x["end"])).days) for k in range(1, 30)) <= 25]
        r["ratio_pct"] = pct_rank(r["ratio"], same)
        r["n_hist"] = len(same)
    rows = [r for r in rows if r["end"] >= "2014-01-01"]
    last = rows[-1]
    stale = (TODAY - date.fromisoformat(last["end"])).days > 200
    return {"ticker": tk, "name": name, "currency": ccy, "source": src, "rows": rows[-40:], "latest": last, "stale": stale}


def yahoo_companies(group, manual_nonus):
    vals = defaultdict(lambda: defaultdict(dict))
    meta = {}
    for r in rcsv(A / "yahoo_fundamentals.csv"):
        if r["group"] != group:
            continue
        vals[r["symbol"]][r["type"]][r["end"]] = num(r["value"])
        meta[r["symbol"]] = (r["name"], r["currency"])
    out = {}
    for sym, t in vals.items():
        inv = t.get("quarterlyInventory") or {}
        sal = t.get("quarterlyTotalRevenue") or {}
        src = "Yahoo Finance fundamentals (company quarterly reports)"
        if len(set(inv) & set(sal)) < 2:   # half-yearly reporters: use annual + any half-year points
            inv = {**(t.get("annualInventory") or {}), **inv}
            sal = {}
            src = "Yahoo Finance fundamentals (company reports; inventory only)"
        c = company_series(sym, meta[sym][0], meta[sym][1], inv, sal, src)
        if c:
            out[sym] = c
    # hand-kept extracts fill companies Yahoo did not return (same column meanings, % from the company's own release)
    by = defaultdict(list)
    for r in manual_nonus:
        by[(r["ticker"], r["company"])].append(r)
    for (tk, nm), rs in by.items():
        if tk in out:
            continue
        rs.sort(key=lambda r: r["period_end"] or "")
        rows = [{"end": r["period_end"], "label": r["period_label"], "inventory": num(r["inventory"]), "sales": num(r["sales"]),
                 "inv_yoy": num(r["inventory_yoy_pct"]), "sales_yoy": num(r["sales_yoy_pct"]), "ratio": None, "ratio_pct": None, "n_hist": 0}
                for r in rs if r["period_end"]]
        for r in rows:
            r["gap"] = round(r["inv_yoy"] - r["sales_yoy"], 1) if r["inv_yoy"] is not None and r["sales_yoy"] is not None else None
        if rows:
            out[tk] = {"ticker": tk, "name": nm, "currency": rs[-1]["currency"], "source": "company results releases (hand-kept)",
                       "rows": rows, "latest": rows[-1], "stale": (TODAY - date.fromisoformat(rows[-1]["end"])).days > 200}
    return list(out.values())


# ------------------------------------------------------------ coffee
def coffee():
    stocks = []
    # Japan: hand-kept history + automated current-year PDF (auto wins for overlapping months)
    jp = {r["month"]: r for r in rcsv(M / "jca_history.csv")}
    for r in rcsv(A / "jca_auto.csv"):
        jp[r["month"]] = r
    ms = sorted(jp)
    b = monthly_block("jca", "Japan green coffee stocks (JCA, month-end)", "t", ms, [num(jp[m]["total_t"]) for m in ms],
                      "All Japan Coffee Association monthly inventory survey", 35,
                      "Monthly detail from 2024; December year-ends from 1996 (JCA supply/demand table).")
    if b:
        ye = sorted((m, num(jp[m]["total_t"])) for m in ms if m.endswith("-12"))
        b["year_end"] = {"years": [m[:4] for m, _ in ye], "vals": [v for _, v in ye]}
        org = ["brazil_t", "colombia_t", "indonesia_t", "vietnam_t", "central_america_t", "others_t"]
        om = [m for m in ms if num(jp[m].get("brazil_t")) is not None]
        b["origins"] = {"months": om, "series": {o.replace("_t", ""): [num(jp[m][o]) for m in om] for o in org}}
        stocks.append(b)
    # ICE arabica certified, month-end: the desk's own ICE daily report from Jun 2024, the ICO monthly report before that.
    # One ICO row (report 2026-09, stock month 2025-10: 1.01m NY / 0.47m London) disagrees with ICE's own figure
    # (0.43m) and both neighbours, so it is skipped.
    ico = {}
    for r in rcsv(ROOT / "coffee/data/ico_certified_stocks.csv"):
        k = r["stock_month"]
        if (r["report_period"], k) == ("2026-09", "2025-10"):
            continue
        if k not in ico or r["report_period"] > ico[k]["report_period"]:
            ico[k] = r
    ice = defaultdict(float)
    for r in rcsv(ROOT / "data/coffee/ice_certs.csv"):
        if r["section"] == "certified":
            ice[r["date"]] += num(r["bags"]) or 0
    ice_me = {}
    for d in sorted(ice):
        ice_me[d[:7]] = ice[d] / 1e6
    ny = {m: num(r["new_york_bags_millions"]) for m, r in ico.items()}
    ny.update(ice_me)
    ms = sorted(ny)
    b = monthly_block("ice_ny", "ICE arabica certified stocks (month-end)", "m bags", ms, [ny[m] for m in ms],
                      "ICE daily certified stock report (from Jun 2024); ICO monthly report before", 5,
                      f"Latest point is the last ICE report of the month so far ({max(ice) if ice else ''}).")
    if b:
        stocks.append(b)
    ms = sorted(ico)
    b = monthly_block("ice_ldn", "ICE robusta certified stocks (London)", "m bags", ms, [num(ico[m]["london_bags_millions"]) for m in ms],
                      "ICO monthly coffee market report (exchange stocks)", 40)
    if b:
        stocks.append(b)
    # Europe ports (ECF): yearly PDFs, published two months at a time
    ecf = [r for r in rcsv(A / "ecf_auto.csv") if num(r["total_t"])]
    if ecf:
        ms = [r["month"] for r in ecf]
        b = monthly_block("ecf", "Europe port stocks (ECF, all coffee)", "t", ms, [num(r["total_t"]) for r in ecf],
                          "European Coffee Federation", 75, "Published two months at a time, about seven weeks after the second month. Includes ICE-certified coffee in European ports.")
        if b:
            b["types"] = {"months": ms, "series": {k: [num(r[k + "_t"]) for r in ecf] for k in ("robusta", "natural", "washed")}}
            stocks.append(b)
        b = monthly_block("ecf_arabica", "Europe port stocks: arabica (ECF natural + washed)", "t", ms,
                          [(num(r["natural_t"]) or 0) + (num(r["washed_t"]) or 0) if num(r["natural_t"]) else None for r in ecf],
                          "European Coffee Federation", 75)
        if b:
            stocks.append(b)
    return {"built": TODAY.isoformat(), "stocks": stocks, "companies": sec_companies("coffee") + yahoo_companies("coffee", []),
            "hedging": json.loads((M / "roasters.json").read_text())["companies"]}


# ------------------------------------------------------------ cocoa
def cocoa():
    g = rcsv(M / "cocoa_grinds.csv")
    regions = []
    for reg in ("Europe", "North America", "Asia"):
        rs = sorted((r for r in g if r["region"] == reg and num(r["tonnes"])), key=lambda r: r["quarter"])
        if not rs:
            continue
        q = [r["quarter"] for r in rs]
        t = [num(r["tonnes"]) for r in rs]
        by = dict(zip(q, t))
        lq = q[-1]
        y, n = int(lq[:4]), int(lq[-1])
        same = [by[f"{yy}-Q{n}"] for yy in range(y - 15, y) if f"{yy}-Q{n}" in by]
        last5 = [by[f"{yy}-Q{n}"] for yy in range(y - 5, y) if f"{yy}-Q{n}" in by]
        qi = lambda s_: int(s_[:4]) * 4 + int(s_[-1]) - 1
        byi = {qi(a): v for a, v in by.items()}
        roll = [sum(byi[qi(a) - k] for k in range(4)) if all(qi(a) - k in byi for k in range(4)) else None for a in q]
        rl = [x for x in roll if x is not None]
        regions.append({"region": reg, "quarters": q, "tonnes": t, "yoy": [num(r["yoy_pct"]) for r in rs], "roll4": roll,
                        "release": rs[-1]["release_date"],
                        "latest": {"quarter": lq, "tonnes": t[-1], "yoy_pct": num(rs[-1]["yoy_pct"]),
                                   "vs5y_pct": round(100 * (t[-1] / (sum(last5) / len(last5)) - 1), 1) if last5 else None,
                                   "pct_season": pct_rank(t[-1], same), "n_season": len(same),
                                   "roll4": roll[-1], "roll4_pct": pct_rank(roll[-1], rl[:-1]) if roll[-1] else None}})
    # ICE cocoa certified (daily, from the desk's ICE drop box)
    certs = defaultdict(float)
    for r in rcsv(ROOT / "data/cocoa/ice_certs_daily.csv"):
        if r["section"] == "certified":
            certs[r["date"]] += num(r["bags"]) or 0
    cd = sorted(certs)
    return {"built": TODAY.isoformat(), "grinds": regions, "next_release": "2027-01-21 (ECA, tentative)",
            "certs": {"dates": cd, "bags": [certs[d] for d in cd]},
            "companies": sec_companies("cocoa") + yahoo_companies("cocoa", []),
            "makers": json.loads((M / "chocolate_makers.json").read_text())["companies"]}


# ------------------------------------------------------------ cotton
def cotton():
    cen = rcsv(A / "census_mrts.csv")
    series = {}
    for r in cen:
        series.setdefault((r["category"], r["type"], r["sa"]), []).append((r["month"], num(r["value"])))
    pick = None
    for cat in ("4481", "448", "4581", "458"):
        if (cat, "SM", "yes") in series and (cat, "IM", "yes") in series:
            pick = cat
            break
    census = None
    if pick:
        sm = dict(series[(pick, "SM", "yes")])
        im = dict(series[(pick, "IM", "yes")])
        ms = sorted(set(sm) & set(im))
        ratio = [round(im[m] / sm[m], 3) if sm[m] else None for m in ms]
        census = {"category": pick, "label": {"4481": "Clothing stores", "448": "Clothing & accessories stores",
                                             "4581": "Clothing retailers", "458": "Clothing, accessories, shoe & jewelry retailers"}[pick],
                  "sales": monthly_block("sm", "Sales (SA, $m)", "$m", ms, [sm[m] for m in ms], "US Census MRTS", 45),
                  "inventory": monthly_block("im", "Inventories (SA, $m)", "$m", ms, [im[m] for m in ms], "US Census MRTS", 45),
                  "ratio": monthly_block("ir", "Inventory / sales (SA)", "x", ms, ratio, "US Census MRTS", 45)}
        for k in ("sales", "inventory"):   # year-on-year % for the chart
            b = census[k]
            by = dict(zip(b["months"], b["vals"]))
            b["yoy"] = [round(100 * (by[m] / by[f"{int(m[:4]) - 1}{m[4:]}"] - 1), 1) if f"{int(m[:4]) - 1}{m[4:]}" in by else None for m in b["months"]]
    nonus = rcsv(M / "apparel_nonus.csv")
    return {"built": TODAY.isoformat(), "census": census, "companies": sec_companies("cotton") + yahoo_companies("cotton", nonus),
            "commentary": json.loads((M / "apparel_commentary.json").read_text())["companies"]}


def producers():
    rows = rcsv(M / "brazil_hedges.csv")
    keep = ["company", "ticker", "release", "release_date", "crop", "season", "hedged_pct", "hedged_price", "price_unit", "basis_of_pct",
            "fx_hedged_pct", "fx_rate", "source_url"]
    out = []
    for r in rows:
        o = {k: r.get(k) for k in keep}
        for k in ("hedged_pct", "hedged_price", "fx_hedged_pct", "fx_rate"):
            o[k] = num(o[k])
        o["secondary"] = "SECONDARY" in (r.get("note") or "").upper()
        if "volume_t" in r:
            o["volume_t"] = num(r["volume_t"])
        out.append(o)
    return {"built": TODAY.isoformat(), "rows": out}


def main():
    for name, fn in (("coffee", coffee), ("cocoa", cocoa), ("cotton", cotton), ("producers", producers)):
        try:
            d = fn()
            (D / f"{name}.json").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
            print(name, "ok")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(name, "FAILED", e)


if __name__ == "__main__":
    main()
