import re, io, os, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
S = requests.Session(); S.headers.update(H)
os.makedirs("probe/seed", exist_ok=True)
for u in ["https://federaciondecafeteros.org/wp-content/uploads/2026/09/Precios-area-y-produccion-de-cafe-Octubre-2026.xlsx",
          "https://federaciondecafeteros.org/wp-content/uploads/2026/06/Exportaciones-Agosto-2026.xlsx"]:
    r = S.get(u, timeout=90); print(u, r.status_code, len(r.content)); open("probe/seed/" + u.rsplit("/", 1)[1], "wb").write(r.content)
r = S.get("https://federaciondecafeteros.org/wp/estadisticas-cafeteras/", timeout=60)
print("FNC xlsx", sorted(set(re.findall(r'href="([^"]+\.xlsx)"', r.text))))
for u in ["https://giacaphe.com/gia-ca-phe-noi-dia/", "https://giacaphe.com/"]:
    r = S.get(u, timeout=60); r.encoding = "utf-8"; t = r.text
    print(u, "scripts:", sorted(set(re.findall(r'(?:src|url)\s*[:=]\s*["\']([^"\']+(?:ajax|api|json|price|gia)[^"\']*)["\']', t, re.I)))[:40])
    for m in re.finditer(r"Đắk Lắk", t):
        print("CTX", re.sub(r"\s+", " ", t[m.start()-200:m.start()+600])); break
    open("probe/seed/giacaphe.html", "w").write(t)
