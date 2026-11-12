#!/usr/bin/env python3
"""Softs option desk (cotton, sugar, coffee, cocoa) from the ICE settlement files collected in BMR-Com/softs--options-.

Reads data/csv/<SYM>_MASTER.csv (one row per date/expiry/strike/call-put: settle, volume, open interest, OI change,
delta, implied vol, futures) and writes data/options/<SYM>.json in the same layout as the CME option desks
(per-expiry ATM vol, skew, walls, max pain, term structure, smiles, OI by strike, IV history), plus a positioning
section built from open interest:
- strikes with the most open interest (calls and puts) per expiry, with their change on the day and over 5 sessions;
- the largest open-interest builds and cuts on the day and over the last 5 sessions;
- volume leaders on the last session;
- a daily table for the last 10 sessions (futures, call/put OI and volume, put/call, front ATM vol and skew,
  delta-weighted OI change = net futures-equivalent position added through options);
- a short written read of the last few sessions.
Days whose file is incomplete (total OI under half the previous day's) are skipped.
"""
import io, json, math, os
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
OUT = D / "options"
LOCAL = ROOT.parent / "softs--options-" / "data" / "csv"
RAW = "https://raw.githubusercontent.com/BMR-Com/softs--options-/main/data/csv/"
NAMES = {"CT": "Cotton", "SB": "Sugar No. 11", "KC": "Coffee C", "CC": "Cocoa"}
MON = {m: i + 1 for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
UNIT = {"CT": "¢/lb", "SB": "¢/lb", "KC": "¢/lb", "CC": "$/t"}
MULT = {"CT": 500, "SB": 1120, "KC": 375, "CC": 10}   # $ per 1 price unit per lot
MIN_IV_DTE = 15   # options this close to expiry are left out of implied-vol readings (pin and gamma noise)


def read(sym, kind):
    p = LOCAL / f"{sym}_{kind}.csv"
    if p.exists():
        return pd.read_csv(p)
    import requests
    r = requests.get(RAW + f"{sym}_{kind}.csv", timeout=60, headers={"Authorization": f"token {os.environ['GH_TOKEN']}"} if os.environ.get("GH_TOKEN") else {})
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))


def lab(code):   # DEC26 -> Dec 26
    return code[:3].title() + " " + code[3:]


def r1(v, n=2):
    return None if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else round(float(v), n)


def smile(g):
    F = float(g.F.iloc[0])
    s = pd.concat([g[(g.cp == "P") & (g.strike < F)], g[(g.cp == "C") & (g.strike >= F)]]).dropna(subset=["iv"])
    return F, s[(s.iv > 1) & (s.iv < 300)].sort_values("strike")


def atm_iv(g):
    F, s = smile(g)
    if len(s) < 2 or not (s.strike.min() <= F <= s.strike.max()):
        return None
    return float(np.interp(F, s.strike, s.iv))


def delta_iv(g, side, target=0.25):
    x = g[g.cp == side].dropna(subset=["delta", "iv"]).copy()
    x["ad"] = x.delta.abs()
    x = x[(x.ad > 0.03) & (x.ad < 0.97) & (x.iv > 1)].sort_values("ad")
    if len(x) < 2 or not (x.ad.min() <= target <= x.ad.max()):
        return None
    return float(np.interp(target, x.ad, x.iv))


def max_pain(g):
    c, p = g[g.cp == "C"].groupby("strike").oi.sum(), g[g.cp == "P"].groupby("strike").oi.sum()
    best = bk = None
    for K in sorted(g.strike.unique()):
        pay = sum(max(0, K - k) * o for k, o in c.items()) + sum(max(0, k - K) * o for k, o in p.items())
        if best is None or pay < best:
            best, bk = pay, K
    return float(bk) if bk is not None else None


def prep(sym):
    d = read(sym, "MASTER").rename(columns={"expiry": "contract", "call_put": "cp", "open_interest": "oi", "implied_vol_pct": "iv",
                                            "futures_price": "F", "underlying_fut": "und", "time_to_expiry_yrs": "T", "settle_price": "settle"})
    d["date"] = pd.to_datetime(d.date)
    d = d[d.F.notna() & d.strike.notna()]
    tot = d.groupby("date").oi.sum()
    bad = [dt for dt, prev in zip(tot.index[1:], tot.values[:-1]) if tot[dt] < 0.5 * prev]
    d = d[~d.date.isin(bad)]
    # gamma per lot (per 1 price unit) from the settlement vol
    sig = d.iv / 100
    T = d["T"].clip(lower=1 / 365)
    d1 = (np.log(d.F / d.strike) + sig ** 2 * T / 2) / (sig * np.sqrt(T))
    d["gamma"] = np.exp(-d1 ** 2 / 2) / np.sqrt(2 * np.pi) / (d.F * sig * np.sqrt(T))
    d["expiry"] = (d.date + pd.to_timedelta(d.dte, unit="D")).dt.date.astype(str)
    return d, [x.date().isoformat() for x in bad]


def b76_gamma(F, K, iv, T):
    sig = np.clip(iv / 100, 0.01, 5)
    T = max(T, 1 / 365)
    d1 = (np.log(F / K) + sig ** 2 * T / 2) / (sig * np.sqrt(T))
    return np.exp(-d1 ** 2 / 2) / np.sqrt(2 * np.pi) / (F * sig * np.sqrt(T))


def sig_label(doi, dpx):
    """who is behind a day's open-interest change on one side (calls or puts), from OI change and premium change"""
    if abs(doi) < 50:
        return "quiet"
    if doi > 0:
        return "new longs" if dpx > 0 else "new shorts" if dpx < 0 else "new positions"
    return "longs closing" if dpx < 0 else "shorts covering" if dpx > 0 else "closing"


def expiry_block(d, dates, con, sym):
    """Everything the desk shows for one option month: OI by strike with changes, top strikes, builds/cuts,
    flow by session (who is buying/selling), and the gamma profile across futures prices."""
    last = dates[-1]
    ds = [x for x in dates if len(d[(d.date == x) & (d.contract == con)])]
    g = d[(d.date == last) & (d.contract == con)]
    F, T, dte = float(g.F.iloc[0]), float(g["T"].iloc[0]), int(g.dte.iloc[0])
    key = ["strike", "cp"]
    d5 = ds[-6] if len(ds) >= 6 else ds[0]
    b5 = d[(d.date == d5) & (d.contract == con)].set_index(key).oi
    x = g.set_index(key)
    x["chg5"] = x.oi - b5.reindex(x.index).fillna(0)
    x = x.reset_index()
    rows = []
    for K, kk in x.groupby("strike"):
        c, p = kk[kk.cp == "C"], kk[kk.cp == "P"]
        if c.oi.sum() + p.oi.sum() + c.volume.sum() + p.volume.sum() == 0:
            continue
        rows.append({"K": float(K), "cOI": int(c.oi.sum()), "pOI": int(p.oi.sum()), "dc": int(c.oi_change.sum()), "dp": int(p.oi_change.sum()),
                     "dc5": int(c.chg5.sum()), "dp5": int(p.chg5.sum()), "cVol": int(c.volume.sum()), "pVol": int(p.volume.sum()),
                     "civ": r1(c.iv.mean(), 1) if len(c) else None, "piv": r1(p.iv.mean(), 1) if len(p) else None,
                     "cs": r1(c.settle.mean(), 4) if len(c) else None, "ps": r1(p.settle.mean(), 4) if len(p) else None})
    pick = lambda r: {"K": float(r.strike), "cp": r.cp, "oi": int(r.oi), "chg1": int(r.oi_change), "chg5": int(r.chg5), "vol": int(r.volume),
                      "settle": r1(r.settle, 4), "delta": r1(r.delta, 2), "iv": r1(r.iv, 1)}
    moves = {"build_1d": [pick(r) for r in x.nlargest(8, "oi_change").itertuples() if r.oi_change > 0],
             "cut_1d": [pick(r) for r in x.nsmallest(8, "oi_change").itertuples() if r.oi_change < 0],
             "build_5d": [pick(r) for r in x.nlargest(8, "chg5").itertuples() if r.chg5 > 0],
             "cut_5d": [pick(r) for r in x.nsmallest(8, "chg5").itertuples() if r.chg5 < 0],
             "volume": [pick(r) for r in x.nlargest(8, "volume").itertuples() if r.volume > 0]}
    top = {"calls": [pick(r) for r in x[x.cp == "C"].nlargest(6, "oi").itertuples()], "puts": [pick(r) for r in x[x.cp == "P"].nlargest(6, "oi").itertuples()]}
    # session-by-session flow: volume, OI change and who is behind it (premium change on volume-weighted strikes)
    flow = []
    prev = None
    for dt in ds[-10:]:
        y = d[(d.date == dt) & (d.contract == con)]
        row = {"date": dt.date().isoformat(), "F": r1(float(y.F.iloc[0]), 2), "dte": int(y.dte.iloc[0])}
        for side, nm in (("C", "c"), ("P", "p")):
            z = y[y.cp == side]
            vol, doi = int(z.volume.sum()), int(z.oi_change.sum())
            dpx = 0.0
            if prev is not None and vol > 0:
                pz = prev[prev.cp == side].set_index("strike").settle
                zz = z[z.volume > 0].set_index("strike")
                ch = (zz.settle - pz.reindex(zz.index)).dropna()
                w = zz.volume.reindex(ch.index)
                dpx = float((ch * w).sum() / w.sum()) if w.sum() > 0 else 0.0
            row.update({nm + "Vol": vol, nm + "dOI": doi, nm + "sig": sig_label(doi, dpx)})
        row["atm"] = r1(atm_iv(y), 1) if row["dte"] >= MIN_IV_DTE else None
        row["pc_vol"] = r1(row["pVol"] / row["cVol"]) if row["cVol"] else None
        flow.append(row)
        prev = y
    # gamma profile: dollar gamma of open interest (per 1% futures move) across futures prices, calls + / puts - (dealer-short-puts convention)
    grid = np.linspace(F * 0.8, F * 1.2, 41)
    z = g[(g.oi > 0) & g.iv.notna() & (g.iv > 1)]
    gp = []
    for S in grid:
        gm = b76_gamma(S, z.strike.values, z.iv.values, T) * z.oi.values * S * S * 0.01 * MULT[sym]
        sign = np.where(z.cp.values == "C", 1, -1)
        gp.append([round(float(S), 2), round(float((gm * sign).sum()) / 1e3, 1), round(float(gm.sum()) / 1e3, 1)])
    flip = None
    for (s1, a1, _), (s2, a2, _) in zip(gp, gp[1:]):
        if a1 == 0 or (a1 < 0) != (a2 < 0):
            flip = round(s1 + (s2 - s1) * (0 - a1) / ((a2 - a1) or 1), 2)
            if abs(flip - F) < F * 0.1:
                break
    peak = max(gp, key=lambda r: r[2])[0] if gp else None
    cOI, pOI = int(g[g.cp == "C"].oi.sum()), int(g[g.cp == "P"].oi.sum())
    return {"exp": lab(con), "und": lab(g.und.iloc[0]), "F": F, "dte": dte, "expiry": g.expiry.iloc[0], "cOI": cOI, "pOI": pOI,
            "dcOI": int(g[g.cp == "C"].oi_change.sum()), "dpOI": int(g[g.cp == "P"].oi_change.sum()),
            "cVol": int(g[g.cp == "C"].volume.sum()), "pVol": int(g[g.cp == "P"].volume.sum()), "pc_oi": r1(pOI / cOI) if cOI else None,
            "rows": [r for r in rows if F * 0.6 < r["K"] < F * 1.6], "top": top, "moves": moves, "flow": flow,
            "gamma": {"grid": gp, "flip": flip, "peak": peak, "note": "$ thousand per 1% futures move; net = calls minus puts"}}


def insights(d, dates):
    """market-wide rankings: expiries by OI and by the day's change, strikes across all expiries"""
    day = d[d.date == dates[-1]]
    ex = []
    for con, g in day.groupby("contract"):
        c, p = g[g.cp == "C"], g[g.cp == "P"]
        ex.append({"exp": lab(con), "und": lab(g.und.iloc[0]), "dte": int(g.dte.iloc[0]), "tot": int(g.oi.sum()), "cOI": int(c.oi.sum()), "pOI": int(p.oi.sum()),
                   "dc": int(c.oi_change.sum()), "dp": int(p.oi_change.sum()), "cVol": int(c.volume.sum()), "pVol": int(p.volume.sum())})
    st = day.groupby(["strike", "cp"]).agg(oi=("oi", "sum"), ch=("oi_change", "sum"), vol=("volume", "sum")).unstack(fill_value=0)
    strikes = []
    for K, r in st.iterrows():
        cO, pO = int(r[("oi", "C")]) if ("oi", "C") in r else 0, int(r[("oi", "P")]) if ("oi", "P") in r else 0
        cC, pC = int(r[("ch", "C")]) if ("ch", "C") in r else 0, int(r[("ch", "P")]) if ("ch", "P") in r else 0
        strikes.append({"K": float(K), "tot": cO + pO, "cOI": cO, "pOI": pO, "dc": cC, "dp": pC, "net": cC + pC})
    return {"by_oi": sorted(ex, key=lambda e: -e["tot"]), "by_change": sorted(ex, key=lambda e: -abs(e["dc"] + e["dp"])),
            "strikes_oi": sorted(strikes, key=lambda e: -e["tot"])[:15], "strikes_change": sorted(strikes, key=lambda e: -abs(e["net"]))[:15]}


def flow_tables(d, dates, front_cons, sym):
    """Positioning from open interest: top strikes, biggest builds/cuts, volume leaders, daily table."""
    last = dates[-1]
    d5 = dates[-6] if len(dates) >= 6 else dates[0]
    day = d[d.date == last]
    key = ["contract", "strike", "cp"]
    base5 = d[d.date == d5].set_index(key).oi
    # OI change over the last 5 sessions per line; day change from the file's own oi_change column
    day = day.set_index(key)
    day["chg5"] = day.oi - base5.reindex(day.index).fillna(0)
    day = day.reset_index()
    pick = lambda x: {"exp": lab(x.contract), "und": lab(x.und), "K": float(x.strike), "cp": x.cp, "oi": int(x.oi), "chg1": int(x.oi_change),
                      "chg5": int(x.chg5), "vol": int(x.volume), "settle": r1(x.settle, 4), "delta": r1(x.delta, 2), "iv": r1(x.iv, 1)}
    top = []
    for con in front_cons:
        g = day[day.contract == con]
        top.append({"exp": lab(con), "und": lab(g.und.iloc[0]), "F": float(g.F.iloc[0]),
                    "calls": [pick(x) for x in g[g.cp == "C"].nlargest(5, "oi").itertuples()],
                    "puts": [pick(x) for x in g[g.cp == "P"].nlargest(5, "oi").itertuples()]})
    act = day[day.dte >= 1]
    moves = {"build_1d": [pick(x) for x in act.nlargest(10, "oi_change").itertuples() if x.oi_change > 0],
             "cut_1d": [pick(x) for x in act.nsmallest(10, "oi_change").itertuples() if x.oi_change < 0],
             "build_5d": [pick(x) for x in act.nlargest(10, "chg5").itertuples() if x.chg5 > 0],
             "cut_5d": [pick(x) for x in act.nsmallest(10, "chg5").itertuples() if x.chg5 < 0],
             "volume": [pick(x) for x in act.nlargest(10, "volume").itertuples() if x.volume > 0]}
    # daily table: last 10 sessions
    daily = []
    fut = d.groupby(["date", "und"]).F.first()
    for dt in dates[-10:]:
        x = d[d.date == dt]
        c, p = x[x.cp == "C"], x[x.cp == "P"]
        fr = x[x.dte >= MIN_IV_DTE]
        fc = fr.loc[fr.dte == fr.dte.min(), "contract"].iloc[0] if len(fr) else None
        g = x[x.contract == fc] if fc else None
        a = atm_iv(g) if g is not None else None
        c25, p25 = (delta_iv(g, "C"), delta_iv(g, "P")) if g is not None else (None, None)
        dd = float((x.delta.fillna(0) * x.oi_change).sum())   # futures-equivalent lots added through options (holder side)
        daily.append({"date": dt.date().isoformat(), "front": lab(fc) if fc else None, "F": r1(float(g.F.iloc[0]), 2) if g is not None and len(g) else None,
                      "cOI": int(c.oi.sum()), "pOI": int(p.oi.sum()), "pc_oi": r1(p.oi.sum() / max(c.oi.sum(), 1)), "dcOI": int(c.oi_change.sum()), "dpOI": int(p.oi_change.sum()),
                      "cVol": int(c.volume.sum()), "pVol": int(p.volume.sum()), "pc_vol": r1(p.volume.sum() / max(c.volume.sum(), 1)),
                      "atm": r1(a, 1), "rr25": r1(c25 - p25, 1) if c25 is not None and p25 is not None else None, "delta_added": int(round(dd))})
    return top, moves, daily


def read_text(name, unit, front, daily, top, moves, wk):
    t = []
    r = front
    t.append(f"{name} {r['label']} options (on {r['underlying']} futures {r['F']:g}, {r['dte']} days to expiry {r['expiry']}): at-the-money implied vol {r['atm']:.1f}%"
             + (f", {r['d_atm_1w']:+.1f} pts vs {wk}" if r["d_atm_1w"] is not None else "") + ".")
    if r.get("rv20"):
        t.append(f"20-day realized vol {r['rv20']:.1f}%, so options trade at a {'premium' if r['vrp'] > 0 else 'discount'} of {abs(r['vrp']):.1f} pts.")
    if r["rr25"] is not None:
        t.append(f"25-delta risk reversal {r['rr25']:+.1f} ({'calls over puts' if r['rr25'] > 0.5 else 'puts over calls' if r['rr25'] < -0.5 else 'balanced'}).")
    if len(daily) >= 2:
        a, b = daily[0], daily[-1]
        n = len(daily)
        dc, dp = b["cOI"] - a["cOI"], b["pOI"] - a["pOI"]
        t.append(f"Over the last {n} sessions ({a['date']} to {b['date']}) call open interest {'rose' if dc > 0 else 'fell'} {abs(dc):,} and puts {'rose' if dp > 0 else 'fell'} {abs(dp):,}; "
                 f"put/call OI {a['pc_oi']} → {b['pc_oi']}" + (f", front futures {a['F']:g} → {b['F']:g}" if a["F"] and b["F"] else "") + ".")
        net = sum(x["delta_added"] for x in daily[-5:])
        t.append(f"Delta-weighted, option holders added about {net:+,} futures-equivalent lots in the last 5 sessions ({'net long exposure bought through options' if net > 0 else 'net short exposure bought through options'}).")
        vols = [x["atm"] for x in daily if x["atm"] is not None]
        if len(vols) >= 2:
            t.append(f"Front ATM vol {vols[0]:.1f}% → {vols[-1]:.1f}%.")
    if top:
        f = top[0]
        c, p = f["calls"][:1], f["puts"][:1]
        if c and p:
            t.append(f"Largest {f['exp']} strikes: {c[0]['K']:g} calls ({c[0]['oi']:,} lots) and {p[0]['K']:g} puts ({p[0]['oi']:,}).")
    b5 = moves["build_5d"][:2]
    if b5:
        t.append("Biggest 5-session builds: " + "; ".join(f"{x['exp']} {x['K']:g} {'calls' if x['cp'] == 'C' else 'puts'} +{x['chg5']:,}" for x in b5) + ".")
    c5 = moves["cut_5d"][:1]
    if c5:
        t.append(f"Biggest cut: {c5[0]['exp']} {c5[0]['K']:g} {'calls' if c5[0]['cp'] == 'C' else 'puts'} {c5[0]['chg5']:,}.")
    return " ".join(t)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vol = json.loads((D / "vol/vol.json").read_text()).get("markets", {}) if (D / "vol/vol.json").exists() else {}
    idx = json.loads((OUT / "index.json").read_text()) if (OUT / "index.json").exists() else {"markets": {}}
    for sym, name in NAMES.items():
        try:
            d, bad = prep(sym)
        except Exception as e:
            print(sym, "no data:", e)
            continue
        dates = sorted(d.date.unique())
        if not dates:
            continue
        last = dates[-1]
        prev = dates[-2] if len(dates) > 1 else None
        wk = [x for x in dates if x <= last - pd.Timedelta(days=6)]
        wk = wk[-1] if wk else None
        day = d[d.date == last]
        rvmap = {c["label"].upper().replace(" ", ""): c for c in vol.get(sym, {}).get("contracts", [])}
        rows = []
        for con, g in sorted(day.groupby("contract"), key=lambda x: x[1].dte.iloc[0]):
            dte = int(g.dte.iloc[0])
            if dte < 1:
                continue
            F, T = float(g.F.iloc[0]), float(g["T"].iloc[0])
            a, c25, p25 = (atm_iv(g), delta_iv(g, "C"), delta_iv(g, "P")) if dte >= MIN_IV_DTE else (None, None, None)
            def at(dt):
                gg = d[(d.date == dt) & (d.contract == con)] if dt is not None else []
                return (atm_iv(gg), gg) if len(gg) else (None, None)
            a_d, _ = at(prev)
            a_w, g_w = at(wk)
            if dte < MIN_IV_DTE:
                a_d = a_w = g_w = None
            rr = c25 - p25 if c25 is not None and p25 is not None else None
            rr_w = None
            if g_w is not None:
                cw, pw = delta_iv(g_w, "C"), delta_iv(g_w, "P")
                rr_w = cw - pw if cw is not None and pw is not None else None
            und = g.und.iloc[0]
            rv = (rvmap.get(und) or {}).get("hv20")
            cOI, pOI = int(g[g.cp == "C"].oi.sum()), int(g[g.cp == "P"].oi.sum())
            ww = None if g_w is None else (int(g_w[g_w.cp == "C"].oi.sum()), int(g_w[g_w.cp == "P"].oi.sum()))
            above, below = g[(g.cp == "C") & (g.strike >= F)], g[(g.cp == "P") & (g.strike <= F)]
            gam = g.assign(gx=g.gamma.fillna(0) * g.oi).groupby("strike").gx.sum()
            sm = smile(g)[1]
            rows.append({"contract": con, "label": lab(con), "underlying": lab(und).upper(), "expiry": g.expiry.iloc[0], "dte": dte, "F": F,
                         "atm": r1(a), "d_atm_1d": r1(a - a_d) if None not in (a, a_d) else None, "d_atm_1w": r1(a - a_w) if None not in (a, a_w) else None,
                         "c25": r1(c25), "p25": r1(p25), "rr25": r1(rr), "d_rr_1w": r1(rr - rr_w) if None not in (rr, rr_w) else None,
                         "bf25": r1((c25 + p25) / 2 - a) if None not in (c25, p25, a) else None,
                         "move": r1(F * a / 100 * math.sqrt(T), 3) if a else None, "move_pct": r1(a * math.sqrt(T), 2) if a else None,
                         "rv20": rv, "vrp": r1(a - rv) if a is not None and rv is not None else None,
                         "cOI": cOI, "pOI": pOI, "d_cOI_1w": (cOI - ww[0]) if ww else None, "d_pOI_1w": (pOI - ww[1]) if ww else None,
                         "cVol": int(g[g.cp == "C"].volume.sum()), "pVol": int(g[g.cp == "P"].volume.sum()), "pc_oi": r1(pOI / cOI) if cOI else None,
                         "call_wall": float(above.loc[above.oi.idxmax(), "strike"]) if len(above) and above.oi.max() > 0 else None,
                         "put_wall": float(below.loc[below.oi.idxmax(), "strike"]) if len(below) and below.oi.max() > 0 else None,
                         "smile": [[float(k), round(float(v), 2)] for k, v in zip(sm.strike, sm.iv) if F * 0.6 < k < F * 1.5],
                         "max_pain": max_pain(g) if cOI + pOI > 0 else None, "gamma_peak": float(gam.idxmax()) if len(gam) and gam.max() > 0 else None})
        big = max([r["cOI"] + r["pOI"] for r in rows] or [0])
        liquid = [r for r in rows if r["cOI"] + r["pOI"] >= max(500, 0.25 * big) and r["atm"] is not None and r["dte"] >= MIN_IV_DTE] or [r for r in rows if r["atm"] is not None]
        if not liquid:
            continue
        front = liquid[0]

        def smile_pts(dt, con):
            gg = d[(d.date == dt) & (d.contract == con)]
            if gg.empty:
                return []
            F_, s = smile(gg)
            s = s[(s.strike > F_ * 0.75) & (s.strike < F_ * 1.3)]
            return [[float(k), round(float(v), 2)] for k, v in zip(s.strike, s.iv)]

        def term(dt):
            out = []
            for con, gg in d[d.date == dt].groupby("contract"):
                if int(gg.dte.iloc[0]) < MIN_IV_DTE:
                    continue
                a = atm_iv(gg)
                if a is not None:
                    out.append({"contract": con, "label": lab(con), "dte": int(gg.dte.iloc[0]), "atm": round(a, 2)})
            return sorted(out, key=lambda x: x["dte"])

        def strike_map(con):
            g = day[day.contract == con]
            F = float(g.F.iloc[0])
            rows_ = []
            for K, kk in g.groupby("strike"):
                if not (F * 0.75 < K < F * 1.3):
                    continue
                c, p = kk[kk.cp == "C"], kk[kk.cp == "P"]
                rows_.append({"K": float(K), "cOI": int(c.oi.sum()), "pOI": int(p.oi.sum()), "cVol": int(c.volume.sum()), "pVol": int(p.volume.sum()),
                              "dc": int(c.oi_change.sum()), "dp": int(p.oi_change.sum()), "gam": round(float((kk.gamma.fillna(0) * kk.oi).sum()), 2)})
            return {"contract": con, "label": lab(con), "F": F, "rows": rows_}

        # IV history: front liquid expiry each day
        ih = []
        for dt in dates:
            x = d[d.date == dt]
            best = None
            for con, gg in sorted(x.groupby("contract"), key=lambda z: z[1].dte.iloc[0]):
                if int(gg.dte.iloc[0]) >= MIN_IV_DTE and gg.oi.sum() >= 500:
                    a = atm_iv(gg)
                    if a is not None:
                        best = [dt.date().isoformat(), round(a, 2), con]
                        break
            if best:
                ih.append(best)
        # positioning on the two most active expiries (by OI) plus the front
        oi_rank = sorted(liquid, key=lambda r: -(r["cOI"] + r["pOI"]))
        fc = list(dict.fromkeys([front["contract"]] + [r["contract"] for r in oi_rank[:2]]))
        top, moves, daily = flow_tables(d, dates, fc, sym)
        txt = read_text(name, UNIT[sym], front, daily, top, moves, wk.date().isoformat() if wk is not None else "")
        out = {"sym": sym, "name": name, "unit": UNIT[sym], "source": "ICE settlements (BMR-Com/softs--options-)", "date": last.date().isoformat(),
               "prev": prev.date().isoformat() if prev is not None else None, "week_ago": wk.date().isoformat() if wk is not None else None,
               "skipped": bad[-5:], "expiries": rows, "front": front["contract"], "term": term(last), "term_week_ago": term(wk) if wk is not None else [],
               "smiles": [{"contract": c["contract"], "label": c["label"], "F": c["F"], "now": smile_pts(last, c["contract"]),
                           "week_ago": smile_pts(wk, c["contract"]) if wk is not None else []} for c in liquid[:2]],
               "strike_maps": [strike_map(c) for c in fc], "read": txt, "flow": {"top": top, "moves": moves, "daily": daily},
               "by_expiry": [expiry_block(d, dates, r["contract"], sym) for r in rows if r["cOI"] + r["pOI"] >= 300],
               "default_exp": front["label"], "insights": insights(d, dates), "min_iv_dte": MIN_IV_DTE,
               "pc_oi_all": r1(day[day.cp == "P"].oi.sum() / max(day[day.cp == "C"].oi.sum(), 1)),
               "pc_vol_all": r1(day[day.cp == "P"].volume.sum() / max(day[day.cp == "C"].volume.sum(), 1)),
               "iv_hist": ih, "iv_hist_days": len(ih),
               "note": "ICE settlement prices and open interest (collected in BMR-Com/softs--options-); implied vols from the settlement file, ATM = out-of-the-money smile interpolated at the futures price."}
        (OUT / f"{sym}.json").write_text(json.dumps(out, default=lambda o: None))
        idx.setdefault("markets", {})[sym] = {"name": name, "date": out["date"], "front": front["label"], "atm": front["atm"], "rv20": front["rv20"], "vrp": front["vrp"], "rr25": front["rr25"]}
        print(sym, out["date"], front["label"], "ATM", front["atm"], "RR", front["rr25"], "| skipped", bad[-3:], "| expiries", len(rows))
    # roll & delivery tracker built in softs--options- (analytics/roll_tracker.py)
    try:
        lp = LOCAL.parent / "web" / "roll.json"
        if lp.exists():
            txt = lp.read_text()
        else:
            import requests
            txt = requests.get(RAW.replace("data/csv/", "data/web/") + "roll.json", timeout=60).text
        json.loads(txt)
        (OUT / "roll.json").write_text(txt)
    except Exception as e:
        print("roll tracker not copied:", e)
    idx["generated"] = date.today().isoformat()
    (OUT / "index.json").write_text(json.dumps(idx))


if __name__ == "__main__":
    main()
