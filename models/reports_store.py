"""Store for the 'Reports' tabs (cotton, coffee and sugar): short own-words key points per source and report.

Files: data/{cotton,coffee,sugar}/reports/<source>.json (USDA reports: models/usda_reports.py writes usda.json)
  {source, name, home, cadence, access, window_start, entries: [{date, title, url, key_points: [..], tag}], ...}
  (sucden.json also carries the balance sheet and revisions written by models/sucden_coffee.py)

Commands
  python models/reports_store.py add --file data/coffee/reports/sucafina.json --date 2026-11-10 --title "..." \
         --url https://... --point "..." --point "..." [--tag field]
  python models/reports_store.py prune            # drop entries older than the current window, both markets
  python models/reports_store.py list [--market coffee]

Window (only the current crop / marketing year is shown):
  coffee: Brazil crop year Y/Y+1 (Y = this year from April, else last year); entries from 1 Jan Y, when the first
          forecasts for that crop appear.
  sugar : Brazil Centre-South season Y/Y+1 (April-March); entries from 1 Apr Y.
  cotton: marketing year Aug Y - Jul Y+1; entries from 1 Apr Y (attaché annuals carry the first forecasts for it).
Key points are written in our own words (no copied sentences, no reproduced tables); numbers are attributed.
"""
import argparse
import glob
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def window_start(market, today=None):
    t = today or date.today()
    if market == "cotton":   # MY Aug-Jul; from 1 Apr before it, when the attaché annuals give the first forecasts
        y = t.year if t.month >= 8 else t.year - 1
        return f"{y}-04-01"
    y = t.year if t.month >= 4 else t.year - 1
    return f"{y}-01-01" if market == "coffee" else f"{y}-04-01"


def files(market=None):
    ms = [market] if market else ["cotton", "coffee", "sugar"]
    return [(m, f) for m in ms for f in sorted(glob.glob(os.path.join(ROOT, "data", m, "reports", "*.json")))]


def save(path, d):
    with open(path, "w") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)


def prune(market=None):
    for m, f in files(market):
        d = json.load(open(f))
        ws = window_start(m)
        before = len(d.get("entries", []))
        d["entries"] = sorted([e for e in d.get("entries", []) if e["date"] >= ws], key=lambda e: e["date"], reverse=True)
        d["window_start"] = ws
        save(f, d)
        print(f"{os.path.relpath(f, ROOT)}: {before} -> {len(d['entries'])} entries (from {ws})")


def add(a):
    path = a.file if os.path.isabs(a.file) else os.path.join(ROOT, a.file)
    if not os.path.exists(path):
        raise SystemExit(f"{path} not found: create the source file first (source, name, home, cadence)")
    if not a.point:
        raise SystemExit("at least one --point")
    d = json.load(open(path))
    e = {"date": a.date, "title": a.title, "url": a.url, "key_points": a.point}
    if a.tag:
        e["tag"] = a.tag
    d["entries"] = [x for x in d.get("entries", []) if x.get("url") != a.url or x.get("date") != a.date] + [e]
    d["entries"].sort(key=lambda x: x["date"], reverse=True)
    save(path, d)
    print("added", a.date, a.title)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("add"); p.add_argument("--file", required=True); p.add_argument("--date", required=True)
    p.add_argument("--title", required=True); p.add_argument("--url", required=True); p.add_argument("--point", action="append")
    p.add_argument("--tag")
    p = sp.add_parser("prune"); p.add_argument("--market")
    p = sp.add_parser("list"); p.add_argument("--market")
    a = ap.parse_args()
    if a.cmd == "add":
        add(a)
    elif a.cmd == "prune":
        prune(a.market)
    else:
        for m, f in files(a.market):
            d = json.load(open(f))
            print(os.path.relpath(f, ROOT), d.get("window_start"))
            for e in d.get("entries", []):
                print("  ", e["date"], e["title"])


if __name__ == "__main__":
    sys.exit(main())
