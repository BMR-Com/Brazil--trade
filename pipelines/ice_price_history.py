"""ICE daily contract history for the softs (first five contracts, settle/high/low/OI/volume), kept continuous.

Two inputs, both through the ICE drop box (pipelines/ice_inbox.py):
  * ICE "<Market> Historical Prices" .xls (daily statistics for the first five contracts since 1994/1999, with
    totals and, where ICE filled them, average implied vol and 30-day historical vol) - re-uploads replace overlapping
    dates, so the newest file always wins.
  * ICE "Futures Daily Market Report" PDFs (one per market per day) - each adds that day's settle, high, low, volume
    and OI for every listed contract, and the market totals.

Out, per market (cotton, coffee, sugar, cocoa, sugar16):
  data/<market>/ice_daily_contracts.csv  date, contract (YYYYMM), high, low, close (= settle), oi, volume, source
  data/<market>/ice_daily_totals.csv     date, total_oi, total_volume, avg_iv, hv30, hv30_source
Cotton October contracts are left out (low volume and OI; the desk ignores October).
hv30 after ICE's own series ends is the 30-day close-to-close vol of the nearby contract (same contract returns only),
annualised, as a fraction (ICE's own column is a fraction too).
"""
import io, re, sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
DIRS = {"CT": "cotton", "KC": "coffee", "SB": "sugar", "CC": "cocoa", "SE": "sugar16"}
TITLES = [("SUGAR NO.16", "SE"), ("SUGAR NO.11", "SB"), ("COFFEE 'C' CONTRACT", "KC"), ("COCOA CONTRACT", "CC"), ("COTTON CONTRACT", "CT")]
CCOLS = ["date", "contract", "high", "low", "close", "oi", "volume", "source"]
TCOLS = ["date", "total_oi", "total_volume", "avg_iv", "hv30", "hv30_source"]
MON = {m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def paths(sym):
    d = D / DIRS[sym]
    return d / "ice_daily_contracts.csv", d / "ice_daily_totals.csv"


def num(s):
    return pd.to_numeric(pd.Series(s).astype(str).str.replace(",", "").str.replace("%", "").str.strip(), errors="coerce")


def detect_xls(first_cell):
    t = str(first_cell).upper()
    if "THE FOLLOWING IS DAILY" not in t:
        return None
    return next((s for k, s in TITLES if k in t), None)


def parse_xls(data):
    d = pd.read_excel(io.BytesIO(data), header=None)
    sym = detect_xls(d.iloc[0, 0])
    if not sym:
        raise ValueError("not an ICE historical prices workbook")
    hdr = [str(v).upper() for v in d.iloc[4]]
    lab = [str(v).upper() for v in d.iloc[3]]
    starts = [i for i, v in enumerate(hdr) if v.startswith("CONTRACT")]
    iv = next((i for i, v in enumerate(lab) if "IMPLIED" in v), None)
    hv = next((i for i, v in enumerate(lab) if "HISTORICAL" in v), None)
    body = d.iloc[5:]
    date = pd.to_datetime(body[0], errors="coerce")
    parts = []
    for s in starts:
        parts.append(pd.DataFrame({"date": date.values, "contract": num(body[s]).values, "high": num(body[s + 1]).values,
                                   "low": num(body[s + 2]).values, "close": num(body[s + 3]).values,
                                   "oi": num(body[s + 4]).values, "volume": num(body[s + 5]).values}))
    c = pd.concat(parts).dropna(subset=["date", "contract", "close"])
    c["contract"] = c.contract.astype(int)
    c["source"] = "ice_history_xls"
    tot = pd.DataFrame({"date": date.values, "total_oi": num(body[2]).values, "total_volume": num(body[3]).values,
                        "avg_iv": num(body[iv]).values if iv is not None else np.nan,
                        "hv30": num(body[hv]).values if hv is not None else np.nan}).dropna(subset=["date"])
    for k in ("avg_iv", "hv30"):
        tot.loc[tot[k] == 0, k] = np.nan
    tot["hv30_source"] = np.where(tot.hv30.notna(), "ice", "")
    return sym, c, tot


def parse_futures_pdf_text(text, sym, d):
    """Rows of an ICE Futures Daily Market Report: trailing nine numbers are settle, change, volume, OI, OI change,
    EFP, EFS, block, spread volume; the four before (when traded) are open, high, low, close."""
    rows = []
    for m in re.finditer(rf"^\s*{sym}\s+([A-Z][a-z]{{2}})-(\d{{2}})\s+(.*)$", text, flags=re.M):
        nums = [float(x.replace(",", "")) for x in re.findall(r"-?[\d,]+\.?\d*", m.group(3))]
        if len(nums) < 9:
            continue
        tail, head = nums[-9:], nums[:-9]
        hi, lo = (head[1], head[2]) if len(head) >= 4 else (np.nan, np.nan)
        rows.append({"date": pd.Timestamp(d), "contract": (2000 + int(m.group(2))) * 100 + MON[m.group(1)], "high": hi, "low": lo,
                     "close": tail[0], "oi": tail[3], "volume": tail[2], "source": "ice_daily_report"})
    t = re.search(rf"Totals for {sym}:\s+([\d,]+)\s+([\d,]+)", text)
    tot = pd.DataFrame([{"date": pd.Timestamp(d), "total_volume": float(t.group(1).replace(",", "")),
                         "total_oi": float(t.group(2).replace(",", "")), "avg_iv": np.nan, "hv30": np.nan, "hv30_source": ""}]) if t else None
    return pd.DataFrame(rows), tot


def _merge(path, new, keys, cols):
    path.parent.mkdir(parents=True, exist_ok=True)
    new = new.copy()
    new["date"] = pd.to_datetime(new["date"]).dt.strftime("%Y-%m-%d")
    if path.exists():
        old = pd.read_csv(path, dtype={"date": str})
        k_new = set(map(tuple, new[keys].astype(str).values))
        old = old[[tuple(x) not in k_new for x in old[keys].astype(str).values]]
        if "contract" in keys:   # a report date in the new rows replaces that whole date
            old = old[~old.date.isin(set(new.date))]
        new = pd.concat([old, new], ignore_index=True)
    for c in cols:
        if c not in new:
            new[c] = np.nan
    return new[cols].sort_values(keys).reset_index(drop=True)


def fill_hv(c, t):
    """30-day close-to-close vol of the nearby contract where ICE's own series is blank."""
    c = c.copy()
    c["date"] = pd.to_datetime(c.date)
    c = c[((c.volume.fillna(0) > 0) | (c.oi.fillna(0) > 0)) & (c.close > 0)]
    near = c.sort_values(["date", "contract"]).groupby("date").first()
    r = np.log(near.close).diff()
    r[near.contract != near.contract.shift()] = np.nan
    r[pd.Series(near.index, index=near.index).diff().dt.days > 5] = np.nan   # no return across a gap in the data
    hv = (r.rolling(30, min_periods=25).std() * np.sqrt(252)).rename("hv_calc")
    t = t.copy()
    t["date"] = pd.to_datetime(t.date)
    t = t.merge(hv, left_on="date", right_index=True, how="left")
    miss = t.hv30.isna() & t.hv_calc.notna()
    t.loc[miss, "hv30"] = t.loc[miss, "hv_calc"].round(4)
    t.loc[miss, "hv30_source"] = "calc_nearby_30d"
    t["date"] = t.date.dt.strftime("%Y-%m-%d")
    return t.drop(columns="hv_calc")


def store(sym, c, t):
    if sym == "CT":
        c = c[c.contract % 100 != 10]
    pc, pt = paths(sym)
    cc = _merge(pc, c, ["date", "contract"], CCOLS)
    cc["contract"] = cc.contract.astype(int)
    tt = _merge(pt, t, ["date"], TCOLS) if t is not None else (pd.read_csv(pt) if pt.exists() else pd.DataFrame(columns=TCOLS))
    tt = fill_hv(cc, tt)
    cc.to_csv(pc, index=False)
    tt[TCOLS].to_csv(pt, index=False)
    return cc, tt


def add_xls(data):
    sym, c, t = parse_xls(data)
    cc, tt = store(sym, c, t)
    return sym, f"{DIRS[sym]}: {len(c):,} contract-days {c.date.min():%Y-%m-%d} to {c.date.max():%Y-%m-%d}; history now {cc.date.min()} to {cc.date.max()}"


def add_futures_pdf(text, sym, d):
    if sym not in DIRS:
        return None
    c, t = parse_futures_pdf_text(text, sym, d)
    if c.empty:
        return None
    store(sym, c, t)
    return f"{len(c)} contracts added to data/{DIRS[sym]}/ice_daily_contracts.csv"


if __name__ == "__main__":   # python pipelines/ice_price_history.py <file.xls> ...
    for f in sys.argv[1:]:
        print(add_xls(Path(f).read_bytes())[1])
