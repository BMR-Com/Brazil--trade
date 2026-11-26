#!/usr/bin/env python3
"""Support tests in tight markets: flags a long when a selloff brings the active futures contract down to its own
200-day average while the market still looks tight, and turns that into a trade idea with an options version.

Conditions (all four softs):
  - active contract (the desk's front unless it reaches first notice / expiry within 15 business days, then the next)
    at least 8% below its 60-day high
  - close between 3% below and 4% above that contract's own 200-day average (no roll gaps in the average)
  - price above the average on at least 60% of the 120 sessions before (a first test from above, not a downtrend)
Confirmation that has to hold as well:
  - SB: No. 11 within 2.5 c/lb of Brazil hydrous-ethanol parity (sugar/data/sugar.json), i.e. near the level where
        Centre-South mills switch cane to ethanol; front spread shown as context
  - CT: front spread (Dec/Mar/May/Jul, October ignored) in the top 30% of its past year and firmer over 5 sessions
  - KC, CC: no confirming input found; the setup is shown as a watch only, not as a trade
A fired setup stays on the page for 15 business days or until the stop (a close 3% under the 200-day average) is hit.

Public output: data/optsig/support_ideas.json (current reading and idea only).
`python models/support_test.py --backtest` prints the history test to the console and writes nothing.
"""
import json, math, sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from watch_common import ROOT, D, MK, load_px, roll_day, contract_month, label, write_json, rd, BD  # noqa: E402

OUT = "data/optsig/support_ideas.json"
LEAD = 15          # business days before notice/expiry when the next contract becomes the active one
DD_MIN = -0.08     # selloff: at least 8% off the 60-day high
BAND = (-0.03, 0.04)
ABOVE = 0.60
STOP = 0.03        # stop: close 3% under the 200-day average
KEEP = 15          # business days a fired setup stays live
PARITY_MAX = 2.5   # SB: c/lb over ethanol parity
LOT = {"SB": 1120, "KC": 375, "CT": 500, "CC": 10}   # $ per price unit per lot
STEP = {"SB": 0.25, "KC": 2.5, "CT": 1.0, "CC": 50}  # listed option strike steps near the money
CONFIRM = {"SB": "parity", "CT": "spread", "KC": None, "CC": None}


def active_pairs(sym, w, lead=LEAD):
    cs = sorted(w.columns, key=contract_month)
    rolls = {c: roll_day(sym, c) for c in cs}
    idx = w.index
    out = {}
    for i, d in enumerate(idx):
        dl = idx[i + lead] if i + lead < len(idx) else d + lead * BD
        live = [c for c in cs if rolls[c] > dl and not math.isnan(w.at[d, c])]
        if len(live) >= 2:
            out[d] = (live[0], live[1])
    return out


def frame(sym, start=None):
    w = load_px(sym)
    ma = w.rolling(200, min_periods=200).mean()
    hi = w.rolling(60, min_periods=40).max()
    W = w if start is None else w[w.index >= pd.Timestamp(start) - pd.Timedelta(days=120)]
    rows = []
    for d, (a, b) in active_pairs(sym, W).items():
        rows.append({"date": d, "c": a, "n": b, "px": w.at[d, a], "ma": ma.at[d, a], "hi": hi.at[d, a], "sp": w.at[d, a] - w.at[d, b]})
    f = pd.DataFrame(rows).set_index("date")
    f["dd"] = f.px / f.hi - 1
    f["dist"] = f.px / f.ma - 1
    f["sp_pct"] = f.sp / f.px * 100
    f["sp_p1y"] = f.sp_pct.rolling(250, min_periods=150).apply(lambda x: (x[:-1] < x[-1]).mean() * 100, raw=True)
    pos = {d: i for i, d in enumerate(w.index)}
    ch5 = []
    for d, r in f.iterrows():
        i = pos[d]
        d0 = w.index[i - 5] if i >= 5 else None
        ch5.append(np.nan if d0 is None else r.sp - (w.at[d0, r.c] - w.at[d0, r.n]))
    f["sp_chg5"] = ch5
    f["above"] = (f.px > f.ma).astype(float).rolling(120, min_periods=80).mean().shift(10)
    if sym == "SB":
        try:
            P = json.loads((ROOT / "sugar/data/sugar.json").read_text())["parity"]
            par = pd.Series(P["par"], index=pd.to_datetime(P["dates"]), dtype=float).dropna()
            f["parity"] = par.reindex(f.index, method="ffill", limit=7)
        except Exception:
            f["parity"] = np.nan
        f["cushion"] = f.px - f.parity
    return w, f


def base(f):
    return (f.dd <= DD_MIN) & f.dist.between(*BAND) & (f.above >= ABOVE)


def confirm(sym, f):
    k = CONFIRM[sym]
    if k == "parity":
        return f.cushion <= PARITY_MAX
    if k == "spread":
        return (f.sp_p1y >= 70) & (f.sp_chg5 > 0)
    return pd.Series(True, index=f.index)


def ordn(v):
    n = int(round(v))
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def episodes(mask, gap=20):
    ds, last = [], None
    idx = mask.index
    for d in idx[mask.fillna(False).astype(bool)]:
        if last is None or idx.get_loc(d) - idx.get_loc(last) > gap:
            ds.append(d)
        last = d
    return ds


# ───────── options version ─────────
def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def b76(F, K, T, iv, call):
    if T <= 0 or iv <= 0:
        return max(0.0, (F - K) if call else (K - F))
    s = iv * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * s * s) / s
    d2 = d1 - s
    return F * ncdf(d1) - K * ncdf(d2) if call else K * ncdf(-d2) - F * ncdf(-d1)


def options_leg(sym, contract, F, ma):
    """Pick an option month on the signal contract with 40-120 days left; price a call spread when vol is cheap to
    realized, a put spread sale under the 200-day average when it is rich. Settlement vols from data/options/<SYM>.json."""
    try:
        O = json.loads((D / "options" / f"{sym}.json").read_text())
    except Exception:
        return None
    und = f"{label(contract).split()[0].upper()} {contract[-2:]}"
    ex = [e for e in O.get("expiries", []) if e.get("underlying") == und and e.get("smile") and 40 <= (e.get("dte") or 0) <= 120]
    if not ex:
        return None
    e = ex[-1]
    T = e["dte"] / 365.0
    sm = {float(k): float(v) for k, v in e["smile"] if v}
    ks = sorted(sm)
    if not ks:
        return None
    iv = lambda k: sm[min(ks, key=lambda x: abs(x - k))] / 100
    step = STEP[sym]
    rnd = lambda x: round(round(x / step) * step, 2)
    atm = rnd(F)
    mv = F * (e.get("atm") or 25) / 100 * math.sqrt(30 / 365)
    cheap = (e.get("vrp") is not None and e["vrp"] < 0)
    dp = MK[sym][2]
    if cheap:
        k1, k2 = atm, rnd(F + 1.5 * mv)
        cost = b76(F, k1, T, iv(k1), True) - b76(F, k2, T, iv(k2), True)
        txt = f"Buy the {e['label']} {k1:g}/{k2:g} call spread"
        why = f"implied vol {e['atm']:.1f}% is below 20-day realized {e['rv20']:.1f}%, so buying options is the cheaper side"
        return {"structure": txt, "option_month": e["label"], "strikes": [k1, k2], "debit": round(cost, dp + 1), "max_gain": round(k2 - k1 - cost, dp + 1),
                "usd_debit_per_lot": round(cost * LOT[sym]), "why": why, "vol_date": O.get("date"), "dte": e["dte"]}
    k1 = rnd(min(ma, F - 0.5 * mv))
    k2 = rnd(k1 - 1.0 * mv)
    if k2 >= k1:
        k2 = k1 - step
    cr = b76(F, k1, T, iv(k1), False) - b76(F, k2, T, iv(k2), False)
    txt = f"Sell the {e['label']} {k1:g}/{k2:g} put spread"
    why = f"implied vol {e['atm']:.1f}% is at or above 20-day realized {e['rv20']:.1f}%, so selling the downside under support collects the premium"
    return {"structure": txt, "option_month": e["label"], "strikes": [k1, k2], "credit": round(cr, dp + 1), "max_loss": round(k1 - k2 - cr, dp + 1),
            "usd_credit_per_lot": round(cr * LOT[sym]), "why": why, "vol_date": O.get("date"), "dte": e["dte"]}


def live(sym):
    name, unit, dp = MK[sym][0], MK[sym][1], MK[sym][2]
    w, f = frame(sym, start=(pd.Timestamp.now() - pd.Timedelta(days=550)).strftime("%Y-%m-%d"))
    f = f.dropna(subset=["ma"])
    if f.empty:
        return {"name": name, "state": "none", "text": "Not enough history."}
    b, cf = base(f), confirm(sym, f)
    last = f.index[-1]
    r = f.iloc[-1]
    out = {"name": name, "unit": unit, "asof": last.strftime("%Y-%m-%d"), "contract": label(r.c), "ticker": r.c, "px": rd(r.px, dp),
           "ma200": rd(r.ma, dp), "dist_pct": rd(r.dist * 100, 1), "off_60d_high_pct": rd(r.dd * 100, 1),
           "spread": {"label": f"{label(r.c)}/{label(r.n)}", "now": rd(r.sp, dp), "pct_1y": rd(r.sp_p1y, 0), "chg_5d": rd(r.sp_chg5, dp)},
           "confirm_kind": CONFIRM[sym]}
    if sym == "SB":
        out["brazil"] = {"ethanol_parity": rd(r.parity, 2), "cushion": rd(r.cushion, 2)}
    # most recent fire of the full setup within KEEP business days
    idx = f.index
    recent = idx[max(0, len(idx) - KEEP - 1):]
    fired = [d for d in recent if bool(b.get(d, False)) and bool(cf.get(d, False))]
    setup_only = [d for d in recent if bool(b.get(d, False))]
    why = []
    if r.dd <= DD_MIN:
        why.append(f"{label(r.c)} is {abs(r.dd) * 100:.0f}% off its 60-day high")
    why.append(f"200-day average {r.ma:,.{dp}f} ({r.dist * 100:+.1f}% from price)")
    if not math.isnan(r.sp_p1y):
        why.append(f"{out['spread']['label']} spread {r.sp:+.{dp}f} ({ordn(r.sp_p1y)} percentile of the past year, {r.sp_chg5:+.{dp}f} over 5 sessions)")
    if sym == "SB" and not math.isnan(r.cushion):
        why.append(f"No. 11 is {r.cushion:.2f} c/lb over Brazil hydrous-ethanol parity ({r.parity:.2f})")
    if fired:
        d0 = fired[0]
        r0 = f.loc[d0]
        c = r0.c
        stop = r0.ma * (1 - STOP)
        cur = w[c].dropna()
        now = float(cur.iloc[-1])
        hit = bool((cur[cur.index > d0] < stop).any())
        tgt = float(w[c].loc[:d0].tail(60).max())
        state = "stopped" if hit else ("fired" if CONFIRM[sym] else "watch")
        at = {"px": rd(r0.px, dp), "ma200": rd(r0.ma, dp), "spread": rd(r0.sp, dp), "spread_pct_1y": rd(r0.sp_p1y, 0), "spread_chg_5d": rd(r0.sp_chg5, dp)}
        if sym == "SB":
            at["cushion"] = rd(r0.cushion, 2)
        why.insert(0, f"Fired {d0.strftime('%-d %b')}: {label(c)} closed {r0.px:,.{dp}f}, {r0.dist * 100:+.1f}% from its 200-day average {r0.ma:,.{dp}f}"
                   + (f", spread {r0.sp:+.{dp}f} ({ordn(r0.sp_p1y)} pct of the year)" if not math.isnan(r0.sp_p1y) else "")
                   + (f", {r0.cushion:.2f} c/lb over ethanol parity" if sym == "SB" and not math.isnan(r0.cushion) else ""))
        out.update({"state": state, "fired": d0.strftime("%Y-%m-%d"), "at_fire": at,
                    "idea": {"side": "Long", "instrument": f"{label(c)} ({c})", "entry": rd(r0.px, dp), "now": rd(now, dp),
                             "stop": rd(stop, dp), "target": rd(r0.ma + 0.5 * (tgt - r0.ma), dp), "horizon": "4 weeks",
                             "rr": rd((r0.ma + 0.5 * (tgt - r0.ma) - r0.px) / max(r0.px - stop, 1e-9), 1),
                             "options": options_leg(sym, c, now, float(w[c].rolling(200).mean().iloc[-1]))}})
        if CONFIRM[sym] is None:
            out["evidence"] = "Watch only: no confirming input has separated good and bad 200-day tests in this market, so this is not a tested trade."
        else:
            out["evidence"] = "Setup with a confirming filter that has tested better than plain 200-day tests on this desk's history (small sample). Size small; the stop is the 200-day average failing."
    elif setup_only:
        out.update({"state": "unconfirmed", "fired": setup_only[0].strftime("%Y-%m-%d"),
                    "evidence": "Price tested the 200-day average after a selloff, but the confirming input did not hold, so no trade."})
    elif r.dd <= DD_MIN and 0.04 < r.dist <= 0.08 and r.above >= ABOVE:
        out.update({"state": "approaching", "evidence": f"Selloff is nearing the 200-day average ({r.ma:,.{dp}f}); the setup fires on a close within {BAND[1] * 100:.0f}% of it if the confirming input holds."})
    else:
        out["state"] = "none"
    out["why"] = why
    return out


def backtest():
    """Console-only history test (nothing written). Forward returns on the active contract, rolled forward if it
    would reach notice/expiry inside the horizon."""
    for sym in ["SB", "CT", "KC", "CC"]:
        w, f = frame(sym)
        f = f[f.index >= ("2012-03-01" if sym == "SB" else "2005-01-01")].dropna(subset=["ma"])
        idx = w.index
        for lab, m in [("all 200-day tests", base(f)), ("with confirmation", base(f) & confirm(sym, f)), ("without confirmation", base(f) & ~confirm(sym, f))]:
            res = []
            for d in episodes(m):
                r = f.loc[d]
                i = idx.get_loc(d)
                for k in (20,):
                    if i + k >= len(idx):
                        continue
                    c = r.c if roll_day(sym, r.c) > idx[i + k] + 3 * BD else r.n
                    a, z = w.at[d, c], w.at[idx[i + k], c]
                    if a == a and z == z:
                        res.append((d, z / a - 1, (z - a) * LOT[sym]))
            if res:
                rr = np.array([x[1] for x in res]); us = np.array([x[2] for x in res])
                print(f"{sym} {lab:22s} n={len(res):2d} up={100 * (rr > 0).mean():3.0f}% avg={100 * rr.mean():+.1f}% ${us.mean():+,.0f}/lot  dates={[x[0].strftime('%Y-%m') for x in res]}")
            else:
                print(f"{sym} {lab:22s} n=0")


def main():
    if "--backtest" in sys.argv:
        backtest()
        return
    res = {}
    for sym in ["SB", "CT", "KC", "CC"]:
        try:
            res[sym] = live(sym)
            print(sym, res[sym].get("state"), res[sym].get("fired"), res[sym].get("dist_pct"))
        except Exception:
            import traceback
            traceback.print_exc()
    write_json(OUT, {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                     "note": "Support tests in tight markets: a selloff down to the active contract's own 200-day average while the market still looks tight. Research only, not investment advice; option prices are model values from settlement vols, check live prices.",
                     "markets": res})


if __name__ == "__main__":
    main()
