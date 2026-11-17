"""ICE files kept as combined history (called by pipelines/ice_inbox.py; one code path for the back-fill and for uploads).

Each kind is recognised by its content and appended to one combined file. A re-upload of the same report date (or month)
replaces that date's rows, so files can be dropped again safely.

  Coffee "C" certified stock aging report (monthly .xls)       -> data/coffee/ice_aging_history.csv
  Coffee "C" end-of-month certified stocks by port since 1996  -> data/coffee/ice_certs_eom_by_port.csv
  Coffee "C" certified warehouse stock report (daily .xls)     -> data/coffee/ice_certs_daily_detail.csv (all sections)
  Coffee grading summary analysis (monthly PDF)                -> data/coffee/ice_grading_monthly.csv
  Cocoa certified stock report (daily .xls)                    -> data/cocoa/ice_certs_daily.csv
  Cocoa grading results with discounts (monthly .xls)          -> data/cocoa/ice_grading_monthly.csv (monthly totals)
  Coffee "C" licensed warehouses list (PDF)                    -> data/coffee/ref/licensed_warehouses.csv (no contacts)
  Coffee "C" warehouse storage and handling rates (PDF)        -> data/coffee/ref/warehouse_rates.csv

The newest original of each kind is kept in data/ice_raw/latest/ for re-checks (not the warehouse list, the rates sheet
or the end-of-month file, which print contact details; their CSVs hold the content).
"""
import io, json, re, shutil, subprocess, tempfile
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
OUT = {
    "kc_aging": D / "coffee" / "ice_aging_history.csv",
    "kc_eom": D / "coffee" / "ice_certs_eom_by_port.csv",
    "kc_daily": D / "coffee" / "ice_certs_daily_detail.csv",
    "kc_grading": D / "coffee" / "ice_grading_monthly.csv",
    "cc_certs": D / "cocoa" / "ice_certs_daily.csv",
    "cc_grading": D / "cocoa" / "ice_grading_monthly.csv",
    "kc_warehouses": D / "coffee" / "ref" / "licensed_warehouses.csv",
    "kc_rates": D / "coffee" / "ref" / "warehouse_rates.csv",
}
LABEL = {
    "kc_aging": "Coffee certs: aging profile (monthly)",
    "kc_eom": "Coffee certs: end-of-month stocks by port since 1996",
    "kc_grading": "Coffee grading summary (monthly)",
    "cc_certs": "Cocoa certs: certified stock and grading (daily)",
    "cc_grading": "Cocoa grading results with discounts (monthly)",
    "kc_warehouses": "Coffee licensed warehouses list",
    "kc_rates": "Coffee warehouse storage and handling rates",
}
LATEST = D / "ice_raw" / "latest"
NO_RAW = {"kc_warehouses", "kc_rates", "kc_eom"}   # these originals print contact e-mail addresses; their CSVs hold the content
MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


class Bad(Exception):
    """A recognised file that could not be read."""


# ---------------- small helpers ----------------
def mdy(s):
    """'10/30/2026', 'Nov 16, 2026' or a datetime -> 'YYYY-MM-DD', else None."""
    if hasattr(s, "strftime"):
        return s.strftime("%Y-%m-%d")
    s = str(s or "")
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", s)
    if m:
        y = int(m.group(3)); y += 2000 if y < 100 else 0
        return f"{y}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    m = re.search(r"\b([A-Za-z]{3})[a-z]*\.? (\d{1,2}),? (\d{4})", s)
    if m and m.group(1).lower() in MON:
        return f"{m.group(3)}-{MON[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    return None


def n(v):
    """Number from a cell ('1,594', 18037.0, '-', '') -> int/float or None."""
    if v is None or (isinstance(v, float) and v != v):
        return None
    s = str(v).replace(",", "").replace("$", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").strip()
    if s in ("", "-"):
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    x = -x if neg else x
    return int(x) if x.is_integer() else x


def txt(v):
    return "" if v is None or (isinstance(v, float) and v != v) else str(v).strip()


def sheets(data):
    return pd.read_excel(io.BytesIO(data), header=None, sheet_name=None, dtype=object)


def upsert(path, new, key, sort):
    """Replace the rows of `path` whose `key` value appears in `new`, then add `new`. Returns rows written for the key(s)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old = pd.read_csv(path, dtype={key: str}, keep_default_na=False)
        old = old[~old[key].isin(set(new[key].astype(str)))]
        new = pd.concat([old, new.astype({key: str})], ignore_index=True)
    new = new.sort_values(sort, kind="stable")
    for c in new.columns:   # whole numbers stay whole after a merge with blanks
        if new[c].dtype == float and new[c].dropna().apply(float.is_integer).all():
            new[c] = new[c].astype("Int64")
    new.to_csv(path, index=False)
    return new


def keep_latest(src, kind, d):
    """Keep one original per kind (the newest report date) in data/ice_raw/latest/."""
    if kind in NO_RAW or src is None:
        return None
    LATEST.mkdir(parents=True, exist_ok=True)
    idx_p = LATEST / "index.json"
    idx = json.loads(idx_p.read_text()) if idx_p.exists() else {}
    cur = idx.get(kind)
    if cur and cur["report_date"] > d:
        return cur["file"]
    if cur and (LATEST / Path(cur["file"]).name).exists():
        (LATEST / Path(cur["file"]).name).unlink()
    name = f"{kind}{Path(src).suffix.lower()}"
    shutil.copyfile(src, LATEST / name)
    idx[kind] = {"report_date": d, "file": f"data/ice_raw/latest/{name}", "original_name": Path(src).name}
    idx_p.write_text(json.dumps(dict(sorted(idx.items())), indent=1))
    return idx[kind]["file"]


# ---------------- recognising ----------------
def classify_table(rows):
    """rows: list of lists of strings (all sheets). Returns info dict for a kind handled here, or None."""
    head = " ".join(" ".join(r) for r in rows[:8]).upper()
    if "CERTIFIED STOCK AGING" in head or (any(r and r[0].strip().lower().startswith("days") for r in rows[:8])
                                             and "AS OF DELIVERY" in head):
        return {"kind": "kc_aging", "sym": "KC"}
    if "END OF MONTH" in head and "COFFEE" in head and "STOCKS BY PORT" in head:
        return {"kind": "kc_eom", "sym": "KC"}
    if "COCOA CERTIFIED STOCK BY PORT" in head:
        return {"kind": "cc_certs", "sym": "CC"}
    if "COCOA GRADING RESULTS FOR" in head:
        return {"kind": "cc_grading", "sym": "CC"}
    return None


def ocr_text(p, dpi=300, psm=6):
    """Text of an image-only PDF: page images with table rules removed, then tesseract. '' if the tools are missing."""
    if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
        return ""
    import numpy as np
    from PIL import Image
    from scipy.ndimage import binary_opening
    out = []
    with tempfile.TemporaryDirectory() as t:
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(p), f"{t}/pg"], capture_output=True, timeout=300)
        for img in sorted(Path(t).glob("pg*.png")):
            a = np.array(Image.open(img).convert("L"))
            dark = a < 150
            b = a.copy()
            b[binary_opening(dark, structure=np.ones((1, dpi // 5))) | binary_opening(dark, structure=np.ones((dpi // 5, 1)))] = 255
            b[(a > 60) & (a < 200)] = 255
            Image.fromarray(b).save(img)
            r = subprocess.run(["tesseract", str(img), "-", "--psm", str(psm)], capture_output=True, text=True, timeout=300)
            out.append(r.stdout)
    return "\f".join(out)


def classify_pdf(p, text):
    """text: pdftotext -layout of the whole file ('' for image-only PDFs)."""
    t, ocr = text, False
    if not re.search(r"\S", t):
        t, ocr = ocr_text(p), True
    if "Grading Summary Analysis" in t and ("Country of Origin" in t or "No Original or Appeal Grading" in t):
        return {"kind": "kc_grading", "sym": "KC", "text": t, "ocr": ocr}
    up = t.upper()
    if "COFFEE" in up and "STORAGE & HANDLING RATES" in up:
        return {"kind": "kc_rates", "sym": "KC", "text": t}
    if "LICENSED COFFEE 'C' WAREHOUSES" in up.replace("’", "'") and "SQ" in up:
        return {"kind": "kc_warehouses", "sym": "KC", "text": t}
    return None


# ---------------- coffee: aging ----------------
def kc_aging(data, fname):
    rows = [[txt(v) for v in r] for df in sheets(data).values() for r in df.itertuples(index=False)]
    deliv = next((mdy(" ".join(r)) for r in rows[:8] if "as of delivery" in " ".join(r).lower()), None)
    d = next((mdy(" ".join(r)) for r in rows if re.match(r"(?i)as of:", " ".join(r).strip())), None)
    if not d:   # file name (odd names like coffee_aging_2023131 = 2023-01-31)
        m = re.search(r"(20\d{2})(\d{1,2})(\d{2})", fname)
        d = f"{m.group(1)}-{int(m.group(2)):02d}-{m.group(3)}" if m else None
    if not d:
        raise Bad("aging report: no 'As of' date")
    hi = next((i for i, r in enumerate(rows) if r and r[0].lower().startswith("days")), None)
    if hi is None:
        raise Bad("aging report: no Days header")
    body = [r for r in rows[hi + 1:] if re.match(r"\d+\s*to\s*\d+", r[0])]
    trow = next((r for r in rows[hi + 1:] if r[0].lower().startswith("total")), None)
    if not body or trow is None:
        raise Bad(f"aging report {d}: no rows or no Total row")
    vcols = [j for j in range(1, max(len(r) for r in body)) if any(n(r[j] if j < len(r) else None) is not None for r in body + [trow])]
    names = [x.strip().upper() for x in rows[hi][1:] if x.strip()]
    if not names or names[-1] != "TOTAL":
        raise Bad(f"aging report {d}: no Total column in the header")
    jt = vcols[-1]
    ports = names[:-1]
    short = len(names) != len(vcols)
    sums = [int(sum(n(r[j]) or 0 for r in body)) for j in vcols[:-1]]
    tots = [int(n(trow[j]) or 0) for j in vcols[:-1]]
    if sums != tots or sum(tots) != int(n(trow[jt]) or 0):
        raise Bad(f"aging report {d}: rows do not add to the Total row")
    eom = OUT["kc_eom"]
    if short:   # ICE once dropped a port name from the header (Dec 2024): name the columns from month-end stocks by port
        e = pd.read_csv(eom, dtype={"date": str}) if eom.exists() else pd.DataFrame(columns=["date", "port", "bags"])
        e = e[e.date == d].set_index("port").bags.dropna().astype(int).to_dict()
        if not e:
            raise Bad(f"aging report {d}: header has {len(names)} names for {len(vcols)} value columns")
        if True:
            fixed, used = [], set()
            for t in tots:
                c = [pt for pt, v in e.items() if v == t and pt != "TOTAL" and pt not in used]
                fixed.append(c[0] if len(c) == 1 else None); used.update(c[:1])
            if None in fixed:
                raise Bad(f"aging report {d}: port names in the header do not match month-end stocks by port")
            print(f"::warning::aging report {d}: header port names {ports} did not match the columns; set from month-end stocks by port: {fixed}")
            ports = fixed
    out = []
    for r in body:
        m = re.match(r"(\d+)\s*to\s*(\d+)", r[0])
        for pt, j in zip(ports, vcols[:-1]):
            b = n(r[j] if j < len(r) else None)
            if b:
                out.append([d, deliv, f"{int(m.group(1))}-{int(m.group(2))}", int(m.group(1)), int(m.group(2)), pt, b])
    df = pd.DataFrame(out, columns=["date", "delivery", "age_days", "age_min", "age_max", "port", "bags"])
    upsert(OUT["kc_aging"], df, "date", ["date", "age_min", "port"])
    return d, f"{len(df)} cells, {int(df.bags.sum()):,} bags (age as of the {deliv} delivery)"


# ---------------- coffee: end-of-month stocks by port ----------------
PORTS_EOM = {"NEW YORK": "NEW YORK", "NEW ORLEANS": "NEW ORLEANS", "HOUSTON": "HOUSTON", "MIAMI": "MIAMI", "ANTWERP": "ANTWERP",
             "HAMBURG": "HAMBURG / BREMEN", "BARCELONA": "BARCELONA", "VIRGINIA": "VIRGINIA", "TOTAL": "TOTAL"}


def loose_date(s, prev):
    """Hand-typed month-end labels in ICE's history file ('Fenruary 28,2011', 'Sept.30,2011', 'October 31,20217')."""
    import difflib
    m = re.match(r"\s*([A-Za-z]+)\.?\s*(\d{1,2})\s*,?\s*(\d{4,5})\s*$", s)
    if not m:
        return None
    names = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
    w = m.group(1).lower()
    hit = next((i for i, x in enumerate(names) if x.startswith(w[:4]) and len(w) >= 3), None)
    if hit is None:
        c = difflib.get_close_matches(w, names, n=1, cutoff=0.6)
        if not c:
            return None
        hit = names.index(c[0])
    mo, day, y = hit + 1, int(m.group(2)), int(m.group(3))
    if not 1990 <= y <= 2100:   # typo in the year: follow on from the previous month-end
        if not prev:
            return None
        py, pm = int(prev[:4]), int(prev[5:7])
        y = py + (1 if mo < pm else 0)
    return f"{y}-{mo:02d}-{day:02d}"


def kc_eom(data, fname):
    rows = [[v for v in r] for df in sheets(data).values() for r in df.itertuples(index=False)]
    hi = next((i for i, r in enumerate(rows) if sum(any(k in txt(c).upper() for k in ("NEW YORK", "HOUSTON", "ANTWERP")) for c in r) >= 3), None)
    if hi is None:
        raise Bad("end-of-month report: no port header")
    cols = {}
    for j, c in enumerate(rows[hi]):
        u = txt(c).upper()
        k = next((v for kk, v in PORTS_EOM.items() if kk in u), None)
        if k:
            cols[j] = k
    out, prev = [], None
    for r in rows[hi + 1:]:
        d = next((mdy(c) for c in r[:3] if hasattr(c, "strftime") or re.search(r"\d+/\d+/\d{4}", txt(c))), None) or \
            loose_date(txt(r[1]) if len(r) > 1 else "", prev)
        if not d:
            continue
        prev = d
        for j, pt in cols.items():
            v = r[j] if j < len(r) else None
            out.append([d, pt, n(v)])
    if not out:
        raise Bad("end-of-month report: no month rows")
    df = pd.DataFrame(out, columns=["date", "port", "bags"])
    # ports not yet licensed show '-': keep them blank; a port with no column at all is not listed
    chk = df[df.port != "TOTAL"].groupby("date").bags.sum(min_count=1)
    tot = df[df.port == "TOTAL"].set_index("date").bags
    bad = [(d, int(chk[d]), tot[d]) for d in tot.index if tot[d] is not None and tot[d] == tot[d] and int(chk.get(d, 0) or 0) != int(tot[d])]
    if bad:
        print(f"::warning::end-of-month coffee stocks: {len(bad)} month(s) where ports do not add to the total, e.g. {bad[:3]}")
    df["bags"] = df.bags.astype("Int64")
    upsert(OUT["kc_eom"], df, "date", ["date", "port"])
    return max(df.date), f"{df.date.nunique()} month-ends {min(df.date)} to {max(df.date)}"


# ---------------- coffee: daily certified stock report, every section ----------------
KC_SECTIONS = [("TOTAL BAGS CERTIFIED", "certified"), ("TRANSITION BAGS", "transition"), ("PENDING GRADING", "pending"),
               ("BAGS PASSED GRADING", "passed"), ("BAGS FAILED GRADING", "failed"), ("FLAGGED FOR REBAGGING", "rebagging")]
KC_DAILY_COLS = ["date", "origin", "port", "certified", "transition", "pending", "passed", "failed", "rebagging", "pass_rate"]


def kc_daily(data, d):
    """All sections of one daily coffee certs report -> data/coffee/ice_certs_daily_detail.csv (one row per origin and port)."""
    df = pd.read_excel(io.BytesIO(data), header=None, dtype=object)
    rows, sec, ports = [], None, None
    for r in df.itertuples(index=False):
        c0 = txt(r[0]); up = c0.upper()
        hit = next((s for k, s in KC_SECTIONS if up.startswith(k)), None)
        if hit or up.startswith("TODAY'S GRADING"):
            sec, ports = hit, None
            continue
        cells = [txt(x) for x in r[1:]]
        if not c0 and "Total" in cells:
            ports = [x or None for x in cells]
            continue
        if sec and ports and c0 and not up.startswith("TOTAL IN BAGS"):
            for p, v in zip(ports, r[1:]):
                b = n(v)
                if p and p != "Total" and b:
                    rows.append((sec, c0, p, int(b)))
    if not any(s == "certified" for s, *_ in rows):
        raise Bad(f"coffee certs report {d}: no certified bags")
    long = pd.DataFrame(rows, columns=["section", "origin", "port", "bags"])
    w = long.pivot_table(index=["origin", "port"], columns="section", values="bags", aggfunc="sum").reset_index()
    for c in KC_DAILY_COLS[3:9]:
        if c not in w:
            w[c] = 0
    w = w.fillna(0)
    g = w.passed + w.failed
    w["pass_rate"] = (w.passed / g.where(g > 0)).round(4)
    w.insert(0, "date", d)
    for c in KC_DAILY_COLS[3:9]:
        w[c] = w[c].astype(int)
    upsert(OUT["kc_daily"], w[KC_DAILY_COLS], "date", ["date", "origin", "port"])
    return int(w.certified.sum()), int(w.pending.sum())


# ---------------- coffee: grading summary analysis (PDF) ----------------
ROWNUM = r"(-?[\d,]+)\s+(-?[\d,]+)\s+(-?[\d,]+)\s+(\d+\.\d+)\s*%?"


def kc_grading(text, fname):
    pages = [pg for pg in re.split(r"\f|(?=Grading Summary Analysis)", text) if "Start Date" in pg]
    out = []
    for pg in pages:
        m = re.search(r"Start Date:\s*(\d+/\d+/\d{4})\s*-\s*End Date:\s*(\d+/\d+/\d{4})", pg)
        if not m:
            continue
        s, e = mdy(m.group(1)), mdy(m.group(2))
        scope = "month" if s[:7] == e[:7] else "year_to_date"
        part = "origin"
        if "No Original or Appeal Grading" in pg:
            for stage in ("original", "appeal"):
                out.append([e[:7], s, e, scope, "total", "Total", stage, 0, 0, 0, 0.0])
            continue
        for line in pg.splitlines():
            l = line.strip()
            if re.match(r"(?i)^ORIGINAL\b", l):
                part = "criterion"
            mm = re.match(r"^([A-Za-z][A-Za-z .,'()/-]*?)\s+" + ROWNUM + r"\s+" + ROWNUM + r"\s*$", l)
            m2 = None if mm else re.match(r"^([A-Za-z][A-Za-z .,'()/-]*?)" + r"\s+(-?[\d,]+)" * 7 + r"\s+([\d.]+)\s*%?\s*$", l)
            if not (mm or m2):
                continue
            name = (mm or m2).group(1).strip()
            if name.lower() in ("pass", "fail"):
                continue
            if mm:
                v = [n(x) for x in mm.groups()[1:]]
            else:   # layout used from late 2025: original pass/fail, appeal pass/fail/total, combined pass/fail/%
                op, of, ap, af, at = [n(x) for x in m2.groups()[1:6]]
                pc = lambda a, b: round(100 * a / (a + b), 2) if a + b else 0.0
                v = [op, of, op + of, pc(op, of), ap, af, at, pc(ap, af)]
            for stage, (p_, f_, t_, pct) in (("original", v[0:4]), ("appeal", v[4:8])):
                out.append([e[:7], s, e, scope, "total" if name.lower() == "total" else part, name, stage, p_, f_, t_, pct])
    if not out:
        raise Bad("grading summary: no table rows could be read")
    df = pd.DataFrame(out, columns=["month", "period_start", "period_end", "scope", "row_type", "name", "stage", "passed", "failed", "total", "pass_pct"])
    df = df.drop_duplicates(["month", "scope", "row_type", "name", "stage"], keep="last")
    bad = df[(df.passed + df.failed != df.total)]
    if len(bad):
        raise Bad(f"grading summary {df.month.iloc[0]}: pass + fail != total on {len(bad)} row(s), e.g. {bad.iloc[0][['name','stage','passed','failed','total']].tolist()}")
    off = df[(df.total > 0) & ((100 * df.passed / df.total.where(df.total > 0) - df.pass_pct).abs() > 0.02)]
    if len(off):
        raise Bad(f"grading summary {df.month.iloc[0]}: pass % does not match pass/total on {len(off)} row(s), e.g. {off.iloc[0][['name','stage','passed','total','pass_pct']].tolist()}")
    for (mo, sc, st), g in df.groupby(["month", "scope", "stage"]):
        t = g[g.row_type == "total"]
        cr = g[g.row_type == "criterion"]
        if st == "original" and len(t) and len(cr) and (cr.total != t.total.iloc[0]).any():
            raise Bad(f"grading summary {mo} {sc}: a criterion row total differs from the graded total {int(t.total.iloc[0])}")
        if len(t) and int(g[g.row_type == "origin"].total.sum()) != int(t.total.iloc[0]):
            raise Bad(f"grading summary {mo} {sc} {st}: origins add to {int(g[g.row_type == 'origin'].total.sum())}, total row {int(t.total.iloc[0])}")
    df["key"] = df.month + "|" + df.scope
    keys = set(df.key)
    old = pd.read_csv(OUT["kc_grading"], dtype=str, keep_default_na=False) if OUT["kc_grading"].exists() else None
    if old is not None:
        old = old[~(old.month + "|" + old.scope).isin(keys)]
        df = pd.concat([old, df.drop(columns="key")], ignore_index=True)
    else:
        df = df.drop(columns="key")
    order = {"origin": 0, "total": 2, "criterion": 1}
    df = df.assign(_o=df.row_type.map(order)).sort_values(["month", "scope", "stage", "_o", "name"]).drop(columns="_o")
    OUT["kc_grading"].parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT["kc_grading"], index=False)
    mo = max(k.split("|")[0] for k in keys)
    return mo, f"{len(keys)} table(s): " + ", ".join(sorted(keys))


# ---------------- cocoa: daily certified stock report ----------------
def cc_certs(data, fname):
    rows = [[v for v in r] for df in sheets(data).values() for r in df.itertuples(index=False)]
    T = [[txt(c) for c in r] for r in rows]
    d = next((mdy(" ".join(r)) for r in T[:4] if " ".join(r).lower().startswith("date")), None) or \
        next((mdy(" ".join(r)) for r in T if " ".join(r).lower().strip().startswith("as of")), None)
    if not d:
        raise Bad("cocoa certs report: no date")
    out, mode, ports = [], None, None
    for r in T:
        j0 = " ".join(r).upper()
        if "CERTIFIED STOCK BY PORT" in j0:
            mode, ports = "certified", None; continue
        if "GRADING RESULTS IN BAGS" in j0:
            mode, ports = "grading", None; continue
        if "TOTAL BAGS REPORTED BY" in j0:
            mode = "warehouse"; continue
        if mode == "certified":
            if not r[0] and any(r[1:]):
                ports = r; continue
            if ports and r[0] and not r[0].lower().startswith("total"):
                m = re.match(r"(.*?)\s+Group\s+([A-Z])\s*$", r[0])
                org, grp = (m.group(1).strip(), m.group(2)) if m else (r[0], "")
                half = next((j for j in range(2, len(r)) if r[j] and r[j] == r[0]), None)   # the lots table repeats the origin
                for j in range(1, half or len(r)):
                    if ports[j] and ports[j] != "Total" and n(r[j]):
                        lots = n(r[half + (j - 0)]) if half and half + j < len(r) else None
                        out.append([d, "certified", org, grp, ports[j], n(r[j]), lots])
        elif mode == "grading":
            if r[0].lower() == "origin":
                continue
            if r[0] and not r[0].lower().startswith("total") and any(r[1:3]):
                half = next((j for j in range(3, len(r)) if r[j] == r[0]), None)
                lp = n(r[half + 1]) if half else None
                lq = n(r[half + 2]) if half else None
                if n(r[1]):
                    out.append([d, "pending_grading", r[0], "", "", n(r[1]), lp])
                if n(r[2]):
                    out.append([d, "passed_grading", r[0], "", "", n(r[2]), lq])
        elif mode == "warehouse":
            if r[0].lower().startswith("port of") and n(r[1]):
                pt = {"port of delaware river": "DR", "port of new york": "NY"}.get(r[0].lower().strip(), r[0])
                out.append([d, "warehouse_total", "", "", pt, n(r[1]), None])
            if r[0].upper().startswith("GRAND TOTAL"):
                mode = None
    if not any(x[1] == "certified" for x in out):
        raise Bad(f"cocoa certs report {d}: no certified rows")
    df = pd.DataFrame(out, columns=["date", "section", "origin", "growth_group", "port", "bags", "lots"])
    df["lots"] = df.lots.astype("Int64")
    trow = next((r for r in T if r[0] == "Total Bags"), None)
    hdr = next((r for r in T if not r[0] and "Total" in r[1:]), None)
    tot = n(trow[hdr.index("Total")]) if trow and hdr else None
    s = int(df[df.section == "certified"].bags.sum())
    if tot is not None and s != tot:
        raise Bad(f"cocoa certs report {d}: certified rows add to {s}, report total {tot}")
    upsert(OUT["cc_certs"], df, "date", ["date", "section", "origin", "growth_group", "port"])
    return d, f"{s:,} bags certified; {int(df[df.section == 'pending_grading'].bags.sum()):,} pending grading"


# ---------------- cocoa: monthly grading results with discounts ----------------
def cc_grading(data, fname):
    df = next(iter(sheets(data).values()))
    T = [[txt(c) for c in r] for r in df.itertuples(index=False)]
    head = " ".join(T[0])
    m = re.search(r"(?i)for\s+(\d+/\d+/\d{4})\s+through\s+(\d+/\d+/\d{4})", head)
    if not m:
        raise Bad("cocoa grading: no period in the title")
    s, e = mdy(m.group(1)), mdy(m.group(2))
    hi = next((i for i, r in enumerate(T) if r and r[0].lower().startswith("date graded")), None)
    if hi is None:
        raise Bad(f"cocoa grading {e[:7]}: no header")
    h = [re.sub(r"\s+", " ", x).lower() for x in T[hi]]
    c = lambda pat: next((j for j, x in enumerate(h) if re.search(pat, x)), None)
    jd, jp, jo, jc, jg, jw, js, ji, jm = c("date graded"), c("^port"), c("^origin"), c("^class"), c("group premium"), c("weight"), c("slate"), c("initial"), c("^mt$")
    recs = []
    for r in df.iloc[hi + 1:].itertuples(index=False):
        dg = mdy(r[jd]) if r[jd] is not None and r[jd] == r[jd] else None
        if not dg:
            continue
        recs.append({"port": txt(r[jp]), "origin": txt(r[jo]), "class": txt(r[jc]), "grade_type": {"I": "initial", "R": "regrade"}.get(txt(r[ji]).upper()[:1], txt(r[ji])),
                     "group_premium": n(r[jg]), "weight_disc": n(r[jw]) or 0, "slate_disc": n(r[js]) or 0, "mt": n(r[jm]) if jm is not None else None})
    if not recs:
        out = pd.DataFrame([[e[:7], s, e, "", "", "", "", 0, None, None, None, None, None, None]],
                           columns=["month", "period_start", "period_end", "port", "origin", "class", "grade_type", "chops", "tonnes",
                                    "group_premium_usd_t", "avg_weight_disc_pct", "chops_with_weight_disc", "chops_with_slate_disc", "avg_slate_disc_usd_t"])
    else:
        x = pd.DataFrame(recs)
        g = x.groupby(["port", "origin", "class", "grade_type"], dropna=False)
        out = g.agg(chops=("origin", "size"), tonnes=("mt", lambda v: round(v.sum(), 1) if v.notna().any() else None),
                    group_premium_usd_t=("group_premium", lambda v: v.mode().iloc[0] if v.notna().any() else None),
                    avg_weight_disc_pct=("weight_disc", lambda v: round(v.mean(), 3)),
                    chops_with_weight_disc=("weight_disc", lambda v: int((v > 0).sum())),
                    chops_with_slate_disc=("slate_disc", lambda v: int((v > 0).sum())),
                    avg_slate_disc_usd_t=("slate_disc", lambda v: round(v.mean(), 2))).reset_index()
        out.insert(0, "period_end", e); out.insert(0, "period_start", s); out.insert(0, "month", e[:7])
    upsert(OUT["cc_grading"], out, "month", ["month", "port", "origin", "class", "grade_type"])
    return e[:7], f"{len(recs)} graded chops in {out.origin.nunique()} origin(s), period {s} to {e}"


# ---------------- coffee: reference PDFs ----------------
def kc_rates(text, fname):
    eff = re.search(r"EFFECTIVE:\s*([A-Za-z]+ \d{1,2},? \d{4})\s*-\s*([A-Za-z]+ \d{1,2},? \d{4})", text)
    s, e = (mdy(eff.group(1)), mdy(eff.group(2))) if eff else (None, None)
    out, port = [], None
    money = r"\$\s*\(?\s*-?[\d.]+\)?|\$\(\s*[\d.]+\)"
    for line in text.splitlines():
        l = line.strip()
        pm = re.match(r"PORT OF ([A-Z /]+):", l)
        if pm:
            port = pm.group(1).strip(); continue
        if port and "$" in l:
            name = re.split(r"\s{2,}\$", l)[0].strip()
            vals = [n(v.replace("$", "").replace(" ", "")) for v in re.findall(money, l)]
            if len(vals) == 5 and name:
                out.append([s, e, port, name] + vals)
    if not out:
        raise Bad("storage and handling rates: no warehouse rows")
    df = pd.DataFrame(out, columns=["effective_from", "effective_to", "port", "warehouse", "storage_usd_bag_month", "rca_usd_bag",
                                    "load_out_usd_bag", "oca_usd_bag", "rebagging_usd_bag"])
    upsert(OUT["kc_rates"], df.astype({"effective_from": str}), "effective_from", ["effective_from", "port", "warehouse"])
    return s or date.today().isoformat(), f"{len(df)} warehouses, {df.port.nunique()} ports (effective {s} to {e})"


def kc_warehouses(text, fname):
    eff = re.search(r"Effective ([A-Za-z]+ \d{1,2},? \d{4})", text)
    d = mdy(eff.group(1)) if eff else date.today().isoformat()
    out, port, ptot = [], None, {}
    for line in text.splitlines():
        l = line.strip()
        pm = re.match(r"PORT of ([A-Za-z /,]+?)\s{2,}", l)
        if pm:
            port = pm.group(1).strip().upper(); continue
        tm = re.match(r"Port of (.+?) Total Licensed Sq\.? ?Ft\.?\s+([\d,]+)", l)
        if tm:
            ptot[port] = n(tm.group(2)); continue
        wm = re.match(r"^(\S.*?)\s{3,}([A-Z]{4})\s+([\d,]{4,})\s*$", l)
        if port and wm and not re.match(r"(?i)(fax|phone|tel|contact)", wm.group(1)):
            out.append([d, port, wm.group(1).strip(), wm.group(2), n(wm.group(3))])
    if not out:
        raise Bad("licensed warehouses list: no warehouse rows")
    df = pd.DataFrame(out, columns=["effective", "port", "warehouse", "ecops_code", "licensed_sq_ft"])
    for pt, v in ptot.items():
        s = df[df.port == pt].licensed_sq_ft.sum()
        if v and s != v:
            print(f"::warning::licensed warehouses {pt}: rows add to {s:,} sq ft, list total {v:,}")
    upsert(OUT["kc_warehouses"], df, "effective", ["effective", "port", "warehouse"])
    return d, f"{len(df)} warehouses in {df.port.nunique()} ports, {int(df.licensed_sq_ft.sum()):,} sq ft"


# ---------------- entry point from ice_inbox ----------------
def handle(p, info):
    """Store one recognised file. Returns (report date, result dict)."""
    k = info["kind"]
    try:
        if k == "kc_grading" and info.get("ocr"):   # image-only PDF: retry other scan settings until the table checks pass
            err = None
            for dpi, psm in [(None, None), (300, 4), (400, 6), (400, 4), (500, 6), (350, 6)]:
                try:
                    d, note = kc_grading(info["text"] if dpi is None else ocr_text(p, dpi, psm), p.name)
                    note += " (read by OCR, table checks passed)"
                    break
                except Bad as x:
                    err = x
            else:
                raise err
        elif k in ("kc_grading", "kc_rates", "kc_warehouses"):
            d, note = {"kc_grading": kc_grading, "kc_rates": kc_rates, "kc_warehouses": kc_warehouses}[k](info["text"], p.name)
        else:
            d, note = {"kc_aging": kc_aging, "kc_eom": kc_eom, "cc_certs": cc_certs, "cc_grading": cc_grading}[k](p.read_bytes(), p.name)
    except Bad:
        raise
    except Exception as e:
        raise Bad(f"{LABEL[k]}: could not be read ({type(e).__name__}: {str(e)[:120]})")
    raw = keep_latest(p, k, d)
    res = {"stored": str(OUT[k].relative_to(ROOT)), "note": note}
    if raw:
        res["original"] = raw
    return d, res
