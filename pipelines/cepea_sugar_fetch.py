"""CEPEA/ESALQ crystal sugar indicators -> sugar/data/cepea_sugar.csv (scheduled GitHub Actions job only).

Two series, both R$ and US$ per 50-kg bag as CEPEA publishes them:
  sp_cristal  Indicador do Açúcar Cristal Branco CEPEA/ESALQ - São Paulo (domestic, ex-mill, 7% ICMS)
  santos_fob  Indicador Açúcar Cristal - Santos (FOB) (export)
c_lb = usd_50kg / 110.231 * 100 (US cents per lb).

Same conduct as pipelines/cepea_fetch.py: honest User-Agent, cepea.org.br/robots.txt checked every run with
urllib.robotparser (skip quietly if not allowed), one request to the indicator page per run. With --backfill it also
downloads CEPEA's own full-series files (two requests), which is how the history was built. CEPEA data are CC BY-NC 4.0
(non-commercial use), credited in the file's source column.
New dates are added; a date already held from CEPEA's series file is never overwritten by the page.
"""
import re
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brazil_physical as bp  # noqa: E402
from cepea_fetch import AGENT, allowed, tables, _br  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sugar" / "data" / "cepea_sugar.csv"
PAGE = "https://www.cepea.org.br/br/indicador/acucar.aspx"
SERIES = ["https://www.cepea.org.br/br/indicador/series/acucar.aspx?id=53",
          "https://www.cepea.org.br/br/indicador/series/acucar.aspx?id=308"]
COLS = ["date", "series", "brl_50kg", "usd_50kg", "c_lb", "source"]
BAG_LB = 110.231
SRC_PAGE = "CEPEA/ESALQ indicator page (CC BY-NC 4.0)"
SRC_FILE = "CEPEA/ESALQ series file (CC BY-NC 4.0)"


def which(title):
    t = title.lower()
    if "santos" in t or "fob" in t:
        return "santos_fob"
    if "cristal" in t and ("paulo" in t or "branco" in t):
        return "sp_cristal"
    return None


def _d(x):
    x = str(x).strip()
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", x)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", x)
    return m.group(0) if m else None


def _n(x):
    x = str(x).strip()
    v = _br(x)
    if v is None:
        try:
            v = float(x)
        except ValueError:
            return None
    return v


def price_rows(rows, series, source):
    """Rows of text cells -> records. Columns: date, R$, [var/day, var/month], US$ (page) or date, R$, US$ (file)."""
    out = []
    for r in rows:
        if not r:
            continue
        d = _d(r[0])
        if not d:
            continue
        vals = [c for c in r[1:] if "%" not in str(c)]
        nums = [_n(c) for c in vals]
        nums = [v for v in nums if v is not None]
        if not nums:
            continue
        brl = nums[0]
        usd = nums[1] if len(nums) > 1 else None
        if not (10 < brl < 1000) or (usd is not None and not (3 < usd < 200)):
            continue
        out.append({"date": d, "series": series, "brl_50kg": round(brl, 2),
                    "usd_50kg": None if usd is None else round(usd, 2),
                    "c_lb": None if usd is None else round(usd / BAG_LB * 100, 3), "source": source})
    return out


def get(url):
    r = requests.get(url, headers={"User-Agent": AGENT, "Accept-Language": "pt-BR,en;q=0.8"}, timeout=90)
    print(f"{url}: HTTP {r.status_code}, {len(r.content)} bytes, {r.headers.get('content-type', '')}")
    return r if r.status_code == 200 else None


def page_records():
    r = get(PAGE)
    if r is None:
        return []
    out = []
    for title, rows in tables(r.text):
        s = which(title[-250:])
        if s:
            out += price_rows(rows, s, SRC_PAGE)
    return out


def file_records(url, page):
    r = get(url)
    if r is None:
        return []
    rows = bp.sheet_rows(r.content)
    head = " ".join(" ".join(str(c) for c in x) for x in rows[:12])
    print("  head:", head[:300])
    s = which(head)
    recs = price_rows(rows, s or "unknown", SRC_FILE)
    if not recs:
        print("  no dated price rows; first rows:", rows[:8])
        return []
    if s is None and page:
        # name the file by matching its latest values to the page's tables
        last = max(recs, key=lambda x: x["date"])
        for p in page:
            if p["date"] == last["date"] and abs(p["brl_50kg"] - last["brl_50kg"]) < 0.02:
                s = p["series"]
        for x in recs:
            x["series"] = s or "unknown"
    print(f"  {s}: {len(recs)} rows {min(x['date'] for x in recs)} .. {max(x['date'] for x in recs)}")
    return [x for x in recs if x["series"] != "unknown"]


def main(argv):
    backfill = "--backfill" in argv
    if not allowed(PAGE):
        print("robots.txt does not allow this agent on the CEPEA sugar page; skipped")
        return 0
    page = page_records()
    recs = list(page)
    if backfill:
        for u in SERIES:
            if allowed(u):
                recs += file_records(u, page)
            else:
                print(f"robots.txt does not allow {u}; skipped")
    if not recs:
        print("::warning::CEPEA sugar: nothing parsed; file left as it was")
        return 1 if not backfill else 0
    new = pd.DataFrame(recs, columns=COLS)
    old = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame(columns=COLS)
    allr = pd.concat([old, new], ignore_index=True)
    allr["_r"] = (allr.source != SRC_FILE).astype(int)
    allr = allr.sort_values(["date", "series", "_r"]).drop_duplicates(["date", "series"], keep="first").drop(columns="_r")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    allr.to_csv(OUT, index=False)
    for s, g in allr.groupby("series"):
        t = g.iloc[-1]
        print(f"{s}: {len(g)} rows {g.date.min()} .. {g.date.max()}; latest R${t.brl_50kg} US${t.usd_50kg} = {t.c_lb} c/lb")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
