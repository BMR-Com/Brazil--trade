"""ICE Coffee "C" certified stocks, from ICE's daily report (one .xls per business day):
https://www.ice.com/publicdocs/futures_us_reports/coffee/coffee_cert_stock_YYYYMMDD.xls

Each report gives bags certified by origin and port, the transition bags (graded under the earlier rules), bags passed
and failed in that day's grading and bags pending grading by origin and port. Stored long in
data/coffee/ice_certs.csv (date, section, origin, port, bags). New days are added on every run; the first run walks
back day by day to fill history (CERTS_BACKFILL days, default 900).
"""
import io
import os
import sys
import time
from datetime import date, timedelta

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "coffee", "ice_certs.csv")
URL = "https://www.ice.com/publicdocs/futures_us_reports/coffee/coffee_cert_stock_{}.xls"
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research)"}
SECTIONS = [("TOTAL BAGS CERTIFIED", "certified"), ("TRANSITION BAGS", "transition"), ("PENDING GRADING", "pending"),
            ("BAGS PASSED GRADING", "graded_passed"), ("BAGS FAILED GRADING", "graded_failed")]


def parse(content, day):
    d = pd.read_excel(io.BytesIO(content), header=None)
    rows, sec, ports = [], None, None
    for r in d.itertuples(index=False):
        c0 = str(r[0]).strip() if pd.notna(r[0]) else ""
        up = c0.upper()
        hit = next((s for k, s in SECTIONS if up.startswith(k)), None)
        if hit:
            sec, ports = hit, None
            continue
        cells = [str(x).strip() for x in r[1:]]
        if not c0 and "Total" in cells:
            ports = [x if x not in ("nan", "") else None for x in cells]
            continue
        if sec and ports and c0 and not up.startswith("TOTAL IN BAGS"):
            for p, v in zip(ports, r[1:]):
                if p and p != "Total" and pd.notna(v):
                    try:
                        b = int(float(v))
                    except ValueError:
                        continue
                    if b:
                        rows.append((day, sec, c0, p, b))
    return rows


def fetch(day):
    try:
        r = requests.get(URL.format(day.strftime("%Y%m%d")), headers=H, timeout=40)
    except Exception:
        return None
    if r.status_code != 200 or len(r.content) < 2000 or b"<html" in r.content[:200].lower():
        return None
    return r.content


def main():
    old = pd.read_csv(OUT, parse_dates=["date"]) if os.path.exists(OUT) else pd.DataFrame(columns=["date", "section", "origin", "port", "bags"])
    have = set(old.date.dt.date) if len(old) else set()
    today = date.today()
    back = int(os.environ.get("CERTS_BACKFILL", "900")) if not have else 21
    misses, rows, t0 = 0, [], time.time()
    for k in range(back):
        day = today - timedelta(days=k)
        if day.weekday() >= 5 or day in have:
            continue
        if time.time() - t0 > float(os.environ.get("CERTS_SECONDS", "1500")):
            print("time budget reached at", day); break
        c = fetch(day)
        if c is None:
            misses += 1
            if have and misses > 15:
                break
            continue
        misses = 0
        try:
            got = parse(c, day)
            # pending-grading rows with no ports header found get skipped; record an explicit zero total so the day exists
            rows += got or [(day, "certified", "ALL", "ALL", 0)]
        except Exception as e:
            print("parse failed", day, e)
        time.sleep(0.4)
    if rows:
        new = pd.DataFrame(rows, columns=["date", "section", "origin", "port", "bags"])
        new["date"] = pd.to_datetime(new.date)
        out = pd.concat([old[~old.date.isin(new.date)], new]).sort_values(["date", "section", "origin", "port"])
        out.to_csv(OUT, index=False)
        tot = new[new.section == "certified"].groupby("date").bags.sum()
        print("ice certs: added", tot.size, "days; latest", tot.index.max().date(), int(tot.iloc[-1]) if tot.size else None)
    else:
        print("ice certs: nothing new")


if __name__ == "__main__":
    sys.exit(main())
