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
    """Rows of the first table whose heading mentions hydrous ethanol (hidratado); values in R$/m³."""
    out = []
    for m in re.finditer(r"(?is)(<h[1-6][^>]*>|<caption[^>]*>|<div class=\"imagenet-titulo[^\"]*\"[^>]*>)(.*?)</(h[1-6]|caption|div)>(.*?)</table>", html):
        title = re.sub(r"<[^>]+>", " ", m.group(2))
        if "idratado" not in title:
            continue
        series = " ".join(title.split())[:120]
        for d, v in re.findall(r"(\d{2}/\d{2}/\d{4})\s*</td>\s*<td[^>]*>\s*([\d\.,]+)", m.group(4)):
            x = float(v.replace(".", "").replace(",", "."))
            if x < 50:                      # quoted per litre
                x *= 1000
            out.append((datetime.strptime(d, "%d/%m/%Y").date().isoformat(), round(x, 2), series))
        if out:
            return out
    return out


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
