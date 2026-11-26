#!/usr/bin/env python3
"""Expiry deliveries for Coffee C (KC), Cotton No. 2 (CT) and London White Sugar No. 5 (WS): one record per expiry with
the reported delivery figures, the named deliverers and receivers, and (KC, CT) the spot-month open interest around the
notice period from the desk's own daily ICE data. Sugar No. 11 has its own builder (models/sugar_deliveries.py).

Inputs, per market (hand-entered rows, one per source; entry=manual):
  data/coffee/deliveries/kc_sources.csv, kc_firms.csv
  data/cotton/deliveries/ct_sources.csv, ct_firms.csv
  data/sugar/deliveries/ws_sources.csv,  ws_firms.csv
  .../auto/<p>_auto_sources.csv, <p>_auto_firms.csv   rows the capture job (pipelines/softs_deliveries.py) parsed
  data/coffee/ice_daily_contracts.csv, data/cotton/ice_daily_contracts.csv   spot-month OI and volume
  data/coffee/ice_certs.csv                                                   certified bags near first notice day
Sources columns: figure = official | preliminary | approximate | back_reference; kind = total | running | fnd | partial |
daily | context (what the number counts: the period total, a running total, first-notice-day notices, a part of the
period, one day's notices, or no count).

Writes <dir>/<p>_history.json (read by the Deliveries tabs). Standard library only.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MON = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6, "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}
MNAME = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MARKETS = {
    "KC": {"dir": "data/coffee/deliveries", "p": "kc", "months": "HKNUZ", "lot": "37,500 lb (about 283.5 bags of 60 kg)",
           "daily": "data/coffee/ice_daily_contracts.csv", "name": "Coffee C"},
    "CT": {"dir": "data/cotton/deliveries", "p": "ct", "months": "HKNZ", "lot": "50,000 lb (about 100 bales)",
           "daily": "data/cotton/ice_daily_contracts.csv", "name": "Cotton No. 2"},
    "WS": {"dir": "data/sugar/deliveries", "p": "ws", "months": "HKQVZ", "lot": "50 tonnes", "lot_t": 50.0,
           "daily": None, "name": "White Sugar No. 5"},
}
FIG_RANK = {"official": 0, "preliminary": 1, "approximate": 2, "back_reference": 3}
KIND_RANK = {"total": 0, "running": 1, "partial": 2, "fnd": 3, "daily": 4, "context": 9}
# one display name per firm; clearing members are kept apart from merchants
ALIAS = [
    (r"^Wilmar", "Wilmar"), (r"^(Louis Dreyfus|LDC)(?!.*Suisse)", "Louis Dreyfus"), (r"Suisse", "LDC Suisse"),
    (r"^Sucden Financial|^SCD", "Sucden Financial"), (r"^Sucden", "Sucden"), (r"^Marex", "Marex"), (r"^Macquarie|^MCQ", "Macquarie"),
    (r"^ADM", "ADM Investor Services"), (r"StoneX|FCStone", "StoneX"), (r"^BNP", "BNP Paribas"), (r"Capital Markets", "ED&F Man Capital Markets"),
    (r"^(ED&F Man|MAN\b)", "ED&F Man"), (r"^Al Khaleej|^Aks", "Al Khaleej"), (r"^Cofco|^COFCO", "COFCO International"),
    (r"^Term", "Term Commodities"), (r"^Olam", "Olam"), (r"^Ra[ií]zen", "Raizen"), (r"^Newedge", "Newedge"),
]


def norm(firm, ftype):
    for pat, name in ALIAS:
        if re.search(pat, firm.strip()):
            if ftype == "clearing" and name in ("Sucden", "ED&F Man", "Louis Dreyfus"):
                continue
            return name
    return firm.strip()


# ---------------------------------------------------------------- calendar (US exchange holidays, stdlib)
def easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mo = (h + l_ - 7 * m + 114) // 31
    return date(y, mo, (h + l_ - 7 * m + 114) % 31 + 1)


def nth(y, m, wd, n):
    d = date(y, m, 1)
    d += timedelta(days=(wd - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def last_wd(y, m, wd):
    d = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
    return d - timedelta(days=(d.weekday() - wd) % 7)


def observed(d):
    return d - timedelta(days=1) if d.weekday() == 5 else d + timedelta(days=1) if d.weekday() == 6 else d


_H = {}


def hols(y):
    if y not in _H:
        H = {observed(date(y, 1, 1)), nth(y, 1, 0, 3), nth(y, 2, 0, 3), easter(y) - timedelta(days=2), last_wd(y, 5, 0),
             observed(date(y, 7, 4)), nth(y, 9, 0, 1), nth(y, 11, 3, 4), observed(date(y, 12, 25))}
        if y >= 2022:
            H.add(observed(date(y, 6, 19)))
        _H[y] = H
    return _H[y]


def isbd(d, uk=False):
    return d.weekday() < 5 and (uk or d not in hols(d.year))


def prev_bd(d, n=1, uk=False):
    while n:
        d -= timedelta(days=1)
        n -= isbd(d, uk)
    return d


def next_bd(d, n=1, uk=False):
    while n:
        d += timedelta(days=1)
        n -= isbd(d, uk)
    return d


def month_bds(y, m):
    d, out = date(y, m, 1), []
    while d.month == m:
        if isbd(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def dates(sym, code, yy):
    """First notice day and last trading day from the ICE rules (KC, CT); last trading day for WS."""
    y, m = 2000 + yy, MON[code]
    B = month_bds(y, m)
    if sym == "CT":   # FND: 5 business days before the first business day of the delivery month; LTD: 17th bd from month end
        return prev_bd(B[0], 5), B[-17], None
    if sym == "KC":   # FND: 7 business days before the first business day; LTD: 1 bd before the last notice day (8 bd from end)
        return prev_bd(B[0], 7), B[-9], B[-8]
    d = date(y, m, 1) - timedelta(days=16)   # WS: 16 calendar days before the delivery month, earlier if not a business day
    while not isbd(d, uk=True):
        d -= timedelta(days=1)
    return None, d, None


def label(c):
    return f"{MNAME[MON[c[-3]]]} {2000 + int(c[-2:])}"


# ---------------------------------------------------------------- inputs
def rows(p):
    p = ROOT / p
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []


def num(v):
    v = (v or "").replace(",", "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def oi_table(path):
    """{yyyymm: [(date, oi, volume, close)]} from the desk's daily contract file."""
    T = defaultdict(list)
    for r in rows(path):
        T[r["contract"]].append((r["date"], num(r["oi"]), num(r["volume"]) or 0.0, num(r["close"])))
    for k in T:
        T[k].sort()
    return T


def certs_kc():
    """Total certified bags by date (all origins, all ports) from ICE certified stock reports in the repo."""
    S = defaultdict(float)
    for r in rows("data/coffee/ice_certs.csv"):
        if r.get("section") == "certified":
            S[r["date"]] += num(r["bags"]) or 0
    return sorted(S.items())


def spot_oi(sym, c, T, certs):
    code, yy = c[-3], int(c[-2:])
    fnd, ltd, lnd = dates(sym, code, yy)
    s = T.get(str((2000 + yy) * 100 + MON[code]), [])
    pre = [x for x in s if x[0] < str(fnd) and x[1] is not None]
    if not pre or pre[-1][0] != str(prev_bd(fnd)):   # the session before first notice day must be in the data
        return None
    on = [x for x in s if x[0] == str(fnd)]
    per = [x for x in s if str(fnd) <= x[0] <= str(ltd)]
    done = bool(s) and s[-1][0] >= str(ltd)
    last = [x for x in s if x[0] <= str(ltd) and x[1] is not None]
    o = {"fnd": str(fnd), "ltd": str(ltd), "lnd": str(lnd) if lnd else None, "oi_fnd_open": int(pre[-1][1]),
         "oi_fnd_close": int(on[0][1]) if on and on[0][1] is not None else None,
         "vol_notice_period": int(sum(x[2] for x in per)), "complete": done,
         "oi_ltd": int(last[-1][1]) if done and last else None,
         "settle_ltd": last[-1][3] if done and last else None}
    if certs:
        cb = [(d, v) for d, v in certs if d <= str(fnd)]
        if cb and (fnd - date.fromisoformat(cb[-1][0])).days <= 10:
            o["certs_bags_fnd"], o["certs_date"] = int(cb[-1][1]), cb[-1][0]
    return o


# ---------------------------------------------------------------- build
def firm_lists(fr, total):
    keep = {}
    for r in sorted(fr, key=lambda r: (r.get("entry") != "manual", FIG_RANK.get(r["figure"], 9), num(r["lots"]) is None)):
        ft = r["firm_type"] or "merchant"
        k = (r["side"], norm(r["firm"], ft), "clearing" if ft == "clearing" else "named", r["figure"] == "official")
        if k not in keep:
            keep[k] = r
    out = {"deliverer": [], "receiver": [], "clearing_deliverer": [], "clearing_receiver": []}
    for (side, firm, grp, _), r in keep.items():
        lots, rk = num(r["lots"]), (r["rank_text"] or "").lower()
        e = {"firm": firm, "type": r["firm_type"], "lots": lots, "tonnes": num(r["tonnes"]) if lots is None else None,
             "share": round(100 * lots / total, 1) if lots and total else num(r["share_pct"]),
             "sole": "sole" in rk or "all " in rk[:6] or (lots is not None and total is not None and abs(lots - total) < 1),
             "figure": r["figure"], "note": r["rank_text"] if lots is None else "",
             "intent": bool(re.search(r"intent|plan|pursuing|expected|unconfirmed", rk))}
        key = side if grp == "named" else "clearing_" + side
        if not any(x["firm"] == firm for x in out[key]):
            out[key].append(e)
    for L in out.values():
        L.sort(key=lambda e: (-(e["lots"] or (e["tonnes"] or 0) / 50), e["firm"]))
        top = (L[0]["lots"] or (L[0]["tonnes"] or 0) / 50) if L else 0
        for e in L:
            v = e["lots"] or (e["tonnes"] or 0) / 50
            e["largest"] = bool(e["sole"] or (top and v == top) or (not top and re.search(r"largest|biggest|main|principal|top", e["note"].lower() or "")))
    return out


def best_total(src):
    """The figure to headline: a period total first, then the latest running total, a partial, FND notices; within a
    kind, official before preliminary, then the larger and later number."""
    have = [r for r in src if num(r["lots"]) is not None or num(r["tonnes"]) is not None]
    if not have:
        return None
    k = lambda r: r.get("kind", "total")
    full = [r for r in have if k(r) in ("total", "running")]
    if full:
        return sorted(full, key=lambda r: (KIND_RANK[k(r)], FIG_RANK.get(r["figure"], 9), -(num(r["lots"]) or 0), r["source_date"]))[0]
    # only part of the period is reported: headline the largest count (a cumulative partial beats one day's notices)
    return sorted(have, key=lambda r: (-(num(r["lots"]) or (num(r["tonnes"]) or 0) / 50), KIND_RANK.get(k(r), 5)))[0]


def build(sym):
    M = MARKETS[sym]
    d, p = M["dir"], M["p"]
    S = rows(f"{d}/{p}_sources.csv") + rows(f"{d}/auto/{p}_auto_sources.csv")
    F = rows(f"{d}/{p}_firms.csv") + rows(f"{d}/auto/{p}_auto_firms.csv")
    T = oi_table(M["daily"]) if M["daily"] else {}
    certs = certs_kc() if sym == "KC" else []
    bys, byf = defaultdict(list), defaultdict(list)
    for r in S:
        bys[r["contract"].replace(" ", "")].append(r)
    for r in F:
        byf[r["contract"].replace(" ", "")].append(r)
    contracts = set(bys)
    if T:   # every contract in the daily data from 2018 on gets a row, reported or not
        for k in T:
            y, m = int(k[:4]), int(k[4:])
            code = next((c for c, v in MON.items() if v == m), None)
            if y >= 2018 and code in M["months"]:
                contracts.add(f"{sym}{code}{y % 100:02d}")
    today = str(date.today())
    exps = []
    for c in contracts:
        code, yy = c[-3], int(c[-2:])
        fnd, ltd, lnd = dates(sym, code, yy)
        if str(fnd or ltd) > today and c not in bys:
            continue
        src = bys.get(c, [])
        b = best_total(src)
        lots = num(b["lots"]) if b else None
        tonnes = num(b["tonnes"]) if b else None
        if sym == "WS" and lots is None and tonnes:
            lots = round(tonnes / M["lot_t"])
        if sym == "WS" and tonnes is None and lots:
            tonnes = lots * M["lot_t"]
        fnd_r = sorted([r for r in src if r.get("kind") == "fnd" and num(r["lots"]) is not None], key=lambda r: r["source_date"])
        first = lambda k: next((r[k] for r in sorted(src, key=lambda r: FIG_RANK.get(r["figure"], 9)) if r.get(k)), "")
        fl = firm_lists(byf.get(c, []), lots if b and b.get("kind", "total") == "total" else None)
        e = {"contract": c, "label": label(c), "expiry_date": (src[0]["expiry_date"] if src else str(ltd)),
             "fnd": str(fnd) if fnd else None, "lots": lots, "tonnes": tonnes,
             "kind": b.get("kind", "total") if b else None, "figure": b["figure"] if b else None,
             "as_of": b["source_date"] if b else None, "lots_derived": bool(b and b.get("lots_derived") == "yes"),
             "fnd_notices": num(fnd_r[0]["lots"]) if fnd_r else None,
             "origins": first("origins"), "ports": first("ports"),
             "expiry_price": num(first("expiry_settle_cents")),
             "deliverers": fl["deliverer"], "receivers": fl["receiver"],
             "clearing_deliverers": fl["clearing_deliverer"], "clearing_receivers": fl["clearing_receiver"],
             "auto": any(r.get("entry") == "auto" for r in src), "note": (b["notes"] if b else (src[0]["notes"] if src else "")),
             "sources": [{"source": r["source"], "date": r["source_date"], "url": r["url"].split(" ; ")[0].strip(), "figure": r["figure"],
                          "kind": r.get("kind", "")} for r in sorted(src, key=lambda r: r["source_date"], reverse=True)]}
        if T:
            e["spot"] = spot_oi(sym, c, T, certs)
            if e["spot"] and e["expiry_price"] is None and e["spot"]["settle_ltd"]:
                e["expiry_price"] = e["spot"]["settle_ltd"]
        exps.append(e)
    exps.sort(key=lambda e: e["expiry_date"], reverse=True)
    lead = {}
    for side in ("deliverer", "receiver"):
        agg = defaultdict(lambda: {"expiries": 0, "largest": 0, "sole": 0, "lots_stated": 0.0, "last": ""})
        for e in exps:
            for f in e[side + "s"]:
                if f["intent"]:
                    continue
                a = agg[f["firm"]]
                a["expiries"] += 1
                a["largest"] += f["largest"]
                a["sole"] += f["sole"]
                a["lots_stated"] += f["lots"] or 0
                a["last"] = max(a["last"], e["expiry_date"])
        lead[side] = sorted(({"firm": k, **v, "lots_stated": round(v["lots_stated"])} for k, v in agg.items()),
                            key=lambda a: (-a["largest"], -a["expiries"], a["firm"]))
    by_month = {}
    for m in M["months"]:
        L = [e["lots"] for e in exps if e["contract"][-3] == m and e["lots"] and e["kind"] == "total"]
        by_month[MNAME[MON[m]]] = {"n": len(L), "avg_lots": round(sum(L) / len(L)) if L else None,
                                   "max_lots": max(L) if L else None, "min_lots": min(L) if L else None}
    rep = [e for e in exps if e["lots"] is not None]
    return {"sym": sym, "name": M["name"], "built": today, "lot": M["lot"], "n_expiries": len(exps), "n_reported": len(rep),
            "n_firms": sum(1 for e in exps if e["deliverers"] or e["receivers"] or e["clearing_deliverers"] or e["clearing_receivers"]),
            "first": exps[-1]["label"] if exps else None, "last": exps[0]["label"] if exps else None,
            "expiries": exps, "leaders": lead, "by_month": by_month}


def main():
    for sym in (sys.argv[1:] or list(MARKETS)):
        sym = sym.upper()
        if sym not in MARKETS:
            continue
        H = build(sym)
        out = ROOT / MARKETS[sym]["dir"] / f"{MARKETS[sym]['p']}_history.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(H, ensure_ascii=False, separators=(",", ":")))
        print(f"wrote {out.relative_to(ROOT)}: {H['n_expiries']} expiries ({H['first']} to {H['last']}), {H['n_reported']} with a reported figure, {H['n_firms']} with named firms")


if __name__ == "__main__":
    main()
