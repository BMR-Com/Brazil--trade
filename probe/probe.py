import re, io, json, traceback
import requests
import pandas as pd
from html import unescape

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
S = requests.Session(); S.headers.update(H)

def txt(html):
    html = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " | ", html)))

B = "https://unicadata.com.br/"
home = S.get(B, timeout=40).text
menu = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', home, re.S)
print("MENU", [(h, txt(t).strip(" |")) for h, t in menu if "php" in h])
for h in ["historico-de-producao-e-moagem.php?idMn=31&tipoHistorico=4",
          "historico-de-producao-e-moagem.php?idMn=31&tipoHistorico=2",
          "historico-de-producao-e-moagem.php?idMn=32&tipoHistorico=4",
          "listagem.php?idMn=63", "listagem.php?idMn=4", "listagem.php?idMn=7"]:
    r = S.get(B + h, timeout=40)
    print("\n=====", h, r.status_code)
    sel = re.findall(r'(?s)<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', r.text)
    for n, body in sel:
        print("SELECT", n, re.findall(r'value="([^"]*)"[^>]*>([^<]*)', body)[:60])
    print("FORMS", re.findall(r'<form[^>]*>', r.text))
    print("LINKS", sorted(set(re.findall(r'href="([^"]*(?:xls|csv|pdf|download|exporta|idMn=)[^"]*)"', r.text)))[:60])
    t = txt(r.text)
    i = t.find("Moagem")
    print("TEXT", t[max(0, i - 200): i + 2500])

# try posting a safra selection to the historico page
try:
    r = S.get(B + "historico-de-producao-e-moagem.php?idMn=31&tipoHistorico=4&acao=visualizar&idTabela=2551&produto=cana&safraIni=2025%2F2026&safraFim=2025%2F2026&estado=RS%2CSC%2CPR%2CSP%2CRJ%2CMG%2CES%2CMS%2CMT%2CGO%2CDF", timeout=40)
    print("\nTRYGET", r.status_code, txt(r.text)[:1500])
except Exception as e:
    print(e)

# ANP weekly state file structure
try:
    r = S.get("https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/semanal/semanal-estados-desde-2013.xlsx", timeout=120)
    x = pd.ExcelFile(io.BytesIO(r.content))
    print("\nANP sheets", x.sheet_names)
    for sh in x.sheet_names[:2]:
        d = x.parse(sh, header=None, nrows=20)
        print(d.to_string()[:3000])
    d = x.parse(x.sheet_names[0], header=None)
    print(d.tail(5).to_string()[:2000])
except Exception:
    traceback.print_exc()

# TradingView expired contracts
try:
    from tvDatafeed import TvDatafeed, Interval
    tv = TvDatafeed()
    for sym, ex in [("WZ2020", "ICEEUR"), ("SBH2021", "ICEUS"), ("WQ2023", "ICEEUR"), ("SBN2023", "ICEUS"), ("WV2026", "ICEEUR"),
                    ("SBV2026", "ICEUS"), ("WH2027", "ICEEUR"), ("W2!", "ICEEUR"), ("SB2!", "ICEUS"), ("ETH2!", "BMFBOVESPA"),
                    ("ETHF2027", "BMFBOVESPA"), ("ACF1!", "BMFBOVESPA"), ("BRN1!", "ICEEUR"), ("SBV2015", "ICEUS"), ("WV2015", "ICEEUR")]:
        try:
            d = tv.get_hist(symbol=sym, exchange=ex, interval=Interval.in_daily, n_bars=5000)
            print("TV", ex, sym, None if d is None else (len(d), str(d.index[0]), str(d.index[-1]), float(d.close.iloc[-1])))
        except Exception as e:
            print("TV err", sym, e)
except Exception:
    traceback.print_exc()
