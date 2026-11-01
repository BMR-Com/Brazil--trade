import re, requests, urllib3
from bs4 import BeautifulSoup
urllib3.disable_warnings()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
def get(u, **k):
    try:
        return requests.get(u, headers=H, timeout=60, verify=False, **k)
    except Exception as e:
        print("ERR", u, str(e)[:200]); return None
r = get("https://www.cecafe.com.br/dados-estatisticos/exportacoes-brasileiras/resumo-diario/")
s = BeautifulSoup(r.text, "html.parser")
for k, t in enumerate(s.find_all("table")):
    prev = []
    for el in t.find_all_previous(string=True, limit=60):
        x = el.strip()
        if x and len(x) < 200: prev.append(x)
        if len(prev) >= 8: break
    print("TABLE", k, "<<", " || ".join(reversed(prev)))
    par = t
    for _ in range(6):
        par = par.parent
        if par is None: break
        print("   anc", par.name, par.get("id"), (par.get("class") or [])[:3])
for u in ["https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/series-historicas/cafe",
          "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/safra-de-cafe/3o-levantamento-de-cafe-safra-2026/3o-levantamento-de-cafe-safra-2026"]:
    r = get(u)
    print("=====", r.status_code, u)
    s = BeautifulSoup(r.text, "html.parser")
    for a in s.find_all("a", href=True):
        h = a["href"]
        if re.search(r"\.(xls|xlsx|pdf|csv|txt|ods)|@@download|/view$|/file$|tabela|serie|levantamento", h, re.I) and "facebook" not in h:
            print("  ", a.get_text(" ", strip=True)[:80], "|", h)
