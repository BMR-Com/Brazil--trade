import re, io, traceback, requests
import pandas as pd
from html import unescape
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
S = requests.Session(); S.headers.update(H)
def txt(h):
    h = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", h); return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " | ", h)))
def get(u, **kw):
    try:
        r = S.get(u, timeout=60, **kw); print(f"\n=== {u}\n{r.status_code} {r.headers.get('content-type','')} len={len(r.content)}"); return r
    except Exception as e:
        print(f"\n=== {u}\nERR {e}")
NA = "https://www.noticiasagricolas.com.br/cotacoes/cafe/"
for s in ["indicador-cepea-esalq-cafe-arabica", "indicador-cepea-esalq-cafe-conillon", "cafe-arabica-mercado-fisico-tipo-6-duro", "cafe-conillon-disponivel-vitoria-es", "cafe-cereja-descascado-mercado-fisico"]:
    r = get(NA + s)
    if r is not None and r.ok:
        try:
            tabs = pd.read_html(io.StringIO(r.text), decimal=",", thousands=".")
            print("tables", len(tabs))
            for t in tabs[:3]: print(t.head(12).to_string()[:1500])
        except Exception as e: print("read_html", e)
        print("DATES", re.findall(r'(?:Fechamento|Data)[^<]{0,40}(\d{2}/\d{2}/\d{4})', r.text)[:5])
        print("hist links", sorted(set(re.findall(r'href="([^"]*' + s + r'[^"]*\d{4}[^"]*)"', r.text)))[:10])
# historical page format on NA: /cotacoes/cafe/<slug>/YYYY-MM-DD ?
r = get(NA + "indicador-cepea-esalq-cafe-arabica/2026-09-15")
if r is not None and r.ok:
    try: print(pd.read_html(io.StringIO(r.text), decimal=",", thousands=".")[0].head(5).to_string())
    except Exception as e: print(e)
for u in ["https://federaciondecafeteros.org/wp/estadisticas-cafeteras/", "https://federaciondecafeteros.org/wp/", "https://federaciondecafeteros.org/app/uploads/2019/10/precio_cafe.pdf"]:
    r = get(u)
    if r is not None and r.ok and "html" in r.headers.get("content-type", ""):
        print("LINKS", sorted(set(re.findall(r'href="([^"]*(?:\.xlsx?|\.pdf|precio|estadistic)[^"]*)"', r.text, re.I)))[:50])
        print(txt(r.text)[:1500])
for u in ["https://giacaphe.com/gia-ca-phe-noi-dia/", "https://giacaphe.com/", "https://www.customs.gov.vn/", "https://tintaynguyen.com/gia-ca-phe/"]:
    r = get(u)
    if r is not None and r.ok:
        t = txt(r.text); i = t.lower().find("đắk lắk"); print(t[max(0,i-300):i+1500] if i>=0 else t[:800])
        try:
            tabs = pd.read_html(io.StringIO(r.text)); print("tables", len(tabs)); [print(x.head(10).to_string()[:1200]) for x in tabs[:2]]
        except Exception as e: print("read_html", e)
