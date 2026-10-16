import re, sys, io, zipfile, json, traceback
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}

def get(u, n=600, **kw):
    try:
        r = requests.get(u, headers=H, timeout=40, **kw)
        ct = r.headers.get("content-type", "")
        print(f"\n=== {u}\n{r.status_code} {ct} len={len(r.content)}")
        if "text" in ct or "json" in ct:
            t = r.text
            print(t[:n].replace("\n", " "))
        return r
    except Exception as e:
        print(f"\n=== {u}\nERR {e}")

# UNICA
r = get("https://unicadata.com.br/", 300)
if r is not None and r.ok:
    links = sorted(set(re.findall(r'href="([^"]+)"', r.text)))
    print([l for l in links if "php" in l][:80])
r = get("https://unicadata.com.br/historico-de-producao-e-moagem.php?idMn=31&tipoHistorico=4", 300)
if r is not None and r.ok:
    print(sorted(set(re.findall(r'(?:href|action|src)="([^"]+)"', r.text)))[:80])
    print(re.findall(r'<select[^>]*name="([^"]+)"', r.text))
get("https://unicadata.com.br/listagem.php?idMn=63", 300)
get("https://www.unica.com.br/", 200)

# CEPEA
for u in ["https://www.cepea.org.br/br/indicador/etanol.aspx",
          "https://www.cepea.esalq.usp.br/br/indicador/series/etanol.aspx?id=103",
          "https://cepea.org.br/br/indicador/etanol-diario-paulinia.aspx",
          "https://www.cepea.org.br/br/indicador/acucar.aspx"]:
    r = get(u, 300)
    if r is not None and r.ok and "html" in r.headers.get("content-type", ""):
        print(sorted(set(re.findall(r'href="([^"]*(?:series|xls)[^"]*)"', r.text)))[:40])

# ANP pump prices
get("https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/semanal/semanal-estados-desde-2013.xlsx", 100)
r = get("https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/levantamento-de-precos-de-combustiveis-ultimas-semanas-pesquisadas", 200)
if r is not None and r.ok:
    print(sorted(set(re.findall(r'href="([^"]+\.xlsx?)"', r.text)))[:40])

# Yahoo
for s in ["SB=F", "SBH27.NYB", "BRL=X", "BZ=F", "SW=F", "QW=F"]:
    get(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?range=5d&interval=1d", 250)

# FAS PSD bulk sugar
r = get("https://apps.fas.usda.gov/psdonline/downloads/psd_sugar_csv.zip", 100)
if r is not None and r.ok:
    try:
        z = zipfile.ZipFile(io.BytesIO(r.content)); print(z.namelist())
        t = z.read(z.namelist()[0]).decode("latin1"); print(t[:800])
    except Exception as e:
        print("zip err", e)

# Comex weekly / monthly
get("https://balanca.economia.gov.br/balanca/bd/comexstat-bd/ncm/EXP_2026.csv", 200, stream=True)
get("https://api-comexstat.mdic.gov.br/general/dates/updated", 300)

# Thailand / India
get("http://www.ocsb.go.th/", 300)
get("https://www.ocsb.go.th/", 300)
get("https://www.indiansugar.com/", 300)
get("https://www.isma.org.in/", 300)

# ICE white sugar settlement / barchart
get("https://www.ice.com/marketdata/DelayedMarkets.shtml?getContractsAsJson=&productId=6&hubId=24", 300)
get("https://www.barchart.com/futures/quotes/SW*0/futures-prices", 200)

# TradingView websocket via tvdatafeed
try:
    from tvDatafeed import TvDatafeed, Interval
    tv = TvDatafeed()
    for sym, ex in [("W1!", "ICEEUR"), ("SB1!", "ICEUS"), ("ETH1!", "BMFBOVESPA"), ("USDBRL", "FX_IDC"), ("WZ2026", "ICEEUR"), ("SBH2027", "ICEUS")]:
        try:
            d = tv.get_hist(symbol=sym, exchange=ex, interval=Interval.in_daily, n_bars=5000)
            print("\nTV", ex, sym, None if d is None else (len(d), d.index[0], d.tail(2).to_string()))
        except Exception as e:
            print("TV err", sym, e)
except Exception:
    traceback.print_exc()
