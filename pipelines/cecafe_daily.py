"""Cecafé daily export summary ("Resumo Diário – Exportações Brasileiras de Café").

The public page shows, for the current and the previous month, three tables in 60-kg bags split into arabica,
conilon and soluble: certificates of origin issued (the exporters' registrations), and the same exports by customs
clearance unit and by port of shipment. Each row has the day's movement, the month to date and the previous month.

The page only ever shows the latest day, so every run appends what it sees to data/coffee/cecafe_daily.csv
(column report = Cecafé's "information received up to" date; one row per report date x month x table x unit x column). Run it every business day; history builds from the
first run. Then writes data/coffee/cecafe.json for the desk (current month pace by type, daily path, ports).
"""
import json, re, sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "coffee"
CSV = OUT / "cecafe_daily.csv"
URL = "https://www.cecafe.com.br/dados-estatisticos/exportacoes-brasileiras/resumo-diario/"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
MES = {m: i + 1 for i, m in enumerate(["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"])}
TABLES = ["certificados", "despacho", "embarque"]   # order on the page within each month tab
COLS = ["day", "mtd", "prev"]
TYPES = ["arabica", "conilon", "soluble", "total"]


def num(x):
    x = x.strip().replace(".", "").replace(",", ".")
    try:
        return float(x)
    except ValueError:
        return None


def scrape():
    r = requests.get(URL, headers=H, timeout=60)
    r.raise_for_status()
    s = BeautifulSoup(r.text, "html.parser")
    rows = []
    tabs = s.select("div.tab-content") or [s]
    for tab in tabs:
        txt = tab.get_text(" ", strip=True)
        m = re.search(r"recebidas at[ée]:?\s*(\d{2})/(\d{2})/(\d{4})", txt)
        mm = re.search(r"(" + "|".join(MES) + r")\s+(\d{4})", txt, re.I)
        if not (m and mm):
            continue
        asof = date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        month = f"{mm.group(2)}-{MES[mm.group(1).lower()]:02d}"
        for k, t in enumerate(tab.find_all("table")[:3]):
            for tr in t.find_all("tr"):
                c = [x.get_text(" ", strip=True) for x in tr.find_all(["td", "th"])]
                if len(c) != 13 or num(c[1]) is None:
                    continue
                v = [num(x) for x in c[1:]]
                for j, col in enumerate(COLS):
                    rows.append({"report": asof, "month": month, "table": TABLES[k], "unit": c[0].title(), "col": col,
                                 **{TYPES[q]: v[4 * j + q] for q in range(4)}})
    if not rows:
        raise RuntimeError("no tables parsed: page layout changed?")
    return pd.DataFrame(rows)


def build(df):
    """Desk summary from the stored history."""
    tot = df[(df.table == "certificados") & (df.unit.str.upper().str.startswith("TOTA"))]
    asof = tot.report.max()
    cur = tot[(tot.report == asof)]
    cm = cur.month.max()
    now = cur[(cur.month == cm) & (cur.col == "mtd")].iloc[0]
    prev_full = cur[(cur.month == cm) & (cur.col == "prev")].iloc[0]
    # month-to-date path for each month we have seen (one point per report date)
    path = {}
    for mo, g in tot[tot.col == "mtd"].groupby("month"):
        g = g.drop_duplicates("report", keep="last").sort_values("report")
        path[mo] = {"asof": g.report.tolist(), "day": [int(d[8:]) if d[:7] == mo else None for d in g.report], **{t: g[t].tolist() for t in TYPES}}
    # final month totals: the 'prev' column of the following month (or the last mtd seen)
    finals = {}
    for _, r in tot[tot.col == "prev"].iterrows():
        y, m = map(int, r.month.split("-"))
        pm = f"{y - (m == 1)}-{(m - 2) % 12 + 1:02d}"
        finals[pm] = {t: r[t] for t in TYPES}
    # same point last month: last month's mtd at the same calendar day, when history allows
    same = None
    py, pmn = map(int, cm.split("-"))
    pm = f"{py - (pmn == 1)}-{(pmn - 2) % 12 + 1:02d}"
    if pm in path:
        dnow = int(asof[8:]) if asof[:7] == cm else 31
        P = path[pm]
        idx = [i for i, d in enumerate(P["day"]) if d is not None and d <= dnow]
        if idx:
            i = idx[-1]
            same = {"asof": P["asof"][i], **{t: P[t][i] for t in TYPES}}
    ports = cur[(cur.month == cm) & (cur.col == "mtd") & (cur.table == "embarque") & ~cur.unit.str.upper().str.startswith("TOTA")]
    ports = [{"unit": r.unit, **{t: r[t] for t in TYPES}} for _, r in ports.sort_values("total", ascending=False).iterrows()]
    day = cur[(cur.month == cm) & (cur.col == "day")].iloc[0]
    return {"generated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "asof": asof, "month": cm, "source": URL,
            "measure": "certificates of origin issued (export registrations), 60-kg bags",
            "mtd": {t: now[t] for t in TYPES}, "day": {t: day[t] for t in TYPES}, "prev_month": pm, "prev_month_total": {t: prev_full[t] for t in TYPES},
            "same_point_prev_month": same, "finals": dict(sorted(finals.items())), "path": path, "ports_mtd": ports,
            "history_from": tot.report.min()}


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, float) or hasattr(o, "item"):
        o = o.item() if hasattr(o, "item") else o
        return None if isinstance(o, float) and o != o else o
    return o


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        new = scrape()
        print("cecafe: parsed", len(new), "rows; report date", new.report.max())
    except Exception as e:
        print("cecafe: scrape failed", e)
        new = pd.DataFrame()
    old = pd.read_csv(CSV, dtype={"month": str}) if CSV.exists() else pd.DataFrame()
    df = pd.concat([old, new], ignore_index=True)
    if df.empty:
        return
    df = df.drop_duplicates(["report", "month", "table", "unit", "col"], keep="last").sort_values(["report", "month", "table", "unit", "col"])
    df.to_csv(CSV, index=False)
    J = build(df)
    (OUT / "cecafe.json").write_text(json.dumps(clean(J)))
    print("cecafe:", J["month"], "to", J["asof"], "MTD", J["mtd"])


if __name__ == "__main__":
    sys.exit(main())
