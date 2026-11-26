#!/usr/bin/env python3
"""CEPEA/ESALQ hydrous ethanol indicator (public page) -> sugar/data/cepea_hydrous.csv (date, brl_m3, series).

Fetched under the desk's own agent name (same as pipelines/cepea_fetch.py), only where the host's robots.txt allows it.
When the page cannot be read the file is left as it is, a warning is printed and the sugar parity falls back to the
B3 hydrous ethanol futures (models/sugar_parity.py says which one it used).
"""
import csv, re, sys, urllib.robotparser
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sugar" / "data" / "cepea_hydrous.csv"
URLS = ["https://www.cepea.org.br/br/indicador/etanol.aspx", "https://www.cepea.esalq.usp.br/br/indicador/etanol.aspx"]
AGENT = "BMR-Com research desk (github.com/BMR-Com)"
UA = {"User-Agent": AGENT, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"}


def allowed(url):
    host = "/".join(url.split("/")[:3])
    try:
        r = requests.get(host + "/robots.txt", headers=UA, timeout=30)
    except Exception as e:
        print(f"{host}/robots.txt could not be read ({str(e)[:80]}); skipped")
        return False
    if r.status_code >= 500 or r.status_code in (401, 403):
        print(f"{host}/robots.txt HTTP {r.status_code}; skipped")
        return False
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(r.text.splitlines() if r.status_code == 200 else [])
    return rp.can_fetch(AGENT, url)


def parse(html):
    """Rows (date, R$/m³) of the first table on the page whose heading text (up to 1,500 characters before it) mentions
    hydrous ethanol (hidratado). Values below 50 are per litre and are converted to per m³."""
    tables = list(re.finditer(r"(?is)<table.*?</table>", html))
    for t in tables:
        before = re.sub(r"(?s)<[^>]+>", " ", html[max(0, t.start() - 400):t.start()])
        heads = re.findall(r"(?i)indicador[^|]*?(?=indicador|$)", " ".join(before.split()))
        head = heads[-1] if heads else before
        if "hidratado" not in head.lower() or "outros fins" in head.lower():
            continue
        before = head
        series = " ".join(before.split())[-140:]
        rows = []
        for tr in re.findall(r"(?is)<tr.*?</tr>", t.group(0)):
            cells = [" ".join(re.sub(r"(?s)<[^>]+>", " ", c).split()) for c in re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", tr)]
            ds = re.findall(r"\d{2}/\d{2}/\d{4}", cells[0]) if cells else []
            num = re.search(r"\d[\d\.]*,\d+|\d+\.\d+", cells[1]) if len(cells) >= 2 else None
            if ds and num:
                v = num.group(0)
                x = float(v.replace(".", "").replace(",", ".")) if "," in v else float(v)
                rows.append((datetime.strptime(ds[-1], "%d/%m/%Y").date().isoformat(), round(x * 1000 if x < 50 else x, 2), series))
        if rows:
            return rows
    print(f"CEPEA page: {len(tables)} tables; headings near tables: " + " | ".join(" ".join(re.sub(r'(?s)<[^>]+>', ' ', html[max(0, t.start() - 300):t.start()]).split())[-80:] for t in tables[:6]))
    return []


def main():
    rows, err = [], []
    for u in URLS:
        if not allowed(u):
            err.append(f"{u}: robots.txt does not allow this agent")
            continue
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
