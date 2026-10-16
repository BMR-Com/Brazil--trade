"""
Sugar data refresh (runs in GitHub Actions).

  MAPA fortnightly cane/sugar/ethanol (gov.br)     -> sugar/data/mapa_fortnight.csv
  UNICA monthly crop report PDF (unicadata.com.br) -> sugar/data/unica_reports.csv
  Prices via TradingView feed (ICE NY11, ICE London No.5 per contract, B3 hydrous ethanol, USD/BRL, Brent)
                                                   -> sugar/data/prices_cont.csv, prices_contracts.csv
  ANP weekly pump prices (São Paulo)               -> sugar/data/anp_sp.csv
  USDA PSD sugar (bulk CSV)                        -> sugar/data/psd_sugar.csv

Usage: python sugar/scripts/fetch.py [--full]
  --full re-downloads every MAPA season back to 2007/08 and the whole contract history.
"""
import io, os, re, sys, time, zipfile, hashlib, argparse, traceback
from datetime import date
import requests
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import mapa, unica  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
S = requests.Session(); S.headers.update(H)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def safra_now(d=None):
    d = d or date.today()
    y = d.year if d.month >= 4 else d.year - 1
    return y


# ---------------------------------------------------------------- MAPA
MAPA_BASE = "https://www.gov.br/agricultura/pt-br/assuntos/sustentabilidade/agroenergia/acompanhamento-da-producao-sucroalcooleira/"


def fetch_mapa(full=False):
    out = os.path.join(DATA, "mapa_fortnight.csv")
    old = pd.read_csv(out, parse_dates=["start", "end"]) if os.path.exists(out) else pd.DataFrame()
    y0 = safra_now()
    seasons = range(2007, y0 + 1) if (full or old.empty) else [y0 - 1, y0]
    tmp = os.path.join(ROOT, ".mapa_tmp"); os.makedirs(tmp, exist_ok=True)
    for y in seasons:
        slug = f"{y}-{y + 1}"
        try:
            t = S.get(MAPA_BASE + slug, timeout=60).text
        except Exception as e:
            log("mapa page fail", slug, e); continue
        links = [l for l in re.findall(r'href="([^"]+\.xlsx?)"', t, re.I) if "basedeconhecimento" not in l]
        log("mapa", slug, len(links), "files")
        for u in links:
            fn = os.path.join(tmp, slug + "__" + u.rsplit("/", 1)[1])
            for k in range(3):
                try:
                    r = S.get(u, timeout=120)
                    if r.ok:
                        open(fn, "wb").write(r.content)
                    break
                except Exception:
                    time.sleep(3)
    new, bad = mapa.build(tmp)
    log("mapa parsed", len(new), "rows;", len(bad), "files skipped")
    if new.empty:
        return
    new = new.drop(columns=["file"])
    if not old.empty:
        keep = ~old["safra"].isin(new["safra"].unique())
        new = pd.concat([old[keep], new])
    new = new.drop_duplicates(["safra", "region", "uf", "end"], keep="last").sort_values(["end", "region", "uf"])
    new.to_csv(out, index=False)
    log("mapa saved", out, new.shape)


# ---------------------------------------------------------------- UNICA
def fetch_unica():
    out = os.path.join(DATA, "unica_reports.csv")
    try:
        t = S.get("https://unicadata.com.br/listagem.php?idMn=63", timeout=90).text
        m = re.search(r"https://unicadata\.com\.br/arquivos/pdfs/[^'\"]+\.pdf", t)
        if not m:
            log("unica: no pdf link"); return
        url = m.group(0)
        r = S.get(url, timeout=180)
        rows = unica.parse_pdf(io.BytesIO(r.content))
        if not rows:
            log("unica: parse returned nothing", url); return
        df = pd.DataFrame(rows); df["source_url"] = url
        if os.path.exists(out):
            old = pd.read_csv(out)
            df = pd.concat([old, df]).drop_duplicates(["position", "table", "metric", "region", "season"], keep="last")
        df.to_csv(out, index=False)
        log("unica saved", df["position"].max(), len(df))
    except Exception:
        traceback.print_exc()


# ---------------------------------------------------------------- prices
def _tv():
    from tvDatafeed import TvDatafeed
    return TvDatafeed()


def _hist(tv, sym, ex, n=5000):
    from tvDatafeed import Interval
    for k in range(4):
        try:
            d = tv.get_hist(symbol=sym, exchange=ex, interval=Interval.in_daily, n_bars=n)
            if d is not None and len(d):
                d = d.reset_index()[["datetime", "open", "high", "low", "close", "volume"]]
                d["date"] = pd.to_datetime(d["datetime"]).dt.date
                return d.drop(columns="datetime")
        except Exception as e:
            log("tv err", sym, e)
        time.sleep(2 + k * 3)
    return None


CONT = [("W1!", "ICEEUR"), ("W2!", "ICEEUR"), ("SB1!", "ICEUS"), ("SB2!", "ICEUS"), ("ETH1!", "BMFBOVESPA"),
        ("ETH2!", "BMFBOVESPA"), ("USDBRL", "FX_IDC"), ("BRN1!", "ICEEUR"), ("RB1!", "NYMEX")]
WHITE = "HKQVZ"           # London No.5 months
PAIR = {"H": ("H", 0), "K": ("K", 0), "Q": ("N", 0), "V": ("V", 0), "Z": ("H", 1)}   # white -> raw (month, year offset)


def fetch_prices(full=False):
    tv = _tv()
    rows = []
    for sym, ex in CONT:
        d = _hist(tv, sym, ex)
        log("tv", sym, None if d is None else len(d))
        if d is not None:
            d.insert(0, "symbol", f"{ex}:{sym}"); rows.append(d)
    if rows:
        new = pd.concat(rows)
        out = os.path.join(DATA, "prices_cont.csv")
        if os.path.exists(out):
            old = pd.read_csv(out)
            old["date"] = pd.to_datetime(old["date"]).dt.date
            new = pd.concat([old, new]).drop_duplicates(["symbol", "date"], keep="last")
        new.sort_values(["symbol", "date"]).to_csv(out, index=False)

    out = os.path.join(DATA, "prices_contracts.csv")
    old = pd.read_csv(out) if os.path.exists(out) else pd.DataFrame(columns=["symbol", "date"])
    y0 = date.today().year
    years = range(2008, y0 + 3) if (full or old.empty) else range(y0 - 1, y0 + 3)
    want = []
    for y in years:
        for w in WHITE:
            rm, dy = PAIR[w]
            want += [(f"W{w}{y}", "ICEEUR"), (f"SB{rm}{y + dy}", "ICEUS")]
    seen, rows = set(), []
    for sym, ex in want:
        if sym in seen:
            continue
        seen.add(sym)
        d = _hist(tv, sym, ex, 1000)
        if d is None:
            log("miss", sym); continue
        d.insert(0, "symbol", sym); rows.append(d)
    if rows:
        new = pd.concat(rows)
        if len(old):
            old["date"] = pd.to_datetime(old["date"]).dt.date
            new = pd.concat([old, new]).drop_duplicates(["symbol", "date"], keep="last")
        new.sort_values(["symbol", "date"]).to_csv(out, index=False)
        log("contracts saved", new.symbol.nunique())


# ---------------------------------------------------------------- ANP
def fetch_anp():
    try:
        r = S.get("https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/semanal/semanal-estados-desde-2013.xlsx", timeout=240)
        d = pd.read_excel(io.BytesIO(r.content), header=None)
        hdr = d.index[d.iloc[:, 0].astype(str).str.contains("DATA INICIAL", na=False)][0]
        d.columns = [str(c).strip() for c in d.iloc[hdr]]
        d = d.iloc[hdr + 1:]
        d = d[d["PRODUTO"].isin(["ETANOL HIDRATADO", "GASOLINA COMUM"]) & (d["ESTADO"] == "SAO PAULO")]
        d = d[["DATA INICIAL", "DATA FINAL", "PRODUTO", "PREÇO MÉDIO REVENDA"]]
        d.columns = ["start", "end", "product", "price"]
        d["end"] = pd.to_datetime(d["end"]).dt.date
        d["price"] = pd.to_numeric(d["price"], errors="coerce")
        p = d.pivot_table(index="end", columns="product", values="price").rename(columns={"ETANOL HIDRATADO": "hydrous", "GASOLINA COMUM": "gasoline"})
        p.to_csv(os.path.join(DATA, "anp_sp.csv"))
        log("anp", len(p))
    except Exception:
        traceback.print_exc()


# ---------------------------------------------------------------- PSD
def fetch_psd():
    try:
        r = S.get("https://apps.fas.usda.gov/psdonline/downloads/psd_sugar_csv.zip", timeout=180)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        d = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), dtype={"Commodity_Code": str})
        d = d[d.Market_Year >= 1995][["Country_Code", "Country_Name", "Market_Year", "Attribute_Description", "Value"]]
        d.to_csv(os.path.join(DATA, "psd_sugar.csv"), index=False)
        log("psd", d.shape)
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--full", action="store_true"); ap.add_argument("--only", default="")
    a = ap.parse_args()
    steps = {"mapa": lambda: fetch_mapa(a.full), "unica": fetch_unica, "prices": lambda: fetch_prices(a.full),
             "anp": fetch_anp, "psd": fetch_psd}
    for k, f in steps.items():
        if a.only and k not in a.only.split(","):
            continue
        try:
            f()
        except Exception:
            traceback.print_exc()
