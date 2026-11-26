"""Vietnam coffee exports by month from the NSO (Cục Thống kê / General Statistics Office) monthly socio-economic
report: data/coffee/diffs/vietnam_exports.csv.

Each monthly (and quarterly) report on nso.gov.vn carries an Excel annex whose export sheet ("14.XK") has a coffee row:
the month's volume (thousand tonnes) and value (US$ million), the year-to-date volume and value, and the change on a
year earlier. The month figure is an estimate (2023: "ước tính") or preliminary ("sơ bộ"); the next report's
year-to-date total carries the revision, so the month series here is year-to-date minus the previous year-to-date
whenever both reports were read, and the first estimate otherwise.
Reports are found through the site's WordPress search API; each report is read once (vietnam_exports_read.json).
"""
import argparse, csv, html, io, json, re, sys, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "coffee" / "diffs" / "vietnam_exports_reports.csv"
SERIES = ROOT / "data" / "coffee" / "diffs" / "vietnam_exports.csv"
STATE = ROOT / "data" / "coffee" / "diffs" / "vietnam_exports_read.json"
AGENT = "BMR-Com research desk (github.com/BMR-Com)"
API = "https://www.nso.gov.vn/wp-json/wp/v2/posts"
H = {"User-Agent": AGENT}
FIELDS = ["year", "month", "kind", "m_kt", "m_usd_m", "ytd_kt", "ytd_usd_m", "published", "file"]
VN_MONTH = {"một": 1, "hai": 2, "ba": 3, "tư": 4, "năm": 5, "sáu": 6, "bảy": 7, "tám": 8, "chín": 9, "mười": 10, "mười một": 11, "mười hai": 12}


def get(url, **kw):
    for i in range(3):
        try:
            r = requests.get(url, headers=H, timeout=120, **kw)
            if r.status_code < 500:
                return r
        except Exception as e:
            print("retry", url[:100], str(e)[:120])
        time.sleep(10 * (i + 1))
    return None


def report_month(title):
    """(year, month) covered by a report title, e.g. 'tháng Mười và 10 tháng năm 2026', 'quý III và 9 tháng năm 2026'."""
    t = title.lower()
    y = re.findall(r"(20\d\d)", t)
    if not y:
        return None
    y = int(y[-1])
    m = re.search(r"(\d{1,2})\s*th[áa]ng", t) or re.search(r"th[áa]ng\s*(\d{1,2})\b", t)
    if m:
        return y, int(m.group(1))
    if re.search(r"s[áa]u th[áa]ng|qu[ýy] ii\b", t):
        return y, 6
    if re.search(r"qu[ýy] iv|v[àa] n[ăa]m 20", t):
        return y, 12
    if re.search(r"qu[ýy] iii", t):
        return y, 9
    if re.search(r"qu[ýy] i\b", t):
        return y, 3
    for name in sorted(VN_MONTH, key=len, reverse=True):
        if re.search(r"th[áa]ng " + name + r"\b", t):
            return y, VN_MONTH[name]
    return None


def reports():
    out, seen = [], set()
    for q in ("Báo cáo tình hình kinh tế xã hội tháng", "Báo cáo tình hình kinh tế xã hội quý"):
        for page in range(1, 40):
            r = get(API, params={"search": q, "per_page": 100, "page": page, "_fields": "date,link,title"})
            if r is None or r.status_code != 200:
                break
            J = r.json()
            if not J:
                break
            for p in J:
                t = html.unescape(p["title"]["rendered"])
                if p["link"] in seen or not re.match(r"B[áa]o c[áa]o t[ìi]nh h[ìi]nh kinh t[ếe]", t):
                    continue
                ym = report_month(t)
                if ym:
                    seen.add(p["link"]); out.append({"link": p["link"], "title": t, "date": p["date"][:10], "ym": ym})
            time.sleep(1)
    return out


def coffee_row(content):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    for ws in wb.worksheets:
        if not re.search(r"XK|xu[aấ]t", ws.title, re.I):
            continue
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        hi = next((i for i, r in enumerate(rows) if sum(1 for c in r if isinstance(c, str) and c.strip() == "Lượng") >= 2), None)
        cof = next((r for r in rows if any(isinstance(c, str) and re.fullmatch(r"\s*c[àa] ph[êe]\s*", c, re.I) for c in r)), None)
        if hi is None or cof is None:
            continue
        width = max(len(r) for r in rows[:hi + 1])
        lab = [""] * width
        for r in rows[max(0, hi - 4):hi]:
            last = ""
            for j in range(width):
                c = r[j] if j < len(r) else None
                if isinstance(c, str) and c.strip():
                    last = c.strip()
                elif c is not None:
                    last = str(c)
                lab[j] += " " + last if last else ""
        qty = [j for j, c in enumerate(rows[hi]) if isinstance(c, str) and c.strip() == "Lượng"]
        num = lambda j: cof[j] if j < len(cof) and isinstance(cof[j], (int, float)) else None
        m = ytd = None
        for j in qty:
            L = lab[j].lower()
            if "%" in L or "so với" in L:
                continue
            if (re.search(r"\d+\s*th[áa]ng", L) or re.search(r"qu[ýy]\s+i\b(?!i)", L) or re.search(r"^\W*(?:(?:ước tính|sơ bộ|chính thức|thực hiện)\s+)?(?:cả\s+)?n[ăa]m\s+20\d\d", L.strip())) and ytd is None:
                ytd = j
            elif re.search(r"th[áa]ng\s*\d+", L) and m is None:
                m = j
        if ytd is None and m is None:
            continue
        # a January report has only the month; build_series uses it as the year to date then
        return (num(m) if m is not None else None), (num(m + 1) if m is not None else None), \
            (num(ytd) if ytd is not None else None), (num(ytd + 1) if ytd is not None else None)
    return None


def build_series(rows):
    by = {(int(r["year"]), int(r["month"])): r for r in rows}
    out = []
    for (y, m), r in sorted(by.items()):
        prev = by.get((y, m - 1))
        f = lambda k: float(r[k]) if r[k] not in ("", None) else None
        kt = None
        if m == 1:
            kt, usd, src = (f("ytd_kt"), f("ytd_usd_m"), "year to date") if f("ytd_kt") is not None else (f("m_kt"), f("m_usd_m"), "first estimate")
        elif prev and f("ytd_kt") is not None and (prev["ytd_kt"] not in ("", None) or (m == 2 and prev["m_kt"] not in ("", None))):
            pk, pu = ("ytd_kt", "ytd_usd_m") if prev["ytd_kt"] not in ("", None) else ("m_kt", "m_usd_m")
            kt, src = f("ytd_kt") - float(prev[pk]), "year to date less previous report"
            usd = f("ytd_usd_m") - float(prev[pu]) if f("ytd_usd_m") is not None and prev[pu] not in ("", None) else None
            fe = f("m_kt")
            if kt <= 0 or (fe and not 0.33 * fe <= kt <= 3 * fe):
                kt = None  # the year-to-date columns don't line up; fall back to the first estimate
        if kt is None:
            kt, usd, src = f("m_kt"), f("m_usd_m"), "first estimate"
        if kt is None:
            continue
        out.append({"month": f"{y}-{m:02d}", "k_t": round(kt, 1), "usd_m": round(usd, 1) if usd is not None else "",
                    "usd_t": round(usd / kt * 1000) if usd and kt else "", "first_est_k_t": round(f("m_kt"), 1) if f("m_kt") is not None else "",
                    "ytd_k_t": round(f("ytd_kt"), 1) if f("ytd_kt") is not None else "", "basis": src})
    return out


def save(rows, state):
    rows.sort(key=lambda r: (int(r["year"]), int(r["month"])))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS); w.writeheader(); w.writerows(rows)
    ser = build_series(rows)
    with open(SERIES, "w", newline="") as f:
        w = csv.DictWriter(f, ["month", "k_t", "usd_m", "usd_t", "first_est_k_t", "ytd_k_t", "basis"]); w.writeheader(); w.writerows(ser)
    STATE.write_text(json.dumps(state, indent=0))
    return ser


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=9, help="time budget; the next run carries on")
    a = ap.parse_args()
    t0 = time.time()
    state = json.loads(STATE.read_text()) if STATE.exists() else {"read": []}
    rows = []
    if OUT.exists():
        with open(OUT) as f:
            rows = list(csv.DictReader(f))
    have = {(int(r["year"]), int(r["month"])) for r in rows}
    reps = reports()
    print(f"NSO: {len(reps)} reports listed", flush=True)
    for rp in sorted(reps, key=lambda x: x["date"]):
        if rp["link"] in state["read"] or rp["ym"] in have or rp["ym"][0] < 2016:
            continue  # reports before 2016 carry no coffee row in an Excel annex
        if time.time() - t0 > a.minutes * 60:
            print("  (time budget reached; the next run carries on)"); break
        r = get(rp["link"])
        if r is None or r.status_code != 200:
            continue
        files = [x for x in dict.fromkeys(re.findall(r'href="([^"]+/wp-content/uploads/[^"]+\.xlsx)"', r.text, re.I))]
        got = None
        for x in files:
            f = get(x)
            if f is None or f.status_code != 200:
                continue
            try:
                got = coffee_row(f.content)
            except Exception as e:
                print("  xlsx", x[-60:], str(e)[:100])
            if got:
                break
        state["read"].append(rp["link"])
        y, m = rp["ym"]
        if not got or (got[0] is None and got[2] is None):
            print("  no coffee row:", rp["title"][:80]); save(rows, state); continue
        if got[0] is not None and got[2] is not None and got[2] < got[0] * 0.99:
            print("  year-to-date below month, skipped:", rp["title"][:80], got); save(rows, state); continue
        rd = lambda v: "" if v is None else round(v, 3)
        rows.append({"year": y, "month": m, "kind": "monthly report", "m_kt": rd(got[0]), "m_usd_m": rd(got[1]),
                     "ytd_kt": rd(got[2]), "ytd_usd_m": rd(got[3]), "published": rp["date"], "file": files[0].rsplit("/", 1)[-1] if files else ""})
        have.add((y, m))
        save(rows, state)
        print(f"  {y}-{m:02d}: month {got[0]} kt, YTD {got[2]} kt", flush=True)
        time.sleep(1)
    ser = save(rows, state)
    print(f"Vietnam exports: {len(rows)} reports, {len(ser)} months, latest {ser[-1]['month'] if ser else '-'}")
    if not ser:
        sys.exit(1)


if __name__ == "__main__":
    main()
