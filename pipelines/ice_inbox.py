"""ICE drop box: every file uploaded to inbox/ is identified by its content (not its name), stored where the desk reads it,
and the original archived or removed.

  ICE settlement reports (Options / Futures Daily Market Report, cotton, coffee, sugar No 11, cocoa; PDF)
      -> data/ice_staging/pdfs/<SYM>_YYYY_MM_DD.pdf (options) or <SYM>_YYYY_MM_DD-2.pdf (futures), listed in
         data/ice_staging/manifest.json. BMR-Com/softs--options- collects them from there and builds its CSVs.
  ICE cotton certificated stock reports (CSV or Excel): stock by delivery point, grade/staple, by warehouse,
      year of growth, strength -> data/cotton/ice/<type>_YYYY-MM-DD.csv in the desk's layout.
  ICE coffee "C" certified warehouse stock report (Excel) -> data/coffee/ice_certs_inbox.csv (same long layout as
      data/coffee/ice_certs.csv); days missing from the automatic series are added to it, days present are compared
      (data/coffee/ice_certs_check.json). The automatic series is never overwritten.
  ICE cotton "four months and older" report -> data/cotton/ice/four_months_older_YYYY-MM-DD.csv.
  Coffee aging, coffee end-of-month stocks by port, coffee grading summary (PDF), cocoa certified stock (daily),
      cocoa grading results with discounts (monthly), coffee licensed-warehouse list and storage/handling rates (PDF)
      -> one combined history file each (pipelines/ice_history.py). The daily coffee certs report also adds every
      section (pending, transition, passed/failed, rebagging) to data/coffee/ice_certs_daily_detail.csv.
  CEPEA/ESALQ arabica or robusta coffee index (xls from cepea.org.br, Portuguese or English page) -> data/coffee/
      brazil_physical_raw.csv and the Brazil physical histories (pipelines/brazil_physical.py); not an ICE file, same box.
  A .zip is opened and each file in it handled as above.
  Anything else -> inbox/unrecognised/ with the reason (run shows a warning; listed on the Data status tab).
  A file that is recognised but cannot be read -> inbox/unrecognised/ too, and the run fails.

Log of what arrived: data/ice_inbox/log.json. Originals: data/ice_raw/<date received>/ (PDFs 14 days, others 90 days;
settlement PDFs are not kept twice, the staged copy is the record). Staged PDFs are kept 14 days.
Usage: python pipelines/ice_inbox.py [files...]   (no arguments = everything in inbox/)
"""
import csv, hashlib, io, json, os, re, shutil, subprocess, sys, tempfile, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "inbox"
UNREC = INBOX / "unrecognised"
STAGE = ROOT / "data" / "ice_staging" / "pdfs"
MANIFEST = ROOT / "data" / "ice_staging" / "manifest.json"
RAW = ROOT / "data" / "ice_raw"
LOG = ROOT / "data" / "ice_inbox" / "log.json"
CT_ICE = ROOT / "data" / "cotton" / "ice"
KC_AUTO = ROOT / "data" / "coffee" / "ice_certs.csv"
KC_INBOX = ROOT / "data" / "coffee" / "ice_certs_inbox.csv"
KC_CHECK = ROOT / "data" / "coffee" / "ice_certs_check.json"
KEEP_PDF_DAYS, KEEP_OTHER_DAYS = 14, 90
SKIP = {"README.md", ".gitkeep"}

MARKETS = {"cotton no 2": "CT", "coffee c": "KC", "sugar no 11": "SB", "cocoa": "CC"}
MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
LABEL = {"options": "{} options settlement (ICE daily market report)", "futures": "{} futures settlement (ICE daily market report)",
         "ct_stock": "Cotton certs: stock by delivery point", "ct_grade": "Cotton certs: grade / staple",
         "ct_warehouse": "Cotton certs: stock by warehouse", "ct_yog": "Cotton certs: year of growth",
         "ct_strength": "Cotton certs: strength", "ct_four_months": "Cotton certs: four months and older",
         "kc_certs": "Coffee certs: certified warehouse stock",
         "cepea_arabica": "CEPEA/ESALQ arabica coffee index (cepea.org.br download)",
         "cepea_robusta": "CEPEA/ESALQ robusta (conilon) coffee index (cepea.org.br download)"}
sys.path.insert(0, str(ROOT / "pipelines"))
import ice_history  # noqa: E402
import ice_price_history  # noqa: E402
LABEL.update(ice_history.LABEL)
LABEL["price_history"] = "ICE historical prices workbook (first five contracts, daily)"
NAMES = {"CT": "Cotton", "KC": "Coffee", "SB": "Sugar No 11", "CC": "Cocoa"}


class Unrecognised(Exception):
    """Not a report this drop box knows."""


class ParseError(Exception):
    """A known report that could not be read; fails the run."""


# ---------------- readers ----------------
def pdf_text(p, first_page=False):
    args = ["pdftotext", "-layout"] + (["-l", "1"] if first_page else []) + [str(p), "-"]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=180)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def cell(v):
    """Excel/CSV cell as text: 18037.0 -> '18037', dates -> ISO."""
    if v is None:
        return ""
    if isinstance(v, float):
        if v != v:
            return ""
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return str(v).strip()


def table_rows(p, data):
    """All rows of a CSV / XLS / XLSX file as lists of strings (every sheet, one after another)."""
    if data[:4] == b"PK\x03\x04" or data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        import pandas as pd
        try:
            sheets = pd.read_excel(io.BytesIO(data), header=None, sheet_name=None, dtype=object)
        except Exception as e:
            raise Unrecognised(f"spreadsheet that could not be opened ({str(e)[:80]})")
        rows = []
        for df in sheets.values():
            rows += [[cell(v) for v in r] for r in df.itertuples(index=False)]
        return rows
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if "\x00" in text[:2000]:
        raise Unrecognised("binary file of an unknown kind")
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(text))]


def iso(s):
    """Date in ICE's formats -> YYYY-MM-DD, or None."""
    s = str(s or "").strip()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})[-/ ]([A-Za-z]{3})[A-Za-z]*[-/ ,]+(\d{4})", s)
    if m and m.group(2).lower() in MON:
        return f"{m.group(3)}-{MON[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"([A-Za-z]{3})[A-Za-z]*\.? (\d{1,2}),? (\d{4})", s)
    if m and m.group(1).lower() in MON:
        return f"{m.group(3)}-{MON[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", s)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


def num(s):
    s = str(s).replace(",", "").strip()
    if s in ("", "-"):
        return 0
    v = float(s)
    return int(v) if v.is_integer() else v


# ---------------- settlement PDFs ----------------
ROW_FUT = r"^\s*{}\s+[A-Z][a-z]{{2}}-\d{{2}}\s+[-\d.,]+"
ROW_OPT = r"^\s*{}\s+[A-Z][a-z]{{2}}-\d{{2}}\s+[\d.,]+\s+[CP]\s+[-\d.]+"


def classify_pdf(p):
    head = pdf_text(p, first_page=True)[:1500]
    m = re.search(r"(Options|Futures) Daily Market Report for ([A-Za-z0-9 .\"]+?)\s*\n", head)
    if not m:
        h = ice_history.classify_pdf(p, pdf_text(p))
        if h:
            return h
        title = next((l.strip() for l in head.splitlines() if l.strip()), "no text")
        raise Unrecognised(f"PDF that is not an ICE options/futures daily market report (starts: {title[:70]!r})")
    kind, mk = m.group(1).lower(), re.sub(r"[^a-z0-9 ]", "", m.group(2).lower()).strip()
    sym = MARKETS.get(mk)
    if not sym:
        raise Unrecognised(f"ICE {kind} report for {m.group(2).strip()!r}, a market this desk does not follow")
    d = iso(head[m.end():m.end() + 200])
    if not d:
        raise ParseError(f"{sym} {kind} report: no report date on the first page")
    text = pdf_text(p)
    n = len(re.findall((ROW_OPT if kind == "options" else ROW_FUT).format(sym), text, flags=re.M))
    if n == 0:
        raise ParseError(f"{sym} {kind} report {d}: no contract rows could be read")
    return {"kind": kind, "sym": sym, "date": d, "rows": n}


def handle_settlement(p, info):
    STAGE.mkdir(parents=True, exist_ok=True)
    name = f"{info['sym']}_{info['date'].replace('-', '_')}{'' if info['kind'] == 'options' else '-2'}.pdf"
    dst = STAGE / name
    if dst.exists() and dst.stat().st_size > p.stat().st_size:
        note = f"already staged a larger copy ({dst.stat().st_size:,} bytes); this {p.stat().st_size:,}-byte upload ignored"
    else:
        shutil.copyfile(p, dst)
        note = f"staged {info['rows']} contract rows for the options archive"
    if info["kind"] == "futures":
        extra = ice_price_history.add_futures_pdf(pdf_text(p), info["sym"], info["date"])
        if extra:
            note += "; " + extra
    return {"stored": f"data/ice_staging/pdfs/{name}", "note": note}, False   # original not archived (staged copy is the record)


# ---------------- cotton certs ----------------
def header_at(rows, test):
    for i, r in enumerate(rows[:40]):
        if test([c.lower() for c in r]):
            return i
    return None


def col(h, *pat):
    for i, x in enumerate(h):
        if any(re.search(p, x, re.I) for p in pat):
            return i
    return None


def report_dates(rows, i0, h):
    j = col(h, r"report\s*date", r"^date$")
    if j is None:
        return None
    ds = {iso(r[j]) for r in rows[i0 + 1:] if j < len(r) and r[j].strip()}
    ds.discard(None)
    if len(ds) > 1:
        raise ParseError(f"several report dates in one file: {sorted(ds)}")
    return ds.pop() if ds else None


def text_date(rows, i_hdr):
    """Report date printed above the table (title lines)."""
    for r in rows[:i_hdr]:
        d = iso(" ".join(r))
        if d:
            return d
    return None


def is_total(s):
    return bool(re.match(r"(?i)^(grand\s+)?totals?\b", s.strip()))


def classify_ct(rows, fname):
    nonblank = [r for r in rows if any(c for c in r)]
    if not nonblank:
        raise Unrecognised("empty file")
    lower = lambda h: [c.lower().strip() for c in h]
    # stock by delivery point (daily)
    i = header_at(rows, lambda h: any(x.startswith("current stock") for x in h) and any("delivery" in x for x in h))
    if i is not None:
        h = rows[i]; d = iso(next(x for x in h if x.lower().startswith("current stock")))
        return {"kind": "ct_stock", "sym": "CT", "date": d, "i": i}
    i = header_at(rows, lambda h: any(x.startswith("color") for x in h) and any(x.startswith("leaf") for x in h))
    if i is not None:
        return {"kind": "ct_grade", "sym": "CT", "i": i}
    i = header_at(rows, lambda h: any("warehouse" in x and ("number" in x or "code" in x) for x in h) and any(re.search(r"receipt|bales", x) for x in h))
    if i is not None:
        return {"kind": "ct_warehouse", "sym": "CT", "i": i}
    i = header_at(rows, lambda h: any(re.search(r"crop\s*year|year of growth", x) for x in h) and any("delivery" in x for x in h))
    if i is not None:
        return {"kind": "ct_yog", "sym": "CT", "i": i}
    i = header_at(rows, lambda h: any(x == "month" for x in h) and sum(bool(re.search(r", [a-z]{2}$", x)) for x in h) >= 2)
    if i is not None:
        return {"kind": "ct_four_months", "sym": "CT", "i": i}
    i = header_at(rows, lambda h: sum(bool(re.search(r"\d{2}\.\d\s*-\s*\d{2}\.\d$|\d{2}\.\d and above$", x)) for x in h) >= 3)
    if i is not None:
        return {"kind": "ct_strength", "sym": "CT", "i": i}
    raise Unrecognised("table that is not one of the ICE cotton certificated-stock reports or the coffee certs report")


def file_date(fname):
    m = re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", fname)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def write_csv(path, header, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")   # ICE's own CSV line ends, so a re-upload of a stored file changes nothing
        w.writerow(header)
        w.writerows(body)


def convert_ct(rows, info, fname):
    k, i = info["kind"], info["i"]
    h = [c.strip() for c in rows[i]]
    body = [r + [""] * (len(h) - len(r)) for r in rows[i + 1:] if any(c.strip() for c in r)]
    d = info.get("date") or report_dates(rows, i, h) or text_date(rows, i) or file_date(fname)
    if not d:
        raise ParseError(f"{LABEL[k]}: no report date in the file")
    out = []
    try:
        if k == "ct_stock":
            j0 = col(h, r"delivery")
            hdr = [h[j0]] + [x for j, x in enumerate(h) if j != j0 and x]
            idx = [j0] + [j for j, x in enumerate(h) if j != j0 and x]
            out = [[r[idx[0]]] + [num(r[j]) for j in idx[1:]] for r in body if r[j0].strip() and not is_total(r[j0])]
            name = f"stock_{d}.csv"
        elif k == "ct_grade":
            jc, jl = col(h, r"^colou?r"), col(h, r"^leaf")
            st = [(j, re.sub(r"(?i)staple\s*", "", x).strip()) for j, x in enumerate(h) if re.fullmatch(r"(?i)(staple\s*)?\d{2}\+?", x.strip())]
            jt = col(h, r"^total")
            if not st:
                raise ParseError("grade/staple report: no staple columns")
            hdr = ["Report Date", "Color Grade", "Leaf Grade"] + [s for _, s in st] + ["Total"]
            for r in body:
                c, l = r[jc].strip(), r[jl].strip()
                if not (c.isdigit() and l.isdigit()):
                    continue
                v = [num(r[j]) for j, _ in st]
                t = num(r[jt]) if jt is not None and r[jt].strip() else sum(v)
                if t != sum(v):
                    raise ParseError(f"grade/staple report: color {c} leaf {l} total {t} is not the sum of its staples {sum(v)}")
                out.append([d, c, l] + v + [t])
            name = f"grade_staple_{d}.csv"
        elif k == "ct_warehouse":
            jn, jw, jr = col(h, r"warehouse\s*(number|code)"), col(h, r"^warehouse(\s*name)?$"), col(h, r"receipt|bales")
            hdr = ["Report Date", "Warehouse Number", "Warehouse", "Receipt"]
            out = [[d, r[jn].strip(), r[jw].strip() if jw is not None else "", num(r[jr])] for r in body if r[jn].strip() and not is_total(r[jn])]
            name = f"warehouse_{d}.csv"
        elif k == "ct_yog":
            jp, jy, jr = col(h, r"delivery"), col(h, r"crop|year"), col(h, r"receipt|bales")
            hdr = ["Report Date", "Delivery Point", "Crop Year", "Receipt"]
            out = [[d, r[jp].strip(), r[jy].strip(), num(r[jr])] for r in body if re.fullmatch(r"\d{4}", r[jy].strip())]
            name = f"year_of_growth_{d}.csv"
        elif k == "ct_strength":
            jp = col(h, r"delivery")
            sc = [j for j, x in enumerate(h) if re.search(r"(?i)\d{2}\.\d\s*(-\s*\d{2}\.\d|and above)$", x.strip())]
            hdr = ["Delivery Point"] + [re.sub(r"(?i)^gpt range\s*", "", h[j]).upper() for j in sc] + ["Totals"]
            for r in body:
                if not r[jp].strip() or is_total(r[jp]):
                    continue
                v = [num(r[j]) for j in sc]
                out.append([r[jp].strip()] + v + [sum(v)])
            name = f"strength_{d}.csv"
        elif k == "ct_four_months":
            jm = col(h, r"^month$")
            pts = [(j, x) for j, x in enumerate(h) if j != jm and x and not re.search(r"(?i)report\s*date|^totals?$", x)]
            hdr = ["Report Date", "Month"] + [x for _, x in pts] + ["Total"]
            jt = col(h, r"^totals?$")
            for r in body:
                if not r[jm].strip() or is_total(r[jm]):
                    continue
                v = [num(r[j]) for j, _ in pts]
                if jt is not None and r[jt].strip() and num(r[jt]) != sum(v):
                    raise ParseError(f"four-months report: month {r[jm]} total {r[jt]} is not the sum of its delivery points {sum(v)}")
                out.append([d, r[jm].strip()] + v + [sum(v)])
            name = f"four_months_older_{d}.csv"
    except (ValueError, IndexError, TypeError) as e:
        raise ParseError(f"{LABEL[k]} {d}: a row could not be read ({e})")
    if not out:
        raise ParseError(f"{LABEL[k]} {d}: no data rows")
    write_csv(CT_ICE / name, hdr, out)
    return d, {"stored": f"data/cotton/ice/{name}", "note": f"{len(out)} rows"}


# ---------------- coffee certs ----------------
def classify_kc(rows):
    head = " ".join(" ".join(r) for r in rows[:6]).upper()
    if "COFFEE" in head and "CERTIFIED" in head and "STOCK" in head:
        d = iso(re.sub(r"(?i).*as of:?", "", next((" ".join(r) for r in rows[:6] if "as of" in " ".join(r).lower()), "")))
        return {"kind": "kc_certs", "sym": "KC", "date": d}
    return None


def handle_kc(data, info):
    import pandas as pd
    sys.path.insert(0, str(ROOT / "pipelines"))
    from coffee_certs import parse
    d = info["date"]
    if not d:
        raise ParseError("coffee certs report: no 'As of' date")
    try:
        got = parse(data, date.fromisoformat(d))
    except Exception as e:
        raise ParseError(f"coffee certs report {d}: could not be read ({e})")
    if not any(s == "certified" for _, s, *_ in got):
        raise ParseError(f"coffee certs report {d}: no certified bags found")
    new = pd.DataFrame(got, columns=["date", "section", "origin", "port", "bags"]).assign(date=d)
    cols = ["date", "section", "origin", "port", "bags"]
    old = pd.read_csv(KC_INBOX, dtype={"date": str}) if KC_INBOX.exists() else pd.DataFrame(columns=cols)
    pd.concat([old[old.date != d], new]).sort_values(cols[:4]).to_csv(KC_INBOX, index=False)
    # merge with the automatic series: fill a missing day, otherwise compare
    auto = pd.read_csv(KC_AUTO, dtype={"date": str}) if KC_AUTO.exists() else pd.DataFrame(columns=cols)
    chk = json.loads(KC_CHECK.read_text()) if KC_CHECK.exists() else {}
    tot_new = int(new[new.section == "certified"].bags.sum())
    a = auto[auto.date == d]
    if a.empty:
        pd.concat([auto, new]).sort_values(cols[:4]).to_csv(KC_AUTO, index=False)
        chk[d] = {"status": "filled from upload", "certified": tot_new}
        note = f"day was missing from the automatic series: added ({tot_new:,} bags certified)"
    else:
        key = lambda x: x[x.section != "zero"].groupby(["section", "origin", "port"]).bags.sum()
        diff = key(new).sub(key(a), fill_value=0)
        diff = diff[diff != 0]
        tot_auto = int(a[a.section == "certified"].bags.sum())
        chk[d] = {"status": "match" if diff.empty else "differs", "certified": tot_new, "certified_auto": tot_auto,
                  "differences": [{"section": s, "origin": o, "port": p, "upload_minus_auto": int(v)} for (s, o, p), v in diff.items()][:50]}
        note = "matches the automatic series" if diff.empty else f"DIFFERS from the automatic series on {len(diff)} cells (certified {tot_new:,} vs {tot_auto:,}); automatic series kept"
        if not diff.empty:
            print(f"::warning::coffee certs {d}: upload differs from the automatic ICE series ({len(diff)} cells); see data/coffee/ice_certs_check.json")
    KC_CHECK.write_text(json.dumps(dict(sorted(chk.items())), indent=1))
    try:
        cert, pend = ice_history.kc_daily(data, d)
    except Exception as e:
        raise ParseError(f"coffee certs report {d}: detail could not be read ({e})")
    return {"stored": "data/coffee/ice_certs_inbox.csv, data/coffee/ice_certs_daily_detail.csv", "note": note + f"; detail: {pend:,} bags pending grading"}


# ---------------- CEPEA coffee indicator files (not ICE, same drop box) ----------------
def classify_cepea(data):
    """CEPEA/ESALQ arabica or robusta coffee index as downloaded from cepea.org.br (xls, often slightly corrupt; Portuguese
    'Data | À vista R$ | À vista US$' or English 'Date | Price US$' layout). cepea.org.br is never fetched automatically."""
    if not (data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" or data[:4] == b"PK\x03\x04" or b"cepea" in data[:8000].lower()):
        return None
    import brazil_physical as bp
    try:
        rows = bp.sheet_rows(data)
    except Exception:
        return None
    if not bp.is_cepea_file(rows):
        return None
    got = bp.cepea_rows(rows)
    if not got:
        raise ParseError("CEPEA coffee index file: no dated prices could be read")
    ser = got[0][1]
    return {"kind": ser, "sym": "KC", "date": max(d for d, *_ in got), "n": len(got)}


def handle_cepea(data, info):
    import brazil_physical as bp
    try:
        ser, a, b, n = bp.ingest_cepea_file(data)
    except Exception as e:
        raise ParseError(f"CEPEA coffee index file: could not be stored ({e})")
    out = "data/coffee/brazil_physical_raw.csv, brazil_physical_history.csv" + (", cepea_robusta_history.csv" if ser == "cepea_robusta" else "")
    return {"stored": out, "note": f"{n:,} daily prices {a} to {b} (replace the same days; nothing else changed)"}


# ---------------- driver ----------------
def identify(p):
    """(info, handler) for one file, by its content."""
    data = p.read_bytes()
    if not data.strip():
        raise Unrecognised("empty file")
    if data[:5] == b"%PDF-":
        return classify_pdf(p), "pdf"
    if data[:4] == b"PK\x03\x04" and zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as z:
            if not any(n.lower().endswith((".xlsx", ".xlsm")) for n in z.namelist()) and "[Content_Types].xml" not in z.namelist():
                return {"kind": "zip"}, "zip"
    cep = classify_cepea(data)
    if cep:
        return cep, "cepea"
    rows = table_rows(p, data)
    if rows and rows[0] and ice_price_history.detect_xls(rows[0][0]):
        return {"kind": "price_history", "sym": ice_price_history.detect_xls(rows[0][0])}, "pricehist"
    h = ice_history.classify_table(rows)
    if h:
        return h, "hist"
    kc = classify_kc(rows)
    if kc:
        return kc, "kc"
    return classify_ct(rows, p.name), "ct"


def process(p, info, how, now):
    """Handle one identified file. Returns (log entry, keep original in the raw archive)."""
    if how == "pdf" and info["kind"] not in ("options", "futures"):
        how = "hist"
    if how == "hist":
        d, res = ice_history.handle(p, info)
        keep = False   # the newest original of each kind is kept in data/ice_raw/latest/
    elif how == "pdf":
        res, keep = handle_settlement(p, info)
        d = info["date"]
    elif how == "pricehist":
        sym, note = ice_price_history.add_xls(p.read_bytes())
        res, keep, d = {"stored": f"data/{ice_price_history.DIRS[sym]}/ice_daily_contracts.csv", "note": note}, False, note.split(" to ")[-1][:10]
    elif how == "cepea":
        res, keep, d = handle_cepea(p.read_bytes(), info), False, info["date"]
    elif how == "kc":
        res, keep, d = handle_kc(p.read_bytes(), info), True, info["date"]
    else:
        d, res = convert_ct(table_rows(p, p.read_bytes()), info, p.name)
        keep = True
    label = LABEL[info["kind"]].format(NAMES.get(info.get("sym"), "")) if info["kind"] in ("options", "futures") else LABEL[info["kind"]]
    key = f"{info['sym']}_{info['kind']}" if info["kind"] in ("options", "futures") else info["kind"]
    e = {"received": now, "file": p.name, "type": key, "label": label, "market": info.get("sym"), "report_date": d,
         **{k: v for k, v in res.items() if k != "original"}}
    if res.get("original"):
        e["kept_copy"] = res["original"]
    return e, keep


def archive(p, now_day):
    dst = RAW / now_day / p.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p), dst)
    return str(dst.relative_to(ROOT))


def to_unrecognised(p, reason, log, now):
    UNREC.mkdir(parents=True, exist_ok=True)
    dst = UNREC / p.name
    if dst.exists():
        dst = UNREC / f"{p.stem}-{datetime.now().strftime('%H%M%S')}{p.suffix}"
    shutil.move(str(p), dst)
    log["unrecognised"] = [u for u in log.get("unrecognised", []) if u["file"] != dst.name] + [{"file": dst.name, "reason": reason, "received": now}]


def prune(today):
    cut_pdf, cut_other = (today - timedelta(days=KEEP_PDF_DAYS)).isoformat(), (today - timedelta(days=KEEP_OTHER_DAYS)).isoformat()
    for f in STAGE.glob("*.pdf") if STAGE.exists() else []:
        d = file_date(f.name)
        if d and d.replace("_", "-") < cut_pdf:
            f.unlink(); print("removed old staged", f.name)
    for day in sorted(RAW.glob("*")) if RAW.exists() else []:
        for f in day.iterdir():
            if day.name < (cut_pdf if f.suffix.lower() in (".pdf", ".zip", ".xls", ".xlsx") else cut_other):
                f.unlink()
        if day.is_dir() and not any(day.iterdir()):
            day.rmdir()


def manifest():
    out = []
    for f in sorted(STAGE.glob("*.pdf")) if STAGE.exists() else []:
        m = re.match(r"([A-Z]{2})_(\d{4})_(\d{2})_(\d{2})(-2)?\.pdf$", f.name)
        if m:
            out.append({"file": f.name, "path": f"data/ice_staging/pdfs/{f.name}", "sym": m.group(1), "kind": "futures" if m.group(5) else "options",
                        "date": f"{m.group(2)}-{m.group(3)}-{m.group(4)}", "bytes": f.stat().st_size, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "files": out}, indent=1))


def main(argv):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    today = datetime.now(timezone.utc).date()
    log = json.loads(LOG.read_text()) if LOG.exists() else {"last": {}, "recent": [], "unrecognised": []}
    files = [Path(a) for a in argv] if argv else sorted(f for f in INBOX.iterdir() if f.is_file() and f.name not in SKIP) if INBOX.exists() else []
    failed, unknown = [], []
    queue = [(f, None) for f in files]
    tmp = Path(tempfile.mkdtemp())
    while queue:
        p, parent = queue.pop(0)
        in_inbox = parent is None and INBOX in p.resolve().parents
        try:
            info, how = identify(p)
            if how == "zip":
                dest = tmp / p.stem; dest.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(p) as z:
                    for n in z.namelist():
                        if not n.endswith("/") and not Path(n).name.startswith("."):
                            t = dest / Path(n).name; t.write_bytes(z.read(n)); queue.append((t, p.name))
                print(f"{p.name}: zip with {len(list(dest.iterdir()))} file(s), each handled below")
                if in_inbox:
                    archive(p, today.isoformat())
                continue
            e, keep = process(p, info, how, now)
        except (Unrecognised, ParseError, ice_history.Bad) as x:
            bad = not isinstance(x, Unrecognised)
            msg = ("could not be read: " if bad else "") + str(x)
            name = p.name + (f" (in {parent})" if parent else "")
            print(f"::{'error' if bad else 'warning'}::{name}: {'recognised but ' if bad else 'not recognised - '}{msg}. Moved to inbox/unrecognised/")
            (failed if bad else unknown).append(name)
            if in_inbox or parent:
                to_unrecognised(p, msg, log, now)
            continue
        if parent:
            e["file"] = f"{parent}/{p.name}"
        print(f"{e['file']}: {e['label']}, report date {e['report_date']} -> {e['stored']} ({e['note']})")
        if in_inbox:
            if keep:
                e["original"] = archive(p, today.isoformat())
            else:
                p.unlink(); e["original"] = e.get("kept_copy") or ("removed (the staged copy is the record)" if how == "pdf" else "removed (stored in the combined file)")
        log["last"][e["type"]] = {k: e[k] for k in ("received", "file", "label", "report_date", "stored")}
        log["recent"] = ([e] + log.get("recent", []))[:200]
    shutil.rmtree(tmp, ignore_errors=True)
    # files still sitting in unrecognised/ (Ma may delete them)
    present = {f.name for f in UNREC.iterdir()} if UNREC.exists() else set()
    log["unrecognised"] = [u for u in log.get("unrecognised", []) if u["file"] in present] + \
        [{"file": n, "reason": "unknown", "received": None} for n in sorted(present - {u["file"] for u in log.get("unrecognised", [])} - SKIP)]
    log["updated"] = now
    prune(today)
    manifest()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(log, indent=1))
    print(f"inbox: {len(files)} file(s) handled, {len(unknown)} not recognised, {len(failed)} could not be read; "
          f"{len(log['unrecognised'])} waiting in inbox/unrecognised/")
    if failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
