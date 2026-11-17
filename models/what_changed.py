#!/usr/bin/env python3
"""Daily "What changed" strip for the Overview tab.

For cotton, sugar, coffee and cocoa: the change since the previous business day and since a week ago in flat price
(front settlement), front spread (front minus next), certified stocks, spot basis (cotton), managed-money net (new COT),
front implied vol (options with fewer than 15 days to expiry left out), cotton on-call (weekly) and the ensemble weather
read for each market's main crop regions. A change is flagged only when it is larger than the 80th percentile of that
series' own absolute changes over the past year (same horizon); otherwise the market reads "no notable change".

Reads only files other workflows already wrote. Writes data/overview/what_changed.json and appends to
data/overview/what_changed_hist.csv (one row per market, item and settlement date).
"""
import csv, json, subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from watch_common import (ROOT, D, MK, ORDER, WX_MAIN, J, rd, fmt, label, last_settled, load_px, chain, front_series,
                          p80, cotton_oncall, oncall_old_crop, wx_label, write_json, bd_between)

HIST = D / "overview" / "what_changed_hist.csv"
Q = 0.8


def item(name, unit, d, now, d1=None, d5=None, n1=None, n5=None, date=None, note="", kind="daily", dec=None):
    dec = d if dec is None else dec
    f1 = bool(d1 is not None and n1 is not None and abs(d1) > n1)
    f5 = bool(d5 is not None and n5 is not None and abs(d5) > n5)
    return {"item": name, "unit": unit, "dp": dec, "now": rd(now, dec), "d1": rd(d1, dec), "d5": rd(d5, dec), "norm1": rd(n1, dec),
            "norm5": rd(n5, dec), "flag1": f1, "flag5": f5, "date": date, "note": note, "kind": kind}


def year_ago(asof):
    return asof - pd.Timedelta(days=365)


def price_items(sym, asof):
    name, unit, dp, _, _ = MK[sym]
    w = load_px(sym, asof)
    fs = front_series(sym, w)
    fs = fs[fs.index <= asof]
    last = fs.iloc[-1]
    yr = fs[fs.index > year_ago(asof)]
    f, n = last.front, last.next
    out = [item(f"Flat price ({label(f)})", unit, dp, last.px, last.dpx1, last.dpx5, p80(yr.dpx1), p80(yr.dpx5),
                str(fs.index[-1].date()))]
    sp_note = f"{label(f)} minus {label(n)}; negative = carry" if n else ""
    out.append(item(f"Front spread ({label(f)}/{label(n)})" if n else "Front spread", unit, dp, last.sp, last.dsp1, last.dsp5,
                    p80(yr.dsp1), p80(yr.dsp5), str(fs.index[-1].date()), sp_note))
    return out, fs


def certs_items(sym, asof):
    if sym == "KC":
        c = pd.read_csv(D / "coffee" / "ice_certs.csv", parse_dates=["date"])
        s = c[c.section == "certified"].groupby("date").bags.sum().sort_index()
        s = s[s.index <= asof]
        if s.empty:
            return []
        d1 = s.diff()
        wk = pd.Series([s.iloc[i] - s[s.index <= s.index[i] - pd.Timedelta(days=7)].iloc[-1]
                        if (s.index <= s.index[i] - pd.Timedelta(days=7)).any() else np.nan for i in range(len(s))], index=s.index)
        yr = s.index > year_ago(asof)
        # report-to-report changes only where reports are on consecutive business days
        gap = pd.Series([bd_between(a, b) if i else np.nan for i, (a, b) in enumerate(zip(s.index.insert(0, s.index[0])[:-1], s.index))], index=s.index)
        n1 = p80(d1[yr & (gap == 1)])
        n5 = p80(wk[yr])
        return [item("ICE certified arabica", "bags", 0, s.iloc[-1], d1.iloc[-1] if gap.iloc[-1] == 1 else None, wk.iloc[-1], n1, n5,
                     str(s.index[-1].date()), "ICE daily certified-stock report" + ("" if gap.iloc[-1] == 1 else "; previous report not the prior business day"))]
    if sym == "CT":
        pts = {}
        for p in sorted((D / "cotton" / "ice").glob("stock_*.csv")):
            t = pd.read_csv(p)
            for col in t.columns:
                if col.startswith("Current Stock - ") or col.startswith("Stock - "):
                    dt = pd.to_datetime(col.split(" - ", 1)[1], format="%d-%b-%Y", errors="coerce")
                    if dt is not pd.NaT:
                        pts[dt] = float(pd.to_numeric(t[col], errors="coerce").sum())
        L = J("data/cotton/ice/latest.json", {})
        if L.get("warehouse") and L.get("warehouse_date"):
            dt = pd.Timestamp(L["warehouse_date"])
            if not pts or dt > max(pts):
                pts[dt] = float(pd.read_csv(ROOT / L["warehouse"])["Receipt"].sum())
        if not pts:
            return []
        s = pd.Series(pts).sort_index()
        s = s[s.index <= asof]
        prev = s[s.index <= s.index[-1] - pd.Timedelta(days=4)]
        wk = s.iloc[-1] - prev.iloc[-1] if len(prev) else None
        note = f"ICE certificated stock, bales; change vs {prev.index[-1].date()}" if len(prev) else "ICE certificated stock, bales"
        return [item("ICE certificated cotton", "bales", 0, s.iloc[-1], None, wk, None, None, str(s.index[-1].date()),
                     note + "; history on the desk too short to rank the change", kind="weekly")]
    if sym == "SB":
        return [item("Certified stocks", "", 0, None, note="No.11 delivers FOB origin: no certified stocks", kind="na")]
    return [item("Certified stocks", "", 0, None, note="ICE cocoa certified stocks are not collected on the desk", kind="na")]


def basis_items(asof):
    b = pd.read_csv(D / "cotton" / "spot_basis.csv", parse_dates=["date"])
    b = b[(b.market == "US Average") & (b.date <= asof)].sort_values("date").reset_index(drop=True)
    if b.empty:
        return []
    b["d1"] = np.where(b.basis_month == b.basis_month.shift(1), b.basis_41_4_34 - b.basis_41_4_34.shift(1), np.nan)
    b["d5"] = np.where(b.basis_month == b.basis_month.shift(5), b.basis_41_4_34 - b.basis_41_4_34.shift(5), np.nan)
    yr = b[b.date > year_ago(asof)]
    L = b.iloc[-1]
    note = f"USDA spot 41-4-34 minus {L.basis_month} futures, points"
    if np.isnan(L.d1):
        note += f"; reference month changed to {L.basis_month}, no like-for-like daily change"
    return [item("Spot basis (US average)", "pts", 0, L.basis_41_4_34, L.d1, L.d5, p80(yr.d1), p80(yr.d5), str(L.date.date()), note)]


def cot_item(sym, asof, prev_cot):
    C = J(f"data/cot_desk/{sym}.json")
    if not C:
        return None
    s = pd.Series(C["series"]["mm_n"], index=pd.to_datetime(C["series"]["date"])).sort_index()
    s = s[s.index <= asof]
    dN = s.diff()
    yr = dN[dN.index > year_ago(asof)]
    new = prev_cot is None or str(s.index[-1].date()) != prev_cot
    it = item("Managed money net", "lots", 0, s.iloc[-1], None, dN.iloc[-1], None, p80(yr), str(s.index[-1].date()),
              ("new report" if new else "no new report since the last run") + f"; CFTC futures and options, positions as of {s.index[-1].date()}",
              kind="weekly")
    it["new"] = new
    return it


def iv_item(sym, asof):
    O = J(f"data/options/{sym}.json")
    if not O or not O.get("iv_hist"):
        return item("Front implied vol", "%", 1, None, note="no option file", kind="na")
    h = pd.DataFrame(O["iv_hist"], columns=["date", "iv", "series"])
    h["date"] = pd.to_datetime(h["date"])
    h = h[h.date <= asof].reset_index(drop=True)
    h["d1"] = np.where(h.series == h.series.shift(1), h.iv - h.iv.shift(1), np.nan)
    h["d5"] = np.where(h.series == h.series.shift(5), h.iv - h.iv.shift(5), np.nan)
    L = h.iloc[-1]
    age = bd_between(L.date, asof)
    n1, n5 = p80(h.d1), p80(h.d5)
    note = f"ATM vol of the first option series with at least {O.get('min_iv_dte', 15)} days to expiry ({L.series}); ICE settlement files to {L.date.date()}"
    if len(h) < 250:
        note += f"; normal range from {len(h)} sessions only"
    if age > 1:
        note += f"; option data {age} business days old"
    it = item(f"Front implied vol ({L.series})", "vol pts", 1, L.iv, L.d1 if age <= 1 else None, L.d5 if age <= 1 else None, n1, n5,
              str(L.date.date()), note)
    return it


def oncall_item(asof):
    g = oncall_old_crop(cotton_oncall())
    if g is None or g.empty:
        return None
    g = g[g.index <= asof]
    d = g.sales.diff()
    yr = d[d.index > year_ago(asof)]
    return item("On-call sales, old crop", "lots", 0, g.sales.iloc[-1], None, d.iloc[-1], None, p80(yr), str(g.index[-1].date()),
                f"CFTC unfixed call sales, Dec/Mar/May/Jul old crop (October ignored); purchases {g.purchases.iloc[-1]:,.0f} lots "
                f"({g.purchases.diff().iloc[-1]:+,.0f})", kind="weekly")


def prev_wx_snapshot(cur_gen):
    """Previous ensemble run: from our own history, else the last committed version at least 18 h older."""
    try:
        cur = datetime.strptime(cur_gen[:16], "%Y-%m-%d %H:%M")
        log = subprocess.run(["git", "-C", str(ROOT), "log", "--format=%H %cI", "-n", "30", "--", "data/geo/wx_ensemble.json"],
                             capture_output=True, text=True, timeout=30).stdout.split("\n")
        for ln in log:
            if not ln.strip():
                continue
            h, t = ln.split(" ", 1)
            old = json.loads(subprocess.run(["git", "-C", str(ROOT), "show", f"{h}:data/geo/wx_ensemble.json"], capture_output=True, text=True, timeout=30).stdout)
            og = datetime.strptime(old["generated"][:16], "%Y-%m-%d %H:%M")
            if (cur - og).total_seconds() >= 18 * 3600:
                return old
    except Exception as e:
        print("weather history from git unavailable:", str(e)[:100])
    return None


def wx_items(sym, W, Wp):
    rows = []
    for rid in WX_MAIN[sym]:
        r = W["regions"].get(rid)
        if not r:
            continue
        lab, src = wx_label(r)
        pl = None
        if Wp and rid in Wp.get("regions", {}):
            pl, _ = wx_label(Wp["regions"][rid])
        e = (r.get("next15") or {}).get("ecmwf_ens") or {}
        flip = bool(pl and lab and pl != lab and lab in ("dry", "wet"))
        rows.append({"region": rid, "name": r["name"], "read": lab, "prev": pl, "flip": flip, "src": src,
                     "rain_p50": e.get("rain_p50"), "rain_normal": e.get("rain_normal"), "frost": r.get("p_frost3_max"),
                     "window": f"{e.get('from')} to {e.get('to')}" if e else None})
    return rows


def main():
    asof = last_settled()
    prev = {}
    if HIST.exists():
        h = pd.read_csv(HIST)
        h = h[h["asof"] < str(asof.date())].sort_values("asof")
        for _, r in h.iterrows():
            prev[(r["sym"], r["item"])] = r["value"]
    W = J("data/geo/wx_ensemble.json", {"regions": {}, "generated": ""})
    Wp = prev_wx_snapshot(W.get("generated", "")) if W.get("generated") else None
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "asof": str(asof.date()), "rule":
           "A move is flagged when it is larger than the 80th percentile of the same series' absolute changes over the past year (same horizon: one business day or one week).",
           "weather": {"generated": W.get("generated"), "prev_generated": (Wp or {}).get("generated")}, "markets": []}
    hist_rows = []
    for sym in ORDER:
        name = MK[sym][0]
        m = {"sym": sym, "name": name, "items": [], "flags": [], "errors": []}
        try:
            its, fs = price_items(sym, asof)
            m["items"] += its
        except Exception as e:
            m["errors"].append(f"prices: {str(e)[:80]}")
        for fn in (lambda: certs_items(sym, asof), lambda: basis_items(asof) if sym == "CT" else [],
                   lambda: [cot_item(sym, asof, prev.get((sym, "cot_date")))], lambda: [iv_item(sym, asof)],
                   lambda: [oncall_item(asof)] if sym == "CT" else []):
            try:
                m["items"] += [x for x in fn() if x]
            except Exception as e:
                m["errors"].append(str(e)[:100])
        try:
            m["weather"] = wx_items(sym, W, Wp)
        except Exception as e:
            m["weather"] = []
            m["errors"].append(f"weather: {str(e)[:80]}")
        for it in m["items"]:
            u = it["unit"]
            if it["flag1"]:
                m["flags"].append(f"{it['item']} {fmt(it['d1'], it['dp'], True)} {u} on the day (normal within ±{fmt(it['norm1'], it['dp'])})")
            if it["flag5"]:
                lab = "on the week" if it["kind"] != "weekly" else f"in the week to {it['date']}"
                m["flags"].append(f"{it['item']} {fmt(it['d5'], it['dp'], True)} {u} {lab} (normal within ±{fmt(it['norm5'], it['dp'])})")
            hist_rows.append([str(asof.date()), sym, it["item"], it["now"], it["d1"], it["d5"], int(it["flag1"] or it["flag5"])])
        for r in m["weather"]:
            if r["flip"]:
                m["flags"].append(f"Weather {r['name']}: next-15-day read turned {r['read']} (was {r['prev']})")
            hist_rows.append([str(asof.date()), sym, "wx:" + r["region"], r["read"], None, None, int(r["flip"])])
        cot = next((i for i in m["items"] if i["item"] == "Managed money net"), None)
        if cot:
            hist_rows.append([str(asof.date()), sym, "cot_date", cot["date"], None, None, 0])
        m["summary"] = "; ".join(m["flags"]) if m["flags"] else "No notable change."
        out["markets"].append(m)
    write_json("data/overview/what_changed.json", out)
    # history: replace rows of this settlement date, keep the rest
    old = pd.read_csv(HIST) if HIST.exists() else pd.DataFrame(columns=["asof", "sym", "item", "value", "d1", "d5", "flag"])
    old = old[old["asof"] != str(asof.date())]
    new = pd.DataFrame(hist_rows, columns=["asof", "sym", "item", "value", "d1", "d5", "flag"])
    pd.concat([old, new]).to_csv(HIST, index=False)
    for m in out["markets"]:
        print(f"{m['name']}: {m['summary']}" + (f"  [errors: {m['errors']}]" if m["errors"] else ""))


if __name__ == "__main__":
    main()
