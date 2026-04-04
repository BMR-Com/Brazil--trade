"""
Brazil Trade Scheduler
======================
Called by GitHub Actions every Monday.
Checks if MDIC has released new monthly data since last run.
If yes — fetches only the current + previous year and updates exports.csv.

Logic:
  MDIC releases month M data around the 20th of month M+1.
  We wait until the 8th of M+1 before declaring data "available"
  (conservative buffer to avoid half-released data).

Run:
  python scheduler.py          # Monday-check mode (used by GitHub Actions)
  python scheduler.py --force  # Skip date check, always update
"""

import logging
from datetime import date, timedelta
import pandas as pd
import scraper

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger(__name__)


def latest_available_period() -> tuple[int, int]:
    """
    Return (year, month) of the latest period MDIC should have published.
    Conservative: assumes available once today >= 8th of the following month.
    """
    today = date.today()
    first_this_month = today.replace(day=1)
    last_month_last  = first_this_month - timedelta(days=1)
    if today.day >= 8:
        return last_month_last.year, last_month_last.month
    # Not yet — go back one more month
    first_last_month = last_month_last.replace(day=1)
    two_months_ago   = first_last_month - timedelta(days=1)
    return two_months_ago.year, two_months_ago.month


def latest_in_csv() -> tuple[int, int] | None:
    """Return (year, month) of the most recent row in exports.csv, or None."""
    if not scraper.EXPORT_CSV.exists():
        return None
    df = pd.read_csv(scraper.EXPORT_CSV, usecols=["year","month"])
    if df.empty:
        return None
    idx = df["year"]*100 + df["month"]
    row = df.loc[idx.idxmax()]
    return int(row["year"]), int(row["month"])


def run(force: bool = False):
    today = date.today()

    # In scheduled mode only act on Mondays (GitHub Actions cron triggers this)
    if not force and today.weekday() != 0:
        log.info("Today is %s — not Monday. Nothing to do.", today.strftime("%A"))
        return

    avail_year, avail_month = latest_available_period()
    log.info("Latest MDIC period expected: %d-%02d", avail_year, avail_month)

    current = latest_in_csv()
    if current:
        log.info("Latest period in CSV: %d-%02d", current[0], current[1])
        csv_ym  = current[0]*100 + current[1]
        need_ym = avail_year*100 + avail_month
        if csv_ym >= need_ym and not force:
            log.info("CSV already up to date — nothing to fetch.")
            return

    # Re-fetch current year and previous year
    # (previous year in case MDIC issued a revision)
    years = sorted({avail_year, avail_year - 1})
    log.info("Fetching years: %s", years)
    scraper.run(years_override=years)
    log.info("Scheduler done.")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="Force update regardless of day or CSV state")
    args = ap.parse_args()
    run(force=args.force)
