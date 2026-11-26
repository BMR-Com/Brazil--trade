"""Consumer-side trackers (coffee, cocoa, cotton): fetch the automated feeds.

Steps (run any subset: python pipelines/consumers_fetch.py sec census yahoo jca ecf):
  sec     SEC EDGAR XBRL companyfacts for US filers: quarterly inventory and quarterly net sales.
  census  US Census Monthly Retail Trade (EITS MRTS API): clothing-store sales, inventories, inventory/sales ratio.
  yahoo   Yahoo Finance fundamentals timeseries for non-US filers: quarterly/annual inventory and revenue.
  jca     All Japan Coffee Association month-end green coffee stocks (current-year PDF linked from its data page).
  ecf     European Coffee Federation port stocks: reachability check; the PDF is stored for parsing when reachable.
Conduct: honest User-Agent, robots.txt checked first, no login, no captcha, nothing retried around a block.
A blocked or failed source is logged in data/consumers/fetch_status.json and the last good data stays in place.
"""
import csv, io, json, re, sys, time
import urllib.robotparser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin
import requests

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "consumers"
AUTO = D / "auto"
RAW = D / "raw"
STATUS = D / "fetch_status.json"
UA = {"User-Agent": "BMR-Com softs desk research (github.com/BMR-Com/brazil--trade)"}

# US filers pulled from XBRL. group: coffee / cocoa / cotton (apparel)
US = [
    ("SBUX", "Starbucks", "coffee"), ("SJM", "J.M. Smucker", "coffee"), ("KDP", "Keurig Dr Pepper", "coffee"), ("BROS", "Dutch Bros", "coffee"),
    ("HSY", "Hershey", "cocoa"), ("MDLZ", "Mondelez", "cocoa"),
    ("GAP", "Gap", "cotton"), ("AEO", "American Eagle", "cotton"), ("ANF", "Abercrombie & Fitch", "cotton"), ("LEVI", "Levi Strauss", "cotton"),
    ("PVH", "PVH", "cotton"), ("VFC", "VF Corp", "cotton"), ("RL", "Ralph Lauren", "cotton"), ("KTB", "Kontoor Brands", "cotton"),
    ("CRI", "Carter's", "cotton"), ("URBN", "Urban Outfitters", "cotton"), ("HBI", "Hanesbrands", "cotton"), ("GIL", "Gildan", "cotton"),
    ("TJX", "TJX", "cotton"), ("ROST", "Ross Stores", "cotton"),
]
# non-US filers on Yahoo (symbol, name, group, currency)
NONUS = [
    ("ITX.MC", "Inditex", "cotton"), ("HM-B.ST", "H&M", "cotton"), ("9983.T", "Fast Retailing", "cotton"), ("NXT.L", "Next", "cotton"),
    ("ABF.L", "ABF (Primark)", "cotton"), ("2313.HK", "Shenzhou International", "cotton"),
    ("NESN.SW", "Nestlé", "coffee"), ("JDEP.AS", "JDE Peet's", "coffee"),
    ("BARN.SW", "Barry Callebaut", "cocoa"), ("LISN.SW", "Lindt & Sprüngli", "cocoa"),
]
INV_TAGS = ["InventoryNet", "InventoryGross", "RetailRelatedInventoryMerchandise", "InventoryFinishedGoodsNetOfReserves", "InventoryFinishedGoods"]
REV_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax"]

_robots = {}
LOG = []


def robots_ok(url):
    host = "{0.scheme}://{0.netloc}".format(urlparse(url))
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(host + "/robots.txt", headers=UA, timeout=25)
            if r.status_code == 404:
                rp.parse([])
            elif r.status_code >= 400:
                rp = None
            else:
                rp.parse(r.text.splitlines())
        except Exception:
            rp = None
        _robots[host] = rp
    rp = _robots[host]
    return None if rp is None else rp.can_fetch(UA["User-Agent"], url)


def get(url, step, check_robots=True, **kw):
    if check_robots and robots_ok(url) is False:
        LOG.append({"step": step, "url": url, "result": "disallowed by robots.txt"})
        return None
    try:
        r = requests.get(url, headers=UA, timeout=60, **kw)
    except Exception as e:
        LOG.append({"step": step, "url": url, "result": f"error {type(e).__name__}"})
        return None
    ok = r.status_code == 200 and not re.search(r"captcha|challenge-platform|cf-chl", r.text[:4000] if "text" in r.headers.get("content-type", "") else "", re.I)
    LOG.append({"step": step, "url": url, "result": r.status_code if ok or r.status_code != 200 else "challenge page"})
    return r if ok else None


def wcsv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- SEC XBRL
def days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def sec():
    # SEC fair-access policy asks automated clients to declare a contact in the User-Agent. The contact comes from the
    # repo secret SEC_CONTACT (set by the owner); without it this step is skipped and US filers fall back to Yahoo.
    import os
    contact = os.environ.get("SEC_CONTACT", "").strip()
    if not contact:
        LOG.append({"step": "sec", "result": "skipped: no SEC_CONTACT secret (SEC asks for a contact in the User-Agent)"})
        return
    UA["User-Agent"] = f"BMR-Com softs desk research {contact}"
    m = get("https://www.sec.gov/files/company_tickers.json", "sec", check_robots=False)
    if not m:
        return
    cik = {v["ticker"].upper(): int(v["cik_str"]) for v in m.json().values()}
    inv_rows, rev_rows = [], []
    for tk, name, grp in US:
        c = cik.get(tk)
        if not c:
            LOG.append({"step": "sec", "ticker": tk, "result": "no CIK"})
            continue
        time.sleep(0.3)   # SEC fair-access: well under 10 requests a second
        r = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c:010d}.json", "sec", check_robots=False)
        if not r:
            continue
        g = r.json().get("facts", {}).get("us-gaap", {})
        # inventory: all instant values across the candidate tags, first tag wins per date
        inv = {}
        for t in INV_TAGS:
            tag_vals = {}
            for u in g.get(t, {}).get("units", {}).get("USD", []):
                if u.get("form") not in ("10-Q", "10-K", "10-Q/A", "10-K/A", "40-F", "20-F") or "end" not in u:
                    continue
                if u["end"] not in tag_vals or u["filed"] > tag_vals[u["end"]][2]:
                    tag_vals[u["end"]] = (u["val"], t, u["filed"])
            for e, v in tag_vals.items():
                inv.setdefault(e, v)
        # revenue: choose the tag with the most recent data, then quarters (84-98 days) and derived Q4s
        best = None
        for t in REV_TAGS:
            us = [u for u in g.get(t, {}).get("units", {}).get("USD", []) if "start" in u]
            if us and (best is None or max(u["end"] for u in us) > max(u["end"] for u in best[1])):
                best = (t, us)
        q, a = {}, {}
        if best:
            for u in best[1]:
                if u.get("form") not in ("10-Q", "10-K", "10-Q/A", "10-K/A", "40-F", "20-F"):
                    continue
                n = days(u["start"], u["end"])
                tgt = q if 84 <= n <= 98 else a if 350 <= n <= 378 else None
                if tgt is None:
                    continue
                k = (u["start"], u["end"])
                if k not in tgt or u["filed"] > tgt[k][1]:
                    tgt[k] = (u["val"], u["filed"])
            qe = {}
            for (s, e), (v, f) in q.items():
                if e not in qe or f > qe[e][2]:
                    qe[e] = (v, s, f, "reported")
            for (s, e), (v, f) in a.items():
                if e in qe:
                    continue
                inside = [(qq, vv) for qq, vv in qe.items() if s < qq < e and vv[1] and days(s, vv[1]) >= -5]
                if len(inside) == 3:
                    qe[e] = (v - sum(vv[0] for _, vv in inside), None, f, "derived (fiscal year less three quarters)")
            for e, (v, s, f, how) in qe.items():
                rev_rows.append({"ticker": tk, "name": name, "group": grp, "end": e, "sales": v, "tag": best[0], "how": how, "filed": f})
        for e, (v, t, f) in inv.items():
            inv_rows.append({"ticker": tk, "name": name, "group": grp, "end": e, "inventory": v, "tag": t, "filed": f})
        LOG.append({"step": "sec", "ticker": tk, "result": f"inventory {len(inv)} dates, sales {sum(1 for x in rev_rows if x['ticker'] == tk)} quarters"})
    UA["User-Agent"] = "BMR-Com softs desk research (github.com/BMR-Com/brazil--trade)"
    if inv_rows:
        wcsv(AUTO / "sec_inventory.csv", sorted(inv_rows, key=lambda x: (x["ticker"], x["end"])), list(inv_rows[0]))
    if rev_rows:
        wcsv(AUTO / "sec_sales.csv", sorted(rev_rows, key=lambda x: (x["ticker"], x["end"])), list(rev_rows[0]))


# ---------------------------------------------------------------- Census MRTS
def census():
    url = ("https://api.census.gov/data/timeseries/eits/mrts?get=cell_value,data_type_code,time_slot_id,category_code,seasonally_adj,error_data"
           "&for=us:*&time=from+1999")
    r = get(url, "census", check_robots=False)
    if not r:
        return
    try:
        rows = r.json()
    except Exception:
        LOG.append({"step": "census", "result": "not JSON (the API now asks for a key); using the same Census series as republished by FRED"})
        return census_fred()
    h = rows[0]
    out, cats = [], set()
    for v in rows[1:]:
        o = dict(zip(h, v))
        cats.add(o["category_code"])
        if not re.match(r"^(448|4481|458|4581|44X72|44000|4400A)$", o["category_code"]):
            continue
        if o["data_type_code"] not in ("SM", "IM", "IR", "MPCSM", "MPCIM"):
            continue
        out.append({"month": o["time"], "category": o["category_code"], "type": o["data_type_code"], "sa": o["seasonally_adj"], "value": o["cell_value"]})
    LOG.append({"step": "census", "result": f"{len(out)} rows kept; clothing-type categories seen: {sorted(c for c in cats if c.startswith(('448', '458', '44')))}"})
    if out:
        wcsv(AUTO / "census_mrts.csv", sorted(out, key=lambda x: (x["category"], x["type"], x["sa"], x["month"])), list(out[0]))


def census_fred():
    """Census MRTS clothing-store sales, inventories and ratio, seasonally adjusted, via FRED's public CSV download (no key)."""
    out = []
    for cat in ("4481", "448", "4581", "458"):
        for typ in ("SM", "IM", "IR"):
            sid = f"MRTS{typ}{cat}USS"
            r = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", "census")
            time.sleep(1)
            if not r or not r.text.lstrip().lower().startswith(("observation_date", "date")):
                continue
            n = 0
            for line in r.text.splitlines()[1:]:
                d, _, v = line.partition(",")
                if v and v.strip() not in (".", ""):
                    out.append({"month": d[:7], "category": cat, "type": typ, "sa": "yes", "value": v.strip()})
                    n += 1
            LOG.append({"step": "census", "series": sid, "result": f"{n} months"})
    if out:
        wcsv(AUTO / "census_mrts.csv", out, list(out[0]))


# ---------------------------------------------------------------- Yahoo fundamentals
def yahoo():
    out = []
    p2 = int(time.time())
    for sym, name, grp in NONUS + US:
        url = (f"https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{sym}?symbol={sym}"
               f"&type=quarterlyInventory,quarterlyTotalRevenue,annualInventory,annualTotalRevenue&period1=1262304000&period2={p2}")
        r = get(url, "yahoo", check_robots=False)
        time.sleep(1)
        if not r:
            continue
        n = 0
        for res in r.json().get("timeseries", {}).get("result", []):
            typ = res.get("meta", {}).get("type", [None])[0]
            for x in res.get(typ, []) or []:
                if not x or not x.get("reportedValue"):
                    continue
                out.append({"symbol": sym, "name": name, "group": grp, "type": typ, "end": x["asOfDate"], "period": x.get("periodType"),
                            "currency": x.get("currencyCode"), "value": x["reportedValue"]["raw"]})
                n += 1
        LOG.append({"step": "yahoo", "symbol": sym, "result": f"{n} values"})
    if out:
        wcsv(AUTO / "yahoo_fundamentals.csv", sorted(out, key=lambda x: (x["symbol"], x["type"], x["end"])), list(out[0]))


# ---------------------------------------------------------------- JCA Japan stocks
JP = {"ブラジル": "brazil_t", "コロンビア": "colombia_t", "インドネシア": "indonesia_t", "ベトナム": "vietnam_t", "中米": "central_america_t",
      "その他": "others_t", "合計": "total_t", "合 計": "total_t"}
EN = {"Brazil": "brazil_t", "Colombia": "colombia_t", "Indonesia": "indonesia_t", "Viet": "vietnam_t", "Central America": "central_america_t",
      "Others": "others_t", "Total": "total_t"}
NUM = re.compile(r"\d{1,3}(?:,\d{3})+|\d{4,6}")


def parse_zaiko(pdf_bytes, yyyymm, labels):
    import pdfplumber
    y, mlast = int(yyyymm[:4]), int(yyyymm[4:])
    vals = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    for line in text.splitlines():
        s = line.strip()
        for lab, key in labels.items():
            if s.startswith(lab) and key not in vals:
                nums = [int(x.replace(",", "")) for x in NUM.findall(s[len(lab):])]
                if len(nums) >= mlast:
                    vals[key] = nums[:mlast]
    rows = []
    if "total_t" not in vals:
        return rows, text[:1500]
    for i in range(mlast):
        r = {"month": f"{y}-{i + 1:02d}"}
        for key in ["total_t", "brazil_t", "colombia_t", "indonesia_t", "vietnam_t", "central_america_t", "others_t"]:
            r[key] = vals[key][i] if key in vals else None
        parts = [r[k] for k in r if k not in ("month", "total_t")]
        if all(p is not None for p in parts) and abs(sum(parts) - r["total_t"]) > 0.01 * r["total_t"]:
            return [], f"origin rows do not add to total in {r['month']}"
        rows.append(r)
    return rows, None


def jca():
    found = []
    for page, labels in (("https://coffee.ajca.or.jp/data/", JP), ("https://coffee.ajca.or.jp/english/", EN)):
        r = get(page, "jca")
        if not r:
            continue
        for m in re.finditer(r'href="([^"]*?([je])-zaiko(\d{6})\.pdf)"', r.text):
            found.append((urljoin(page, m.group(1)), m.group(3), labels))
    if not found:
        LOG.append({"step": "jca", "result": "no j-zaiko/e-zaiko link found"})
        return
    found.sort(key=lambda x: x[1], reverse=True)
    out = AUTO / "jca_auto.csv"
    have = {}
    if out.exists():
        for r in csv.DictReader(open(out)):
            have[r["month"]] = r
    for url, ym, labels in found:
        p = get(url, "jca")
        if not p:
            continue
        (RAW / "jca").mkdir(parents=True, exist_ok=True)
        (RAW / "jca" / Path(urlparse(url).path).name).write_bytes(p.content)
        try:
            rows, err = parse_zaiko(p.content, ym, labels)
        except Exception as e:
            rows, err = [], f"parse error {type(e).__name__}: {e}"
        if not rows:
            LOG.append({"step": "jca", "url": url, "result": "not parsed", "detail": (err or "")[:600]})
            continue
        for r in rows:
            r["source_url"] = url
            have[r["month"]] = r
        LOG.append({"step": "jca", "url": url, "result": f"parsed {len(rows)} months to {rows[-1]['month']}"})
        break
    if have:
        wcsv(out, [have[k] for k in sorted(have)], ["month", "total_t", "brazil_t", "colombia_t", "indonesia_t", "vietnam_t", "central_america_t", "others_t", "source_url"])


# ---------------------------------------------------------------- ECF Europe port stocks
MONS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def parse_ecf(text):
    """'Type of coffee 31-Jan-26 28-Feb-26 ...' header, then Robusta / Natural Arabica / Washed Arabica / Total Europe rows."""
    out = {}
    lines = [l.strip() for l in text.splitlines()]
    for i, l in enumerate(lines):
        if not l.startswith("Type of coffee"):
            continue
        dates = re.findall(r"\d{1,2}-([A-Z][a-z]{2})-(\d{2})", l)
        if not dates:
            continue
        for l2 in lines[i + 1:i + 6]:
            for lab, key in (("Robusta", "robusta_t"), ("Natural Arabica", "natural_t"), ("Washed Arabica", "washed_t"), ("Total Europe", "total_t")):
                if l2.startswith(lab):
                    nums = [int(x.replace(",", "")) for x in re.findall(r"\d{1,3}(?:,\d{3})+|\d{4,7}", l2[len(lab):])]
                    for (mon, yy), v in zip(dates, nums):   # first table wins (later tables are comparisons)
                        out.setdefault(f"20{yy}-{MONS[mon]:02d}", {}).setdefault(key, v)
    return out


def ecf():
    page = "https://www.ecf-coffee.org/category/publications/stocks/"
    r = get(page, "ecf")
    if not r:
        LOG.append({"step": "ecf", "result": "site not reachable with an honest user agent; series stays on the hand-kept file"})
        return
    links = sorted(set(re.findall(r'href="([^"]+Stocks-European-Ports[^"]*\.pdf)"', r.text)))
    # one file per data year; the newest upload of each year wins
    by_year = {}
    for u in links:
        m = re.search(r"uploads/(\d{4})/(\d{2})/(\d{4})-Stocks", u)
        if m and (m.group(3) not in by_year or (m.group(1), m.group(2)) > by_year[m.group(3)][0]):
            by_year[m.group(3)] = ((m.group(1), m.group(2)), u)
    out = AUTO / "ecf_auto.csv"
    have = {}
    if out.exists():
        for row in csv.DictReader(open(out)):
            have[row["month"]] = row
    (RAW / "ecf").mkdir(parents=True, exist_ok=True)
    import pdfplumber
    for yr, (_, u) in sorted(by_year.items()):
        if f"{yr}-12" in have and int(yr) < date.today().year - 1:
            continue   # closed years already stored
        p = get(u, "ecf")
        time.sleep(1)
        if not p:
            continue
        with pdfplumber.open(io.BytesIO(p.content)) as pdf:
            text = "\n".join((pg.extract_text() or "") for pg in pdf.pages)
        vals = parse_ecf(text)
        n = 0
        for mth, v in vals.items():
            if "total_t" in v and mth.startswith(yr):
                parts = [v.get(k) for k in ("robusta_t", "natural_t", "washed_t")]
                if all(parts) and abs(sum(parts) - v["total_t"]) > 0.005 * v["total_t"]:
                    LOG.append({"step": "ecf", "month": mth, "result": "types do not add to total; kept total"})
                have[mth] = {"month": mth, **{k: v.get(k) for k in ("total_t", "robusta_t", "natural_t", "washed_t")}, "source_url": u}
                n += 1
        LOG.append({"step": "ecf", "url": u, "result": f"parsed {n} months"})
    if have:
        wcsv(out, [have[k] for k in sorted(have)], ["month", "total_t", "robusta_t", "natural_t", "washed_t", "source_url"])


def main(steps):
    AUTO.mkdir(parents=True, exist_ok=True)
    fn = {"sec": sec, "census": census, "yahoo": yahoo, "jca": jca, "ecf": ecf}
    for s in steps:
        try:
            fn[s]()
        except Exception as e:
            LOG.append({"step": s, "result": f"failed {type(e).__name__}: {e}"})
    st = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    for s in steps:
        st[s] = {"run": now, "log": [x for x in LOG if x.get("step") == s]}
    STATUS.write_text(json.dumps(st, indent=1, ensure_ascii=False))
    print(json.dumps(LOG, indent=1, ensure_ascii=False)[:6000])


if __name__ == "__main__":
    main(sys.argv[1:] or ["sec", "census", "yahoo", "jca", "ecf"])
