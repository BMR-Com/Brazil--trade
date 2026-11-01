import io, re, requests, urllib3
import pandas as pd
from bs4 import BeautifulSoup
urllib3.disable_warnings()
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_rows", 200)
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
get = lambda u: requests.get(u, headers=H, timeout=90, verify=False)
X = "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/safra-de-cafe/3o-levantamento-de-cafe-safra-2026/site_previsao-de-safra-cafe-set-2026.xls"
r = get(X); print("XLS", r.status_code, len(r.content), r.headers.get("content-type"))
try:
    xs = pd.read_excel(io.BytesIO(r.content), sheet_name=None, header=None)
    for name, df in xs.items():
        print("=== SHEET", name, df.shape); print(df.head(70).to_string())
except Exception as e:
    print("xls err", e, r.content[:300])
for k in ["arabica", "conilon", "total-arabica-e-conilon"]:
    u = f"https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/series-historicas/cafe/{k}"
    s = BeautifulSoup(get(u).text, "html.parser")
    print("=====", u)
    for a in s.find_all("a", href=True):
        if re.search(r"\.(xls|xlsx|csv|ods)|@@download|/view$|/file$", a["href"], re.I): print("  ", a.get_text(" ", strip=True)[:80], "|", a["href"])
