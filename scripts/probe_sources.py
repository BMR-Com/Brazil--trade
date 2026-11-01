import re, requests, urllib3
from bs4 import BeautifulSoup
urllib3.disable_warnings()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
def get(u, **k):
    try:
        return requests.get(u, headers=H, timeout=60, **k)
    except Exception as e:
        print("ERR", u, str(e)[:200]); return None
# 1) Cecafé daily summary: dump tables, iframes, scripts with data, file links
r = get("https://www.cecafe.com.br/dados-estatisticos/exportacoes-brasileiras/resumo-diario/")
if r is not None:
    print("===== resumo", r.status_code, len(r.text))
    s = BeautifulSoup(r.text, "html.parser")
    main = s.find("main") or s.find("article") or s
    for t in s.find_all("table")[:8]:
        print("--- TABLE"); 
        for tr in t.find_all("tr")[:40]:
            print("  |", " | ".join(c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])))
    for f in s.find_all(["iframe", "embed", "object"]):
        print("FRAME", f.get("src") or f.get("data"))
    for a in s.find_all("a", href=True):
        if re.search(r"\.(pdf|xlsx?|csv)|upload|grafico", a["href"], re.I): print("FILE", a.get_text(" ", strip=True)[:60], "|", a["href"])
    txt = (s.find("div", class_=re.compile("entry|content|post")) or s).get_text("\n", strip=True)
    i = txt.find("Resumo"); print("TEXT>>", txt[i:i+3000] if i >= 0 else txt[:2000])
    for sc in s.find_all("script"):
        c = sc.string or ""
        if re.search(r"arabica|arábica|conilon|sacas", c, re.I): print("SCRIPT>>", c[:1500])
# 2) Conab café pages (new gov.br site and the information portal)
for u in ["https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/safra-de-cafe",
          "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/series-historicas",
          "https://portaldeinformacoes.conab.gov.br/safra-serie-historica-cafe.html",
          "https://portaldeinformacoes.conab.gov.br/downloads/arquivos/SerieHistoricaCafe.txt"]:
    r = get(u, verify=False)
    if r is None: continue
    print("=====", r.status_code, u, len(r.content), r.headers.get("content-type"))
    if "html" in (r.headers.get("content-type") or ""):
        s = BeautifulSoup(r.text, "html.parser"); n = 0
        for a in s.find_all("a", href=True):
            if re.search(r"caf|serie|série|xls|txt|csv|pdf|levantamento|boletim", a["href"] + a.get_text(), re.I):
                print("  ", a.get_text(" ", strip=True)[:70], "|", a["href"]); n += 1
            if n > 60: break
    else:
        print(r.text[:2500])
