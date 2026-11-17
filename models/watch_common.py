"""Shared helpers for the desk-watch models (what_changed, delivery_desk, alerts, desk_calls, sugar_parity).

Settled prices only: TradingView files carry the evening session of the next trade date, so any bar dated after the
last completed ICE settlement (US Eastern clock) is dropped before anything is computed.
"""
import csv, json, math, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
sys.path.insert(0, str(ROOT / "models"))
from contract_calendar import ice_cotton, ice_sugar, ice_coffee, ice_cocoa, HOL, BD, first_bd, bdays  # noqa: E402

CODES = "FGHJKMNQUVXZ"
MK = {  # sym: name, unit, decimals, listed months used (cotton: October ignored), calendar rule, certs unit
    "CT": ("Cotton", "¢/lb", 2, "HKNZ", ice_cotton),
    "SB": ("Sugar No. 11", "¢/lb", 2, "HKNV", ice_sugar),
    "KC": ("Coffee C", "¢/lb", 2, "HKNUZ", ice_coffee),
    "CC": ("Cocoa", "$/t", 0, "HKNUZ", ice_cocoa),
}
ORDER = ["CT", "SB", "KC", "CC"]

# main crop regions per market for the weather read (ids in data/geo/wx_ensemble.json)
WX_MAIN = {
    "CT": ["us_tx", "br_mt", "br_ba", "in_gj", "au_nsw"],
    "SB": ["br_sp", "br_spw", "br_gos", "br_mgc", "in_sl", "th_kk"],
    "KC": ["br_mg", "br_cer", "br_zm", "br_es", "vn_dl"],
    "CC": ["ci_sb", "ci_dl", "gh_ku"],
}
FROST_REGIONS = ["br_mg", "br_cer", "br_zm", "br_nmg", "br_spc", "br_prc", "br_sp", "br_spw", "br_gos", "br_mgc", "br_ms", "br_prs"]


def J(p, default=None):
    try:
        return json.loads((ROOT / p).read_text())
    except Exception:
        return default


def rd(x, n=2):
    if x is None:
        return None
    try:
        x = float(x)
    except Exception:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return round(x, n)


def now_et():
    # US Eastern without tz database: EDT second Sunday of March to first Sunday of November
    u = datetime.now(timezone.utc)
    y = u.year
    mar = datetime(y, 3, 8, 7, tzinfo=timezone.utc)
    mar += timedelta(days=(6 - mar.weekday()) % 7)
    nov = datetime(y, 11, 1, 6, tzinfo=timezone.utc)
    nov += timedelta(days=(6 - nov.weekday()) % 7)
    off = -4 if mar <= u < nov else -5
    return (u + timedelta(hours=off)).replace(tzinfo=None)


def isbd(d):
    d = pd.Timestamp(d)
    return d.dayofweek < 5 and d not in HOL


def last_settled():
    """Last ICE softs session that has settled (softs settle by about 14:30 ET; 15:30 gives the data runs time)."""
    t = now_et()
    d = pd.Timestamp(t.date())
    if not (isbd(d) and t.hour * 60 + t.minute >= 15 * 60 + 30):
        d = d - BD
    while not isbd(d):
        d = d - pd.Timedelta(days=1)
    return d


def bd_between(a, b):
    """Business days from a (exclusive) to b (inclusive); negative if b < a."""
    a, b = pd.Timestamp(a), pd.Timestamp(b)
    if b >= a:
        return len(bdays(a, b)) - 1
    return -(len(bdays(b, a)) - 1)


def contract_month(c):
    n = len(c) - 5
    return pd.Period(f"{c[-4:]}-{CODES.index(c[n]) + 1:02d}", "M")


def rule_dates(sym, c):
    r = MK[sym][4](contract_month(c))
    return {k: (v if v is None else pd.Timestamp(v)) for k, v in r.items()}


def roll_day(sym, c):
    """Day the contract stops being the 'front' on this desk: first notice (cotton, coffee, cocoa) or expiry (sugar)."""
    r = rule_dates(sym, c)
    return r["fnd"] if r.get("fnd") is not None else r["ltd"]


def load_px(sym, cutoff=None):
    """Settlement matrix date x contract (only the months the desk uses), bars after the last settlement dropped."""
    f = pd.read_csv(D / "contracts" / f"{sym}.csv", usecols=["contract", "date", "close"])
    f["date"] = pd.to_datetime(f["date"])
    f = f[f.contract.str[len(sym)].isin(list(MK[sym][3]))]
    cutoff = cutoff or last_settled()
    f = f[(f.date <= cutoff) & (f.close > 0)]
    w = f.pivot_table(index="date", columns="contract", values="close", aggfunc="last").sort_index()
    w = w[w.index.dayofweek < 5]
    return w


def chain(sym, w):
    """For each date: front (first contract whose roll day is after the date) and next listed contract."""
    cs = sorted(w.columns, key=lambda c: contract_month(c))
    rolls = {c: roll_day(sym, c) for c in cs}
    out = {}
    for d in w.index:
        live = [c for c in cs if rolls[c] > d and not math.isnan(w.at[d, c])]
        if len(live) >= 1:
            out[d] = (live[0], live[1] if len(live) > 1 else None)
    return out


def front_series(sym, w, ch=None):
    """Front price, its same-contract 1-day and 5-day changes, front-next spread and its same-pair changes."""
    ch = ch or chain(sym, w)
    idx = list(ch.keys())
    rows = []
    for i, d in enumerate(idx):
        f, n = ch[d]
        r = {"date": d, "front": f, "next": n, "px": w.at[d, f], "sp": (w.at[d, f] - w.at[d, n]) if n else np.nan}
        for k, lag in (("1", 1), ("5", 5)):
            if i - lag >= 0:
                d0 = idx[i - lag]
                p0 = w.at[d0, f] if f in w.columns else np.nan
                r["dpx" + k] = r["px"] - p0
                s0 = (w.at[d0, f] - w.at[d0, n]) if n else np.nan
                r["dsp" + k] = r["sp"] - s0
            else:
                r["dpx" + k] = r["dsp" + k] = np.nan
        rows.append(r)
    return pd.DataFrame(rows).set_index("date")


def p80(series, q=0.8):
    s = pd.Series(series).dropna().abs()
    return float(s.quantile(q)) if len(s) >= 20 else None


def fmt(v, d=2, sign=False, unit=""):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–"
    s = f"{v:+,.{d}f}" if sign else f"{v:,.{d}f}"
    return s.replace("-", "−") + (f" {unit}" if unit else "")


def label(c):
    return f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][CODES.index(c[-5])]} {c[-2:]}"


def index_roll_windows(sym, c):
    """GSCI rolls on the 5th-9th and BCOM on the 6th-10th business day of the month before the delivery month
    (sugar: the month before expiry month for the March contract = February, i.e. the month of expiry)."""
    m = contract_month(c)
    roll_m = (m - 1)
    days = bdays(roll_m.start_time, roll_m.end_time.normalize())
    return {"gsci": [str(days[4].date()), str(days[8].date())], "bcom": [str(days[5].date()), str(days[9].date())]}


def cotton_oncall(cache=D / "watch" / "oncall_ct.csv"):
    """CFTC cotton on-call by contract month (BMR-Com/cotton-on-call); refreshed from GitHub, cached in the repo."""
    url = "https://raw.githubusercontent.com/BMR-Com/cotton-on-call/main/data/cotton_oncall.csv"
    df = None
    try:
        import requests
        r = requests.get(url, timeout=40)
        if r.ok and "Unfixed Call Sales" in r.text[:400]:
            from io import StringIO
            df = pd.read_csv(StringIO(r.text))
            df["Report Date"] = pd.to_datetime(df["Report Date"], format="%m/%d/%Y", errors="coerce")
            keep = df[df["Report Date"] >= df["Report Date"].max() - pd.Timedelta(days=4 * 366)]
            cache.parent.mkdir(parents=True, exist_ok=True)
            keep.to_csv(cache, index=False)
            df = keep
    except Exception as e:  # offline: use the cache
        print("on-call fetch failed:", str(e)[:120])
    if df is None and cache.exists():
        df = pd.read_csv(cache, parse_dates=["Report Date"])
    return df


def oncall_old_crop(df):
    """Weekly old-crop totals (Mar, May, Jul, Dec of the current marketing year; October ignored)."""
    if df is None:
        return None
    x = df[(df["Old/New"] == "old") & (df["Month"].isin([3, 5, 7, 12]))].copy()
    g = x.groupby("Report Date")[["Unfixed Call Sales", "Unfixed Call Purchases"]].sum().sort_index()
    g.columns = ["sales", "purchases"]
    return g


def wx_label(r):
    """Consensus of the two ECMWF ensembles; ECMWF ENS alone (same 60% rule) where AIFS is missing."""
    if r.get("consensus"):
        return r["consensus"], "ECMWF ENS + AIFS"
    e = (r.get("next15") or {}).get("ecmwf_ens") or {}
    if "p_dry" not in e:
        return None, None
    if e["p_dry"] >= .6:
        return "dry", "ECMWF ENS only"
    if e["p_wet"] >= .6:
        return "wet", "ECMWF ENS only"
    return "near normal", "ECMWF ENS only"


def write_json(rel, obj):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=lambda o: None if (isinstance(o, float) and math.isnan(o)) else str(o)))
