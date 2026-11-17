#!/usr/bin/env python3
"""Track record of the desk's own directional calls.

Each run logs the standing reads that carry a direction and a horizon, with the price or spread at the time, and
scores every call whose horizon has passed against later settlements (data/contracts/<SYM>.csv):
  - Overview read per market (bullish / bearish shades; neutral is not a call): outright, 20 business days, measured on
    the first contract whose notice/expiry falls after the horizon (so the call is not cut by a roll)
  - Cotton price outlook: base-case May contract at May option expiry vs the May price when logged
  - Delivery-period read "delivery does not pay -> liquidation pressure": front minus next spread weaker by first notice
  - Front-month roll idea (data/options/roll.json) when it leans bull or bear spread: spread by the notice day
  - Past morning-brief cotton views (data/brief/calls.csv, Oct 2026), 5 business days, weekend repeats dropped
A call is logged again only when no call from the same source and market is open in the same direction.
Writes data/scorecard/calls.csv and data/scorecard/scorecard.json.
"""
import csv
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from watch_common import ROOT, D, MK, ORDER, J, rd, label, last_settled, load_px, roll_day, contract_month, BD, bd_between, write_json

CALLS = D / "scorecard" / "calls.csv"
COLS = ["id", "logged", "source", "market", "kind", "leg1", "leg2", "direction", "entry", "horizon", "text", "status", "exit_date", "exit", "move"]
KEY = {"cotton": "CT", "sugar": "SB", "coffee": "KC", "cocoa": "CC"}
MON = {"DEC": "Z", "MAR": "H", "MAY": "K", "JUL": "N", "SEP": "U", "OCT": "V"}


def load():
    if CALLS.exists():
        return pd.read_csv(CALLS, dtype=str).fillna("")
    return pd.DataFrame(columns=COLS)


def px_on(sym, c, d, W):
    w = W[sym]
    if c not in w.columns:
        return None
    s = w[c].dropna()
    s = s[s.index <= pd.Timestamp(d)]
    return (float(s.iloc[-1]), s.index[-1]) if len(s) else None


def value(r, d, W):
    sym = r["leg1"][:2]
    a = px_on(sym, r["leg1"], d, W)
    if not a:
        return None
    if r["kind"] == "spread":
        b = px_on(sym, r["leg2"], d, W)
        if not b:
            return None
        return a[0] - b[0], max(a[1], b[1])
    return a


def contract_after(sym, d, W):
    cs = sorted(W[sym].columns, key=contract_month)
    for c in cs:
        if roll_day(sym, c) > pd.Timestamp(d) and not np.isnan(W[sym][c].iloc[-1]):
            return c
    return None


def candidates(asof, W):
    out = []
    O = J("data/overview/overview.json", {})
    for m in O.get("markets", []):
        sym = m.get("sym")
        v = (m.get("view") or "")
        if sym not in MK or not ("bull" in v or "bear" in v):
            continue
        hz = asof + 20 * BD
        c = contract_after(sym, hz, W)
        e = px_on(sym, c, asof, W) if c else None
        if e:
            out.append({"source": "Overview read", "market": sym, "kind": "outright", "leg1": c, "leg2": "", "direction": "up" if "bull" in v else "down",
                        "entry": e[0], "horizon": hz, "text": f"Overview {v} ({O.get('generated', '')[:10]}); measured on {label(c)}"})
    P = J("data/derived/ct_price_outlook.json")
    try:
        k = next(c for c in W["CT"].columns if c.startswith("CTK") and roll_day("CT", c) > asof)
        e = px_on("CT", k, asof, W)
        base = P["scenarios"]["base"]["may"]
        if e and P.get("expiry"):
            out.append({"source": "Cotton price outlook", "market": "CT", "kind": "outright", "leg1": k, "leg2": "", "direction": "up" if base > e[0] else "down",
                        "entry": e[0], "horizon": pd.Timestamp(P["expiry"]), "text": f"Base case {label(k)} {base:.1f}¢ at May option expiry ({P['asof']})"})
    except Exception:
        pass
    X = J("data/delivery/delivery.json", {})
    for m in X.get("markets", []):
        if any("liquidation pressure" in t for t in m.get("read", [])):
            fn = next((r for r in m["calendar"] if r["event"] == "First notice"), None)
            e = value({"kind": "spread", "leg1": m["contract"], "leg2": m["next"]}, asof, W)
            if fn and e and fn["bd"] > 0:
                out.append({"source": "Delivery read", "market": m["sym"], "kind": "spread", "leg1": m["contract"], "leg2": m["next"], "direction": "down",
                            "entry": e[0], "horizon": pd.Timestamp(fn["date"]), "text": f"Delivery does not pay: {label(m['contract'])}/{label(m['next'])} under pressure into first notice"})
    R = (J("data/options/roll.json", {}) or {}).get("markets", {})
    for sym, r in R.items():
        lean = (r.get("idea") or {}).get("lean", "")
        if lean not in ("bear spread", "bull spread") or sym not in MK:
            continue
        c1 = f"{sym}{MON[r['contract'][:3]]}20{r['contract'][3:]}"
        c2 = f"{sym}{MON[r['next'][:3]]}20{r['next'][3:]}"
        e = value({"kind": "spread", "leg1": c1, "leg2": c2}, asof, W)
        if e and pd.Timestamp(r["T0"]) > asof:
            out.append({"source": "Roll idea", "market": sym, "kind": "spread", "leg1": c1, "leg2": c2, "direction": "down" if lean == "bear spread" else "up",
                        "entry": e[0], "horizon": pd.Timestamp(r["T0"]), "text": r["idea"]["text"][:160]})
    return out


def brief_import(df, W):
    p = D / "brief" / "calls.csv"
    if not p.exists() or (df.source == "Morning brief (Oct 2026)").any():
        return df
    b = pd.read_csv(p)
    b = b[b.sym.isin(list(MK)) & b.view.str.contains("bull|bear", na=False)]
    b["date"] = pd.to_datetime(b.date)
    b = b[b.date.dt.dayofweek < 5].drop_duplicates(["code", "last"])
    rows = []
    for _, r in b.iterrows():
        rows.append({"id": f"brief-{r.date.date()}-{r.sym}", "logged": str(r.date.date()), "source": "Morning brief (Oct 2026)", "market": r.sym,
                     "kind": "outright", "leg1": r.code, "leg2": "", "direction": "up" if "bull" in r.view else "down", "entry": str(r["last"]),
                     "horizon": str((r.date + 5 * BD).date()), "text": f"Brief view {r.view} ({r.conviction}); price in the brief", "status": "open",
                     "exit_date": "", "exit": "", "move": ""})
    return pd.concat([df, pd.DataFrame(rows, columns=COLS)], ignore_index=True)


def main():
    asof = last_settled()
    W = {s: load_px(s, asof) for s in ORDER}
    df = brief_import(load(), W)
    n0 = len(df)
    for c in candidates(asof, W):
        same = df[(df.source == c["source"]) & (df.market == c["market"]) & (df.status == "open")]
        if (same.direction == c["direction"]).any():
            continue
        df.loc[len(df)] = {"id": f"{asof.date()}-{c['source'][:8].replace(' ', '')}-{c['market']}", "logged": str(asof.date()), "source": c["source"], "market": c["market"],
                           "kind": c["kind"], "leg1": c["leg1"], "leg2": c["leg2"], "direction": c["direction"], "entry": f"{c['entry']:.4g}",
                           "horizon": str(c["horizon"].date()), "text": c["text"], "status": "open", "exit_date": "", "exit": "", "move": ""}
    # score
    for i, r in df.iterrows():
        if r.status != "open" or pd.Timestamp(r.horizon) > asof:
            continue
        v = value(r, r.horizon, W)
        if not v:
            continue
        mv = v[0] - float(r.entry)
        hit = (mv > 0) if r.direction == "up" else (mv < 0)
        df.loc[i, ["status", "exit_date", "exit", "move"]] = ["hit" if hit else "miss", str(v[1].date()), f"{v[0]:.4g}", f"{mv:+.4g}"]
    CALLS.parent.mkdir(parents=True, exist_ok=True)
    df[COLS].to_csv(CALLS, index=False)
    closed = df[df.status.isin(["hit", "miss"])]
    by = []
    for s, g in closed.groupby("source"):
        by.append({"source": s, "n": len(g), "hits": int((g.status == "hit").sum()), "hit_rate": rd((g.status == "hit").mean() * 100, 0) if len(g) >= 10 else None})
    sc = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "asof": str(asof.date()), "min_n": 10,
          "open": df[df.status == "open"].to_dict("records"), "closed": closed.tail(30).to_dict("records"),
          "n_closed": len(closed), "hits": int((closed.status == "hit").sum()),
          "hit_rate": rd((closed.status == "hit").mean() * 100, 0) if len(closed) >= 10 else None, "by_source": by,
          "logging_since": "2026-11-17 (desk reads); morning-brief cotton views of Oct 2026 imported from data/brief/calls.csv"}
    write_json("data/scorecard/scorecard.json", sc)
    print(f"calls: {len(df)} ({len(df) - n0} new this run); open {len(sc['open'])}; closed {len(closed)}, hits {sc['hits']}, hit rate {sc['hit_rate']}")
    for r in sc["open"]:
        print("  open", r["source"], r["market"], r["direction"], r["leg1"], r["leg2"], r["entry"], "->", r["horizon"])
    for r in sc["closed"]:
        print("  closed", r["logged"], r["market"], r["direction"], r["entry"], r["exit"], r["move"], r["status"])


if __name__ == "__main__":
    main()
