"""Data freshness for the softs desk: data/status.json, one row per source with its latest data date, expected cadence and
a late flag. Reads only files in this repo (plus the on-call CSV from BMR-Com/cotton-on-call when reachable).

Ages are counted in business days for daily sources and calendar days for the rest. A source is "late" when its age is
over the limit for its cadence (daily > 2 business days, weekly > 9 days, fortnightly > 20, monthly > 40 days; some
weekly reports carry an older reference date, e.g. COT positions are Tuesday's, so their limit is set per source).
"""
import csv, io, json, re
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
TODAY = datetime.now(ZoneInfo("America/Chicago")).date()


def J(p):
    return json.loads((ROOT / p).read_text())


def d10(v):
    m = re.search(r"\d{4}-\d{2}-\d{2}", str(v or ""))
    return m.group(0) if m else None


def max_csv_date(p, col="date"):
    with open(ROOT / p) as f:
        return max((r[col] for r in csv.DictReader(f) if r.get(col)), default=None)


def tech_last(sym):
    T = J(f"data/technicals/{sym}.json")
    s = next((x for x in T["series"] if x["ticker"] == T.get("default")), T["series"][0])
    return s["bars"][-1][0]


def oncall():
    import requests
    t = requests.get("https://raw.githubusercontent.com/BMR-Com/cotton-on-call/main/data/cotton_oncall.csv", timeout=30).text
    ds = re.findall(r"(\d{2})/(\d{2})/(\d{4})", t[-20000:])
    return max(f"{y}-{m}-{d}" for m, d, y in ds) if ds else None


def wasde_release():
    idx = J("data/grains/derived/wasde_brief/index.json")
    rep = idx["reports"][0]["report"]                       # e.g. 2026-11
    try:
        b = J(f"data/grains/derived/wasde_brief/{rep}.json")
        r = d10(b.get("release") or b.get("date") or (b.get("cotton") or {}).get("release"))
        if r:
            return r
    except Exception:
        pass
    return rep + "-10"                                       # WASDE comes out around the 8th-12th; month is what matters


# (group, name, cadence, limit, unit, manual, getter, note)
B, C = "bd", "d"
SOURCES = [
    ("Prices", "Futures closes, all softs (Yahoo)", "daily", 2, B, False, lambda: tech_last("CT"), "technicals, overview, certs tab prices"),
    ("Prices", "Per-contract settlements (TradingView)", "daily", 2, B, False, lambda: max_csv_date("data/contracts/CT.csv"), "spreads, seasonality, carry history"),
    ("Prices", "ICE options settlements (uploaded ICE files)", "daily", 2, B, True, lambda: J("data/options/CT.json")["date"], "options pricer, vol, trade ideas"),
    ("Positions", "CFTC COT, positions date", "weekly (Tue, out Fri)", 10, C, False, lambda: J("data/cot_desk/CT.json")["date"], "COT sections, overview"),
    ("Positions", "CFTC cotton on-call (as of Fri, out next Thu)", "weekly", 13, C, False, oncall, "on-call tab, WASDE brief"),
    ("Cotton", "ICE quality grid (AMS daily spot quotes)", "daily", 2, B, False, lambda: J("data/cotton/ice_diffs.json")["date"], "certs tab"),
    ("Cotton", "ICE certs: stock by warehouse (upload)", "weekly (Mon)", 9, C, True, lambda: J("data/cotton/ice/latest.json").get("warehouse_date"), "certs tab"),
    ("Cotton", "ICE certs: grade / staple (upload)", "weekly (Mon)", 9, C, True, lambda: J("data/cotton/ice/latest.json").get("grade_date"), "certs tab premiums"),
    ("Cotton", "ICE certs: year of growth (upload)", "weekly (Mon)", 9, C, True, lambda: J("data/cotton/ice/latest.json").get("year_of_growth_date"), "certs tab"),
    ("Cotton", "ICE certs: strength (upload)", "weekly (Mon)", 9, C, True, lambda: J("data/cotton/ice/latest.json").get("strength_date"), "certs tab"),
    ("Cotton", "ICE certs: stock by delivery point (upload)", "daily", 2, B, True, lambda: J("data/cotton/ice/latest.json").get("stock_date"), "certs tab"),
    ("Cotton", "EWR receipts (upload)", "weekly", 9, C, True, lambda: J("data/cotton/ewr/latest.json").get("asof"), "certs tab"),
    ("Cotton", "CFR Far East quotes (upload)", "weekly", 9, C, True, lambda: J("data/cotton/cfr_compare.json").get("asof"), "certs tab export comparison"),
    ("Cotton", "Spread vs full carry history", "daily", 2, B, False, lambda: max_csv_date("data/cotton/carry_history.csv"), "certs tab"),
    ("Cotton", "AMS weekly cotton market review", "weekly (Fri)", 9, C, False, lambda: J("data/cotton_review/latest.json")["date"], "AMS review tab"),
    ("Cotton", "AMS daily classing", "daily", 3, B, False, lambda: J("data/cotton_review/classing_daily.json").get("as_of"), "AMS review tab"),
    ("Cotton", "US export sales (week ending)", "weekly (Thu)", 15, C, False, lambda: next(c["week"] for c in J("data/grains/derived/esr_brief.json")["commodities"] if c.get("key") == "cotton"), "export sales tab"),
    ("Cotton", "WASDE (latest report)", "monthly", 40, C, False, wasde_release, "WASDE tab, balance sheets"),
    ("Cotton", "WASDE brief, latest-data section", "daily", 2, B, False, lambda: d10(J("data/grains/derived/wasde_brief/index.json")["generated"]), "WASDE tab"),
    ("Cotton", "Cotton loan (FSA)", "weekly", 9, C, False, lambda: J("data/cotton_loan/loan.json")["state"]["as_of"], "loan tab"),
    ("Cotton", "China", "daily", 2, B, False, lambda: d10(J("data/china/cotton.json")["generated"]), "China tab"),
    ("Cotton", "India", "daily", 2, B, False, lambda: d10(J("data/india/india.json")["built"]), "India tab"),
    ("Cotton", "Australia (synced from US desk)", "daily", 2, B, False, lambda: d10(J("data/australia/australia.json")["built"]), "Australia tab"),
    ("Coffee", "Coffee desk (ICE certs, basis, origins)", "daily", 2, B, False, lambda: d10(J("coffee/data/coffee.json")["built"]), "coffee tabs"),
    ("Coffee", "Cecafé daily registrations", "daily", 2, B, False, lambda: J("data/coffee/cecafe.json")["asof"], "Cecafé tab"),
    ("Coffee", "Brazil coffee weather (weighted)", "daily", 2, B, False, lambda: d10(J("data/coffee/weather_weighted.json")["generated"]), "weather tab"),
    ("Sugar", "Sugar desk", "daily", 2, B, False, lambda: d10(J("sugar/data/sugar.json")["built"]), "sugar tabs"),
    ("Sugar", "Centre-South crush (MAPA fortnightly)", "fortnightly", 25, C, False, lambda: J("sugar/data/sugar.json")["unica"]["implied_mix"][-1]["end"], "crush tab"),
    ("Sugar", "Brazil sugar export line-up (weekly)", "weekly", 9, C, False, lambda: J("data/sugar/flows.json")["weekly"]["asof"], "exports tab"),
    ("Cocoa", "ICCO balance", "monthly", 40, C, False, lambda: J("data/cocoa/icco.json")["updated"], "cocoa balance tab"),
    ("Macro", "Markets snapshot", "hourly in trading hours", 1, B, False, lambda: d10(J("data/markets/markets.json")["generated"]), "markets tab"),
    ("Macro", "US economic data (BLS, BEA, Fed)", "daily", 2, B, False, lambda: d10(J("data/macro/us_econ.json")["generated"]), "markets tab"),
    ("Macro", "Events calendar", "daily", 2, B, False, lambda: d10(J("data/calendar/calendar.json")["generated"]), "calendars on each tab"),
    ("Macro", "Contract calendar (notice and roll dates)", "daily", 2, B, False, lambda: J("data/specs/calendar.json")["generated"], "primers, certs delivery pair"),
    ("Macro", "News", "every few hours", 1, B, False, lambda: d10(J("data/news/news.json")["generated"]), "news sections"),
]


def age(d, unit):
    if not d:
        return None
    x = date.fromisoformat(d)
    return max(0, int(np.busday_count(x, TODAY)) if unit == B else (TODAY - x).days)   # UTC-stamped files can be a day ahead of Chicago


def main():
    out = []
    for grp, name, cad, lim, unit, manual, get, used in SOURCES:
        try:
            d = d10(get())
        except Exception as e:
            d = None; print("status:", name, "unreadable:", repr(e)[:100])
        a = age(d, unit)
        state = "missing" if d is None else "late" if a > lim else "ok"
        out.append({"group": grp, "source": name, "latest": d, "cadence": cad, "age": a, "age_unit": "business days" if unit == B else "days",
                    "limit": lim, "state": state, "manual": manual, "used_in": used})
        print(f"{state:7s} {str(d):10s} age {a} ({lim}) {name}")
    J_ = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "today": TODAY.isoformat(), "sources": out,
          "late": sum(r["state"] != "ok" for r in out)}
    (D / "status.json").write_text(json.dumps(J_, indent=1))


if __name__ == "__main__":
    main()
