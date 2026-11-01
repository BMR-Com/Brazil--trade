import re, requests
from bs4 import BeautifulSoup
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
URLS = ["https://www.cecafe.com.br/", "https://www.cecafe.com.br/dados-estatisticos/exportacoes-brasileiras/",
        "https://www.cecafe.com.br/publicacoes/relatorio-de-exportacoes/", "https://www.cecafe.com.br/sitemap.xml",
        "https://www.conab.gov.br/info-agro/safras/cafe", "https://www.conab.gov.br/info-agro/safras/serie-historica-das-safras",
        "https://portaldeinformacoes.conab.gov.br/safra-serie-historica-cafe.html", "https://portaldeinformacoes.conab.gov.br/downloads/arquivos/SerieHistoricaCafe.txt",
        "https://www.noticiasagricolas.com.br/noticias/cafe/", "https://revistacafeicultura.com.br/?s=green+coffee+exports"]
KEY = re.compile(r"export|registr|diári|diari|embarq|relat|planilha|xls|csv|txt|serie|série|safra|cafe|café", re.I)
for u in URLS:
    try:
        r = requests.get(u, headers=H, timeout=40)
        print("=====", r.status_code, u, len(r.content), r.headers.get("content-type"))
        if "html" in (r.headers.get("content-type") or "") or u.endswith(".xml"):
            s = BeautifulSoup(r.text, "html.parser")
            seen = set()
            for a in s.find_all(["a", "loc"]):
                href = a.get("href") if a.name == "a" else a.text
                t = (a.get_text(" ", strip=True) if a.name == "a" else "")[:80]
                if href and KEY.search(href + " " + t) and href not in seen:
                    seen.add(href); print("  ", t, "|", href)
                if len(seen) > 70: break
        else:
            print(r.text[:1500])
    except Exception as e:
        print("=====", "ERR", u, e)
