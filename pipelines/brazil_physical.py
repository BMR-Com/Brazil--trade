"""Brazil physical arabica prices, long history -> data/coffee/brazil_physical_history.csv (+ _meta.json).

Series (R$ per 60-kg bag unless stated), stored raw in data/coffee/brazil_physical_raw.csv (date, series, place, brl_60kg,
usd_60kg, source):
  cepea_arabica  CEPEA/ESALQ arabica indicator: tipo 6 bebida dura para melhor, delivered São Paulo city (domestic, naturals,
                 not FOB). Daily from Sep 1996. Sources: the CEPEA file Ma downloads and drops in inbox/ (pipelines/ice_inbox.py
                 recognises it and calls ingest_cepea_file; cepea.org.br disallows automated access, so it is never fetched
                 here), and as an interim source the Notícias Agrícolas daily tables (only if its robots.txt allows them).
  cepea_robusta  CEPEA/ESALQ robusta (conilon) index, US$/bag (Ma's file) -> data/coffee/cepea_robusta_history.csv.
  coop_cd        semi-washed (cereja descascado), co-op quotes in Minas Gerais / São Paulo (Notícias Agrícolas), co-op average.
  coop_t6        tipo 6 bebida dura, co-op quotes (Notícias Agrícolas), co-op average.
  coop_t67       tipo 6/7, co-op quotes (Notícias Agrícolas), co-op average.
FX: USD/BRL PTAX sell (Banco Central do Brasil SGS series 1) in data/coffee/usdbrl_ptax.csv; TradingView FX_IDC USDBRL
    from the coffee desk (coffee/data/prices_cont.csv) fills days BCB has not been read for.
KC: front, 2nd and 3rd positions from data/coffee/kc_spreads_history.csv (ICE settlements, 1994 on; the front rolls at first
    notice). B3 4/5 (ICF1!, US$/bag, 2006 on) from coffee/data/prices_cont.csv.

Output columns (one row per Brazil business day with a CEPEA or co-op quote; all prices US cents/lb unless named _brl):
  date, cepea_brl_60kg, usdbrl, cepea_usc_lb, kc_front_contract, kc_front_usc_lb, kc_2nd3rd_usc_lb,
  cepea_basis_front, cepea_basis_2nd3rd, cd_brl_60kg, cd_usc_lb, cd_basis_2nd3rd, t6_coop_usc_lb, t67_coop_usc_lb,
  icf_usc_lb, icf_basis_2nd3rd, sources
  (basis = Brazil price minus ICE KC, US cents/lb; 60 kg = 132.277 lb)

Usage: python pipelines/brazil_physical.py [--backfill] [--build]
  (no flag)   daily: Notícias Agrícolas latest pages (robots permitting), recent PTAX, rebuild
  --backfill  also pages Notícias Agrícolas back to 1996 and reads PTAX from 1996 (runs by itself while the history is short;
              at most once a week).
  --build     rebuild the history from stored files only (no network)
"""
import io, json, os, re, sys, time
from datetime import date, datetime, timedelta, timezone

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data", "coffee")
RAW = os.path.join(D, "brazil_physical_raw.csv")
FXF = os.path.join(D, "usdbrl_ptax.csv")
OUT = os.path.join(D, "brazil_physical_history.csv")
META = os.path.join(D, "brazil_physical_meta.json")
LB_BAG = 132.277
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"}
NA = "https://www.noticiasagricolas.com.br/cotacoes/cafe/"
NA_SERIES = {"indicador-cepea-esalq-cafe-arabica": "cepea_arabica", "cafe-cereja-descascado-mercado-fisico": "coop_cd",
             "cafe-arabica-mercado-fisico-tipo-6-duro": "coop_t6", "cafe-arabica-mercado-fisico-tipo-6-7": "coop_t67"}
EARLIEST = date(1996, 9, 1)
COLS = ["date", "series", "place", "brl_60kg", "usd_60kg", "source"]
LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s[:300])
    print(time.strftime("%H:%M:%S"), s, flush=True)


def meta_load():
    try:
        return json.load(open(META))
    except Exception:
        return {}


def num(v):
    s = str(v).strip().replace("R$", "").replace("US$", "").strip()
    if s in ("", "-", "***", "nan", "None", "NaN"):
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        x = float(s)
        return x if x > 0 else None
    except Exception:
        return None


def dparse(v):
    s = str(v).strip()
    for f in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%y"):
        try:
            return datetime.strptime(s[:19] if f.startswith("%Y-%m-%d %H") else s[:10], f).date()
        except Exception:
            pass
    return None


# ---------------------------------------------------------------- CEPEA series file (download or inbox)
def cepea_rows(rows):
    """Rows (lists of text cells) of a CEPEA indicator spreadsheet -> [(date, series, brl, usd)].
    Portuguese page: title 'Indicador do Café Arábica CEPEA/ESALQ', header 'Data | À vista R$ | À vista US$', dates dd/mm/yyyy.
    English page (cepea.org.br/en/indicator/coffee.aspx): title 'CEPEA/ESALQ Arabica (or Robusta) Coffee Price Index',
    header 'Date | Price US$', dates mm/dd/yyyy (text), US$ only; zeros before the first quote are blanks."""
    head = " ".join(" ".join(str(c) for c in r) for r in rows[:8]).lower()
    series = "cepea_robusta" if ("robusta" in head or "conillon" in head or "conilon" in head) else "cepea_arabica"
    out, hdr = [], None
    for r in rows:
        cells = [str(c).strip() for c in r]
        low = [c.lower() for c in cells]
        if hdr is None:
            if low and (low[0].startswith("data") or low[0].startswith("date")) and any("$" in c for c in low):
                hdr = {"brl": next((i for i, c in enumerate(low) if "r$" in c), None),
                       "usd": next((i for i, c in enumerate(low) if "us$" in c), None),
                       "us_dates": low[0].startswith("date")}
            continue
        if not cells or not cells[0]:
            continue
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", cells[0])
        d = None
        if m:
            a_, b_, y_ = int(m.group(1)), int(m.group(2)), int(m.group(3))
            mo, dy = (a_, b_) if hdr["us_dates"] else (b_, a_)
            try:
                d = date(y_, mo, dy)
            except ValueError:
                d = None
        else:
            d = dparse(cells[0])
        if d is None or d < EARLIEST:
            continue
        b = num(cells[hdr["brl"]]) if hdr["brl"] is not None and len(cells) > hdr["brl"] else None
        u = num(cells[hdr["usd"]]) if hdr["usd"] is not None and len(cells) > hdr["usd"] else None
        if b or u:
            out.append((d.isoformat(), series, b, u))
    return out


def _cell(v):
    if v is None or (isinstance(v, float) and v != v):
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, float):
        return repr(v)
    return str(v)


def sheet_rows(data):
    """Any CEPEA download format (real xls, often slightly corrupt; xlsx; or an HTML table with an .xls name) -> rows of text."""
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        import xlrd
        wb = xlrd.open_workbook(file_contents=data, ignore_workbook_corruption=True)
        rows = []
        for sh in wb.sheets():
            for i in range(sh.nrows):
                rr = []
                for c in sh.row(i):
                    if c.ctype == xlrd.XL_CELL_DATE:
                        rr.append(xlrd.xldate.xldate_as_datetime(c.value, wb.datemode).strftime("%Y-%m-%d"))
                    else:
                        rr.append(_cell(c.value))
                rows.append(rr)
        return rows
    if data[:4] == b"PK\x03\x04":
        sh = pd.read_excel(io.BytesIO(data), header=None, sheet_name=None, dtype=object)
        rows = []
        for df in sh.values():
            rows += [[_cell(v) if not hasattr(v, "strftime") else v.strftime("%Y-%m-%d") for v in r] for r in df.itertuples(index=False)]
        return rows
    t = data.decode("utf-8", "ignore") if b"<" in data[:2000] else data.decode("latin-1", "ignore")
    rows = []
    for tr in re.findall(r"(?is)<tr.*?</tr>", t):
        rows.append([" ".join(re.sub(r"(?s)<[^>]+>", " ", c).split()) for c in re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", tr)])
    if not rows:
        rows = [ln.split(";") if ";" in ln else ln.split("\t") for ln in t.splitlines()]
    title = " ".join(re.sub(r"(?s)<[^>]+>", " ", t[:3000]).split())[:300]
    return [[title]] + rows


def is_cepea_file(rows):
    head = " ".join(" ".join(str(c) for c in r) for r in rows[:10]).lower()
    return "cepea" in head and ("caf" in head or "coffee" in head) and \
        any(r and str(r[0]).strip().lower().startswith(("data", "date")) for r in rows[:30])


def ingest_cepea_file(data, source="CEPEA file uploaded to inbox"):
    """Add a CEPEA coffee indicator file (arabica or robusta, Portuguese or English page) to the raw store and rebuild.
    Returns (series, first, last, n)."""
    rows = cepea_rows(sheet_rows(data))
    if len(rows) < 5:
        raise ValueError("no CEPEA price rows found")
    new = pd.DataFrame([{"date": d, "series": s, "place": "CEPEA/ESALQ", "brl_60kg": b, "usd_60kg": u, "source": source} for d, s, b, u in rows])
    save_raw(new)
    build()
    return new.series.iloc[0], new.date.min(), new.date.max(), len(new)


# ---------------------------------------------------------------- Notícias Agrícolas
def parse_na(html, series):
    out = []
    try:
        tabs = pd.read_html(io.StringIO(html), thousands=".", decimal=",")
    except Exception:
        return out
    dates = re.findall(r'class="fechamento"[^>]*>[^0-9]*(\d{2}/\d{2}/\d{4})', html) or \
        re.findall(r"Fechamento:?\s*(?:<[^>]+>)*\s*(\d{2}/\d{2}/\d{4})", html)
    for k, t in enumerate(tabs):
        cols = [str(c) for c in t.columns]
        if series == "cepea_arabica":
            if "Data" not in cols:
                continue
            for _, r in t.iterrows():
                v, d = num(r[cols[1]]), dparse(r["Data"])
                if v and d:
                    out.append({"date": d.isoformat(), "series": series, "place": "CEPEA/ESALQ", "brl_60kg": v, "usd_60kg": None,
                                "source": "CEPEA via Noticias Agricolas"})
        else:
            if k >= len(dates):
                continue
            d = dparse(dates[k])
            for _, r in t.iterrows():
                v = num(r[cols[1]])
                if v and d and 100 < v < 10000:
                    out.append({"date": d.isoformat(), "series": series, "place": str(r[cols[0]]).strip(), "brl_60kg": v, "usd_60kg": None,
                                "source": "co-op quotes via Noticias Agricolas"})
    return out


def na_allowed(S, st):
    """Notícias Agrícolas robots.txt must allow the cotações pages (checked on every run; nothing is fetched otherwise)."""
    from urllib import robotparser
    try:
        r = S.get("https://www.noticiasagricolas.com.br/robots.txt", timeout=30)
        rp = robotparser.RobotFileParser()
        rp.parse(r.text.splitlines() if r.ok else [])
        test = [NA + slug + "/2010-06-15" for slug in NA_SERIES]
        ok = all(rp.can_fetch(UA["User-Agent"], u) and rp.can_fetch("*", u) for u in test)
        st["robots"] = {"checked": date.today().isoformat(), "http": r.status_code, "allowed": ok,
                        "disallow_lines": [ln.strip() for ln in r.text.splitlines() if ln.lower().startswith("disallow")][:30]}
        return ok
    except Exception as e:
        st["robots"] = {"checked": date.today().isoformat(), "error": str(e)[:120], "allowed": False}
        return False


def fetch_na(S, M, backfill):
    st = M.setdefault("noticias_agricolas", {})
    if not na_allowed(S, st):
        log("Noticias Agricolas: robots.txt does not allow these pages (or could not be read); skipped", st.get("robots"))
        return
    try:
        r = S.get(NA, timeout=60)
        slugs = sorted(set(re.findall(r'/cotacoes/cafe/([a-z0-9\-]+)', r.text)))
        st["slugs_on_index"] = slugs[:80]
    except Exception as e:
        st["index_error"] = str(e)[:120]
    have = read_raw()
    for slug, name in NA_SERIES.items():
        rows = []
        try:
            r = S.get(NA + slug, timeout=60)
            rows += parse_na(r.text, name) if r.ok else []
        except Exception as e:
            log("NA latest", name, e)
        if backfill and name != "cepea_arabica":
            got = have[have.series == name].date
            start = min(pd.to_datetime(got).min().date() if len(got) else date.today(), date(2018, 3, 1))
            d, miss, n_req, t0 = start, 0, 0, time.time()
            while d > EARLIEST and miss < 10 and time.time() - t0 < 840:
                try:
                    r = S.get(f"{NA}{slug}/{d:%Y-%m-%d}", timeout=60)
                    n_req += 1
                    got_ = parse_na(r.text, name) if r.ok else []
                except Exception as e:
                    got_ = []; log("NA", name, d, e)
                inwin = [x for x in got_ if (d - timedelta(days=21)).isoformat() <= x["date"] <= d.isoformat()]
                miss = 0 if inwin else miss + 1
                rows += inwin
                d -= timedelta(days=7)
                time.sleep(0.25)
            st[name] = {"requests": n_req, "rows": len(rows), "stopped_at": d.isoformat(), "seconds": int(time.time() - t0),
                        "first": min((x["date"] for x in rows), default=None)}
            log("NA backfill", name, st[name])
        if rows:
            save_raw(pd.DataFrame(rows))


# ---------------------------------------------------------------- FX
def fetch_ptax(S, M, backfill):
    st = {}
    old = pd.read_csv(FXF) if os.path.exists(FXF) else pd.DataFrame(columns=["date", "usdbrl", "source"])
    start = EARLIEST if backfill or old.empty else date.today() - timedelta(days=40)
    rows, a = [], start
    while a <= date.today():
        b = min(a + timedelta(days=365 * 9), date.today())
        u = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados?formato=json&dataInicial={a:%d/%m/%Y}&dataFinal={b:%d/%m/%Y}")
        try:
            r = S.get(u, timeout=60)
            js = r.json() if r.ok else []
            rows += [{"date": dparse(x["data"]).isoformat(), "usdbrl": float(x["valor"]), "source": "BCB PTAX sell (SGS 1)"} for x in js]
            st[f"{a}"] = f"HTTP {r.status_code}, {len(js)} days"
        except Exception as e:
            st[f"{a}"] = f"error {str(e)[:100]}"
        a = b + timedelta(days=1)
    if rows:
        new = pd.concat([old, pd.DataFrame(rows)]).drop_duplicates("date", keep="last").sort_values("date")
        new.to_csv(FXF, index=False)
        st["first"], st["last"], st["n"] = new.date.min(), new.date.max(), len(new)
    log("PTAX", st)
    M["ptax"] = st


# ---------------------------------------------------------------- store
def read_raw():
    if os.path.exists(RAW):
        return pd.read_csv(RAW, dtype={"date": str})
    return pd.DataFrame(columns=COLS)


def save_raw(new):
    old = read_raw()
    new = new.reindex(columns=COLS)
    # CEPEA's own file wins over the Notícias Agrícolas copy for the same day
    rank = {"CEPEA series download": 0, "CEPEA file uploaded to inbox": 0}
    allr = pd.concat([old, new])
    allr["_r"] = allr.source.map(rank).fillna(1)
    allr = allr.sort_values(["date", "series", "place", "_r"]).drop_duplicates(["date", "series", "place"], keep="first").drop(columns="_r")
    allr.to_csv(RAW, index=False)


def build():
    raw = read_raw()
    # recent co-op and CEPEA quotes the daily coffee fetch already keeps (coffee/data/br_physical.csv, 2018 on)
    bp = os.path.join(ROOT, "coffee", "data", "br_physical.csv")
    if os.path.exists(bp):
        b = pd.read_csv(bp, dtype={"date": str})
        b = b[b.series.isin(["cepea_arabica", "coop_cd", "coop_arabica", "coop_67"])]
        b = b.assign(series=b.series.replace({"coop_arabica": "coop_t6", "coop_67": "coop_t67"}), brl_60kg=b.brl_bag, usd_60kg=None,
                     source=b.series.map(lambda s: "CEPEA via Noticias Agricolas" if s == "cepea_arabica" else "co-op quotes via Noticias Agricolas"))
        raw = pd.concat([raw, b.reindex(columns=COLS)])
        raw["_r"] = raw.source.map({"CEPEA series download": 0, "CEPEA file uploaded to inbox": 0}).fillna(1)
        raw = raw.sort_values(["date", "series", "place", "_r"]).drop_duplicates(["date", "series", "place"], keep="first")
    if raw.empty:
        log("build: no raw data"); return None
    raw["date"] = pd.to_datetime(raw.date)
    raw["brl_60kg"] = pd.to_numeric(raw.brl_60kg, errors="coerce")
    raw["usd_60kg"] = pd.to_numeric(raw.usd_60kg, errors="coerce")
    piv = raw.groupby(["date", "series"]).brl_60kg.mean().unstack()
    pusd = raw.groupby(["date", "series"]).usd_60kg.mean().unstack()
    src = raw[raw.series == "cepea_arabica"].groupby("date").source.first()
    # FX: PTAX, else TradingView USDBRL from the desk
    fx = pd.Series(dtype=float)
    if os.path.exists(FXF):
        f = pd.read_csv(FXF, parse_dates=["date"]).set_index("date").usdbrl
        fx = f
    pc = os.path.join(ROOT, "coffee", "data", "prices_cont.csv")
    icf = pd.Series(dtype=float)
    if os.path.exists(pc):
        p = pd.read_csv(pc, parse_dates=["date"])
        tv = p[p.symbol == "USDBRL"].set_index("date").close
        fx = pd.concat([fx, tv[~tv.index.isin(fx.index)]]).sort_index()
        icf = p[p.symbol == "ICF1!"].set_index("date").close / LB_BAG * 100
    kc = pd.read_csv(os.path.join(D, "kc_spreads_history.csv"), parse_dates=["date"]).set_index("date")
    rob_w = robusta(pusd, piv, fx, kc, p if os.path.exists(pc) else None)
    piv = piv.reindex(columns=sorted(set(piv.columns) | {"cepea_arabica"}))
    ara = raw[(raw.series == "cepea_arabica") & (raw.brl_60kg.notna() | raw.usd_60kg.notna())]
    idx = pd.DatetimeIndex(sorted(set(ara.date) | set(raw[raw.series.str.startswith("coop")].date)))
    piv = piv.reindex(idx)
    H = pd.DataFrame(index=idx)
    H["cepea_brl_60kg"] = piv.get("cepea_arabica")
    H["usdbrl"] = fx.reindex(idx, method="ffill", tolerance=pd.Timedelta(days=5)) if len(fx) else None
    # CEPEA's own US$ series (the file Ma downloads) first; R$ / PTAX only for days held only as the Notícias Agrícolas R$ copy
    cu = pusd.get("cepea_arabica").reindex(idx) / LB_BAG * 100 if "cepea_arabica" in pusd else pd.Series(float("nan"), index=idx)
    H["cepea_usc_lb"] = cu.fillna(H.cepea_brl_60kg / H.usdbrl / LB_BAG * 100)
    k = kc.reindex(idx, method="ffill", tolerance=pd.Timedelta(days=4))
    H["kc_front_contract"] = k.front
    H["kc_front_usc_lb"] = k.f1
    H["kc_2nd3rd_usc_lb"] = (k.f2 + k.f3) / 2
    H["cepea_basis_front"] = H.cepea_usc_lb - H.kc_front_usc_lb
    H["cepea_basis_2nd3rd"] = H.cepea_usc_lb - H.kc_2nd3rd_usc_lb
    H["cd_brl_60kg"] = piv.get("coop_cd")
    H["cd_usc_lb"] = H.cd_brl_60kg / H.usdbrl / LB_BAG * 100
    H["cd_basis_2nd3rd"] = H.cd_usc_lb - H.kc_2nd3rd_usc_lb
    H["t6_coop_usc_lb"] = piv.get("coop_t6") / H.usdbrl / LB_BAG * 100 if "coop_t6" in piv else None
    H["t67_coop_usc_lb"] = piv.get("coop_t67") / H.usdbrl / LB_BAG * 100 if "coop_t67" in piv else None
    H["icf_usc_lb"] = icf.reindex(idx, method="ffill", tolerance=pd.Timedelta(days=4)) if len(icf) else None
    H["icf_basis_2nd3rd"] = H.icf_usc_lb - H.kc_2nd3rd_usc_lb
    fxsrc = pd.Series("PTAX" if os.path.exists(FXF) else "TV USDBRL", index=idx)
    if os.path.exists(FXF):
        fxsrc[~idx.isin(pd.read_csv(FXF, parse_dates=["date"]).date)] = "TV USDBRL"
    H["sources"] = [";".join(x for x in [("CEPEA file" if s in ("CEPEA series download", "CEPEA file uploaded to inbox") else "CEPEA via NA") if isinstance(s, str) else "",
                                          ("co-ops via NA" if cd == cd else ""), f"FX {fs}", "ICE KC"] if x)
                    for s, cd, fs in zip(src.reindex(idx), H.cd_brl_60kg, fxsrc)]
    H = H[H.cepea_usc_lb.notna() | H.cd_brl_60kg.notna()]
    # CEPEA arabica alone, as CEPEA publishes it (US$/bag), with its basis to ICE KC
    if "cepea_arabica" in pusd and pusd.cepea_arabica.notna().sum() > 100:
        A = pd.DataFrame({"usd_bag": pusd.cepea_arabica.dropna()})
        A["c_lb"] = A.usd_bag / LB_BAG * 100
        ka = kc.reindex(A.index, method="ffill", tolerance=pd.Timedelta(days=4))
        A["kc_front_contract"], A["kc_front_usc_lb"], A["kc_2nd3rd_usc_lb"] = ka.front, ka.f1, (ka.f2 + ka.f3) / 2
        A["basis_front_usc_lb"] = A.c_lb - A.kc_front_usc_lb
        A["basis_2nd3rd_usc_lb"] = A.c_lb - A.kc_2nd3rd_usc_lb
        A.index.name = "date"
        A.round(3).to_csv(ARA, date_format="%Y-%m-%d")
        log("arabica", len(A), A.index.min().date(), A.index.max().date())
    H.index.name = "date"
    num_cols = [c for c in H.columns if c not in ("kc_front_contract", "sources")]
    H[num_cols] = H[num_cols].astype(float).round(3)
    H.to_csv(OUT, date_format="%Y-%m-%d")
    M = meta_load()
    first = lambda c: H.index[H[c].notna()].min().strftime("%Y-%m-%d") if H[c].notna().any() else None
    M["history"] = {"built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "rows": len(H), "last": H.index.max().strftime("%Y-%m-%d"),
                    "first": {c: first(c) for c in ("cepea_brl_60kg", "cepea_usc_lb", "cepea_basis_2nd3rd", "cd_basis_2nd3rd", "t6_coop_usc_lb", "icf_basis_2nd3rd")},
                    "days": {c: int(H[c].notna().sum()) for c in ("cepea_usc_lb", "cepea_brl_60kg", "cd_brl_60kg", "icf_usc_lb")}}
    ch = M.setdefault("charts", {})
    ch["robusta_vs_rc"] = rob_w
    # long Brazil arabica basis chart: only once the CEPEA history reaches meaningfully before the 2018 Notícias Agrícolas copy
    a0 = H.index[H.cepea_basis_2nd3rd.notna()].min() if H.cepea_basis_2nd3rd.notna().any() else None
    ch["cepea_basis_2nd3rd"] = weekly(H.cepea_basis_2nd3rd, 1) if a0 is not None and a0 < pd.Timestamp("2016-01-01") else None
    if ch["cepea_basis_2nd3rd"]:
        mm = H[["cepea_basis_2nd3rd", "cepea_basis_front"]].resample("MS").mean().dropna(how="all")
        mk_ = []
        rc_ = os.path.join(D, "ref", "rule_changes.csv")
        if os.path.exists(rc_):
            r_ = pd.read_csv(rc_)
            keep = ("Brazil", "Re-grading", "Port differentials", "duty paid")
            mk_ = [{"date": str(e)[:7], "label": sh} for e, sh, area in zip(r_.effective_date, r_.short, r_.rule_area)
                   if any(k in str(area) + str(sh) for k in keep) and str(e)[:7] <= mm.index[-1].strftime("%Y-%m")]
        ch["cepea_basis_m"] = {"months": [d.strftime("%Y-%m") for d in mm.index], "b23": [None if x != x else round(float(x), 1) for x in mm.cepea_basis_2nd3rd],
                               "bfront": [None if x != x else round(float(x), 1) for x in mm.cepea_basis_front], "markers": mk_}
    M["arabica_columns"] = {"usd_bag": "CEPEA/ESALQ arabica index (tipo 6 bebida dura para melhor, delivered São Paulo city), US$/60-kg bag (CEPEA, Ma's download)",
                            "c_lb": "US cents/lb (usd_bag / 132.277 x 100)", "kc_front_contract": "ICE KC front (rolls at first notice)",
                            "kc_front_usc_lb": "ICE KC front settlement", "kc_2nd3rd_usc_lb": "average of ICE KC 2nd and 3rd positions",
                            "basis_front_usc_lb": "CEPEA minus KC front, US cents/lb", "basis_2nd3rd_usc_lb": "CEPEA minus KC 2nd/3rd, US cents/lb"}
    M["manual_inputs"] = "CEPEA/ESALQ arabica and robusta indices: manual weekly download by Ma from cepea.org.br, dropped into inbox/ (cepea.org.br disallows automated access)"
    M["robusta_columns"] = {"usd_bag": "CEPEA/ESALQ robusta (conilon) index, US$/60-kg bag (CEPEA, Ma's download)", "c_lb": "US cents/lb",
                            "usd_t": "US$/t (usd_bag / 0.06)", "rc_front_usd_t": "ICE London robusta front (TradingView RC1!), US$/t",
                            "diff_vs_rc_usd_t": "Brazil conilon minus London front, US$/t (Espírito Santo/Rondônia domestic, not FOB; quality differs from LIFFE grade)",
                            "kc_front_usc_lb": "ICE KC front, US cents/lb", "kc_minus_robusta_usc_lb": "KC front minus Brazil conilon, US cents/lb (arbitrage context)"}
    M["columns"] = {
        "cepea_brl_60kg": "CEPEA/ESALQ arabica indicator, tipo 6 bebida dura para melhor, delivered São Paulo city, R$/60-kg bag (CEPEA; Notícias Agrícolas copy where CEPEA's file is not held)",
        "usdbrl": "USD/BRL, BCB PTAX sell (SGS 1); TradingView FX_IDC USDBRL where PTAX not read",
        "cepea_usc_lb": "CEPEA indicator in US cents/lb (R$/bag / USDBRL / 132.277 lb x 100)",
        "kc_front_contract": "ICE KC front contract (rolls at first notice)", "kc_front_usc_lb": "ICE KC front settlement, US cents/lb",
        "kc_2nd3rd_usc_lb": "average of ICE KC 2nd and 3rd positions, US cents/lb (the ICO reference)",
        "cepea_basis_front": "CEPEA minus KC front, US cents/lb", "cepea_basis_2nd3rd": "CEPEA minus KC 2nd/3rd average, US cents/lb",
        "cd_brl_60kg": "semi-washed (cereja descascado), co-op quotes average, R$/60-kg bag (Notícias Agrícolas)", "cd_usc_lb": "semi-washed in US cents/lb",
        "cd_basis_2nd3rd": "semi-washed minus KC 2nd/3rd, US cents/lb", "t6_coop_usc_lb": "tipo 6 duro, co-op average, US cents/lb",
        "t67_coop_usc_lb": "tipo 6/7, co-op average, US cents/lb", "icf_usc_lb": "B3 arabica 4/5 front future (ICF1!, TradingView), US$/bag -> US cents/lb",
        "icf_basis_2nd3rd": "B3 4/5 minus KC 2nd/3rd, US cents/lb", "sources": "per-row source tags"}
    M["quality_note"] = ("CEPEA tipo 6 is a domestic São Paulo price for natural (dry-processed) coffee: not semi-washed, not FOB Santos, not an "
                         "exchange grade. Semi-washed certs on ICE need a quality premium and freight/fobbing on top. Like the ICO series, only the "
                         "change in each gap against its own history means anything; the level is a quality/location difference.")
    json.dump(M, open(META, "w"), indent=1, ensure_ascii=False)
    log("built", OUT, len(H), M["history"]["first"])
    return H


ROB = os.path.join(D, "cepea_robusta_history.csv")
ARA = os.path.join(D, "cepea_arabica_history.csv")


def robusta(pusd, pbrl, fx, kc, prices):
    """CEPEA/ESALQ robusta (conilon) index -> data/coffee/cepea_robusta_history.csv, with the differential to ICE London
    robusta (RC front, US$/t; TradingView RC1!, coffee/data/prices_cont.csv) and to ICE KC front (arbitrage context)."""
    u = pusd.get("cepea_robusta") if "cepea_robusta" in pusd else None
    if u is None or u.notna().sum() < 50:
        b = pbrl.get("cepea_robusta") if "cepea_robusta" in pbrl else None
        if b is None or not len(fx):
            return
        u = b / fx.reindex(b.index, method="ffill", tolerance=pd.Timedelta(days=5))
    u = u.dropna()
    u = u[u > 0]
    R = pd.DataFrame({"usd_bag": u})
    R["c_lb"] = R.usd_bag / LB_BAG * 100
    R["usd_t"] = R.usd_bag / 0.06
    rc = pd.Series(dtype=float)
    if prices is not None:
        rc = prices[prices.symbol == "RC1!"].set_index("date").close.sort_index()
    R["rc_front_usd_t"] = rc.reindex(R.index, method="ffill", tolerance=pd.Timedelta(days=4)) if len(rc) else float("nan")
    R["diff_vs_rc_usd_t"] = R.usd_t - R.rc_front_usd_t
    k = kc.f1.reindex(R.index, method="ffill", tolerance=pd.Timedelta(days=4))
    R["kc_front_usc_lb"] = k
    R["kc_minus_robusta_usc_lb"] = k - R.c_lb
    R.index.name = "date"
    R.round(3).to_csv(ROB, date_format="%Y-%m-%d")
    log("robusta", len(R), R.index.min().date(), R.index.max().date(), "RC from", R.rc_front_usd_t.first_valid_index())
    return weekly(R.diff_vs_rc_usd_t, 0)


def weekly(s, n):
    """Friday averages for the page chart, plus the 5-year percentile of the latest week."""
    w = s.dropna().resample("W-FRI").mean().dropna()
    if w.empty:
        return None
    last5 = w[w.index >= w.index[-1] - pd.DateOffset(years=5)]
    return {"dates": [d.strftime("%Y-%m-%d") for d in w.index], "v": [round(float(x), n) for x in w],
            "now": round(float(w.iloc[-1]), n), "now_date": s.dropna().index[-1].strftime("%Y-%m-%d"),
            "pct5y": round(float((last5 <= w.iloc[-1]).mean() * 100), 0), "median_all": round(float(w.median()), n),
            "median5y": round(float(last5.median()), n)}


def main(argv):
    if "--build" in argv:
        build(); return 0
    import requests
    S = requests.Session(); S.headers.update(UA)
    M = meta_load()
    raw = read_raw()
    # the CEPEA indices come from Ma's files; the backfill only pages the co-op quotes (semi-washed first) further back
    short = raw[raw.series == "coop_cd"].date.min() if len(raw) and (raw.series == "coop_cd").any() else None
    last_bf = (M.get("backfill") or {}).get("ran")
    backfill = "--backfill" in argv or ((short is None or short > "2015-01-01") and (not last_bf or last_bf < (date.today() - timedelta(days=7)).isoformat()))
    M["cepea_download"] = "not fetched automatically (cepea.org.br disallows automated access); CEPEA files come only from Ma's downloads dropped into inbox/"
    fetch_ptax(S, M, backfill or not os.path.exists(FXF))
    fetch_na(S, M, backfill)
    if backfill:
        M["backfill"] = {"ran": date.today().isoformat()}
    M["log"] = LOG[-60:]
    json.dump(M, open(META, "w"), indent=1, ensure_ascii=False)
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
