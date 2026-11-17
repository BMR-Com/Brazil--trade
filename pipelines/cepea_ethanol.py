#!/usr/bin/env python3
"""CEPEA/ESALQ hydrous ethanol indicator (public page) -> sugar/data/cepea_hydrous.csv (date, brl_m3, series).

CEPEA often refuses automated requests; when the page cannot be read the file is left as it is, a warning is printed
and the sugar parity falls back to the B3 hydrous ethanol futures (models/sugar_parity.py says which one it used).
"""
import csv, re, sys
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sugar" / "data" / "cepea_hydrous.csv"
URLS = ["https://www.cepea.org.br/br/indicador/etanol.aspx", "https://www.cepea.esalq.usp.br/br/indicador/etanol.aspx"]
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"}


def parse(html):
    """Rows (date, R$/m³) of the first table on the page whose heading text (up to 1,500 characters before it) mentions
    hydrous ethanol (hidratado). Values below 50 are per litre and are converted to per m³."""
    tables = list(re.finditer(r"(?is)<table.*?</table>", html))
    for t in tables:
        before = re.sub(r"(?s)<[^>]+>", " ", html[max(0, t.start() - 1500):t.start()])
        if "idratado" not in before:
            continue
        series = " ".join(before.split())[-140:]
        rows = []
        for tr in re.findall(r"(?is)<tr.*?</tr>", t.group(0)):
            cells = [" ".join(re.sub(r"(?s)<[^>]+>", " ", c).split()) for c in re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", tr)]
            if len(cells) >= 2 and re.fullmatch(r"\d{2}/\d{2}/\d{4}", cells[0]) and re.fullmatch(r"[\d\.,]+", cells[1]):
                x = float(cells[1].replace(".", "").replace(",", "."))
                rows.append((datetime.strptime(cells[0], "%d/%m/%Y").date().isoformat(), round(x * 1000 if x < 50 else x, 2), series))
        if rows:
            return rows
    print(f"CEPEA page: {len(tables)} tables; headings near tables: " + " | ".join(" ".join(re.sub(r'(?s)<[^>]+>', ' ', html[max(0, t.start() - 300):t.start()]).split())[-80:] for t in tables[:6]))
    return []


def main():
    rows, err = [], []
    for u in URLS:
        try:
            r = requests.get(u, headers=UA, timeout=40)
            if r.status_code != 200:
                err.append(f"{u}: HTTP {r.status_code}")
                continue
            rows = parse(r.text)
            if rows:
                break
            err.append(f"{u}: no hydrous table found ({len(r.text)} bytes)")
        except Exception as e:
            err.append(f"{u}: {str(e)[:120]}")
    if not rows:
        print("::warning::CEPEA hydrous ethanol not retrieved; parity uses B3 futures. " + " | ".join(err))
        return 0
    old = {}
    if OUT.exists():
        for r in csv.DictReader(open(OUT)):
            old[r["date"]] = r
    for d, v, s in rows:
        old[d] = {"date": d, "brl_m3": v, "series": s}
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "brl_m3", "series"])
        w.writeheader()
        for k in sorted(old):
            w.writerow(old[k])
    print(f"CEPEA hydrous: {len(rows)} rows, latest {max(rows)[0]} R${max(rows)[1]}/m³ ({rows[0][2]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
