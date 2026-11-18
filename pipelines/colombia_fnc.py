"""Colombia coffee (Federación Nacional de Cafeteros, FNC) for the Coffee -> Colombia tab.

Sources (all public, robots.txt allows everything):
  https://federaciondecafeteros.org/estadisticas-cafeteras/   statistics page; links to
    - "Precios, área y producción de café" (xlsx): daily internal price since 2003, monthly internal price since 1944,
      ex-dock price since 1913, ICO group prices, registered production by month since 1956
    - "Exportaciones de café colombiano" (xlsx): monthly exports since 1958, monthly by destination x type since 2017,
      annual by type since 2000
    - "Informe mensual" (pdf): the month's prices, Colombian differential, stocks, consumption, imports
    - precio_cafe.pdf: today's internal reference price and the NY close it was set from
  https://federaciondecafeteros.org/publicaciones/              publications (used to find files when the stats page fails)
  USD/COP: official TRM (Superintendencia Financiera, datos.gov.co open data); Yahoo COP=X as fallback.

Usage:
  python pipelines/colombia_fnc.py              fetch from FNC, store, build the page JSON (fails if FNC unreachable)
  python pipelines/colombia_fnc.py --build      rebuild the page JSON from stored data only
  python pipelines/colombia_fnc.py --file X...  store FNC files downloaded by hand (not needed: GitHub runners can download them)

Output: data/coffee/colombia/*.csv, sources.json, colombia.json (page; data only, no publication notes).
"""
import argparse, csv, io, json, math, re, subprocess, sys, tempfile, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "coffee" / "colombia"
BASE = "https://federaciondecafeteros.org"
PAGES = [BASE + "/estadisticas-cafeteras/", BASE + "/wp/estadisticas-cafeteras/", BASE + "/publicaciones/"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
LB_PER_CARGA = 125 * 70 / 94 * 2.20462     # 125 kg dry parchment -> excelso green at yield factor 94, in lb (FNC table: 93.09 kg)
TYPES = {"Café Verde": "green", "Tostados": "roasted", "Soluble": "soluble", "Extractos": "extracts"}
COUNTRY_EN = {"Estados Unidos": "United States", "EE.UU.": "United States", "EE. UU.": "United States", "Alemania": "Germany", "Japón": "Japan", "Bélgica": "Belgium", "Canadá": "Canada",
              "Corea del Sur": "South Korea", "Italia": "Italy", "Países Bajos": "Netherlands", "Paises Bajos": "Netherlands",
              "Reino Unido": "United Kingdom", "España": "Spain", "Francia": "France", "Suecia": "Sweden", "Australia": "Australia",
              "Ecuador": "Ecuador", "Perú": "Peru", "Rusia": "Russia", "Polonia": "Poland", "Finlandia": "Finland", "Taiwán": "Taiwan",
              "China": "China", "México": "Mexico", "Chile": "Chile", "Argentina": "Argentina", "Turquía": "Turkey", "Noruega": "Norway",
              "Dinamarca": "Denmark", "Israel": "Israel", "Arabia Saudita": "Saudi Arabia", "Emiratos Árabes Unidos": "UAE",
              "Vietnam": "Vietnam", "Malasia": "Malaysia", "Suiza": "Switzerland", "Grecia": "Greece", "Portugal": "Portugal",
              "Nueva Zelanda": "New Zealand", "Sudáfrica": "South Africa", "Filipinas": "Philippines", "India": "India", "Jordania": "Jordan",
              "Líbano": "Lebanon", "Ucrania": "Ukraine", "Austria": "Austria", "Irlanda": "Ireland", "Venezuela": "Venezuela"}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ------------------------------------------------------------------ http
def http(url, tries=5, timeout=90, **kw):
    import requests
    last = None
    for k in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout, **kw)
            if r.status_code == 200 and r.content:
                return r
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = repr(e)[:160]
        log("retry", url, last); time.sleep(4 + 6 * k)
    raise RuntimeError(f"{url}: {last}")


def file_month(url):
    """(year, month) a FNC file is about, from its name (e.g. Exportaciones-Septiembre-2026.xlsx); None if absent."""
    n = url.rsplit("/", 1)[-1].lower().replace("%c3%a9", "e")
    m = re.search(r"(" + "|".join(MESES) + r")[-_ ]*(?:de[-_ ]*)?(\d{4})", n)
    if m:
        return int(m.group(2)), MESES.index(m.group(1)) + 1
    m = re.search(r"uploads/(\d{4})/(\d{2})/", url)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def discover():
    """Links to the current FNC files, read from the statistics page (publications page as fallback)."""
    links, seen = set(), []
    for p in PAGES:
        try:
            t = http(p, tries=3).text
        except Exception as e:
            log("page fail", p, e); continue
        seen.append(p)
        links |= set(re.findall(r'href="(https?://[^"]+?\.(?:xlsx|pdf))"', t, re.I))
        if any("Exportaciones" in l and l.lower().endswith(".xlsx") for l in links) and any("Precios" in l for l in links):
            break
    if not seen:
        raise RuntimeError("FNC: no page could be read (statistics and publications pages)")
    pick = lambda pat: sorted((l for l in links if re.search(pat, l, re.I)), key=file_month)
    return {"prices_xlsx": pick(r"Precios.*produccion.*\.xlsx$"), "exports_xlsx": pick(r"/Exportaciones-[^/]*\.xlsx$"),
            "monthly_pdf": pick(r"Informe-mensual-[^/]*\.pdf$"), "expos_pdf": pick(r"Informe-Expos[^/]*\.pdf$"),
            "daily_pdf": pick(r"precio_cafe\.pdf$"), "pages": seen}


# ------------------------------------------------------------------ readers
def _xl(src):
    from openpyxl import load_workbook
    return load_workbook(io.BytesIO(src) if isinstance(src, bytes) else src, read_only=True, data_only=True)


def _sheet(wb, *keys):
    for n in wb.sheetnames:
        k = re.sub(r"^\s*\d+\.\s*", "", n).strip().lower()
        if all(x in k for x in keys):
            return wb[n]
    raise ValueError(f"sheet with {keys} not found in {wb.sheetnames}")


def _date_rows(ws, ncol=2):
    """(datetime, values...) rows of a FNC sheet: first date cell, then the next ncol-1 numbers."""
    out = []
    for row in ws.iter_rows(values_only=True):
        for i, v in enumerate(row):
            if isinstance(v, datetime):
                vals = list(row[i + 1:i + ncol])
                if vals and isinstance(vals[0], (int, float)):
                    out.append((v, *vals))
                break
    return out


def is_prices_book(wb):
    names = " ".join(wb.sheetnames).lower()
    return "precio interno diario" in names and "producci" in names


def is_exports_book(wb):
    names = " ".join(wb.sheetnames).lower()
    return "total_volumen" in names and "destino_tipo" in names


def read_prices_book(wb):
    daily = [(d.strftime("%Y-%m-%d"), float(v)) for d, v in _date_rows(_sheet(wb, "precio interno diario"))]
    monthly = [(d.strftime("%Y-%m"), float(v)) for d, v in _date_rows(_sheet(wb, "precio interno mensual"))]
    exdock = [(d.strftime("%Y-%m"), float(v)) for d, v in _date_rows(_sheet(wb, "ex_dock mensual"))]
    prod = [(d.strftime("%Y-%m"), float(v)) for d, v in _date_rows(_sheet(wb, "producci", "mensual"))]
    if len(daily) < 3000 or len(prod) < 500 or len(exdock) < 1000:
        raise ValueError(f"prices book too short: daily {len(daily)}, production {len(prod)}, ex-dock {len(exdock)}")
    return {"daily": daily, "monthly": monthly, "exdock": exdock, "prod": prod}


def read_exports_book(wb):
    total = [(d.strftime("%Y-%m"), float(v)) for d, v in _date_rows(_sheet(wb, "total_volumen"))]
    ws = _sheet(wb, "destino_tipo")
    hdr, rows = None, []
    for row in ws.iter_rows(values_only=True):
        cells = [c for c in row]
        if hdr is None:
            low = [str(c).strip().lower() if c is not None else "" for c in cells]
            if "año" in low and "mes" in low:
                hdr = {k: low.index(k) for k in ("año", "mes")}
                hdr["country"] = next(i for i, c in enumerate(low) if c.startswith("país"))
                hdr["type"] = next(i for i, c in enumerate(low) if c.startswith("tipo"))
                hdr["bags"] = next(i for i, c in enumerate(low) if "60 kg" in c)
            continue
        y, m = cells[hdr["año"]], cells[hdr["mes"]]
        if isinstance(y, (int, float)) and isinstance(m, (int, float)):
            rows.append((f"{int(y)}-{int(m):02d}", str(cells[hdr["country"]]).strip(), TYPES.get(str(cells[hdr["type"]]).strip(), "other"),
                         float(cells[hdr["bags"]] or 0)))
    annual = []
    try:
        wt = _sheet(wb, "tipo_volumen")
        head = None
        for row in wt.iter_rows(values_only=True):
            low = [str(c).strip() if c is not None else "" for c in row]
            if "Año" in low:
                head = low; continue
            if head and isinstance(row[head.index("Año")], (int, float)):
                rec = {"year": int(row[head.index("Año")])}
                for k, lab in [("green", "Verde"), ("green_decaf", "Verde descafeinado"), ("roasted_beans", "Tostado en grano"),
                               ("roasted_ground", "Tostado y molido"), ("soluble_extract", "Extracto y soluble"), ("total", "Total")]:
                    v = row[head.index(lab)] if lab in head else None
                    rec[k] = round(float(v), 3) if isinstance(v, (int, float)) else None
                annual.append(rec)
    except ValueError:
        pass
    if len(total) < 500 or len(rows) < 5000:
        raise ValueError(f"exports book too short: monthly {len(total)}, destination rows {len(rows)}")
    return {"total": total, "dest": rows, "annual": annual}


def pdf_text(src):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(src if isinstance(src, bytes) else Path(src).read_bytes()); f.flush()
        return subprocess.run(["pdftotext", f.name, "-"], capture_output=True, text=True, timeout=120).stdout


def _n(s):
    return float(s.replace(".", "").replace(",", ".")) if s else None


def read_monthly_report(text):
    """Headline numbers of the FNC 'Informe mensual' (Spanish number format)."""
    t = re.sub(r"\s+", " ", text)
    m = re.search(r"INFORME MENSUAL (" + "|".join(m.upper() for m in MESES) + r") (\d{4})", t, re.I)
    if not m:
        return None
    rec = {"month": f"{m.group(2)}-{MESES.index(m.group(1).lower()) + 1:02d}"}
    pats = {"differential_c_lb": r"diferencial del caf[ée] colombiano promedi[óo] ([\d.,]+) ?¢",
            "kc_avg_c_lb": r"Contrato KC \(Bolsa de Nueva York\) se ubic[óo] en ([\d.,]+) ?¢",
            "internal_avg_cop": r"precio interno del caf[ée] alcanz[óo] un promedio de \$ ?([\d.,]+)",
            "trm_avg": r"TRM\) cerr[óo] \w+ con un promedio de \$ ?([\d.,]+)",
            "production_m": r"producci[óo]n de caf[ée] fue de ([\d.,]+) millones",
            "production_12m_m": r"acumulado 12 meses, la producci[óo]n se ubica en ([\d.,]+) millones",
            "inventories_m": r"ubic[áa]ndose en ([\d.,]+) millones de sacos",
            "consumption_k": r"consumo interno preliminar se estim[óo] en ([\d.,]+) mil sacos",
            "imports_k": r"importaciones (?:preliminares )?de \w+ se sit[úu]en\s*(?:en )?([\d.,]+) mil sacos"}
    for k, p in pats.items():
        x = re.search(p, t, re.I)
        rec[k] = _n(x.group(1).rstrip(".,")) if x else None
    # price table: "Diferencial <this month> <previous month> <a year ago>"
    x = re.search(r"Diferencial ([\d.,]+) ([\d.,]+) ([\d.,]+)", t)
    if x:
        rec["differential_table"] = [_n(v) for v in x.groups()]
    return rec


def read_daily_pdf(text):
    """precio_cafe.pdf: date, NY close the price was set from, internal price per carga (FR 94)."""
    t = re.sub(r"\s+", " ", text)
    m = re.search(r"(" + "|".join(m.capitalize() for m in MESES) + r") (\d{1,2}) ?/ ?(\d{4})", t)
    p = re.search(r"Precio total por carga de 125 Kg de pergamino seco FR ?94 ([\d,.]+) COP", t)
    k = re.search(r"Cierre contrato C Nueva York ([\d.,]+)", t)
    if not (m and p):
        return None
    d = date(int(m.group(3)), MESES.index(m.group(1).lower()) + 1, int(m.group(2)))
    return {"date": d.isoformat(), "cop_per_carga": float(p.group(1).replace(",", "")), "kc_close": float(k.group(1).replace(",", "")) if k else None}


def classify(data):
    """Kind of a FNC file from its content: prices_xlsx | exports_xlsx | monthly_pdf | daily_pdf | expos_pdf | None."""
    if data[:4] == b"PK\x03\x04":
        try:
            wb = _xl(data)
        except Exception:
            return None
        return "prices_xlsx" if is_prices_book(wb) else "exports_xlsx" if is_exports_book(wb) else None
    if data[:5] == b"%PDF-":
        t = pdf_text(data)
        flat = re.sub(r"\s+", " ", t)
        if re.search(r"INFORME MENSUAL DE EXPORTACIONES", flat, re.I) and "caf" in flat.lower():
            return "expos_pdf"
        if "FEDERACIÓN NACIONAL DE CAFETEROS" not in flat.upper():
            return None
        if read_daily_pdf(t):
            return "daily_pdf"
        if read_monthly_report(t):
            return "monthly_pdf"
    return None


# ------------------------------------------------------------------ store
def wcsv(name, header, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / name, "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def rcsv(name):
    p = OUT / name
    return list(csv.DictReader(open(p))) if p.exists() else []


def load_sources():
    p = OUT / "sources.json"
    return json.loads(p.read_text()) if p.exists() else {"files": {}}


def save_sources(S):
    S["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    (OUT / "sources.json").write_text(json.dumps(S, indent=1, ensure_ascii=False))


def note_source(S, kind, url, latest, how):
    S["files"][kind] = {"url": url, "latest_data": latest, "read": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "via": how}


def store(kind, data, url, S, how):
    """Parse one FNC file and merge it into the CSVs. Returns the latest date in it."""
    if kind == "prices_xlsx":
        P = read_prices_book(_xl(data))
        old = {r["date"]: r for r in rcsv("internal_price_daily.csv")}
        for d, v in P["daily"]:
            o = old.get(d, {})
            old[d] = {"date": d, "cop_per_carga": f"{v:.0f}", "kc_close": o.get("kc_close", ""), "source": "fnc_xlsx"}
        wcsv("internal_price_daily.csv", ["date", "cop_per_carga", "kc_close", "source"], [[r["date"], r["cop_per_carga"], r["kc_close"], r["source"]] for _, r in sorted(old.items())])
        wcsv("internal_price_monthly.csv", ["month", "cop_per_carga"], [[m, f"{v:.0f}"] for m, v in P["monthly"]])
        wcsv("exdock_monthly.csv", ["month", "exdock_c_lb"], [[m, f"{v:.2f}"] for m, v in P["exdock"]])
        wcsv("production_monthly.csv", ["month", "k_bags"], [[m, f"{v:.1f}"] for m, v in P["prod"]])
        latest = max(P["prod"])[0]
        note_source(S, kind, url, f"production {latest}, internal price {P['daily'][-1][0]}", how)
        return latest
    if kind == "exports_xlsx":
        E = read_exports_book(_xl(data))
        by = {}
        for m, c, t, b in E["dest"]:
            by.setdefault(m, {}).setdefault(t, 0.0); by[m][t] += b
        rows = []
        for m, v in E["total"]:
            tt = by.get(m, {})
            rows.append([m, f"{v:.1f}"] + [f"{tt[t] / 1000:.1f}" if m in by else "" for t in ("green", "roasted", "soluble", "extracts")])
        wcsv("exports_monthly.csv", ["month", "total_k_bags", "green_k_bags", "roasted_k_bags", "soluble_k_bags", "extracts_k_bags"], rows)
        agg = {}
        for m, c, t, b in E["dest"]:
            agg[(m, c, t)] = agg.get((m, c, t), 0) + b
        wcsv("exports_by_destination_monthly.csv", ["month", "country", "type", "bags_60kg"], [[m, c, t, f"{b:.0f}"] for (m, c, t), b in sorted(agg.items())])
        if E["annual"]:
            ks = list(E["annual"][0].keys())
            wcsv("exports_by_type_annual.csv", ks, [[r[k] if r[k] is not None else "" for k in ks] for r in E["annual"]])
        latest = E["total"][-1][0]
        note_source(S, kind, url, f"exports {latest}", how)
        return latest
    if kind == "monthly_pdf":
        R = read_monthly_report(pdf_text(data))
        if not R or R.get("differential_c_lb") is None:
            raise ValueError("monthly report: month or differential not found")
        R["url"] = url
        old = {r["month"]: r for r in rcsv("monthly_report.csv")}
        tab = R.pop("differential_table", None)
        old[R["month"]] = {k: ("" if v is None else v) for k, v in R.items()}
        if tab:      # the table also carries last month's and last year's differential: fill gaps only
            y, mo = map(int, R["month"].split("-"))
            for mm, v in [(f"{y if mo > 1 else y - 1}-{(mo - 2) % 12 + 1:02d}", tab[1]), (f"{y - 1}-{mo:02d}", tab[2])]:
                if mm not in old:
                    old[mm] = {"month": mm, "differential_c_lb": v, "url": url + " (comparison column)"}
        cols = ["month", "differential_c_lb", "kc_avg_c_lb", "internal_avg_cop", "trm_avg", "production_m", "production_12m_m", "inventories_m", "consumption_k", "imports_k", "url"]
        wcsv("monthly_report.csv", cols, [[r.get(c, "") for c in cols] for _, r in sorted(old.items())])
        if url and not url.startswith("inbox:"):
            S.setdefault("monthly_reports", {})[R["month"]] = url
        note_source(S, kind, url, f"report {R['month']}", how)
        return R["month"]
    if kind == "daily_pdf":
        R = read_daily_pdf(pdf_text(data))
        old = {r["date"]: r for r in rcsv("internal_price_daily.csv")}
        o = old.get(R["date"], {})
        old[R["date"]] = {"date": R["date"], "cop_per_carga": f"{R['cop_per_carga']:.0f}", "kc_close": R["kc_close"] or "",
                          "source": o.get("source") if o.get("source") == "fnc_xlsx" else "fnc_daily_pdf"}
        if o.get("source") == "fnc_xlsx":
            old[R["date"]]["cop_per_carga"] = o["cop_per_carga"]
        wcsv("internal_price_daily.csv", ["date", "cop_per_carga", "kc_close", "source"], [[r["date"], r["cop_per_carga"], r.get("kc_close", ""), r["source"]] for _, r in sorted(old.items())])
        note_source(S, kind, url, R["date"], how)
        return R["date"]
    if kind == "expos_pdf":
        note_source(S, kind, url, "", how)     # read for key points only; numbers come from the Excel file
        return None
    raise ValueError(kind)


def ingest_file(path, how="inbox"):
    """Store one FNC file Ma downloaded. Returns (kind, latest) or None if it is not a FNC file."""
    data = Path(path).read_bytes()
    kind = classify(data)
    if not kind:
        return None
    S = load_sources()
    latest = store(kind, data, "inbox:" + Path(path).name, S, how)
    save_sources(S)
    return kind, latest


# ------------------------------------------------------------------ USD/COP
def fx_update():
    """Daily USD/COP: official TRM (datos.gov.co, Superfinanciera) first, Yahoo COP=X second."""
    old = {r["date"]: r for r in rcsv("usdcop.csv")}
    non_trm = [d for d, r in old.items() if r["source"] != "TRM"]
    start = min(non_trm) if non_trm else max(old) if old else "2002-12-01"      # replace fallback rates by the TRM when it is back
    got = 0
    try:
        q = f"https://www.datos.gov.co/resource/32sa-8pi3.json?$where=vigenciadesde>='{start}T00:00:00.000'&$limit=50000&$order=vigenciadesde"
        for j in http(q, tries=3, timeout=120).json():
            d0, d1 = j["vigenciadesde"][:10], j["vigenciahasta"][:10]
            d = date.fromisoformat(d0)
            while d.isoformat() <= d1:       # the TRM holds over weekends/holidays
                old[d.isoformat()] = {"date": d.isoformat(), "cop_per_usd": j["valor"], "source": "TRM"}
                d += timedelta(days=1); got += 1
    except Exception as e:
        log("TRM fail:", str(e)[:160])
    if not got:
        try:
            p1 = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp())
            r = http(f"https://query1.finance.yahoo.com/v8/finance/chart/COP=X?period1={p1}&period2={int(time.time())}&interval=1d", tries=3).json()
            res = r["chart"]["result"][0]
            for ts, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]):
                if c:
                    d = datetime.fromtimestamp(ts, timezone.utc).date().isoformat()
                    if old.get(d, {}).get("source") != "TRM":
                        old[d] = {"date": d, "cop_per_usd": f"{c:.2f}", "source": "Yahoo COP=X"}; got += 1
        except Exception as e:
            log("Yahoo COP=X fail:", str(e)[:160])
    if not got and old and (date.today() - date.fromisoformat(max(old))).days <= 1:
        return 0         # already up to date
    if not got:      # last resort: the desk's own USDCOP series (TradingView feed, coffee/data/prices_cont.csv)
        p = ROOT / "coffee" / "data" / "prices_cont.csv"
        if p.exists():
            for r in csv.DictReader(open(p)):
                if r["symbol"] == "USDCOP" and r["close"] and r["date"] >= start and r["date"] not in old:
                    old[r["date"]] = {"date": r["date"], "cop_per_usd": r["close"], "source": "TradingView USDCOP"}; got += 1
        if not got and (not old or (date.today() - date.fromisoformat(max(old))).days > 5):
            raise RuntimeError("USD/COP: neither the TRM, Yahoo nor the desk's USDCOP series could be read")
        log("USD/COP: TRM and Yahoo unreachable, used the desk's TradingView series")
    wcsv("usdcop.csv", ["date", "cop_per_usd", "source"], [[r["date"], r["cop_per_usd"], r["source"]] for _, r in sorted(old.items())])
    log("USD/COP rows added/refreshed:", got, "latest", max(old) if old else None)
    return got


# ------------------------------------------------------------------ fetch
def fetch():
    S = load_sources()
    L = discover()
    log("found", {k: len(v) for k, v in L.items() if k != "pages"})
    errors = []
    for kind in ("prices_xlsx", "exports_xlsx", "monthly_pdf", "daily_pdf", "expos_pdf"):
        if not L[kind]:
            (errors.append(f"{kind}: no link on the FNC pages") if kind in ("prices_xlsx", "exports_xlsx") else log("no link for", kind))
            continue
        url = L[kind][-1]
        try:
            latest = store(kind, http(url, timeout=180).content, url, S, "auto")
            log(kind, "->", latest, url)
        except Exception as e:
            errors.append(f"{kind}: {e}")
    try:
        fx_update()
    except Exception as e:
        errors.append(str(e))
    S["last_check"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    S["pages_read"] = L["pages"]
    if not errors:
        S["last_ok"] = S["last_check"]
    save_sources(S)
    return errors


# ------------------------------------------------------------------ build
def r1(v, n=1):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(v, n)


def cy_of(m):
    y, mo = int(m[:4]), int(m[5:7])
    return y if mo >= 10 else y - 1        # coffee year Oct-Sep, labelled by its first year (2026 = 2026/27)


def cy_label(y):
    return f"{y}/{str(y + 1)[2:]}"


def series(rows, key, val):
    return {r[key]: float(r[val]) for r in rows if r.get(val) not in (None, "")}


def add_months(m, k):
    y, mo = int(m[:4]), int(m[5:7]) - 1 + k
    return f"{y + mo // 12}-{mo % 12 + 1:02d}"


def roll12(s):
    out = {}
    for m in sorted(s):
        ms = [add_months(m, -i) for i in range(12)]
        if all(x in s for x in ms):
            out[m] = sum(s[x] for x in ms)
    return out


def compare(s, m):
    """latest month vs same month last year and the 5-year average of the same month."""
    prev = s.get(add_months(m, -12))
    avg5 = [s.get(add_months(m, -12 * k)) for k in range(1, 6)]
    avg5 = sum(avg5) / 5 if all(v is not None for v in avg5) else None
    v = s[m]
    return {"month": m, "value": r1(v), "prev": r1(prev), "avg5": r1(avg5),
            "vs_prev_pct": r1((v / prev - 1) * 100) if prev else None, "vs_avg5_pct": r1((v / avg5 - 1) * 100) if avg5 else None}


def seasonal(s, years=6):
    """coffee-year seasonal table: {label: [Oct..Sep]} for the last `years` coffee years, plus 5-yr average."""
    last = cy_of(max(s))
    out = {}
    for y in range(last - years + 1, last + 1):
        out[cy_label(y)] = [r1(s.get(add_months(f"{y}-10", i))) for i in range(12)]
    full = [y for y in range(last - 5, last) if all(add_months(f"{y}-10", i) in s for i in range(12))]
    out["avg5"] = [r1(sum(s[add_months(f"{y}-10", i)] for y in full) / len(full)) for i in range(12)] if full else None
    out["avg5_years"] = f"{cy_label(full[0])}–{cy_label(full[-1])}" if full else None
    return out


def cy_totals(s, last_m):
    out = []
    for y in range(cy_of(min(s)) + 1, cy_of(last_m) + 1):
        ms = [add_months(f"{y}-10", i) for i in range(12)]
        have = [m for m in ms if m in s and m <= last_m]
        out.append({"cy": cy_label(y), "total": r1(sum(s[m] for m in have) / 1000, 2), "months": len(have)})
    return out


def kc_daily():
    p = ROOT / "coffee" / "data" / "prices_cont.csv"
    out = {}
    if p.exists():
        for r in csv.DictReader(open(p)):
            if r["symbol"] == "KC1!" and r["close"]:
                out[r["date"]] = float(r["close"])
    return out


def build():
    prod = series(rcsv("production_monthly.csv"), "month", "k_bags")
    exp_rows = rcsv("exports_monthly.csv")
    exp = series(exp_rows, "month", "total_k_bags")
    if not prod or not exp:
        raise RuntimeError("no stored FNC production/exports yet")
    pm, em = max(prod), max(exp)
    rp, re_ = roll12(prod), roll12(exp)
    J = {"built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "units": "thousand 60-kg bags unless stated",
         "coffee_year": {"label": cy_label(cy_of(date.today().strftime("%Y-%m"))), "start": f"{cy_of(date.today().strftime('%Y-%m'))}-10-01"}}
    J["production"] = {"latest": compare(prod, pm), "seasonal": seasonal(prod), "roll12": {"month": sorted(rp)[-240:], "v": [r1(rp[m] / 1000, 2) for m in sorted(rp)[-240:]]},
                       "roll12_now": r1(rp[pm] / 1000, 2), "roll12_year_ago": r1(rp.get(add_months(pm, -12), 0) / 1000, 2) or None,
                       "roll12_3m_ago": r1(rp.get(add_months(pm, -3), 0) / 1000, 2) or None, "cy_totals": cy_totals(prod, pm)[-12:],
                       "history_from": min(prod)}
    J["exports"] = {"latest": compare(exp, em), "seasonal": seasonal(exp), "roll12": {"month": sorted(re_)[-240:], "v": [r1(re_[m] / 1000, 2) for m in sorted(re_)[-240:]]},
                    "roll12_now": r1(re_[em] / 1000, 2), "roll12_year_ago": r1(re_.get(add_months(em, -12), 0) / 1000, 2) or None,
                    "roll12_3m_ago": r1(re_.get(add_months(em, -3), 0) / 1000, 2) or None, "cy_totals": cy_totals(exp, em)[-12:], "history_from": min(exp)}
    # by type, last 12 months vs the 12 before
    tt = {}
    for k in ("green", "roasted", "soluble", "extracts"):
        s = series(exp_rows, "month", k + "_k_bags")
        if em in s:
            a = sum(s.get(add_months(em, -i), 0) for i in range(12)); b = sum(s.get(add_months(em, -12 - i), 0) for i in range(12))
            tt[k] = {"last12": r1(a, 0), "prev12": r1(b, 0), "chg_pct": r1((a / b - 1) * 100) if b else None, "latest_month": r1(s[em], 0)}
    J["exports"]["by_type"] = tt
    ann = rcsv("exports_by_type_annual.csv")
    J["exports"]["by_type_annual"] = ann[-12:]
    # destinations, last 12 months to the latest month vs the 12 before (all types)
    dest = {}
    for r in rcsv("exports_by_destination_monthly.csv"):
        m = r["month"]
        k = 0 if add_months(em, -11) <= m <= em else 1 if add_months(em, -23) <= m <= add_months(em, -12) else None
        if k is None:
            continue
        c = COUNTRY_EN.get(r["country"], r["country"])
        dest.setdefault(c, [0.0, 0.0])[k] += float(r["bags_60kg"]) / 1000
    tot = sum(v[0] for v in dest.values())
    top = sorted(dest.items(), key=lambda x: -x[1][0])
    J["destinations"] = {"period": f"{add_months(em, -11)} to {em}", "total": r1(tot, 0),
                         "top": [{"country": c, "k_bags": r1(v[0], 0), "share": r1(v[0] / tot * 100), "prev": r1(v[1], 0),
                                  "chg_pct": r1((v[0] / v[1] - 1) * 100) if v[1] else None} for c, v in top[:10]],
                         "rest": r1(sum(v[0] for _, v in top[10:]), 0)}
    # prices
    fx = series(rcsv("usdcop.csv"), "date", "cop_per_usd")
    kc = kc_daily()
    ip = {r["date"]: r for r in rcsv("internal_price_daily.csv")}
    dates = sorted(d for d in ip if d >= "2010-01-01")
    pts, fx_last, kc_last = [], None, None
    fxk, kck = sorted(fx), sorted(kc)
    import bisect
    for d in dates:
        i = bisect.bisect_right(fxk, d) - 1; j = bisect.bisect_right(kck, d) - 1
        if i < 0 or j < 0:
            continue
        f, k = fx[fxk[i]], kc[kck[j]]
        if (date.fromisoformat(d) - date.fromisoformat(fxk[i])).days > 6 or (date.fromisoformat(d) - date.fromisoformat(kck[j])).days > 6:
            continue
        c = float(ip[d]["cop_per_carga"]) / f / LB_PER_CARGA * 100
        pts.append((d, float(ip[d]["cop_per_carga"]), f, c, k))
    wk = {}
    for p in pts:          # weekly (Friday or last day of week)
        y, w, _ = date.fromisoformat(p[0]).isocalendar()
        wk[(y, w)] = p
    W = [wk[k] for k in sorted(wk)]
    if pts:
        last = pts[-1]
        J["internal"] = {"dates": [p[0] for p in W], "cop": [r1(p[1], 0) for p in W], "fx": [r1(p[2], 0) for p in W], "c_lb": [r1(p[3]) for p in W],
                         "kc": [r1(p[4]) for p in W], "diff": [r1(p[3] - p[4]) for p in W],
                         "now": {"date": last[0], "cop": r1(last[1], 0), "fx": r1(last[2], 1), "c_lb": r1(last[3]), "kc": r1(last[4], 2), "diff": r1(last[3] - last[4]),
                                 "fx_source": next((r["source"] for r in rcsv("usdcop.csv")[::-1] if r["date"] <= last[0]), None)},
                         "yr_ago": next(({"date": p[0], "cop": r1(p[1], 0), "c_lb": r1(p[3])} for p in reversed(pts) if p[0] <= (date.fromisoformat(last[0]) - timedelta(days=365)).isoformat()), None)}
    # ex-dock and FNC differential, monthly
    exd = series(rcsv("exdock_monthly.csv"), "month", "exdock_c_lb")
    kcm = {}
    for d, v in kc.items():
        kcm.setdefault(d[:7], []).append(v)
    kcm = {m: sum(v) / len(v) for m, v in kcm.items()}
    mr = rcsv("monthly_report.csv")
    dif = series(mr, "month", "differential_c_lb")
    ms = sorted(m for m in exd if m >= "2012-01")
    J["exdock"] = {"month": ms, "exdock": [r1(exd[m]) for m in ms], "kc": [r1(kcm.get(m)) for m in ms],
                   "spread": [r1(exd[m] - kcm[m]) if m in kcm else None for m in ms], "fnc_diff": [r1(dif.get(m)) for m in ms]}
    if exd:
        m0 = max(exd)
        hist = [exd[m] - kcm[m] for m in exd if m in kcm and m >= add_months(m0, -120)]
        sp = exd[m0] - kcm.get(m0, float("nan"))
        J["exdock"]["now"] = {"month": m0, "exdock": r1(exd[m0]), "kc": r1(kcm.get(m0)), "spread": r1(sp),
                              "pct_10y": r1(sum(h <= sp for h in hist) / len(hist) * 100, 0) if hist and sp == sp else None}
    if mr:
        L = mr[-1]
        J["monthly_report"] = {k: (float(v) if re.fullmatch(r"-?[\d.]+", str(v)) else v) for k, v in L.items() if v not in ("", None)}
        J["differential_hist"] = {"month": sorted(dif), "v": [dif[m] for m in sorted(dif)]}
    # ICE certs: Colombian coffee in the certified stock (from the certs profile)
    try:
        CP = json.loads((ROOT / "data" / "coffee" / "certs_profile.json").read_text())
        rows = CP["current"]["origin_age"]["rows"]
        col = next((r for r in rows if r["origin"].lower().startswith("colombia")), None)
        J["certs"] = {"date": CP["current"]["daily_date"], "total": CP["current"]["total_bags"], "colombia": col["total"] if col else 0}
    except Exception as e:
        log("certs profile unreadable:", e)
    # deliverable premium for Colombia on KC (rule file kept by hand)
    try:
        RP = json.loads((ROOT / "data" / "coffee" / "ref" / "kc_rule_params.json").read_text())
        J["kc_premium"] = find_colombia_premium(RP)
    except Exception as e:
        log("rule params unreadable:", e)
    S = load_sources()
    J["sources"] = S.get("files", {}); J["last_check"] = S.get("last_check")
    J["brief"] = brief(J)
    (OUT / "colombia.json").write_text(json.dumps(J, ensure_ascii=False, separators=(",", ":")))
    log("built colombia.json: production", pm, "exports", em)
    return J


def find_colombia_premium(RP):
    """Colombia's premium (¢/lb) in the KC delivery schedule in force now (data/coffee/ref/kc_rule_params.json; points/100)."""
    scheds = []
    def walk(o):
        if isinstance(o, dict):
            if "from_delivery" in o and isinstance(o.get("pts"), dict) and "Colombia" in o["pts"]:
                scheds.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(RP)
    now = date.today().strftime("%Y-%m")
    cur = [x for x in scheds if x["from_delivery"] <= now]
    if not cur:
        return None
    x = max(cur, key=lambda x: x["from_delivery"])
    return {"c_lb": x["pts"]["Colombia"] / 100, "from_delivery": x["from_delivery"]}


def pct(v):
    return f"{'+' if v > 0 else ''}{v:.0f}%" if v is not None else "n/a"


def mname(m):
    return datetime.strptime(m + "-01", "%Y-%m-%d").strftime("%B %Y")


def brief(J):
    P, E = J["production"], J["exports"]
    pl, el = P["latest"], E["latest"]
    out = []
    out.append(f"Production (FNC registered) in {mname(pl['month'])}: {pl['value'] / 1000:.2f}m bags, {pct(pl['vs_prev_pct'])} on a year ago and "
               f"{pct(pl['vs_avg5_pct'])} against the 5-year average for the month. Last 12 months: {P['roll12_now']:.2f}m bags "
               f"(a year earlier {P['roll12_year_ago']:.2f}m; three months ago {P['roll12_3m_ago']:.2f}m).")
    out.append(f"Exports in {mname(el['month'])}: {el['value'] / 1000:.2f}m bags, {pct(el['vs_prev_pct'])} on a year ago and {pct(el['vs_avg5_pct'])} against "
               f"the 5-year average. Last 12 months: {E['roll12_now']:.2f}m bags (a year earlier {E['roll12_year_ago']:.2f}m).")
    trend_p = P["roll12_now"] - P["roll12_3m_ago"] if P["roll12_3m_ago"] else 0
    tight = P["roll12_now"] < P["roll12_year_ago"]
    s = ("Washed-arabica supply from Colombia is smaller than a year ago" if tight else "Washed-arabica supply from Colombia is larger than a year ago")
    s += f", and the 12-month production total is {'still falling' if trend_p < -0.05 else 'rising again' if trend_p > 0.05 else 'flat'} over the last three months."
    out.append(s)
    MR = J.get("monthly_report") or {}
    prem = (J.get("kc_premium") or {}).get("c_lb")
    if MR.get("differential_c_lb") is not None:
        d = MR["differential_c_lb"]
        t = f"FNC put the Colombian differential at {d:.1f}¢/lb over New York in {mname(MR['month'])}"
        if prem is not None:
            t += (f"; the KC contract pays only +{prem:g}¢ for Colombian coffee, so a delivered lot gives up about {d - prem:.0f}¢/lb against "
                  f"selling it in the physical market. Colombian coffee is not expected on the exchange while that gap lasts")
        t += "."
        c = J.get("certs")
        if c:
            t += f" ICE certified stock held {c['colombia']:,.0f} bags of Colombian coffee on {c['date']} (total {c['total']:,.0f})."
        out.append(t)
    I = J.get("internal")
    if I:
        n = I["now"]
        out.append(f"Internal reference price {n['cop'] / 1e6:.3f}m COP per carga on {n['date']} = {n['c_lb']:.1f}¢/lb green at {n['fx']:,.0f} COP/US$, "
                   f"{n['diff']:+.1f}¢ against KC front ({n['kc']:.1f}¢)." + (f" A year earlier it was {I['yr_ago']['cop'] / 1e6:.3f}m COP." if I.get("yr_ago") else ""))
    return out


# ------------------------------------------------------------------ main
def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true");
    ap.add_argument("--file", nargs="+")
    a = ap.parse_args(argv)
    if a.file:
        for f in a.file:
            log(f, "->", ingest_file(f, how="manual"))
        build(); return 0
    if a.build:
        build(); return 0
    errors = fetch()
    build()
    for e in errors:
        print("::error::" + e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
