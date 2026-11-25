"""India ex-mill sugar prices by state and grade from ChiniMandi's public "Daily Sugar Market Update By Vizzie" pages.

Stores only the numbers (Rs per quintal, excluding GST), the date and the source URL in data/sugar/india_prices.csv;
no article text. Fills from the day after the last stored date (first run: 60 days back) to today, then spends what is
left of a time budget (BACKFILL_SECS, default 300 s) walking back from the earliest date tried so far, to build the
price history; the walk stops for good after BACKFILL_STOP consecutive days without a page (default 120) or at
BACKFILL_FLOOR (default 2018-01-01). Every URL is checked against the site's robots.txt first. Writes
data/sugar/india_prices_status.json with the result of each run. Exits 1 when every request failed (site blocked
or down), so the workflow step shows red; the page then falls back to data/sugar/manual/india.csv.
"""
import csv, html as htmlmod, json, os, re, sys, time
import urllib.robotparser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sugar" / "india_prices.csv"
STATUS = ROOT / "data" / "sugar" / "india_prices_status.json"
URL = "https://www.chinimandi.com/daily-sugar-market-update-by-vizzie-{d:%d-%m-%Y}/"
UA = {"User-Agent": "Mozilla/5.0 (compatible; BMR-Com research desk; github.com/BMR-Com)"}
ROBOTS = "https://www.chinimandi.com/robots.txt"


def robots():
    """Parser for the site's robots.txt (fetched with our user agent). None = could not be read, in which case
    only the daily forward fill runs (the history walk needs an explicit allow)."""
    try:
        r = requests.get(ROBOTS, headers=UA, timeout=30)
        rp = urllib.robotparser.RobotFileParser()
        if r.status_code == 404:
            rp.parse([])              # no robots.txt: nothing disallowed
            return rp
        if r.status_code >= 400:
            return None
        rp.parse(r.text.splitlines())
        return rp
    except Exception:
        return None


def allowed(rp, url):
    return True if rp is None else rp.can_fetch(UA["User-Agent"], url)
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


def fetch(url, codes):
    """(rows, blocked) for one daily page."""
    try:
        r = requests.get(url, headers=UA, timeout=30)
        codes[str(r.status_code)] = codes.get(str(r.status_code), 0) + 1
        if r.status_code == 200:
            return parse(r.text), False
        return [], r.status_code in (401, 403, 429, 503)
    except Exception as e:
        codes["error"] = codes.get("error", 0) + 1
        print("error", url, str(e)[:120], flush=True)
        return [], True


def main():
    t0 = time.time()
    rows = list(csv.DictReader(OUT.open())) if OUT.exists() else []
    old = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    have = {r["date"] for r in rows}
    last = max(have) if have else None
    start = date.fromisoformat(last) + timedelta(days=1) if last else date.today() - timedelta(days=60)
    rp = robots()
    tried = ok = blocked = disallowed = 0
    codes = {}
    d = start
    while d <= date.today():
        url = URL.format(d=d)
        if not allowed(rp, url):
            disallowed += 1; d += timedelta(days=1); continue
        tried += 1
        got, blk = fetch(url, codes)
        blocked += blk
        if got:
            ok += 1
            rows += [{"date": d.isoformat(), **g, "url": url} for g in got]
        time.sleep(2)
        d += timedelta(days=1)
    # history walk backwards (Sundays skipped: no market update)
    bf = old.get("backfill") or {}
    floor = date.fromisoformat(os.environ.get("BACKFILL_FLOOR", "2018-01-01"))
    stop_after = int(os.environ.get("BACKFILL_STOP", "120"))
    budget = float(os.environ.get("BACKFILL_SECS", "300"))
    cursor = date.fromisoformat(bf["cursor"]) if bf.get("cursor") else (min(date.fromisoformat(x) for x in have) - timedelta(days=1) if have else start - timedelta(days=1))
    miss = int(bf.get("miss_run", 0))
    done = bool(bf.get("done"))
    b_tried = b_ok = 0
    while not done and rp is not None and time.time() - t0 < budget and cursor >= floor:
        if cursor.weekday() == 6 or cursor.isoformat() in have:
            cursor -= timedelta(days=1); continue
        url = URL.format(d=cursor)
        if not allowed(rp, url):
            disallowed += 1; cursor -= timedelta(days=1); continue
        b_tried += 1
        got, blk = fetch(url, codes)
        if blk:
            break                     # blocked or down: try the same date next run
        if got:
            b_ok += 1; miss = 0
            rows += [{"date": cursor.isoformat(), **g, "url": url} for g in got]
        else:
            miss += 1
            if miss >= stop_after:
                done = True
        cursor -= timedelta(days=1)
        time.sleep(2)
    if cursor < floor:
        done = True
    rows = list({(r["date"], r["state"], r["grade"]): r for r in rows}.values())
    rows.sort(key=lambda r: (r["date"], r["state"], r["grade"]))
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    st = {"run": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "from": start.isoformat(), "tried": tried, "pages_with_prices": ok,
          "http": codes, "latest": max((r["date"] for r in rows), default=None), "earliest": min((r["date"] for r in rows), default=None),
          "rows": len(rows), "robots_txt": "read" if rp is not None else "unreadable (history walk paused)", "disallowed": disallowed,
          "backfill": {"cursor": cursor.isoformat(), "miss_run": miss, "done": done, "tried_this_run": b_tried, "pages_this_run": b_ok}}
    STATUS.write_text(json.dumps(st, indent=1))
    print(json.dumps(st))
    if tried and blocked == tried:
        print("ChiniMandi blocked or down for every request: page falls back to the manual India file", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
