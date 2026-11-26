"""One-off probe #4 (deleted after): Vietnam coffee exports in NSO monthly reports and VICOFA."""
import re, html, io, zipfile, requests
H = {"User-Agent": "BMR-Com research desk (github.com/BMR-Com)"}
def get(url, t=120, **kw):
    try:
        r = requests.get(url, headers=H, timeout=t, **kw); print(f"  GET {url[:160]} -> {r.status_code} {len(r.content)}B {r.headers.get('content-type','')[:30]}"); return r
    except Exception as e:
        print(f"  GET {url[:160]} -> ERR {str(e)[:150]}"); return None
def text(b):
    return html.unescape(re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", b)))
def coffee(t, n=3, w=300):
    for i, m in enumerate(re.finditer(r"c[àa] ph[êe]", t, re.I)):
        if i >= n: break
        print("     >", t[max(0, m.start()-w): m.start()+w])
print("== NSO wp-json")
for q in ["tình hình kinh tế xã hội tháng", "thông cáo báo chí tình hình kinh tế"]:
    r = get("https://www.nso.gov.vn/wp-json/wp/v2/posts", params={"search": q, "per_page": 30, "_fields": "date,link,title"})
    if r is not None and r.ok:
        try:
            for p in r.json(): print("    ", p["date"][:10], p["link"][:150], "|", html.unescape(p["title"]["rendered"])[:80])
        except Exception as e: print("   json err", e, r.text[:200])
print("== NSO 2026 report pages")
pages = ["https://www.nso.gov.vn/bai-top/2026/11/mot-so-net-chinh-tinh-hinh-kinh-te-xa-hoi-thang-10-va-10-thang-nam-2026/"]
r = get("https://www.nso.gov.vn/?s=b%C3%A1o+c%C3%A1o+t%C3%ACnh+h%C3%ACnh+kinh+t%E1%BA%BF+x%C3%A3+h%E1%BB%99i+th%C3%A1ng+n%C4%83m+2026")
if r is not None and r.ok:
    for h in dict.fromkeys(re.findall(r'href="(https://www\.nso\.gov\.vn/[^"]+2026[^"]+)"', r.text)):
        if re.search(r"kinh-te-xa-hoi", h): print("    ", h[:170]); pages.append(h)
for u in list(dict.fromkeys(pages))[:5]:
    r = get(u)
    if r is None or not r.ok: continue
    coffee(text(r.text), 2)
    files = sorted(set(re.findall(r'href="([^"]+/wp-content/uploads/[^"]+)"', r.text)))
    for a in files[:12]: print("     file", a)
    for a in files[:6]:
        if a.lower().endswith(".docx"):
            f = get(a)
            if f is not None and f.ok:
                try:
                    x = zipfile.ZipFile(io.BytesIO(f.content)).read("word/document.xml").decode("utf8", "ignore"); coffee(text(x), 3, 250)
                except Exception as e: print("   docx err", e)
        if a.lower().endswith((".xlsx", ".xls")):
            f = get(a)
            if f is not None and f.ok:
                try:
                    import openpyxl
                    wb = openpyxl.load_workbook(io.BytesIO(f.content), read_only=True, data_only=True)
                    for ws in wb.worksheets:
                        for row in ws.iter_rows(values_only=True):
                            if any(isinstance(c, str) and re.search(r"c[àa] ph[êe]", c, re.I) for c in row): print("     xlsx", ws.title, [c for c in row if c is not None][:12])
                except Exception as e: print("   xlsx err", e)
print("== NSO 2023 xlsx (format check)")
f = get("https://www.nso.gov.vn/wp-content/uploads/2023/10/02.-Bieu-so-lieu-T10.2023.xlsx")
if f is not None and f.ok:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(f.content), read_only=True, data_only=True)
    print("   sheets", wb.sheetnames[:40])
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            if any(isinstance(c, str) and re.search(r"c[àa] ph[êe]", c, re.I) for c in row): print("     xlsx", ws.title, [c for c in row if c is not None][:12])
print("== VICOFA")
for u in ["https://vicofa.org.vn/tinh-hinh-xuat-khau-ca-phe-viet-nam-thang-3-nam-2025-bid2922.html", "https://vicofa.org.vn/ban-tin-thang-b44.html"]:
    r = get(u)
    if r is None or not r.ok: continue
    t = text(r.text); coffee(t, 2, 400)
    for h, tx in re.findall(r'href="([^"]+)"[^>]*>([^<]{4,200})', r.text):
        if re.search(r"xu[aấ]t kh[aẩ]u c[àa] ph[êe]|b[aả]n tin", tx, re.I): print("    ", h[:140], "|", tx.strip()[:90])
