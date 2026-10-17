import re, io, zipfile, traceback, requests
from html import unescape
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
S = requests.Session(); S.headers.update(H)
def txt(h):
    h = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", h); return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " | ", h)))
def get(u, n=1500, show=True):
    try:
        r = S.get(u, timeout=60); ct = r.headers.get("content-type", "")
        print(f"\n=== {u}\n{r.status_code} {ct} len={len(r.content)}")
        if show and ("html" in ct or "text" in ct or "json" in ct): print(txt(r.text)[:n])
        return r
    except Exception as e:
        print(f"\n=== {u}\nERR {e}")
for u in ["https://www.ico.org/coffee_prices.asp", "https://ico.org/resources/coffee-prices/", "https://www.ico.org/prices/pr-prices.pdf",
          "https://ico.org/resources/coffee-market-report-statistics-section/", "https://www.ico.org/prices/p1-January.pdf",
          "https://www.ico.org/new_historical.asp", "https://www.ico.org/prices/po-production.pdf"]:
    r = get(u, 1200)
    if r is not None and r.ok and "html" in r.headers.get("content-type", ""):
        print("LINKS", sorted(set(re.findall(r'href="([^"]*(?:\.pdf|\.xlsx?|price|indicator)[^"]*)"', r.text, re.I)))[:60])
for u in ["https://www.noticiasagricolas.com.br/cotacoes/cafe", "https://www.noticiasagricolas.com.br/cotacoes/cafe/indicador-cepea-esalq-cafe-arabica",
          "https://www.noticiasagricolas.com.br/cotacoes/cafe/indicador-cepea-esalq-cafe-conillon", "https://www.noticiasagricolas.com.br/cotacoes/cafe/cafe-arabica-mercado-fisico-tipo-6-duro"]:
    r = get(u, 2500)
    if r is not None and r.ok:
        print("LINKS", sorted(set(re.findall(r'href="(/cotacoes/cafe/[^"]+)"', r.text)))[:80])
get("https://www.cecafe.com.br/dados-estatisticos/exportacoes-brasileiras/", 800)
r = get("https://apps.fas.usda.gov/psdonline/downloads/psd_coffee_csv.zip", show=False)
if r is not None and r.ok:
    z = zipfile.ZipFile(io.BytesIO(r.content)); print(z.namelist()); print(z.read(z.namelist()[0])[:600])
get("https://www.conab.gov.br/info-agro/safras/cafe", 800)
try:
    from tvDatafeed import TvDatafeed, Interval
    tv = TvDatafeed()
    for sym, ex in [("KC1!", "ICEUS"), ("KC2!", "ICEUS"), ("RC1!", "ICEEUR"), ("RC2!", "ICEEUR"), ("ICF1!", "BMFBOVESPA"), ("KCZ2026", "ICEUS"),
                    ("KCH2027", "ICEUS"), ("RCX2026", "ICEEUR"), ("RCF2027", "ICEEUR"), ("KCZ2015", "ICEUS"), ("RCX2015", "ICEEUR"), ("ICFZ2026", "BMFBOVESPA")]:
        try:
            d = tv.get_hist(symbol=sym, exchange=ex, interval=Interval.in_daily, n_bars=5000)
            print("TV", ex, sym, None if d is None else (len(d), str(d.index[0])[:10], str(d.index[-1])[:10], float(d.close.iloc[-1])))
        except Exception as e:
            print("TV err", sym, e)
except Exception:
    traceback.print_exc()
