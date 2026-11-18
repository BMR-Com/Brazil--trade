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


_CP = {}
def crop_projection(key=None):
    """BMR-Com/cotton-crop-progress docs/data/crop_projection.json (shown on the Crop tab)."""
    if not _CP:
        import requests
        _CP.update(requests.get("https://raw.githubusercontent.com/BMR-Com/cotton-crop-progress/main/docs/data/crop_projection.json", timeout=30).json())
    return _CP.get("asof") if key is None else (_CP.get("inputs_through") or {}).get(key)


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
    ("Cotton", "ICE certs: four months and older (upload)", "weekly (Mon)", 9, C, True, lambda: J("data/cotton/ice/latest.json").get("four_months_older_date"), "stored for the certs tab over-age allowance"),
    ("Cotton", "EWR receipts (upload)", "weekly", 9, C, True, lambda: J("data/cotton/ewr/latest.json").get("asof"), "certs tab"),
    ("Cotton", "CFR Far East quotes (upload)", "weekly", 9, C, True, lambda: J("data/cotton/cfr_compare.json").get("asof"), "certs tab export comparison"),
    ("Cotton", "Spread vs full carry history", "daily", 2, B, False, lambda: max_csv_date("data/cotton/carry_history.csv"), "certs tab"),
    ("Cotton", "AMS weekly cotton market review", "weekly (Fri)", 9, C, False, lambda: J("data/cotton_review/latest.json")["date"], "AMS review tab"),
    ("Cotton", "AMS daily classing", "daily", 3, B, False, lambda: J("data/cotton_review/classing_daily.json").get("as_of"), "AMS review tab"),
    ("Cotton", "US export sales (week ending)", "weekly (Thu)", 15, C, False, lambda: next(c["week"] for c in J("data/grains/derived/esr_brief.json")["commodities"] if c.get("key") == "cotton"), "export sales tab"),
    ("Cotton", "Crop projection (cotton-crop-progress)", "weekly, after crop progress / ginnings / drought", 9, C, False, crop_projection, "Crop tab"),
    ("Cotton", "Crop projection input: NASS ginnings", "about twice a month", 20, C, False, lambda: crop_projection("ginnings"), "Crop tab"),
    ("Cotton", "Crop projection input: crop progress", "weekly (Mon)", 9, C, False, lambda: crop_projection("crop_progress"), "Crop tab"),
    ("Cotton", "WASDE (latest report)", "monthly", 40, C, False, wasde_release, "WASDE tab, balance sheets"),
    ("Cotton", "WASDE brief, latest-data section", "daily", 2, B, False, lambda: d10(J("data/grains/derived/wasde_brief/index.json")["generated"]), "WASDE tab"),
    ("Cotton", "Cotton loan (FSA)", "weekly", 9, C, False, lambda: J("data/cotton_loan/loan.json")["state"]["as_of"], "loan tab"),
    ("Cotton", "China", "daily", 2, B, False, lambda: d10(J("data/china/cotton.json")["generated"]), "China tab"),
    ("Cotton", "India", "daily", 2, B, False, lambda: d10(J("data/india/india.json")["built"]), "India tab"),
    ("Cotton", "Australia (synced from US desk)", "daily", 2, B, False, lambda: d10(J("data/australia/australia.json")["built"]), "Australia tab"),
    ("Coffee", "Coffee desk (ICE certs, basis, origins)", "daily", 2, B, False, lambda: d10(J("coffee/data/coffee.json")["built"]), "coffee tabs"),
    ("Coffee", "ICE certs detail: pending, transition, passed/failed, rebagging (upload)", "daily", 2, B, True, lambda: max_csv_date("data/coffee/ice_certs_daily_detail.csv"), "Certs profile tab"),
    ("Coffee", "ICE certs aging by port (upload)", "monthly", 40, C, True, lambda: max_csv_date("data/coffee/ice_aging_history.csv"), "Certs profile tab"),
    ("Coffee", "ICE end-of-month certs by port since 1996 (upload)", "monthly", 40, C, True, lambda: max_csv_date("data/coffee/ice_certs_eom_by_port.csv"), "Certs profile tab"),
    ("Coffee", "ICE grading summary by origin (upload)", "monthly", 40, C, True, lambda: max_csv_date("data/coffee/ice_grading_monthly.csv", "period_end"), "Certs profile tab"),
    ("Coffee", "Certs profile and delivery economics (built from the ICE files)", "daily", 2, B, False, lambda: d10(J("data/coffee/certs_profile.json")["current"]["daily_date"]), "Certs profile tab"),
    ("Coffee", "ICO group prices for the certs physical comparison", "monthly", 40, C, False, lambda: J("data/coffee/certs_profile.json")["physical"]["ico_month"] + "-28", "Certs profile tab"),
    ("Coffee", "Cecafé daily registrations", "daily", 2, B, False, lambda: J("data/coffee/cecafe.json")["asof"], "Cecafé tab"),
    ("Coffee", "Brazil coffee weather (weighted)", "daily", 2, B, False, lambda: d10(J("data/coffee/weather_weighted.json")["generated"]), "weather tab"),
    ("Sugar", "Sugar desk", "daily", 2, B, False, lambda: d10(J("sugar/data/sugar.json")["built"]), "sugar tabs"),
    ("Sugar", "Centre-South crush (MAPA fortnightly)", "fortnightly", 25, C, False, lambda: J("sugar/data/sugar.json")["unica"]["implied_mix"][-1]["end"], "crush tab"),
    ("Sugar", "Cane-belt weather, stoppage days, season range (ERA5)", "daily", 3, B, False, lambda: J("data/sugar/world.json")["cane_weather"]["asof"], "sugar Brazil cane weather tab"),
    ("Sugar", "Cane-belt ensemble forecast (ECMWF ENS, GEFS)", "daily", 2, B, False, lambda: d10(J("data/sugar/wx/ens_latest.json")["generated"]), "sugar Brazil cane weather tab"),
    ("Sugar", "India releases: ISMA, DGFT, quotas, prices (manual)", "fortnightly", 20, C, True, lambda: max(r["date"] for r in J("data/sugar/world.json")["india"]["releases"]), "sugar India tab"),
    ("Sugar", "EC balance sheet and EU price (manual)", "monthly", 45, C, True, lambda: J("data/sugar/world.json")["europe"]["ec"][0]["release_date"], "sugar Europe tab"),
    ("Sugar", "ICE expiry deliveries (manual, from news)", "per expiry", 75, C, True, lambda: max(r["source_date"] for r in J("data/sugar/world.json")["deliveries"] if r["source_date"]), "sugar deliveries tab"),
    ("Sugar", "Agency revisions: ISO, EC, Conab, USDA (manual)", "monthly", 45, C, True, lambda: max(r["release_date"] for r in J("data/sugar/world.json")["revisions"]), "sugar revisions table"),
    ("Sugar", "Brazil fuel-policy log (manual)", "as announced", 35, C, True, lambda: max(r["date"] for r in J("data/sugar/world.json")["fuel_policy"]), "sugar Brazil cane weather tab"),
    ("Sugar", "India ex-mill prices (ChiniMandi daily update)", "daily", 4, B, False, lambda: J("data/sugar/india_prices_status.json")["latest"], "sugar India detail tab, import parity"),
    ("Sugar", "UNICA Centre-South report (last published)", "irregular", 120, C, False, lambda: J("data/sugar/unica_check.json")["latest_position"] or J("sugar/data/sugar.json")["unica"]["position"], "crush tab ATR; MAPA is the main series"),
    ("Sugar", "Weekly report input pack", "daily", 3, B, False, lambda: J("data/sugar/weekly_inputs.json")["built"], "weekly sugar research"),
    ("Sugar", "Brazil sugar export line-up (weekly)", "weekly", 9, C, False, lambda: J("data/sugar/flows.json")["weekly"]["asof"], "exports tab"),
    ("Cocoa", "ICE cocoa certs and grading (upload)", "daily", 2, B, True, lambda: max_csv_date("data/cocoa/ice_certs_daily.csv"), "Certs profile tab"),
    ("Cocoa", "ICE cocoa grading results with discounts (upload)", "monthly", 40, C, True, lambda: max_csv_date("data/cocoa/ice_grading_monthly.csv", "period_end"), "Certs profile tab"),
    ("Cocoa", "Certs profile and delivery value (built from the ICE files)", "daily", 2, B, False, lambda: J("data/cocoa/certs_profile.json")["current"]["date"], "Certs profile tab"),
    ("Cocoa", "CC calendar-spread history (per-contract closes)", "daily", 3, B, False, lambda: max_csv_date("data/cocoa/cc_spreads_history.csv"), "Certs profile tab"),
    ("Coffee", "KC spread model: fair front spread from certified stocks", "daily", 3, B, False, lambda: J("data/coffee/spread_model.json")["asof"], "Certified stocks & structure tab"),
    ("Coffee", "KC calendar-spread history (per-contract closes)", "daily", 3, B, False, lambda: max_csv_date("data/coffee/kc_spreads_history.csv"), "Certs profile tab"),
    ("Cocoa", "ICCO balance", "monthly", 40, C, False, lambda: J("data/cocoa/icco.json")["updated"], "cocoa balance tab"),
    ("Desk watch", "What changed strip (settlement date)", "daily", 2, B, False, lambda: J("data/overview/what_changed.json")["asof"], "overview what-changed strip"),
    ("Desk watch", "Delivery-period dashboard (settlement date)", "daily", 2, B, False, lambda: J("data/delivery/delivery.json")["asof"], "delivery tab"),
    ("Desk watch", "Alerts check", "daily", 2, B, False, lambda: J("data/alerts/state.json")["generated"], "overview alerts card, email"),
    ("Desk watch", "Desk call log / track record", "daily", 2, B, False, lambda: J("data/scorecard/scorecard.json")["asof"], "overview track record"),
    ("Sugar", "Ethanol price used for parity (CEPEA, else B3 futures)", "daily", 3, B, False, lambda: J("data/sugar/parity_read.json")["now"]["eth_date"], "ethanol parity tab"),
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


INBOX_ORDER = ["CT_options", "CT_futures", "KC_options", "KC_futures", "SB_options", "SB_futures", "CC_options", "CC_futures",
               "ct_stock", "ct_grade", "ct_warehouse", "ct_yog", "ct_strength", "ct_four_months", "kc_certs", "kc_aging", "kc_eom",
               "kc_grading", "cc_certs", "cc_grading", "kc_warehouses", "kc_rates"]


def inbox():
    """ICE drop box (pipelines/ice_inbox.py): last file received per type and the files it could not recognise."""
    try:
        L = J("data/ice_inbox/log.json")
    except Exception:
        return None
    last = [dict(type=k, **v) for k, v in L.get("last", {}).items()]
    last.sort(key=lambda r: INBOX_ORDER.index(r["type"]) if r["type"] in INBOX_ORDER else 99)
    return {"updated": L.get("updated"), "last": last, "unrecognised": L.get("unrecognised", [])}


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
    ib = inbox()
    if ib is not None:
        n = len(ib["unrecognised"])
        lr = max((r["received"] for r in ib["last"]), default=None)
        out.append({"group": "ICE drop box", "source": f"Files not recognised (inbox/unrecognised): {n}", "latest": d10(lr), "cadence": "on upload",
                    "age": None, "age_unit": "days", "limit": 0, "state": "check" if n else "ok", "manual": True,
                    "used_in": "last file received per type is listed below the table"})
        print(f"inbox: {n} unrecognised file(s)")
    J_ = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "today": TODAY.isoformat(), "sources": out,
          "late": sum(r["state"] != "ok" for r in out), "inbox": ib}
    (D / "status.json").write_text(json.dumps(J_, indent=1))


if __name__ == "__main__":
    main()
