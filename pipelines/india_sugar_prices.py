"""India ex-mill sugar prices by state and grade from ChiniMandi's public "Daily Sugar Market Update By Vizzie" pages.

Stores only the numbers (Rs per quintal, excluding GST), the date and the source URL in data/sugar/india_prices.csv;
no article text. Fills from the day after the last stored date (first run: 60 days back) to today. Writes
data/sugar/india_prices_status.json with the result of each run. Exits 1 when every request failed (site blocked
or down), so the workflow step shows red; the page then falls back to data/sugar/manual/india.csv.
"""
import csv, html as htmlmod, json, re, sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sugar" / "india_prices.csv"
STATUS = ROOT / "data" / "sugar" / "india_prices_status.json"
URL = "https://www.chinimandi.com/daily-sugar-market-update-by-vizzie-{d:%d-%m-%Y}/"
UA = {"User-Agent": "Mozilla/5.0 (compatible; BMR-Com research desk; github.com/BMR-Com)"}
FIELDS = ["date", "state", "grade", "lo", "hi", "url"]


def nums(cell):
    v = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]{2,}", cell)]
    return (min(v[0], v[-1]), max(v[0], v[-1])) if v else (None, None)


def parse(html):
    """Rows of the 'Ex-mill Sugar Prices' table: state, S/30 and M/30 cells."""
    i = html.find("Ex-mill Sugar Prices")
    if i < 0:
        return []
    j = html.find("</table>", i)
    block = html[i:j if j > 0 else i + 20000]
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", block, re.S | re.I):
        cells = [re.sub(r"<[^>]+>|&nbsp;", " ", c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        cells = [re.sub(r"\s+", " ", htmlmod.unescape(c)).strip() for c in cells]
        if len(cells) < 3 or not cells[0] or cells[0].lower().startswith(("state", "(all")):
            continue
        for grade, cell in (("S/30", cells[1]), ("M/30", cells[2])):
            lo, hi = nums(cell)
            if lo:
                out.append({"state": cells[0], "grade": grade, "lo": lo, "hi": hi})
    return out


def main():
    rows = list(csv.DictReader(OUT.open())) if OUT.exists() else []
    have = {r["date"] for r in rows}
    last = max(have) if have else None
    start = date.fromisoformat(last) + timedelta(days=1) if last else date.today() - timedelta(days=60)
    tried = ok = blocked = 0
    codes = {}
    d = start
    while d <= date.today():
        url = URL.format(d=d)
        tried += 1
        try:
            r = requests.get(url, headers=UA, timeout=30)
            codes[str(r.status_code)] = codes.get(str(r.status_code), 0) + 1
            if r.status_code == 200:
                got = parse(r.text)
                if got:
                    ok += 1
                    rows += [{"date": d.isoformat(), **g, "url": url} for g in got]
            elif r.status_code in (401, 403, 429, 503):
                blocked += 1
        except Exception as e:
            blocked += 1
            codes["error"] = codes.get("error", 0) + 1
            print("error", url, str(e)[:120], flush=True)
        time.sleep(2)
        d += timedelta(days=1)
    rows.sort(key=lambda r: (r["date"], r["state"], r["grade"]))
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    st = {"run": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "from": start.isoformat(), "tried": tried, "pages_with_prices": ok,
          "http": codes, "latest": max((r["date"] for r in rows), default=None), "rows": len(rows)}
    STATUS.write_text(json.dumps(st, indent=1))
    print(json.dumps(st))
    if tried and blocked == tried:
        print("ChiniMandi blocked or down for every request: page falls back to the manual India file", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
