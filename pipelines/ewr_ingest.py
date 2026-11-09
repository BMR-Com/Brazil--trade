"""EWR Inc. cotton receipt statistics (ewrinc.com, "EWR Receipt Statistics by State"), kept as a daily history.

EWR's site does not allow automated collection, so snapshots come from the page's own CSV/Text export or a copy of the
page text, dropped into data/cotton/ewr/inbox/. This script parses whatever is there, appends one row per state per
report time to data/cotton/ewr/history.csv, keeps the prior-years "issued on this date" table, and writes
data/cotton/ewr/latest.json for the certs tab.
"""
import csv, json, re, sys
from pathlib import Path
import pandas as pd

D = Path(__file__).resolve().parent.parent / "data" / "cotton" / "ewr"
COLS = ["state", "issued", "new_issued", "ccc", "shipping_order", "open_cur", "open_prev", "open_prev2", "open_older", "total_open"]
num = lambda x: int(str(x).replace(",", "").strip() or 0)


def parse(text):
    asof = re.search(r"Current Totals as of\s*([A-Za-z]{3}\s+\d{1,2}\s+\d{4})", text)
    asof = pd.to_datetime(asof.group(1)).date().isoformat() if asof else None
    head = {}
    for k, pat in [("new_issued_total", r"Total new receipts issued for (\d{4}) crop year:\s*([\d,]+)"), ("crop_est", r"USDA Estimated Crop Size:\s*([\d,]+)"),
                   ("tenderable_cert", r"Total open tenderable certificated receipts:\s*([\d,]+)"), ("trust_protocol", r"Total open Trust Protocol receipts:\s*([\d,]+)")]:
        m = re.search(pat, text)
        if m:
            head[k] = num(m.groups()[-1])
            if k == "new_issued_total":
                head["crop_year"] = int(m.group(1))
    rows, prior = [], []
    for line in text.splitlines():
        ln = line.strip()
        if "\t" in ln:
            p = [x.strip() for x in ln.split("\t") if x.strip()]
        elif '"' in ln or ln.count(",") >= 5:
            p = [x.strip() for x in next(csv.reader([ln])) if x.strip()]
        else:
            p = [x.strip() for x in re.split(r"\s{2,}", ln) if x.strip()]
        if len(p) == 10 and re.match(r"^(--)?[A-Z]{2}( & [A-Z]{2})?$|^--TOTAL$", p[0]) and all(re.match(r"^[\d,]+$", x) for x in p[1:]):
            rows.append([p[0].lstrip("-")] + [num(x) for x in p[1:]])
        elif len(p) == 6 and re.match(r"^[A-Z]{2}( & [A-Z]{2})?$", p[0]) and all(re.match(r"^[\d,]+$", x) for x in p[1:]):
            prior.append([p[0]] + [num(x) for x in p[1:]])
    return asof, head, rows, prior


def main():
    inbox = D / "inbox"; inbox.mkdir(parents=True, exist_ok=True)
    hist = D / "history.csv"
    H = pd.read_csv(hist) if hist.exists() else pd.DataFrame(columns=["asof"] + COLS)
    latest = None
    for f in sorted(inbox.glob("*")):
        asof, head, rows, prior = parse(f.read_text(errors="ignore"))
        if not asof or not rows:
            print("skip", f.name); continue
        df = pd.DataFrame(rows, columns=COLS); df.insert(0, "asof", asof)
        H = pd.concat([H[H["asof"] != asof], df]).sort_values(["asof", "state"])
        years = re.findall(r"Region\s+((?:\d{4}\s+)+)", f.read_text(errors="ignore"))
        yrs = [int(y) for y in years[0].split()] if years else []
        snap = {"asof": asof, **head, "states": df.drop(columns="asof").to_dict("records"),
                "issued_same_date": {"years": yrs, "rows": prior}}
        (D / f"snapshot_{asof}.json").write_text(json.dumps(snap, indent=0))
        latest = snap if latest is None or asof >= latest["asof"] else latest
        print("ewr", asof, len(rows), "states")
    H.to_csv(hist, index=False)
    if latest:
        (D / "latest.json").write_text(json.dumps(latest, indent=0))


if __name__ == "__main__":
    sys.exit(main())
