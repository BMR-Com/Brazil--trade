"""Honduras realized export prices (IHCAFE daily figures) for the Coffee > Differentials view.

IHCAFE's daily "Cifras de café - Honduras" sheet (crop to date: purchases, sales contracts, physical exports, average
price per 46-kg bag exported, sales by quality and US$ price band, exports by quality, NY 'C' closes, BCH rate) is
reposted as PDFs in the public GitHub repo thenexuscoffee/cifrascafeteras (Spanish and English copies, one per business
day since 11 Feb 2026). Each run lists that repo through the GitHub API, downloads PDFs not read before, parses them with
pdftotext and writes:
  data/coffee/diffs/honduras_ihcafe_daily.csv   one row per data date (fields below)
  data/coffee/diffs/honduras_ihcafe_read.json   files already read (so each PDF is fetched once)
Derived series (c/lb; a 46-kg bag is 101.41 lb) are computed in pipelines/coffee_diffs.py.
Usage: python pipelines/honduras_ihcafe.py [--dir LOCAL_CLONE]   (--dir parses a local copy instead of downloading)
"""
import argparse, csv, json, os, re, subprocess, sys, tempfile, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "coffee" / "diffs"
CSV = OUT / "honduras_ihcafe_daily.csv"
READ = OUT / "honduras_ihcafe_read.json"
REPO = "thenexuscoffee/cifrascafeteras"
AGENT = "BMR-Com research desk (github.com/BMR-Com)"

MES = {m: i + 1 for i, m in enumerate("enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split())}
MON = {m: i + 1 for i, m in enumerate("january february march april may june july august september october november december".split())}
MSH = {"ene": 1, "jan": 1, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "aug": 8,
       "sep": 9, "oct": 10, "nov": 11, "dic": 12, "dec": 12}
BANDS = ["0-100", "101-150", "151-200", "201-250", "251-300", "301-350", "351-400", ">400"]
FIELDS = (["date", "crop", "avg_export_price_usd_46kg", "exports_cum_46kg", "sales_cum_46kg", "sales_shg", "sales_hg",
           "sales_stocklot", "exp_shg", "exp_hg", "exp_stocklot", "sales_value_usd", "ny_front", "ny_close", "bch_buy"]
          + [f"b{b}_{q}" for b in BANDS for q in ("shg", "hg", "sl")] + ["file"])


def N(s):
    return float(s.replace(",", ""))


def pdf_text(path):
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout


def fname_date(name):
    n = name.lower()
    m = re.search(r"(\d{1,2})[_-]([a-z]{3})[_-](20\d\d)", n)
    if m:
        return f"{m.group(3)}-{MSH.get(m.group(2), 0):02d}-{int(m.group(1)):02d}"
    m = re.search(r"([a-z]{3})_+(\d{1,2})_(20\d\d)", n) or re.search(r"([a-z]{3})-(\d{1,2})-(20\d\d)", n)
    if m:
        return f"{m.group(3)}-{MSH.get(m.group(1), 0):02d}-{int(m.group(2)):02d}"
    return None


def parse(t):
    R = {}
    m = re.search(r"(\d{1,2}) de ([a-zé]+) de (20\d\d)", t, re.I)
    if m and m.group(2).lower() in MES:
        R["date"] = f"{m.group(3)}-{MES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    else:
        m = re.search(r"\b([A-Z][a-z]+) (\d{1,2}), (20\d\d)", t)
        if not m or m.group(1).lower() not in MON:
            return None
        R["date"] = f"{m.group(3)}-{MON[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    m = re.search(r"(?:Cosecha|Harvest)\s+(\d{4}/\d{4})", t)
    R["crop"] = m.group(1) if m else ""
    head = re.split(r"Pron[óo]stico de|Export Forecast", t)[0]
    head = re.sub(r"\(ant:[^)]*\)", " ", head)
    head = re.sub(r"(?:ant|prev)[.:]?\s*[\d,.]+", " ", head, flags=re.I)
    p = re.findall(r"(?<![\d.,%+-])(\d{2,3}\.\d{2})(?![\d%])", head)
    R["avg_export_price_usd_46kg"] = N(p[0]) if p else None
    m = re.search(r"(?:realizadas|Exports)\s+([\d,]+)\s+([\d,]+)", t)
    R["exports_cum_46kg"] = N(m.group(2)) if m else None
    m = re.search(r"(?:Generaci[óo]n de divisas|Generation)(?:\s*\(mill[^)]*\))?\s+([\d,]+)\s+([\d,]+)", t)
    R["sales_value_usd"] = N(m.group(2)) if m else None
    for b in BANDS:
        m = re.search(r"^\s*" + re.escape(b) + r"\s+([\d,]+)\s+[\d.]+%\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)", t, re.M)
        for q, g in zip(("shg", "hg", "sl"), (2, 3, 4)):
            R[f"b{b}_{q}"] = N(m.group(g)) if m else None
    m = re.search(r"^\s*TOTAL\s+([\d,]+)\s+[\d.]+%\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)", t, re.M)
    if m:
        R.update(sales_cum_46kg=N(m.group(1)), sales_shg=N(m.group(2)), sales_hg=N(m.group(3)), sales_stocklot=N(m.group(4)))
    for q, k in (("SHG", "exp_shg"), ("HG", "exp_hg"), ("STOCK LOT", "exp_stocklot")):
        m = re.search(r"(?<![A-Z])" + q + r" \(([\d,]+) - [\d.]+%\)", t)
        R[k] = N(m.group(1)) if m else None
    m = re.search(r"^\s*(Mar|May|Jul|Sep|Dic|Dec)-(\d\d)\s+\$([\d.,]+)\s+\$([\d.,]+)", t, re.M)
    if m:
        R["ny_front"] = f"{m.group(1).replace('Dic', 'Dec')}-{m.group(2)}"
        R["ny_close"] = N(m.group(4))
    m = re.search(r"Compra:\s*L\.\s*([\d.]+)", t)
    R["bch_buy"] = float(m.group(1)) if m else None
    return R


def load():
    rows = {}
    if CSV.exists():
        with open(CSV) as f:
            for r in csv.DictReader(f):
                rows[r["date"]] = r
    return rows


def merge(rows, R, name):
    """Spanish and English copies of the same day fill each other's gaps; a file whose name gives another date is skipped."""
    fd = fname_date(name)
    if fd and fd != R["date"]:
        print(f"skip {name}: named {fd}, data dated {R['date']}")
        return
    old = rows.get(R["date"], {})
    new = {k: old.get(k, "") for k in FIELDS}
    for k in FIELDS:
        v = R.get(k)
        if (new.get(k) in ("", None)) and v not in (None, ""):
            new[k] = ((str(int(v)) if float(v).is_integer() else f"{v:.4f}".rstrip("0")) if isinstance(v, float) else v)
    new["date"] = R["date"]
    new["file"] = (old.get("file") + ";" if old.get("file") else "") + name
    rows[R["date"]] = new


def listing():
    H = {"User-Agent": AGENT, "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        H["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    for i in range(4):
        r = requests.get(f"https://api.github.com/repos/{REPO}/contents/", headers=H, timeout=60)
        if r.ok:
            return [x for x in r.json() if x["name"].lower().endswith(".pdf")]
        print("listing", r.status_code, r.text[:200]); time.sleep(20 * (i + 1))
    raise SystemExit("cannot list the IHCAFE repost repo")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load()
    done = set(json.loads(READ.read_text())) if READ.exists() else set()
    skip = lambda n: ("Boletin" in n or "Reporte" in n or not re.search(r"(cifras|coffee).*honduras", n, re.I))
    if a.dir:
        items = [(p.name, p) for p in sorted(Path(a.dir).glob("*.pdf"))]
    else:
        items = [(x["name"], x["download_url"]) for x in listing()]
    new = 0
    with tempfile.TemporaryDirectory() as tmp:
        for name, src in sorted(items):
            if name in done or skip(name):
                continue
            if isinstance(src, Path):
                path = src
            else:
                r = requests.get(src, headers={"User-Agent": AGENT}, timeout=120)
                if not r.ok:
                    print("download", name, r.status_code); continue
                path = Path(tmp) / "f.pdf"; path.write_bytes(r.content)
            R = parse(pdf_text(path))
            done.add(name)
            if not R or not R.get("avg_export_price_usd_46kg"):
                print("unreadable", name); continue
            merge(rows, R, name); new += 1
    with open(CSV, "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS); w.writeheader()
        for d in sorted(rows):
            w.writerow({k: rows[d].get(k, "") for k in FIELDS})
    READ.write_text(json.dumps(sorted(done), indent=0, ensure_ascii=False))
    print(f"Honduras IHCAFE: {new} new files, {len(rows)} days, latest {max(rows) if rows else '-'}")
    if not rows:
        sys.exit(1)


if __name__ == "__main__":
    main()
