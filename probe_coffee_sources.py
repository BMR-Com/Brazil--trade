"""One-off probe #2 (deleted after)."""
import json, re, html, urllib.robotparser
from urllib.parse import urlparse
import requests
AGENT = "BMR-Com research desk (github.com/BMR-Com)"
H = {"User-Agent": AGENT}
def get(url, t=90, **kw):
    try:
        r = requests.get(url, headers=H, timeout=t, **kw)
        print(f"  GET {url[:140]} -> {r.status_code} {len(r.content)}B"); return r
    except Exception as e:
        print(f"  GET {url[:140]} -> ERR {str(e)[:160]}"); return None
txt = lambda s: re.sub(r"\s+", " ", html.unescape(re.sub("<[^>]+>", " ", s)))
KW = r"(MTGB|fine cup|good cup|semi-?washed|cereja descascad|bebida dura|bebida rio|conillon|conilon|tipo 6|t\.?6|17/18|14/16|13 ?up|FOB|diferencia|differential|R\$ ?[\d.,]+)"
print("== SAFRAS PT daily posts")
r = get("https://safras.com.br/wp-json/wp/v2/posts", params={"search": "café", "per_page": 30, "_fields": "date,link,title,content"})
for p in (r.json() if r is not None and r.ok else []):
    t = txt(p["content"]["rendered"])
    hits = re.findall(r"[^.]*" + KW + r"[^.]*\.", t, re.I)
    print("  --", p["date"][:10], txt(p["title"]["rendered"])[:90], "| words", len(t.split()), "| hits", len(hits))
    for h in [x for x in re.findall(r"[^.]{0,260}(?:R\$ ?[\d.,]+|FOB|bebida dura|cereja|conilon|tipo 6)[^.]{0,200}\.", t, re.I)][:4]:
        print("       ", h.strip()[:420])
print("== SAFRAS EN coffee posts with quality words (all pages of search=coffee)")
n = 0
for page in range(1, 6):
    r = get("https://safras.com.br/eng/wp-json/wp/v2/posts", params={"search": "coffee", "per_page": 100, "page": page, "_fields": "date,link,title,content"})
    if r is None or not r.ok: break
    for p in r.json():
        t = txt(p["content"]["rendered"])
        hits = re.findall(r"[^.]{0,200}(?:MTGB|fine cup|good cup|semi-?washed|13 ?up|17/18|14/16|differential)[^.]{0,200}\.", t, re.I)
        if hits:
            n += 1
            print("  --", p["date"][:10], txt(p["title"]["rendered"])[:80])
            for h in hits[:3]: print("       ", h.strip()[:400])
print("  EN posts with quality words:", n)
print("== IBGE 254 categories")
r = get("https://servicodados.ibge.gov.br/api/v3/agregados/254/metadados", t=120)
if r is not None and r.ok:
    J = r.json()
    print("  vars:", [(v["id"], v["nome"], v.get("unidade")) for v in J.get("variaveis", [])])
    for c in J["classificacoes"]:
        print("  class", c["id"], c["nome"], [(k["id"], k["nome"]) for k in c["categorias"] if c["id"] != 162 or re.search("caf", k["nome"], re.I)][:20])
    ids = [k["id"] for c in J["classificacoes"] if c["id"] == 162 for k in c["categorias"] if re.search("caf", k["nome"], re.I)]
    if ids:
        v = J["variaveis"][-1]["id"]
        for vv in [x["id"] for x in J["variaveis"]]:
            r = get(f"https://servicodados.ibge.gov.br/api/v3/agregados/254/periodos/-6/variaveis/{vv}", t=120, params={"localidades": "N1[all]", "classificacao": "162[" + ",".join(map(str, ids)) + "]"})
            if r is not None and r.ok:
                for x in r.json():
                    for res in x["resultados"]:
                        print("   ", x["variavel"], x.get("unidade"), res["classificacoes"][0]["categoria"], json.dumps(res["series"][0]["serie"])[:300])
print("== Vietnam")
for u in ["https://www.nso.gov.vn/", "https://nso.gov.vn/", "https://customs.gov.vn/", "https://www.customs.gov.vn/", "https://vicofa.org.vn/", "https://www.mae.gov.vn/"]:
    r = get(u, t=120)
    if r is not None and r.ok:
        for h, tx in sorted(set(re.findall(r'href="([^"]+)"[^>]*>([^<]{2,120})', r.text)))[:400]:
            if re.search(r"th[oố]ng k[eê]|s[oố] li[eệ]u|xu[aấ]t kh[aẩ]u|statist|c[aà] ph[eê]|coffee", tx + h, re.I): print("    ", h[:140], "|", tx.strip()[:80])
print("== CONAB new site")
for u in ["https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/safra-de-cafe", "https://www.gov.br/conab/pt-br/assuntos/informacoes-agropecuarias/safras/safra-de-cafe"]:
    r = get(u, t=90)
    if r is not None and r.ok:
        for h in sorted(set(re.findall(r'href="([^"]+)"', r.text))):
            if re.search("estoque", h, re.I): print("    ", h)
