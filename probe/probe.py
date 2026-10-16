import re, io, traceback
import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
S = requests.Session(); S.headers.update(H)
B = "https://unicadata.com.br/"

def form_html(t, fid):
    m = re.search(r'(?s)<form[^>]*id="%s".*?</form>' % fid, t)
    return m.group(0) if m else ""

r = S.get(B + "listagem.php?idMn=63", timeout=40)
f = form_html(r.text, "formConsulta")
print("FORM63", re.sub(r"\s+", " ", f)[:4000])
i = r.text.find("download_media")
print("AROUND", re.sub(r"\s+", " ", r.text[i - 3000:i + 500]))

r = S.get(B + "historico-de-producao-e-moagem.php?idMn=31&tipoHistorico=4", timeout=40)
print("\nFORM31", re.sub(r"\s+", " ", form_html(r.text, "formulario"))[-3000:])

for q in ["historico-de-producao-e-moagem.php?idMn=31&tipoHistorico=4&safra=2020%2F2021&estado%5B%5D=SP&acao=visualizar",
          "historico-de-producao-e-moagem.php?tipoHistorico=4&idMn=31&safra=2020%2F2021&estados%5B%5D=SP"]:
    t = S.get(B + q, timeout=40).text
    j = t.find("<table")
    print("\nQ", q, j, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "|", t[j:j + 3000])) if j > 0 else "")

# latest report PDF
try:
    import pdfplumber
    p = S.get(B + "download_media.php?idM=6758186", timeout=60)
    print("\nPDF", p.status_code, p.headers.get("content-type"), len(p.content), p.headers.get("content-disposition"))
    with pdfplumber.open(io.BytesIO(p.content)) as pdf:
        print("pages", len(pdf.pages))
        for k, pg in enumerate(pdf.pages[:8]):
            print(f"\n--- page {k+1}\n", (pg.extract_text() or "")[:3500])
            for tb in pg.extract_tables()[:3]:
                print("TABLE", tb[:25])
except Exception:
    traceback.print_exc()

# older reports listing?
for q in ["listagem.php?idMn=63&pagina=2", "listagem.php?idMn=63&idioma=2"]:
    t = S.get(B + q, timeout=40).text
    print("\nQ", q, sorted(set(re.findall(r'download_media\.php\?idM=\d+', t))))
