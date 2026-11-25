"""India 2026/27 import scenarios (Sugar > India): history, market-implied read, scenario matrices, TRQ use to 31 Mar 2027.

Inputs
  data/sugar/manual/india_stock_history.csv   season balances 2000/01 on (opening, production, imports raw/white, consumption,
                                              exports, closing) and what followed the low-stock seasons
  data/sugar/manual/india_balance_inputs.csv  opening stock, consumption range, exports, TRQ size and use
  sugar/data/prices_contracts.csv             ICE No. 11 settlements (front contract, latest final settle)
  data/markets/closes.csv                     USD/INR (Yahoo INR=X)
  data/sugar/india_prices.csv                 ChiniMandi daily ex-mill quotes (Maharashtra S/30, Uttar Pradesh M/30)
build(proj) -> dict for world.json['india']['crush']['imports']; outputs and variable names only.
"""
import math
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MAN = ROOT / "data" / "sugar" / "manual"
LB_T = 22.0462
MCODE = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6, "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}

# desk settings (not shown on the page)
HURDLE = {"low": 1150, "mid": 1350, "high": 1550}      # Rs/qtl between landed raws at zero duty and ex-mill
BAND = 1000                                             # Rs/qtl over which remaining TRQ use goes 0 -> 100%
ELAST = 0.15
TRIGGER = 5800                                          # Rs/qtl Maharashtra S/30 at which the quota was opened (Aug 2026)
FLOOR = 1.0                                             # months
MONSOON = {"good": 1.25, "normal": 1.75, "poor": 2.25}  # end-Sep-2027 months the government accepts
NY_LEVELS = [14, 17, 20, 23]
CUTOFF = pd.Timestamp("2027-02-15")                     # last contracting date for raws to land by 31 Mar 2027


def rd(v, n=1):
    return None if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else round(float(v), n)


# ------------------------------------------------------------------ live inputs
def front_sb():
    p = pd.read_csv(ROOT / "sugar/data/prices_contracts.csv")
    p = p[p.symbol.str.match(r"^SB[FGHJKMNQUVXZ]\d{4}$")]
    last = p.date.max()
    live = p[p.date == last].copy()
    live["key"] = live.symbol.str[3:].astype(int) * 100 + live.symbol.str[2].map(MCODE)
    r = live.sort_values("key").iloc[0]
    return float(r.close), r.symbol, r.date


def usd_inr():
    c = pd.read_csv(ROOT / "data/markets/closes.csv", index_col=0, parse_dates=True)["INR=X"].dropna()
    c = c[(c > 40) & (c < 200)]
    return float(c.iloc[-1]), str(c.index[-1].date())


def domestic():
    q = pd.read_csv(ROOT / "data/sugar/india_prices.csv", parse_dates=["date"])
    q["mid"] = (q.lo + q.hi) / 2
    out = {}
    for k, st, g in (("mh", "Maharashtra", "S/30"), ("up", "Uttar Pradesh", "M/30")):
        s = q[(q.state == st) & (q.grade == g)].groupby("date").mid.mean().sort_index()
        if not len(s):
            continue
        d = s.index[-1]
        ago = lambda days: float(s.loc[:d - pd.Timedelta(days=days)].iloc[-1]) if len(s.loc[:d - pd.Timedelta(days=days)]) else None
        hi12 = s.loc[d - pd.Timedelta(days=365):]
        out[k] = {"label": f"{st} {g}", "value": rd(s.iloc[-1], 0), "date": str(d.date()), "w4": rd(ago(28), 0), "w12": rd(ago(84), 0),
                  "peak": rd(hi12.max(), 0), "peak_date": str(hi12.idxmax().date()), "low": rd(hi12.min(), 0), "low_date": str(hi12.idxmin().date()),
                  "url": q[(q.state == st) & (q.date == d)].url.iloc[0]}
    return out


# ------------------------------------------------------------------ history
def history():
    H = pd.read_csv(MAN / "india_stock_history.csv", dtype={"season": str})
    H["months"] = H.closing / H.consumption * 12
    m = H.months
    stress = H[H.months < 2.5]
    stats = {"min_months": rd(m.min(), 2), "min_months_season": H.loc[m.idxmin(), "season"],
             "min_closing": rd(H.closing.min()), "min_closing_season": H.loc[H.closing.idxmin(), "season"],
             "q1_months": rd(m.quantile(0.25), 2), "median_months": rd(m.median(), 2), "stress_median_months": rd(stress.months.median(), 2),
             "n": len(H), "first": H.season.iloc[0], "last": H.season.iloc[-1],
             "max_imports": rd(H.imports.max()), "max_imports_season": H.loc[H.imports.idxmax(), "season"]}
    rows = [{"season": r.season, "closing": rd(r.closing), "months": rd(r.months, 1), "imports": rd(r.imports), "raw": rd(r.raw_imports), "white": rd(r.white_imports),
             "production": rd(r.production), "consumption": rd(r.consumption), "next": r.next if isinstance(r.next, str) else "",
             "rank_months": int((m < r.months).sum()) + 1} for r in H.itertuples()]
    return H, stats, rows


# ------------------------------------------------------------------ scenario cell
def parity(ny, inr):
    return ny * LB_T * inr / 10                     # Rs/qtl, zero duty, before freight and refining


def use_share(gap, h):
    return float(np.clip((gap - (h - BAND / 2)) / BAND, 0, 1))


def cell(P, months, ny, ctx, h=None):
    """Economic / likely imports for one case: likely tonnage, requirement before any market response, part beyond the
    duty-free quota, and the domestic price at which that tonnage comes in."""
    h = h or HURDLE["mid"]
    O, C, X, inr, D0, left, cap = ctx["O"], ctx["C"], ctx["X"], ctx["inr"], ctx["D0"], ctx["left"], ctx["cap"]
    par = parity(ny, inr)
    d_pay = par + h
    need = lambda d: C * (1 - ELAST * max(0.0, d - D0) / D0)
    req = C * (1 + months / 12) + X - O - P
    arb = left * use_share(D0 - par, h) * ctx["tf"]
    c2 = need(d_pay)
    req2 = c2 * (1 + months / 12) + X - O - P
    if req2 <= left:
        likely, d_at = max(req2, arb), (d_pay if req2 > arb else D0)
    else:                                   # beyond the quota needs a policy step, which needs prices up first
        d_at = max(d_pay, TRIGGER)
        c2 = need(d_at)
        req3 = c2 * (1 + months / 12) + X - O - P
        likely = max(left, req3)
        if req3 <= left:
            d_at = max(d_pay, D0)
    likely = float(np.clip(likely, 0, cap))
    return {"likely": rd(likely), "requirement": rd(req), "beyond_trq": rd(max(0.0, likely - left)), "domestic_needed": rd(max(d_at, D0), 0),
            "pays_now": bool(D0 >= d_pay), "closing_months": rd(12 * (O + P + likely - c2 - X) / c2, 1)}


# ------------------------------------------------------------------ public output
def build(proj):
    if not proj:
        return None
    B = pd.read_csv(MAN / "india_balance_inputs.csv").set_index("item")
    g = lambda k, c="mid": float(B.loc[k, c])
    H, st, hist_rows = history()
    ny, sym, ny_date = front_sb()
    inr, inr_date = usd_inr()
    dom = domestic()
    D0 = dom["mh"]["value"]
    quota, used = g("trq_quota"), g("trq_used")
    left = quota - used
    today = pd.Timestamp(date.today())
    tf = float(np.clip((CUTOFF - today).days / 60, 0, 1))
    ctx = {"O": g("opening_stock"), "C": g("consumption"), "X": g("exports"), "inr": inr, "D0": D0, "left": left, "cap": st["max_imports"], "tf": tf}
    crops = [("low", "Desk low", proj["low"]), ("mid", "Desk mid", proj["mid"]), ("isma", "ISMA", proj["isma"]), ("high", "Desk high", proj["high"])]
    crops = [c for c in crops if c[2]]

    par = parity(ny, inr)
    gap = D0 - par
    be = (D0 - HURDLE["mid"]) * 10 / inr / LB_T
    be_lo, be_hi = (D0 - HURDLE["high"]) * 10 / inr / LB_T, (D0 - HURDLE["low"]) * 10 / inr / LB_T
    R = pd.read_csv(MAN / "india.csv", dtype=str).fillna("")
    dv = [float(r.value) for r in R.itertuples() if r.item.startswith("Normal import duty")]
    duty = dv[0] if dv else 100.0
    ctx["duty"] = duty
    full_duty = parity(ny, inr) * (1 + duty / 100)
    W5 = None
    try:
        w = pd.read_csv(ROOT / "sugar/data/prices_contracts.csv")
        w = w[w.symbol.str.match(r"^WH\d{4}$|^W[FGHJKMNQUVXZ]\d{4}$")]
        if len(w):
            lw = w[w.date == w.date.max()].copy()
            lw["key"] = lw.symbol.str[-4:].astype(int) * 100 + lw.symbol.str[-5].map(MCODE)
            W5 = float(lw.sort_values("key").close.iloc[0])
    except Exception:
        pass
    white_full = W5 * inr * (1 + duty / 100) / 10 if W5 else None

    # TRQ use by 31 Mar 2027
    trq = {k: rd(min(quota, used + left * use_share(gap, HURDLE[h]) * tf)) for k, h in (("low", "high"), ("likely", "mid"), ("high", "low"))}

    # matrices
    cur = round(ny, 2)
    mon = [{"crop": lab, "production": rd(P), "cells": {m: cell(P, MONSOON[m], ny, ctx) for m in MONSOON}} for k, lab, P in crops]
    nys = sorted(set(NY_LEVELS + [cur]))
    nyt = [{"crop": lab, "production": rd(P), "cells": [dict(cell(P, MONSOON["normal"], x, ctx), ny=x) for x in nys]} for k, lab, P in crops]
    ny_rows = [{"ny": x, "current": x == cur, "raw_trq": rd(parity(x, inr), 0), "raw_full_duty": rd(parity(x, inr) * (1 + duty / 100), 0),
                "gap": rd(D0 - parity(x, inr), 0), "pays": D0 - parity(x, inr) >= HURDLE["mid"],
                "domestic_needed": rd(parity(x, inr) + HURDLE["mid"], 0)} for x in nys]
    levels = [("Pre-crush floor", FLOOR, None), (f"Historical minimum ({st['min_months_season']})", st["min_months"], None),
              ("Median of low-stock seasons", st["stress_median_months"], None), ("2.5-month norm", 2.5, None),
              (f"Low quartile {st['first']}–{st['last']}", st["q1_months"], None), (f"Median {st['first']}–{st['last']}", st["median_months"], None)]
    levels = sorted(levels, key=lambda x: x[1])
    stk = [{"crop": lab, "production": rd(P), "cells": [cell(P, m, ny, ctx) for _, m, _ in levels]} for k, lab, P in crops]
    stock_cols = [{"label": l, "months": rd(m, 2), "lakh_t": rd(ctx["C"] * m / 12)} for l, m, _ in levels]

    base = next(r for r in mon if r["crop"] == "ISMA") if any(r["crop"] == "ISMA" for r in mon) else mon[1]
    midr = next(r for r in mon if r["crop"] == "Desk mid")
    lk, lk_mid = base["cells"]["normal"], midr["cells"]["normal"]
    norm_req = cell(base["production"], 2.5, ny, ctx)["requirement"]
    norm_req_mid = cell(midr["production"], 2.5, ny, ctx)["requirement"]
    rng = [c["likely"] for r in mon if r["crop"] in ("Desk mid", "ISMA") for c in r["cells"].values()]

    # market-implied read
    close_trq = lambda P, C: ctx["O"] + P + (trq["likely"] - used) - C - ctx["X"]
    Pi = proj["isma"] or proj["mid"]
    c_ok = (ctx["O"] + Pi + (trq["likely"] - used) - ctx["X"]) / (1 + MONSOON["good"] / 12)
    mh, up = dom["mh"], dom.get("up")
    trend = (mh["value"] - mh["w4"]) if mh.get("w4") else None
    implied = {
        "domestic": mh, "domestic_up": up, "trend_4w": rd(trend, 0), "trend_4w_pct": rd(100 * trend / mh["w4"], 1) if trend is not None else None,
        "vs_12w_pct": rd(100 * (mh["value"] / mh["w12"] - 1), 1) if mh.get("w12") else None,
        "ny": cur, "ny_contract": sym, "ny_date": ny_date, "inr": rd(inr, 2), "inr_date": inr_date,
        "raw_trq": rd(par, 0), "gap": rd(gap, 0), "raw_full_duty": rd(full_duty, 0), "duty_pct": duty, "white_full_duty": rd(white_full, 0) if white_full else None,
        "breakeven_ny": rd(be, 1), "breakeven_ny_range": [rd(be_lo, 1), rd(be_hi, 1)],
        "trq_used": used, "trq_used_date": B.loc["trq_used", "as_of"], "trq_quota": quota,
        "closing_trq_only_isma": rd(close_trq(Pi, ctx["C"])), "closing_trq_only_isma_months": rd(12 * close_trq(Pi, ctx["C"]) / ctx["C"], 1),
        "closing_trq_only_mid": rd(close_trq(proj["mid"], ctx["C"])), "closing_trq_only_mid_months": rd(12 * close_trq(proj["mid"], ctx["C"]) / ctx["C"], 1),
        "consumption_ceiling_good_monsoon": rd(c_ok), "consumption": ctx["C"], "consumption_range": [g("consumption", "low"), g("consumption", "high")],
        "opening": ctx["O"]}
    pays = gap >= HURDLE["mid"]
    sig = "rising" if trend and trend > 0.02 * mh["w4"] else "easing" if trend and trend < -0.02 * mh["w4"] else "flat"
    implied["read"] = (
        f"Domestic ex-mill ({mh['label']}) is Rs {mh['value']:,.0f}/qtl, {sig} over four weeks ({implied['trend_4w_pct']:+.1f}%) and Rs {mh['peak'] - mh['value']:,.0f} below the {mh['peak_date'][:7]} peak; "
        f"it sits Rs {gap:,.0f}/qtl over landed raws at zero duty, {'just enough' if pays else 'not enough'} to cover freight, refining and margin, so TRQ imports pay only with No. 11 below about {be:.1f}¢ (current {cur:.2f}¢). "
        f"With {used:g} of {quota:g} lakh t of the quota used by {B.loc['trq_used', 'as_of']} and part of it re-offered, the market is pricing a gap that the quota and a stock run-down can cover, not a 50 lakh t shortage. "
        f"If only the likely TRQ tonnage arrives, ISMA's crop and {ctx['C']:g} lakh t of consumption end September 2027 at about {implied['closing_trq_only_isma']:.0f} lakh t ({implied['closing_trq_only_isma_months']:.1f} months): "
        f"tight, so the test comes in June–September, when the crush is over and prices, not the balance, decide whether the quota is widened.")

    by_mar = max(0.0, trq["likely"] - used)
    ext = max(0.0, min(lk["likely"], left) - by_mar)
    beyond = max(0.0, lk["likely"] - left)
    most = (f"Most likely: about {lk['likely']:.0f} lakh t of imports in 2026/27 (ISMA crop, normal 2027 monsoon, No. 11 at {cur:.2f}¢): about {by_mar:.0f} lakh t more under the duty-free quota by 31 March"
            + (f", about {ext:.0f} more if the quota is extended again (it has been twice)" if ext >= 0.5 else "")
            + (f" and about {beyond:.0f} beyond the 10 lakh t only if summer prices rise to the level that opened the quota (about Rs {TRIGGER:,}/qtl)" if beyond >= 0.5 else "")
            + f". On the desk's lower mid crop, about {lk_mid['likely']:.0f} lakh t. Range across monsoon cases for the ISMA and desk-mid crops: {min(rng):.0f} to {max(rng):.0f} lakh t. "
            f"Reaching the 2.5-month norm would need {max(norm_req, 0):.0f} lakh t ({max(norm_req_mid, 0):.0f} on the desk mid crop), which the market is not paying for.")
    parts = {"by_march": rd(by_mar), "extension": rd(ext), "beyond_quota": rd(beyond)}

    hist_show = [r for r in hist_rows if r["months"] < 2.5 or r["imports"] and r["imports"] >= 4 or r["season"] >= "2021/22"]
    return {"as_of": str(today.date()), "most_likely": most, "likely": lk["likely"], "likely_mid_crop": lk_mid["likely"], "range": [rd(min(rng)), rd(max(rng))],
            "parts": parts, "norm_requirement": rd(max(norm_req, 0)), "norm_requirement_mid": rd(max(norm_req_mid, 0)),
            "trq": dict(trq, used=used, quota=quota, deadline="2027-03-31"), "implied": implied,
            "history": {"rows": hist_show, "stats": st, "source": "ChiniMandi statistics (ISMA, reconciled with government data); Lok Sabha answers for the raw/white split; ISMA for 2025/26",
                        "url": "https://www.chinimandi.com/statistics/statement-showing-sugar-stocks-production-consumption-export-of-sugar/"},
            "monsoon": {"targets": MONSOON, "rows": mon}, "ny": {"rows": nyt, "levels": ny_rows, "monsoon": "normal"},
            "stock": {"cols": stock_cols, "rows": stk},
            "variables": ["Opening stock 1 Oct 2026 (ISMA) and consumption range (ISMA, government, last season's balance)",
                          "2026/27 production: desk projection low / mid / high and ISMA's first estimate",
                          "End-September 2027 stock by 2027 monsoon outcome, and the stock history 2000/01 on",
                          f"ICE No. 11 front contract ({sym}, latest settlement), USD/INR (Yahoo), Maharashtra S/30 ex-mill (ChiniMandi)",
                          "Duty-free raw TRQ size, use to date and deadline (DGFT); basic duty outside the quota",
                          "Highest imports in any season since 2000/01 as the ceiling"]}


if __name__ == "__main__":
    import json, india_crush
    b = india_crush.build()
    print(json.dumps(build(b["projection"]), indent=1, default=str)[:6000])
