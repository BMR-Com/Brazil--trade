#!/usr/bin/env python3
"""Sugar No. 11 expiry deliveries: one record per expiry (total lots and tonnes, origins, ports, expiry price) with the named
deliverers and receivers, built from the dated source rows in data/sugar/deliveries/:

  sb_sources.csv   expiry totals, one row per source (hand-entered; figure = official | preliminary | approximate | back_reference)
  sb_firms.csv     named firms, one row per expiry x side x firm x source (hand-entered)
  auto/sb_auto_sources.csv, auto/sb_auto_firms.csv   rows the capture job (pipelines/sugar_deliveries.py) parsed from news;
                   a hand-entered row for the same expiry and firm always wins.

Writes data/sugar/deliveries/sb_history.json (read by the Sugar > Deliveries tab). Standard library only.
`--lab PATH` writes the research tables (concentration, size against the expiring spread) to PATH; keep PATH outside
the repo, the results go to the private Lab only.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data/sugar/deliveries"
OUT = D / "sb_history.json"
RANK = {"official": 0, "preliminary": 1, "approximate": 2, "back_reference": 3}
MON = {"H": "Mar", "K": "May", "N": "Jul", "V": "Oct"}
LOT_T = 50.802  # 112,000 lb


def rows(p):
    p = D / p
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []


def num(v):
    v = (v or "").replace(",", "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def label(c):
    return f"{MON[c[2]]} {2000 + int(c[3:5])}" if len(c) == 5 else c


def pick(src):
    """Best row for the total: official first, then preliminary, approximate, back-reference; within a kind, a row with
    lots, then the latest source date."""
    return sorted(src, key=lambda r: (RANK.get(r["figure"], 9), num(r["lots"]) is None, -int(re.sub(r"\D", "", r["source_date"])[:8].ljust(8, "0") or 0)))


def firm_lists(fr, total):
    keep = {}
    for r in sorted(fr, key=lambda r: (r.get("entry") != "manual", num(r["lots"]) is None)):
        k = (r["side"], r["firm"], r["firm_type"])
        if k not in keep:
            keep[k] = r
    out = {"deliverer": [], "receiver": [], "clearing": []}
    for (side, firm, ft), r in keep.items():
        if ft == "unnamed":
            continue
        lots = num(r["lots"])
        rk = r["rank_text"].lower()
        e = {"firm": firm, "lots": lots, "tonnes": num(r["tonnes"]) if lots is None else None,
             "share": round(100 * lots / total, 1) if lots and total else None,
             "sole": "sole" in rk or (lots is not None and total is not None and abs(lots - total) < 1),
             "note": r["rank_text"] if lots is None else ""}
        out["clearing" if ft == "clearing_member" else side].append(e)
    for side in out:
        L = out[side]
        L.sort(key=lambda e: (-(e["lots"] or (e["tonnes"] or 0) / LOT_T), e["firm"]))
        if L:
            top_lots = L[0]["lots"] or (L[0]["tonnes"] or 0) / LOT_T
            for e in L:
                v = e["lots"] or (e["tonnes"] or 0) / LOT_T
                named_top = bool(re.search(r"largest|biggest|main|sole|top|principal", e["note"].lower())) if e["note"] else False
                e["largest"] = bool(e["sole"] or (top_lots and v == top_lots) or (not top_lots and named_top))
    return out


def build():
    S = rows("sb_sources.csv") + rows("auto/sb_auto_sources.csv")
    F = rows("sb_firms.csv") + rows("auto/sb_auto_firms.csv")
    bys, byf = defaultdict(list), defaultdict(list)
    for r in S:
        bys[r["contract"]].append(r)
    for r in F:
        byf[r["contract"]].append(r)
    exps = []
    for c, src in bys.items():
        o = pick(src)
        best = o[0]
        lots = num(best["lots"])
        tonnes = num(best["tonnes"]) or next((num(r["tonnes"]) for r in o if num(r["tonnes"])), None)
        first = lambda k: next((r[k] for r in o if r[k]), "")
        fl = firm_lists(byf.get(c, []), lots)
        gaps = [k for k, v in (("lots", lots), ("tonnes", tonnes), ("deliverers", fl["deliverer"]), ("receivers", fl["receiver"]),
                               ("origin", first("origins")), ("ports", first("ports")), ("expiry price", first("expiry_settle_cents"))) if not v]
        exps.append({"contract": c, "label": label(c), "expiry_date": best["expiry_date"], "lots": lots, "tonnes": tonnes,
                     "figure": best["figure"], "lots_derived": best.get("lots_derived") == "yes", "origins": first("origins"),
                     "ports": first("ports"), "expiry_settle_cents": num(first("expiry_settle_cents")),
                     "deliverers": fl["deliverer"], "receivers": fl["receiver"], "clearing_members": fl["clearing"],
                     "auto": any(r.get("entry") == "auto" for r in src), "gaps": gaps,
                     "sources": [{"source": r["source"], "date": r["source_date"], "url": r["url"].split(" ; ")[0].strip(), "figure": r["figure"]} for r in o]})
    exps.sort(key=lambda e: e["expiry_date"], reverse=True)
    lead = {}
    for side in ("deliverer", "receiver"):
        agg = defaultdict(lambda: {"expiries": 0, "largest": 0, "sole": 0, "lots_stated": 0.0, "last": ""})
        for e in exps:
            for f in e[side + "s"]:
                a = agg[f["firm"]]
                a["expiries"] += 1
                a["largest"] += f["largest"]
                a["sole"] += f["sole"]
                a["lots_stated"] += f["lots"] or (e["lots"] if f["sole"] and e["lots"] else 0)
                a["last"] = max(a["last"], e["expiry_date"])
        lead[side] = sorted(({"firm": k, **v, "lots_stated": round(v["lots_stated"])} for k, v in agg.items()),
                            key=lambda a: (-a["largest"], -a["expiries"], a["firm"]))
    by_month = {}
    for m, name in MON.items():
        L = [e["lots"] for e in exps if e["contract"][2] == m and e["lots"]]
        by_month[name] = {"n": len(L), "avg_lots": round(sum(L) / len(L)) if L else None, "max_lots": max(L) if L else None, "min_lots": min(L) if L else None}
    return {"built": str(date.today()), "lot_tonnes": LOT_T, "n_expiries": len(exps),
            "first": exps[-1]["label"] if exps else None, "last": exps[0]["label"] if exps else None,
            "latest_source_date": max((s["date"] for e in exps for s in e["sources"] if s["date"]), default=None),
            "expiries": exps, "leaders": lead, "by_month": by_month,
            "note": "Firms are the trading houses named in trade reports of each tender (mostly preliminary trader information "
                    "published on expiry day); ICE's own notice confirms the total. Blank means not reported, not zero."}


def lab(H, path):
    """Research tables for the private Lab (not written to the repo)."""
    import pandas as pd
    px = pd.read_csv(ROOT / "data/contracts/SB.csv", usecols=["contract", "date", "close"])
    px["date"] = pd.to_datetime(px["date"])
    nxt = {"H": ("K", 0), "K": ("N", 0), "N": ("V", 0), "V": ("H", 1)}
    out = []
    for e in sorted(H["expiries"], key=lambda e: e["expiry_date"]):
        c = e["contract"]
        y = 2000 + int(c[3:5])
        m2, dy = nxt[c[2]]
        a, b = f"SB{c[2]}{y}", f"SB{m2}{y + dy}"
        ltd = pd.Timestamp(e["expiry_date"])
        w = px[px.contract.isin([a, b])].pivot_table(index="date", columns="contract", values="close").sort_index()
        r = {"contract": e["label"], "lots": e["lots"], "figure": e["figure"]}
        if a in w and b in w:
            pre = w[w.index <= ltd]
            if len(pre) > 6:
                r["spread_ltd"] = round(pre[a].iloc[-1] - pre[b].iloc[-1], 2)
                r["spread_ltd_m5"] = round(pre[a].iloc[-6] - pre[b].iloc[-6], 2)
                r["spread_chg_last5"] = round(r["spread_ltd"] - r["spread_ltd_m5"], 2)
            post = w[w.index > ltd][b]
            if len(post) >= 10 and len(pre):
                r["next_chg_10d"] = round(post.iloc[9] - pre[b].iloc[-1], 2)
                r["next_chg_10d_pct"] = round(100 * (post.iloc[9] / pre[b].iloc[-1] - 1), 2)
        top_d = max((f["lots"] or 0 for f in e["deliverers"]), default=0)
        top_r = max((f["lots"] or (e["lots"] if f["sole"] else 0) or 0 for f in e["receivers"]), default=0)
        r["top_deliverer"] = next((f["firm"] for f in e["deliverers"] if f["largest"]), None)
        r["top_receiver"] = next((f["firm"] for f in e["receivers"] if f["largest"]), None)
        r["top_deliverer_share"] = round(100 * top_d / e["lots"], 1) if e["lots"] and top_d else None
        r["top_receiver_share"] = round(100 * top_r / e["lots"], 1) if e["lots"] and top_r else None
        r["n_receivers"] = len(e["receivers"])
        r["n_deliverers"] = len(e["deliverers"])
        out.append(r)
    T = pd.DataFrame(out)
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    T.to_csv(p / "sb_delivery_lab.csv", index=False)
    lines = [T.to_string(index=False), ""]
    v = T.dropna(subset=["lots", "spread_ltd"])
    if len(v) > 5:
        lines.append(f"corr(lots, spread at LTD) = {v.lots.corr(v.spread_ltd):.2f} (n={len(v)})")
        v2 = v.dropna(subset=["spread_chg_last5"])
        lines.append(f"corr(lots, spread change last 5 days) = {v2.lots.corr(v2.spread_chg_last5):.2f} (n={len(v2)})")
        v3 = T.dropna(subset=["lots", "next_chg_10d_pct"])
        lines.append(f"corr(lots, next contract % change 10 days after) = {v3.lots.corr(v3.next_chg_10d_pct):.2f} (n={len(v3)})")
        big = v3[v3.lots >= v3.lots.median()]
        small = v3[v3.lots < v3.lots.median()]
        lines.append(f"next contract 10d % change: deliveries >= median {big.next_chg_10d_pct.mean():.2f}% (n={len(big)}), below {small.next_chg_10d_pct.mean():.2f}% (n={len(small)})")
        rs = T.dropna(subset=["top_receiver_share"])
        lines.append(f"expiries with one receiver taking >=75%: {(rs.top_receiver_share >= 75).sum()} of {len(rs)} with a stated share")
    (p / "sb_delivery_lab.txt").write_text("\n".join(lines))
    print("\n".join(lines))


def main():
    H = build()
    OUT.write_text(json.dumps(H, ensure_ascii=False, separators=(",", ":")))
    print("wrote", OUT, H["n_expiries"], "expiries,", H["first"], "to", H["last"])
    if "--lab" in sys.argv:
        lab(H, sys.argv[sys.argv.index("--lab") + 1])


if __name__ == "__main__":
    main()
