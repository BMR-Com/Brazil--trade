"""CFTC Commitments of Traders for the desk's contracts (no key), full history.

Writes data/cot/<sym>.csv from the Disaggregated futures-and-options combined report
(Socrata dataset kh3c-gbw2), plus the futures-only version (72hh-3qpy).
"""
import csv, io, time
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parent.parent / "data" / "cot"
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research; github actions)"}
CODES = {  # CFTC contract market codes (softs desk)
    "CT": "033661",   # Cotton No. 2
    "SB": "080732",   # Sugar No. 11
    "KC": "083731",   # Coffee C
}
SETS = {"fo": "kh3c-gbw2", "fut": "72hh-3qpy"}


def fetch(ds, code):
    rows, off = [], 0
    while True:
        u = (f"https://publicreporting.cftc.gov/resource/{ds}.csv?cftc_contract_market_code={code}"
             f"&$order=report_date_as_yyyy_mm_dd&$limit=50000&$offset={off}")
        for i in range(3):
            try:
                r = requests.get(u, headers=H, timeout=120)
                if r.status_code == 200:
                    break
            except Exception as e:
                print("err", e)
            time.sleep(5)
        else:
            return rows
        part = list(csv.DictReader(io.StringIO(r.text)))
        rows += part
        if len(part) < 50000:
            return rows
        off += 50000


def latest_ok():
    """True when the CFTC has published this week's report (positions as of the latest Tuesday)."""
    import datetime as dt
    t = dt.date.today(); tue = t - dt.timedelta(days=(t.weekday() - 1) % 7)
    u = (f"https://publicreporting.cftc.gov/resource/{SETS['fo']}.json?cftc_contract_market_code={CODES['CT']}"
         "&$select=max(report_date_as_yyyy_mm_dd) as d")
    try:
        d = requests.get(u, headers=H, timeout=60).json()[0]["d"][:10]
        print("CFTC latest", d, "expected", tue)
        return d >= str(tue)
    except Exception as e:
        print("check failed", e); return False


if __name__ == "__main__":
    import datetime as dt, os
    OUT.mkdir(parents=True, exist_ok=True)
    # Fridays (release 3:30 pm ET): wait up to COT_WAIT minutes for the new week before fetching
    if dt.date.today().weekday() == 4:
        end = time.time() + 60 * float(os.environ.get("COT_WAIT", "40"))
        while not latest_ok() and time.time() < end:
            time.sleep(120)
    for sym, code in CODES.items():
        for tag, ds in SETS.items():
            rows = fetch(ds, code)
            if not rows:
                print(sym, tag, "no rows")
                continue
            with (OUT / f"{sym}_{tag}.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            print(sym, tag, len(rows), rows[-1].get("report_date_as_yyyy_mm_dd", "")[:10])
