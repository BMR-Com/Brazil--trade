"""One-off probe #5 (deleted after): NSO monthly report export table layout and history."""
import re, html, io, requests, openpyxl
H = {"User-Agent": "BMR-Com research desk (github.com/BMR-Com)"}
def get(url, t=120, **kw):
    try:
        r = requests.get(url, headers=H, timeout=t, **kw); print(f"  GET {url[:160]} -> {r.status_code} {len(r.content)}B"); return r
    except Exception as e:
        print(f"  GET {url[:160]} -> ERR {str(e)[:150]}"); return None
def dump(b):
    wb = openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True)
    print("   sheets", wb.sheetnames)
    for ws in wb.worksheets:
        if not re.search(r"XK|xu[aấ]t", ws.title, re.I): continue
        rows = list(ws.iter_rows(values_only=True))
        for i, row in enumerate(rows[:9]): print("    H", i, [c for c in row if c is not None][:14])
        for row in rows:
            if any(isinstance(c, str) and re.search(r"c[àa] ph[êe]|T[ổo]ng tr[ịi] gi[áa]|TỔNG", c, re.I) for c in row): print("    R", list(row)[:14])
seen = []
for page in range(1, 9):
    r = get("https://www.nso.gov.vn/wp-json/wp/v2/posts", params={"search": "Báo cáo tình hình kinh tế xã hội tháng", "per_page": 100, "page": page, "_fields": "date,link,title"})
    if r is None or not r.ok: break
    J = r.json()
    if not J: break
    for p in J:
        t = html.unescape(p["title"]["rendered"])
        if re.match(r"B[áa]o c[áa]o t[ìi]nh h[ìi]nh kinh t[ếe]", t): seen.append((p["date"][:10], p["link"], t))
print("reports found", len(seen), "oldest", seen[-1][:1] if seen else None)
for d, l, t in seen[:40]: print("   ", d, l[:130], "|", t[:70])
for d, l, t in [s for s in seen if s[0] >= "2026-10-01"][:1] + [s for s in seen if s[0] < "2021-03-01"][:1]:
    r = get(l)
    if r is None or not r.ok: continue
    files = sorted(set(re.findall(r'href="([^"]+/wp-content/uploads/[^"]+\.(?:xlsx?|docx?|pdf))"', r.text, re.I)))
    for a in files: print("     file", a)
    for a in files:
        if a.lower().endswith((".xlsx", ".xls")):
            f = get(a)
            if f is not None and f.ok:
                try: dump(f.content)
                except Exception as e: print("   xlsx err", e)
f = get("https://www.nso.gov.vn/wp-content/uploads/2023/10/02.-Bieu-so-lieu-T10.2023.xlsx")
if f is not None and f.ok: dump(f.content)
