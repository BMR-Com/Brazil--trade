"""One-off probe (deleted after): can the runner read the new coffee-differential sources? Prints what each returns."""
import json, re, sys, urllib.robotparser
from urllib.parse import urlparse
import requests
AGENT = "BMR-Com research desk (github.com/BMR-Com)"
H = {"User-Agent": AGENT}
_rp = {}
def ok(url):
    p = urlparse(url); base = f"{p.scheme}://{p.netloc}"
    if base not in _rp:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(base + "/robots.txt", headers=H, timeout=30)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            print(f"  robots {base}: {r.status_code}")
        except Exception as e:
            print(f"  robots {base}: {e}"); rp.parse([])
        _rp[base] = rp
    return _rp[base].can_fetch(AGENT, url)
def get(url, **kw):
    if not ok(url):
        print(f"  ROBOTS DISALLOW {url}"); return None
    try:
        r = requests.get(url, headers=H, timeout=60, **kw)
        print(f"  GET {url[:140]} -> {r.status_code} {len(r.content)}B {r.headers.get('content-type','')[:40]}")
        return r
    except Exception as e:
        print(f"  GET {url[:140]} -> ERR {e}"); return None

print("== SAFRAS")
for host in ["https://safras.com.br/eng", "https://safras.com.br"]:
    r = get(f"{host}/wp-json/wp/v2/categories", params={"per_page": 100, "_fields": "id,name,count"})
    if r is not None and r.ok:
        try: print("  cats:", [(c["id"], c["name"], c["count"]) for c in r.json() if re.search("caf|coffee|agri", c["name"], re.I)])
        except Exception as e: print("  json", e, r.text[:200])
    r = get(f"{host}/wp-json/wp/v2/posts", params={"search": "coffee" if "eng" in host else "café", "per_page": 20, "_fields": "id,date,link,title"})
    if r is not None and r.ok:
        print("  total", r.headers.get("X-WP-Total"))
        for p in r.json()[:20]: print("   ", p["date"][:10], p["title"]["rendered"][:90], p["link"])
r = get("https://safras.com.br/eng/wp-json/wp/v2/posts", params={"categories": 111, "per_page": 100, "page": 1, "_fields": "id,date,link,title,content"})
if r is not None and r.ok:
    print("  cat111 total", r.headers.get("X-WP-Total"), "pages", r.headers.get("X-WP-TotalPages"))
    n = 0
    for p in r.json():
        t = re.sub("<[^>]+>", " ", p["content"]["rendered"])
        if re.search(r"MTGB|fine cup|good cup|semi-washed|conillon|differential", t, re.I):
            n += 1
            if n <= 3:
                print("   --", p["date"][:10], p["title"]["rendered"][:80])
                for m in re.finditer(r"[^.]*(?:MTGB|fine cup|semi-washed|13 up|13up)[^.]*\.", t, re.I): print("      ", m.group(0).strip()[:220])
    print("  coffee-diff posts on page 1:", n)

print("== giacaphe raw HTML (FOB / tru lui)")
r = get("https://giacaphe.com/")
if r is not None and r.ok:
    t = r.text
    for kw in ["FOB", "Trừ lùi", "trừ lùi", "HCM", "data-cur"]:
        idx = [m.start() for m in re.finditer(re.escape(kw), t)][:3]
        print(f"  {kw!r}: {len(re.findall(re.escape(kw), t))} hits")
        for i in idx: print("     ", re.sub(r"\s+", " ", t[max(0,i-200):i+250]))
r = get("https://giacaphe.com/gia-ca-phe-noi-dia-ngay-2026-11-25/")
if r is not None and r.ok:
    t = r.text
    for kw in ["FOB", "Trừ lùi", "trừ lùi"]:
        for m in list(re.finditer(re.escape(kw), t))[:3]: print(f"  day {kw}:", re.sub(r"\s+", " ", t[max(0,m.start()-200):m.start()+300]))

print("== Vietnam customs")
for u in ["https://www.customs.gov.vn/", "https://www.customs.gov.vn/index.jsp?pageId=442&group=Ph%C3%A2n%20t%C3%ADch&category=S%E1%BB%91%20li%E1%BB%87u%20th%E1%BB%91ng%20k%C3%AA"]:
    r = get(u)
    if r is not None and r.ok:
        links = set(re.findall(r'href="([^"]+)"[^>]*>([^<]{0,120})', r.text))
        for h, tx in list(links):
            if re.search(r"th[oố]ng k[eê]|s[oố] li[eệ]u|xu[aấ]t kh[aẩ]u|statist", tx + h, re.I): print("    ", h[:150], "|", tx.strip()[:80])
print("== GSO")
r = get("https://www.gso.gov.vn/")
print("== IBGE aggregates with estoque")
r = get("https://servicodados.ibge.gov.br/api/v3/agregados")
if r is not None and r.ok:
    for pq in r.json():
        for a in pq.get("agregados", []):
            if re.search(r"estoque", a["nome"], re.I): print("   ", pq["id"], pq["nome"][:50], "|", a["id"], a["nome"][:140])
for t in ["254", "1415", "8425"]:
    r = get(f"https://servicodados.ibge.gov.br/api/v3/agregados/{t}/metadados")
    if r is not None and r.ok:
        J = r.json(); print("   meta", t, J.get("nome"), J.get("periodicidade"), [ (c["id"], c["nome"]) for c in J.get("classificacoes", [])][:6])
print("== FNC informe mensual / FEPCafe")
for u in ["https://federaciondecafeteros.org/wp/estadisticas-cafeteras/", "https://federaciondecafeteros.org/wp/publicaciones/"]:
    r = get(u)
    if r is not None and r.ok:
        for h in sorted(set(re.findall(r'href="([^"]+\.pdf)"', r.text, re.I)))[:40]: print("    ", h)
print("== CONAB")
r = get("https://www.conab.gov.br/info-agro/safras/cafe")
if r is not None and r.ok:
    for h in sorted(set(re.findall(r'href="([^"]+)"', r.text)))[:0]: pass
    print("   estoque mentions:", len(re.findall("estoque", r.text, re.I)))
