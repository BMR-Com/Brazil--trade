"""Is a CFTC cotton on-call report out that data/cotton/oncall/cotton_oncall.csv does not have yet?
Prints due=1/0 (and appends it to $GITHUB_OUTPUT). Standard library only, so the workflow can skip installs when nothing is due."""
import csv, os, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines"))
import release_rules as R


def stored_latest():
    with open(ROOT / "data" / "cotton" / "oncall" / "cotton_oncall.csv", newline="") as f:
        return max(datetime.strptime(r["Report Date"], "%m/%d/%Y").date() for r in csv.DictReader(f) if r.get("Report Date"))


def status(now=None):
    cal = R.load_calendar(); e = R.entry(cal, "cftc_oncall"); C = R.Cal(cal)
    now = now or datetime.now(R.ET)
    have = stored_latest()
    out = R.latest_due(e, C, now)           # newest release already published (no grace)
    exp = R.expected(e, C, now)             # newest release past its late limit
    return {"have": have.isoformat(), "out": out[1].isoformat() if out else None, "out_at": out[0].isoformat() if out else None,
            "overdue": bool(exp and exp["data_date"] > have.isoformat()), "expected_by_now": exp}


if __name__ == "__main__":
    s = status()
    due = int(bool(s["out"] and s["out"] > s["have"]) or os.environ.get("FORCE_SCRAPE") == "1")
    print(f"stored {s['have']}; newest released {s['out']} (released {s['out_at']}); overdue={s['overdue']}; due={due}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"due={due}\n")
