"""ICE cocoa certified stock report, downloaded daily from ICE's public folder (like pipelines/coffee_certs.py does for coffee):
https://www.ice.com/publicdocs/futures_us_reports/cocoa/cocoa_cert_stock_YYYYMMDD.xls

Every business day after the newest date in data/cocoa/ice_certs_daily.csv (up to 15 days back) is tried.
Each file found is kept in data/ice_raw/cocoa_certs_auto/ (raw copy, review history) and logged in
data/ice_inbox/cocoa_fetch_log.json. Only when data/cocoa/ref/cc_certs_autoload.json says {"load": true} is a copy also
put in inbox/, where the next step (pipelines/ice_inbox.py) reads it into the desk exactly as a manual upload.
"""
import json
import os
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
HIST = ROOT / "data" / "cocoa" / "ice_certs_daily.csv"
RAW = ROOT / "data" / "ice_raw" / "cocoa_certs_auto"
LOG = ROOT / "data" / "ice_inbox" / "cocoa_fetch_log.json"
CFG = ROOT / "data" / "cocoa" / "ref" / "cc_certs_autoload.json"
INBOX = ROOT / "inbox"
URL = "https://www.ice.com/publicdocs/futures_us_reports/cocoa/cocoa_cert_stock_{}.xls"
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research)"}
OLE = b"\xd0\xcf\x11\xe0"


def last_held():
    try:
        with open(HIST) as f:
            ds = [l.split(",", 1)[0] for l in f.readlines()[1:] if l[:4].isdigit()]
        return date.fromisoformat(max(ds))
    except Exception:
        return date.today() - timedelta(days=15)


def main():
    load = False
    try:
        load = bool(json.loads(CFG.read_text()).get("load"))
    except Exception:
        pass
    today = datetime.now(timezone.utc).date()
    start = max(last_held() + timedelta(days=1), today - timedelta(days=15))
    RAW.mkdir(parents=True, exist_ok=True)
    log = json.loads(LOG.read_text()) if LOG.exists() else {"runs": []}
    got, missing = [], []
    d = start
    while d <= today:
        if d.weekday() < 5:
            tag = d.strftime("%Y%m%d")
            dst = RAW / f"cocoa_cert_stock_{tag}.xls"
            if dst.exists():
                got.append(tag)
            else:
                try:
                    r = requests.get(URL.format(tag), headers=H, timeout=60)
                    ok = r.status_code == 200 and r.content[:4] == OLE
                except Exception as e:
                    print(f"{tag}: {e}")
                    ok = False
                if ok:
                    dst.write_bytes(r.content)
                    got.append(tag)
                else:
                    missing.append(tag)
            if load and dst.exists():
                INBOX.mkdir(exist_ok=True)
                shutil.copyfile(dst, INBOX / dst.name)
        d += timedelta(days=1)
    entry = {"run": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "load": load, "have": got, "not_posted": missing}
    log["runs"] = (log.get("runs", []) + [entry])[-60:]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(log, indent=1))
    print(json.dumps(entry))


if __name__ == "__main__":
    sys.exit(main())
