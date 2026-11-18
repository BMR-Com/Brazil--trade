"""CIC Papua New Guinea weekly market report -> differential indications + Reports-tab entry.

Usage
  python models/cic_png.py --url https://www.cic.org.pg/weekly-market-report-15-november-2026/      # fetch (may be blocked)
  python models/cic_png.py --html saved.html --url <same URL>                                       # parse a saved copy
  python models/cic_png.py --text report.txt --date 2026-11-15 --url <URL>
  add --point "own-words key point" (repeatable) for the Reports tab; --dry-run prints only.

Writes
  data/coffee/manual/png_diffs.csv      date, grade, diff (c/lb vs ICE NY arabica; range midpoint), range, basis, source_url, note
  data/coffee/reports/cic_png.json      one entry per report (diffs + key points); older than the window are pruned by
                                        models/reports_store.py prune

The report's author states the differentials are indications from sources he cannot verify, and the PNG Y1 figure
is his own inference from the other origins; the CSV note column records that.
"""
import argparse
import csv
import html as htmlmod
import json
import os
import re
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "data", "coffee", "manual", "png_diffs.csv")
REP = os.path.join(ROOT, "data", "coffee", "reports", "cic_png.json")
GRADES = [("Brazil 3/4", "brazil"), ("Honduras HG", "hondura"), ("Kenya AB FAQ", "kenya"), ("Colombia UGQ", "colombia"),
          ("PNG Y1", "y1"), ("PNG Y2", "y2"), ("PNG A", "png a"), ("PNG X", "png x"), ("PNG PSC", "psc")]
NUM = re.compile(r"(minus|plus|\+|−|-)\s?(\d+(?:\.\d+)?)(?:\s*(?:and|to|-)\s*(minus|plus|\+|−|-)?\s?(\d+(?:\.\d+)?))?", re.I)


def sign(w):
    return -1 if w and re.match(r"minus|−|-", w, re.I) else 1


def parse(text):
    low = re.sub(r"\s+", " ", text).lower()
    low = re.split(r"source ?:|related posts", low)[0]
    i = low.find("differential")
    if i < 0:
        return {}, None
    seg = low[max(0, i - 150): i + 650]
    end = re.search(r"fixed|if this|this means", seg)
    seg = seg[:end.start()] if end else seg
    out = {}
    for g, k in GRADES:
        j = seg.find(k)
        if j < 0:
            continue
        m = NUM.search(seg[j:j + 110])
        if not m:
            continue
        a = sign(m.group(1)) * float(m.group(2))
        if m.group(4):
            b = (sign(m.group(3)) if m.group(3) else sign(m.group(1))) * float(m.group(4))
            out[g] = ((a + b) / 2, f"{a:g} to {b:g}")
        else:
            out[g] = (a, "")
    kc = re.search(r"closing at ([0-9.,]+) ?cents/lb", low)
    return out, (float(kc.group(1).replace(",", "")) if kc else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True); ap.add_argument("--html"); ap.add_argument("--text"); ap.add_argument("--date")
    ap.add_argument("--point", action="append", default=[]); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.text:
        text = open(a.text, encoding="utf-8").read()
    else:
        if a.html:
            raw = open(a.html, encoding="utf-8", errors="ignore").read()
        else:
            import requests
            raw = requests.get(a.url, timeout=40, headers={"User-Agent": "Mozilla/5.0 (research desk)"}).text
        m = re.search(r'(?is)<div class="entry-content[^"]*">(.*?)</article>', raw)
        text = htmlmod.unescape(re.sub(r"(?s)<[^>]+>", " ", m.group(1) if m else raw))
    date = a.date
    if not date:
        m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?[-\s]+([a-z]+)[-\s]+(\d{4})", a.url.lower())
        date = datetime.strptime(" ".join(m.groups()), "%d %B %Y").date().isoformat()
    diffs, kc = parse(text)
    print(date, "KC 2nd", kc, {g: v for g, (v, _) in diffs.items()})
    if not diffs:
        raise SystemExit("no differential indications found")
    if a.dry_run:
        return 0
    rows = list(csv.DictReader(open(CSV))) if os.path.exists(CSV) else []
    rows = [r for r in rows if r["date"] != date]
    for g, (v, rng) in diffs.items():
        rows.append({"date": date, "grade": g, "diff": f"{v:g}", "range": rng, "basis": "c/lb vs ICE NY arabica", "source_url": a.url,
                     "note": "author estimate (inferred from other origins)" if g == "PNG Y1" else "indication quoted in report"})
    rows.sort(key=lambda r: (r["date"], r["grade"]))
    with open(CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "grade", "diff", "range", "basis", "source_url", "note"]); w.writeheader(); w.writerows(rows)
    R = json.load(open(REP))
    e = {"date": date, "title": f"Weekly Market Report – {datetime.fromisoformat(date):%d %B %Y}", "url": a.url,
         "diffs": {g: v for g, (v, _) in diffs.items()}, "kc_second": kc, "key_points": a.point}
    R["entries"] = sorted([x for x in R["entries"] if x["date"] != date] + [e], key=lambda x: x["date"], reverse=True)
    with open(REP, "w") as f:
        json.dump(R, f, indent=1, ensure_ascii=False)
    print("updated", CSV, REP)


if __name__ == "__main__":
    sys.exit(main())
