"""Input pack for the weekly sugar research note: every number the note uses, with its date and source.

Reads repo data only (sugar workflow, markets, COT desk, flows, data/sugar/world.json) and writes
data/sugar/weekly_inputs.json. Week = Friday to Friday (settlements); later data (e.g. Monday COT) is flagged by its date.
Run after models/sugar_world.py (see .github/workflows/sugar_world.yml).
"""
import json
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sugar" / "weekly_inputs.json"
LB_T = 22.0462


def jl(p):
    try:
        return json.loads((ROOT / p).read_text())
    except Exception:
        return None


def r(x, n=2):
    return None if x is None or pd.isna(x) else round(float(x), n)


def fridays(today=None):
    t = today or date.today()
    f = t - timedelta(days=(t.weekday() - 4) % 7)
    return f, f - timedelta(days=7)


def contracts(fri, prev):
    p = pd.read_csv(ROOT / "sugar/data/prices_contracts.csv")
    out = {}
    for sym in ["SBH2027", "SBK2027", "SBN2027", "SBV2027", "SBH2028", "WZ2026", "WH2027", "WK2027", "WQ2027", "WV2027"]:
        s = p[p.symbol == sym].sort_values("date")
        a = s[s.date <= str(fri)]
        b = s[s.date <= str(prev)]
        if len(a):
            out[sym] = {"settle": r(a.close.iloc[-1]), "date": a.date.iloc[-1], "prev": r(b.close.iloc[-1]) if len(b) else None,
                        "prev_date": b.date.iloc[-1] if len(b) else None, "chg": r(a.close.iloc[-1] - b.close.iloc[-1]) if len(b) else None,
                        "chg_pct": r(100 * (a.close.iloc[-1] / b.close.iloc[-1] - 1), 1) if len(b) else None, "volume": r(a.volume.iloc[-1], 0)}
    sp = {}
    for a, b in (("SBH2027", "SBK2027"), ("SBK2027", "SBN2027"), ("SBN2027", "SBV2027"), ("SBH2027", "SBH2028"), ("WH2027", "WK2027"), ("WZ2026", "WH2027")):
        if a in out and b in out:
            sp[f"{a}/{b}"] = {"now": r(out[a]["settle"] - out[b]["settle"]), "prev": r(out[a]["prev"] - out[b]["prev"]) if out[a]["prev"] and out[b]["prev"] else None}
    for w, s in (("WH2027", "SBH2027"), ("WK2027", "SBK2027"), ("WQ2027", "SBN2027"), ("WV2027", "SBV2027")):
        if w in out and s in out:
            sp[f"white premium {w}-{s}"] = {"now": r(out[w]["settle"] - out[s]["settle"] * LB_T, 1),
                                            "prev": r(out[w]["prev"] - out[s]["prev"] * LB_T, 1) if out[w]["prev"] and out[s]["prev"] else None}
    return out, sp


def macro(fri, prev):
    c = pd.read_csv(ROOT / "data/markets/closes.csv", index_col=0, parse_dates=True)
    out = {}
    for k, lab in (("BRL=X", "USD/BRL"), ("INR=X", "USD/INR"), ("EURUSD=X", "EUR/USD"), ("BZ=F", "Brent front"), ("DX-Y.NYB", "Dollar index"), ("RB=F", "RBOB gasoline")):
        if k not in c:
            continue
        s = c[k].dropna()
        a, b = s[s.index <= pd.Timestamp(fri)], s[s.index <= pd.Timestamp(prev)]
        if len(a) and len(b):
            out[lab] = {"now": r(a.iloc[-1], 4), "date": str(a.index[-1].date()), "prev": r(b.iloc[-1], 4), "chg_pct": r(100 * (a.iloc[-1] / b.iloc[-1] - 1), 1)}
    return out


def parity_at(S, d):
    P = S.get("parity") or {}
    ds = P.get("dates") or []
    idx = [i for i, x in enumerate(ds) if x <= str(d)]
    if not idx:
        return None
    jdx = [k for k, x in enumerate(ds) if x <= str(d - timedelta(days=7))]
    i, j = idx[-1], (jdx[-1] if jdx else idx[0])
    return {"date": ds[i], "parity": P["par"][i], "sb_front": P["sb"][i], "eth": P["eth"][i], "fx": P["fx"][i],
            "sugar_minus_parity": r(P["sb"][i] - P["par"][i]), "week_ago": {"date": ds[j], "parity": P["par"][j], "sb_front": P["sb"][j]}}


def main():
    fri, prev = fridays()
    S = jl("sugar/data/sugar.json") or {}
    W = jl("data/sugar/world.json") or {}
    C = jl("data/cot_desk/SB.json") or {}
    F = jl("data/sugar/flows.json") or {}
    Z = jl("data/sugar/czapp_digest.json") or {}
    px, sp = contracts(fri, prev)
    mm = (C.get("cats") or {}).get("mm") or {}
    inputs = {
        "prices": {"value": px, "date": str(fri), "source": "ICE settlements via TradingView (sugar/data/prices_contracts.csv)"},
        "spreads": {"value": sp, "date": str(fri), "source": "computed from ICE settlements; white premium = No. 5 $/t − No. 11 ¢/lb × 22.0462"},
        "macro": {"value": macro(fri, prev), "date": str(fri), "source": "Yahoo Finance closes (data/markets/closes.csv)"},
        "parity": {"value": parity_at(S, fri), "date": (parity_at(S, fri) or {}).get("date"), "source": "B3 hydrous ethanol futures, USD/BRL, No. 11 front (sugar/data/sugar.json)"},
        "pump": {"value": {k: (S.get("pump") or {}).get(k, [None])[-1] for k in ("hydrous", "gasoline", "ratio")},
                 "date": ((S.get("pump") or {}).get("dates") or [None])[-1], "source": "ANP weekly pump prices, São Paulo"},
        "white_curve": {"value": (S.get("white") or {}).get("curve"), "date": ((S.get("white") or {}).get("curve") or [{}])[0].get("date"), "source": "ICE No. 5 / No. 11"},
        "cot": {"value": {"mm_net": mm.get("N"), "mm_chg": mm.get("dN"), "mm_chg4": mm.get("dN4"), "mm_long": mm.get("L"), "mm_short": mm.get("S"),
                          "pct_3y": (mm.get("pct") or {}).get("y3"), "range_3y": mm.get("range_3y"), "record": mm.get("record"), "oi": C.get("oi"),
                          "pm_net": ((C.get("cats") or {}).get("pm") or {}).get("N")}, "date": C.get("date"), "source": "CFTC disaggregated COT, futures + options (data/cot_desk/SB.json)"},
        "crush_scorecard": {"value": W.get("scorecard"), "date": (W.get("scorecard") or {}).get("end"), "source": "MAPA fortnightly Centre-South"},
        "crush_states": {"value": (S.get("crush") or {}).get("states"), "date": ((S.get("crush") or {}).get("projection") or {}).get("end"), "source": "MAPA by state"},
        "cane_weather": {"value": W.get("cane_weather"), "date": (W.get("cane_weather") or {}).get("asof"), "source": "ERA5 via Open-Meteo; ECMWF ENS / GEFS via Open-Meteo"},
        "season_range": {"value": W.get("range"), "date": (W.get("range") or {}).get("from_fortnight"), "source": "MAPA + ERA5 + ensemble (models/sugar_world.py)"},
        "exports": {"value": {"weekly": F.get("weekly"), "forecast": F.get("forecast"), "pace": (S.get("exports") or {}).get("pace")},
                    "date": (F.get("weekly") or {}).get("asof"), "source": "MDIC/SECEX weekly and monthly (HS 1701)"},
        "india": {"value": W.get("india"), "date": max([x.get("date", "") for x in ((W.get("india") or {}).get("releases") or [])] or [""]), "source": "ISMA, DGFT, DFPD, oil companies via cited news; parity from ICE and Yahoo FX"},
        "europe": {"value": W.get("europe"), "date": ((W.get("europe") or {}).get("ec") or [{}])[0].get("release_date"), "source": "European Commission; ERA5-Land via Open-Meteo"},
        "deliveries": {"value": W.get("deliveries"), "date": max([x.get("source_date", "") for x in W.get("deliveries") or []] or [""]), "source": "news reports of ICE expiry tenders (data/sugar/manual/deliveries.csv)"},
        "revisions": {"value": W.get("revisions"), "date": max([x.get("release_date", "") for x in W.get("revisions") or []] or [""]), "source": "ISO, EC, Conab, USDA (data/sugar/manual/agency_revisions.csv)"},
        "fuel_policy": {"value": {"items": W.get("fuel_policy"), "sensitivity": W.get("fuel_sensitivity")}, "date": max([x.get("date", "") for x in W.get("fuel_policy") or []] or [""]), "source": "Brazil federal government (cited news)"},
        "psd": {"value": {k: {kk: v[kk][-2:] for kk in ("years", "prod", "cons", "exp", "end") if kk in v} for k, v in (S.get("psd") or {}).items()}, "date": "USDA PSD (latest in repo)", "source": "USDA FAS PSD"},
        "industry_reading": {"value": {"week_ending": Z.get("week_ending"), "n_themes": len(Z.get("themes") or [])}, "date": Z.get("week_ending"), "source": "Czapp free insights digest (themes summarised in our own words on the Outlook tab)"},
    }
    status = [{"input": k, "date": v.get("date"), "source": v.get("source")} for k, v in inputs.items()]
    OUT.write_text(json.dumps({"built": str(date.today()), "week_ending": str(fri), "prev_friday": str(prev), "status": status, "inputs": inputs},
                              ensure_ascii=False, separators=(",", ":"), default=str))
    print("wrote", OUT, OUT.stat().st_size)
    for s in status:
        print(f"  {s['input']:<16} {s['date']}")


if __name__ == "__main__":
    main()
