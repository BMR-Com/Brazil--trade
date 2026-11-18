"""Honduras coffee (ADECAFEH, Asociación de Exportadores de Café de Honduras) for the Coffee > Centrals & Col tab.

https://exportadoresdecafe.com/cifras shows only the current crop year (Oct-Sep) as text: export and production
forecasts, sales and exports to date with year-on-year change, the latest month's exports, main destinations, and the
last closed crop's exports. No files or history are offered, so each run keeps one row per "datos al" date in
data/coffee/honduras/snapshots.csv (history builds from the first run, 2026-11-18) and writes honduras.json.
Fails the run when the page cannot be read or its headline numbers are not found.
"""
import csv, html, json, re, sys, time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "coffee" / "honduras"
URL = "https://exportadoresdecafe.com/cifras"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
COLS = ["as_of", "crop_year", "export_forecast_m", "export_forecast_yoy_pct", "production_forecast_m", "sales_k", "sales_yoy_pct",
        "exports_k", "exports_yoy_pct", "exports_value_musd", "month", "month_exports_k", "month_yoy_pct", "prev_crop", "prev_crop_exports_m", "destinations"]


def get():
    last = None
    for k in range(4):
        try:
            r = requests.get(URL, headers=UA, timeout=60)
            if r.ok and len(r.text) > 5000:
                return r.text
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = repr(e)[:150]
        print("retry", last, flush=True); time.sleep(5 + 10 * k)
    raise RuntimeError(f"ADECAFEH page unreachable: {last}")


def num(s):
    return float(s.replace(",", "")) if s else None


def parse(page):
    x = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    x = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x)))
    f = lambda p: (lambda m: m.groups() if m else None)(re.search(p, x, re.I))
    R = {}
    cy = f(r"Cosecha (\d{4}/\d{4}) Cifras")
    a = f(r"datos al (\d{1,2}) de (\w+),? (\d{4})")
    e = f(r"pron[óo]stico preliminar de exportaciones es de ([\d.]+) millones de sacos.{0,80}?\), una (reducci[óo]n|aumento|incremento) interanual del ([\d.]+)%")
    if not (cy and a and e):
        raise ValueError("ADECAFEH: crop year, 'datos al' date or export forecast not found (page layout changed?)")
    R["crop_year"] = cy[0]
    R["as_of"] = date(int(a[2]), MESES.index(a[1].lower()) + 1, int(a[0])).isoformat()
    R["export_forecast_m"] = num(e[0]); R["export_forecast_yoy_pct"] = -num(e[2]) if e[1].lower().startswith("reduc") else num(e[2])
    p = f(r"producci[óo]n se estima[^0-9]*([\d.]+) millones de sacos")
    R["production_forecast_m"] = num(p[0]) if p else None
    s = f(r"ventas de caf[ée] suman ([\d.,]+) (mil|millones de) sacos \(([+-]?[\d.]+)% interanual")
    if s:
        R["sales_k"] = num(s[0]) * (1000 if s[1].startswith("mill") else 1); R["sales_yoy_pct"] = num(s[2])
    s = f(r"se exportaron ([\d.,]+) (mil|millones de) sacos \(([+-]?[\d.]+)% interanual[^)]*\).{0,120}?US\$ ?([\d.,]+) millones")
    if s:
        R["exports_k"] = num(s[0]) * (1000 if s[1].startswith("mill") else 1); R["exports_yoy_pct"] = num(s[2]); R["exports_value_musd"] = num(s[3])
    m = f(r"cierre preliminar de (\w+) reporta ([\d.,]+) (mil|millones de) sacos exportados, lo que representa un[a]? (disminuci[óo]n|aumento|incremento) del ([\d.]+)%")
    if m:
        mo = MESES.index(m[0].lower()) + 1
        y = int(R["crop_year"][:4]) if mo >= 10 else int(R["crop_year"][5:])
        R["month"] = f"{y}-{mo:02d}"; R["month_exports_k"] = num(m[1]) * (1000 if m[2].startswith("mill") else 1)
        R["month_yoy_pct"] = -num(m[4]) if m[3].lower().startswith("dismin") else num(m[4])
    pc = f(r"Cosecha (\d{4}/\d{4}) \(cerrada\).*?a ([\d.]+) millones de sacos exportados en la cosecha \1")
    if pc:
        R["prev_crop"], R["prev_crop_exports_m"] = pc[0], num(pc[1])
    d = f(r"siendo los principales: (.*?) y otros \(([\d.]+)%\)")
    if d:
        R["destinations"] = "; ".join(re.sub(r"\s+\(", " (", z.strip()) for z in d[0].split(" , ")) + f"; others ({d[1]}%)"
    return R


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    R = parse(get())
    p = OUT / "snapshots.csv"
    rows = {r["as_of"]: r for r in csv.DictReader(open(p))} if p.exists() else {}
    rows[R["as_of"]] = {k: ("" if R.get(k) is None else R[k]) for k in COLS}
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, COLS); w.writeheader(); [w.writerow(rows[k]) for k in sorted(rows)]
    hist = [rows[k] for k in sorted(rows)][-30:]
    J = {"built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "source": URL, "latest": R, "history": hist}
    (OUT / "honduras.json").write_text(json.dumps(J, ensure_ascii=False, indent=1))
    print("ADECAFEH", R["as_of"], R["crop_year"], "export forecast", R["export_forecast_m"], "m; exports to date", R.get("exports_k"), "k")
    return 0


if __name__ == "__main__":
    sys.exit(main())
