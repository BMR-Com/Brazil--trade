#!/usr/bin/env python3
"""Delivery-period dashboard: for each soft, the contract nearest its first notice (sugar: expiry), with the calendar,
spot-month open interest and how fast it is leaving, the front spread (cotton: against full carry), certified stocks,
cotton on-call against the contract, managed-money position and spreading, option open interest by strike for the next
expiring option series, the index-roll windows, and a short rule-based read of those numbers.

Inputs (all already on the desk): data/contracts/<SYM>.csv, data/specs/calendar.json rules (models/contract_calendar.py),
data/options/roll.json (ICE open interest by contract), data/options/<SYM>.json, data/cotton/carry_history.csv,
data/cotton/ice/*, data/coffee/ice_certs.csv, data/cot/<SYM>_fut.csv, BMR-Com/cotton-on-call.
Writes data/delivery/delivery.json.
"""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from watch_common import (ROOT, D, MK, ORDER, J, rd, fmt, label, last_settled, load_px, rule_dates, contract_month,
                          bd_between, index_roll_windows, cotton_oncall, BD, bdays, write_json)

MON = {"H": "March", "K": "May", "N": "July", "U": "September", "V": "October", "Z": "December"}


def spot_contract(sym, w, asof):
    cs = sorted([c for c in w.columns if not np.isnan(w[c].iloc[-1])], key=contract_month)
    for c in cs:
        if rule_dates(sym, c)["ltd"] >= asof:
            return c, (cs[cs.index(c) + 1] if cs.index(c) + 1 < len(cs) else None)
    return None, None


def calendar(sym, c, asof):
    r = rule_dates(sym, c)
    m = contract_month(c)
    days = bdays(m.start_time, m.end_time.normalize())
    lnd = None
    if sym == "CT":
        lnd = days[-10]                      # ICE cotton: last notice ten business days from the end of the delivery month
    elif sym in ("KC", "CC"):
        lnd = r["ltd"] + BD                  # coffee and cocoa: last trading day is the business day before last notice
    ev = [("First notice", r.get("fnd")), ("Last trading day", r["ltd"]), ("Last notice", lnd)]
    rows = [{"event": k, "date": str(v.date()), "bd": bd_between(asof, v)} for k, v in ev if v is not None]
    ir = index_roll_windows(sym, c)
    return rows, ir, r


def oi_block(sym, c):
    R = (J("data/options/roll.json", {}) or {}).get("markets", {}).get(sym)
    if not R or R.get("contract") != MON[c[len(sym)]][:3].upper() + c[-2:]:
        return None
    P = R.get("path", [])
    last5 = P[-5:]
    pace = -np.mean([p["doi"] for p in last5]) if last5 else None
    return {"asof": R["asof"], "oi": R["oi"], "pct_left": R.get("rem"), "band": R.get("band"), "lots_band": R.get("lots_band"),
            "share_of_all_oi": R.get("share"), "state": R.get("state"), "k": R.get("k"), "K0": R.get("K0"), "T0": R.get("T0"), "T0_kind": R.get("T0_kind"),
            "pace_lots_per_day": rd(pace, 0), "typical_at_notice": (R.get("band_path") or {}).get("at_T0_lots"),
            "path": [{"date": p["date"], "bd_to_notice": p["k"], "oi": p["oi"], "chg": p["doi"], "pct_left": p["rem"], "spread": p["spread"]} for p in P[-8:]],
            "src": "ICE daily open interest by contract (exchange report, previous business day)"}


def spread_block(sym, w, c, n, asof):
    dp = MK[sym][2]
    s = (w[c] - w[n]).dropna()
    s = s[s.index <= asof]
    out = {"pair": f"{label(c)}/{label(n)}", "now": rd(s.iloc[-1], dp), "date": str(s.index[-1].date()),
           "chg_1w": rd(s.iloc[-1] - s.iloc[-6], dp) if len(s) > 5 else None, "front": rd(w[c].dropna().iloc[-1], dp),
           "next": rd(w[n].dropna().iloc[-1], dp), "unit": MK[sym][1], "sign": "front minus next; negative = carry"}
    if sym == "CT":
        p = ROOT / "data" / "cotton" / "carry_history.csv"
        if p.exists():
            h = pd.read_csv(p, parse_dates=["date"])
            h = h[(h.date <= asof) & (h.front == c)]
            if len(h):
                L = h.iloc[-1]
                wk = h[h.date <= L.date - pd.Timedelta(days=7)]
                out["carry"] = {"date": str(L.date.date()), "next_over_front": rd(L.spread, 2), "full_carry": rd(L.full_carry, 2),
                                "pct_of_full_carry": rd(L.pct_of_full_carry, 1), "pct_1w_ago": rd(wk.pct_of_full_carry.iloc[-1], 1) if len(wk) else None,
                                "storage": rd(L.storage, 2), "financing": rd(L.financing, 2),
                                "penalties": rd((L.over_age or 0) + (L.weight_date or 0) + (L.year_of_growth or 0), 2),
                                "cert_premium_pts": rd(L.avg_premium_pts, 0), "basis": L.carry_basis,
                                "shortfall": rd(L.full_carry - L.spread, 2), "src": "data/cotton/carry_history.csv (certs tab)"}
    return out


def certs_block(sym, asof):
    if sym == "KC":
        k = pd.read_csv(D / "coffee" / "ice_certs.csv", parse_dates=["date"])
        k = k[k.date <= asof]
        s = k[k.section == "certified"].groupby("date").bags.sum().sort_index()
        pend = k[k.section == "pending"].groupby("date").bags.sum()
        wk = s[s.index <= s.index[-1] - pd.Timedelta(days=7)]
        return {"now": int(s.iloc[-1]), "date": str(s.index[-1].date()), "unit": "bags", "chg_1w": int(s.iloc[-1] - wk.iloc[-1]) if len(wk) else None,
                "pending": int(pend.iloc[-1]) if len(pend) else None, "src": "ICE daily certified arabica report"}
    if sym == "CT":
        L = J("data/cotton/ice/latest.json", {})
        if not L.get("warehouse"):
            return None
        now = float(pd.read_csv(ROOT / L["warehouse"])["Receipt"].sum())
        prev, pdte = None, None
        for st in sorted((D / "cotton" / "ice").glob("stock_*.csv")):
            t = pd.read_csv(st)
            col = next((x for x in t.columns if x.startswith("Current Stock - ")), None)
            if col:
                pdte = pd.to_datetime(col.split(" - ", 1)[1], format="%d-%b-%Y")
                prev = float(t[col].sum())
        return {"now": int(now), "date": L["warehouse_date"], "unit": "bales", "chg": int(now - prev) if prev is not None else None,
                "chg_vs": str(pdte.date()) if pdte is not None else None, "src": "ICE certificated stock (weekly warehouse report, uploaded)"}
    return None


def oncall_block(c):
    df = cotton_oncall()
    if df is None:
        return None
    last = df["Report Date"].max()
    x = df[df["Report Date"] == last]
    mname = f"{MON[c[2]]} {c[-4:]}"
    r = x[x["Futures Based On"] == mname]
    if r.empty:
        return None
    r = r.iloc[0]
    return {"date": str(last.date()), "contract": mname, "sales": int(r["Unfixed Call Sales"]), "sales_chg": int(r["Chg Sales"]),
            "purchases": int(r["Unfixed Call Purchases"]), "purchases_chg": int(r["Chg Purchases"]),
            "net": int(r["Unfixed Call Sales"] - r["Unfixed Call Purchases"]), "src": "CFTC cotton on-call (weekly, as of Friday)"}


def mm_block(sym):
    p = D / "cot" / f"{sym}_fut.csv"
    if not p.exists():
        return None
    c = pd.read_csv(p, usecols=["report_date_as_yyyy_mm_dd", "m_money_positions_long_all", "m_money_positions_short_all", "m_money_positions_spread",
                                "change_in_m_money_spread", "open_interest_all"])
    c["date"] = pd.to_datetime(c.report_date_as_yyyy_mm_dd.str[:10])
    c = c.sort_values("date")
    L = c.iloc[-1]
    yr = c[c.date > L.date - pd.Timedelta(days=3 * 365)]
    pct = float((yr.m_money_positions_spread <= L.m_money_positions_spread).mean() * 100)
    return {"date": str(L.date.date()), "long": int(L.m_money_positions_long_all), "short": int(L.m_money_positions_short_all),
            "net": int(L.m_money_positions_long_all - L.m_money_positions_short_all), "spreading": int(L.m_money_positions_spread),
            "spreading_chg": int(L.change_in_m_money_spread), "spreading_pct3y": rd(pct, 0),
            "spreading_share_oi": rd(L.m_money_positions_spread / L.open_interest_all * 100, 1), "src": "CFTC disaggregated, futures only"}


def options_block(sym, asof):
    O = J(f"data/options/{sym}.json")
    if not O or not O.get("by_expiry"):
        return None
    exp = [b for b in O["by_expiry"] if b.get("expiry") and pd.Timestamp(b["expiry"]) >= asof]
    gone = [b for b in O["by_expiry"] if b.get("expiry") and pd.Timestamp(b["expiry"]) < asof]
    if not exp:
        return None
    b = exp[0]
    rows = b.get("rows", [])
    calls = sorted(rows, key=lambda r: -r["cOI"])[:5]
    puts = sorted(rows, key=lambda r: -r["pOI"])[:5]
    return {"series": b["exp"], "underlying": b["und"], "expiry": b["expiry"], "bd_to_expiry": bd_between(asof, b["expiry"]), "F": b.get("F"),
            "call_oi": b["cOI"], "put_oi": b["pOI"], "pc_oi": b.get("pc_oi"), "date": O["date"],
            "top_calls": [{"K": r["K"], "oi": r["cOI"], "chg": r["dc"]} for r in calls if r["cOI"]],
            "top_puts": [{"K": r["K"], "oi": r["pOI"], "chg": r["dp"]} for r in puts if r["pOI"]],
            "expired": [f"{g['exp']} options expired {g['expiry']}" for g in gone],
            "src": f"ICE option settlement files, last good session {O['date']}"}


def read(sym, X, asof):
    """Rule-based read of the numbers above; no forecast."""
    out = []
    cal = {r["event"]: r for r in X["calendar"]}
    fn = cal.get("First notice")
    oi, sp, ce = X.get("oi"), X["spread"], X.get("certs")
    lab = label(X["contract"])
    if fn and fn["bd"] < 0 and sym != "SB":
        out.append(f"{lab} is in its delivery period (first notice was {fn['date']}); last trading day {cal['Last trading day']['date']} ({cal['Last trading day']['bd']} business days).")
    if oi and fn and fn["bd"] >= 0:
        left = fn["bd"]
        pace = oi.get("pace_lots_per_day")
        stale = bd_between(oi["asof"], asof)
        txt = (f"{oi['oi']:,} lots still open in {lab} on {oi['asof']} ({oi['pct_left']}% left; past {lab[:3]} rolls at this stage "
               f"{oi['band']['lo']}–{oi['band']['hi']}%) with {left} business days to first notice ({fn['date']}).")
        if pace:
            txt += f" At the last five reports' pace (about {pace:,.0f} lots a day) "
            txt += "the contract would not clear before notice." if pace * (left + stale) < oi["oi"] else "the contract clears before notice."
        if stale > 2:
            txt += f" Open-interest data is {stale} business days old."
        out.append(txt)
    if sym == "CT" and sp.get("carry"):
        C = sp["carry"]
        pays = C["pct_of_full_carry"] is not None and C["pct_of_full_carry"] >= 100
        out.append(f"{sp['pair']} pays {C['next_over_front']:+.2f}¢, {C['pct_of_full_carry']}% of full carry ({C['full_carry']:.2f}¢) on {C['date']}"
                   + (f", up from {C['pct_1w_ago']}% a week earlier" if C.get('pct_1w_ago') and C['pct_1w_ago'] < C['pct_of_full_carry'] else
                      f", down from {C['pct_1w_ago']}% a week earlier" if C.get('pct_1w_ago') else "") + ". "
                   + ("Holding certs into the next month covers its cost." if pays else
                      f"Taking certs and redelivering does not cover storage, financing and penalties ({C['shortfall']:.2f}¢ short)")
                   + (f", and the certs on board carry an average ICE premium of {C['cert_premium_pts']:+.0f} pts that a taker pays." if not pays and C.get("cert_premium_pts") else "."))
        oc = X.get("oncall")
        if oc:
            out.append(f"On-call against {oc['contract']} ({oc['date']}): {oc['sales']:,} lots unfixed sales (mills still to buy futures to fix) "
                       f"and {oc['purchases']:,} lots unfixed purchases (sellers still to fix by selling); net {oc['net']:+,} lots.")
        if oi and fn and fn["bd"] >= 0 and not pays:
            fixing = f" and net on-call fixing is {'buying' if oc and oc['net'] > 0 else 'selling'} ({oc['net']:+,} lots)" if oc else ""
            out.append(f"Read: longs must roll or sell with {fn['bd']} business days left; delivery does not pay (see Certs){fixing} "
                       f"→ liquidation pressure on {lab} against {label(X['next'])} into first notice.")
    elif sym == "KC" and ce:
        inv = sp["now"] is not None and sp["now"] > 0
        out.append(f"{sp['pair']} {sp['now']:+.2f}¢ ({'inverted' if inv else 'carry'}) on {sp['date']}; certified stock {ce['now']:,} bags on {ce['date']}"
                   + (f", {ce['chg_1w']:+,} on the week" if ce.get("chg_1w") is not None else "") + ".")
        if inv and ce.get("chg_1w") is not None and ce["chg_1w"] < 0:
            out.append(f"Read: deliverable stock is falling while the front holds a premium: shorts without certs must buy back or roll, which supports {lab} against {label(X['next'])} into notice.")
        elif inv:
            out.append(f"Read: front premium with certs not falling: the inversion depends on who holds the certs, not on stock size alone.")
    elif sym == "CC":
        out.append(f"{sp['pair']} {sp['now']:+,.0f} $/t on {sp['date']} ({'carry' if sp['now'] < 0 else 'inverted'}). Certified stocks are not on the desk, so delivery economics cannot be read here.")
    elif sym == "SB":
        ltd = cal["Last trading day"]
        out.append(f"{lab} expires {ltd['date']} ({ltd['bd']} business days); No. 11 has no notice period and delivers FOB origin. "
                   f"{sp['pair']} {sp['now']:+.2f}¢ on {sp['date']} ({'front premium' if sp['now'] > 0 else 'carry'}). Index roll out of {lab}: GSCI {X['index_roll']['gsci'][0]} to {X['index_roll']['gsci'][1]}.")
    return out


def main():
    asof = last_settled()
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "asof": str(asof.date()), "markets": []}
    for sym in ["CT", "KC", "CC", "SB"]:
        X = {"sym": sym, "name": MK[sym][0], "errors": []}
        try:
            w = load_px(sym, asof)
            c, n = spot_contract(sym, w, asof)
            X["contract"], X["next"] = c, n
            X["label"] = label(c)
            X["calendar"], X["index_roll"], _ = calendar(sym, c, asof)
            X["spread"] = spread_block(sym, w, c, n, asof)
        except Exception as e:
            X["errors"].append(f"core: {e}")
            out["markets"].append(X)
            continue
        for k, fn in (("oi", lambda: oi_block(sym, c)), ("certs", lambda: certs_block(sym, asof)),
                      ("oncall", lambda: oncall_block(c) if sym == "CT" else None), ("mm", lambda: mm_block(sym)),
                      ("options", lambda: options_block(sym, asof))):
            try:
                X[k] = fn()
            except Exception as e:
                X[k] = None
                X["errors"].append(f"{k}: {str(e)[:100]}")
        X["index_roll_past"] = X["index_roll"]["bcom"][1] < str(asof.date())
        try:
            X["read"] = read(sym, X, asof)
        except Exception as e:
            X["read"] = []
            X["errors"].append(f"read: {str(e)[:100]}")
        out["markets"].append(X)
        print(f"== {X['name']} {X['label']}", X["errors"] or "")
        for t in X["read"]:
            print("  ", t)
    write_json("data/delivery/delivery.json", out)


if __name__ == "__main__":
    main()
