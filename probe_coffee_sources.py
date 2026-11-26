"""One-off probe #3 (deleted after): Vietnam export statistics."""
import re, html, json, requests
H = {"User-Agent": "BMR-Com research desk (github.com/BMR-Com)"}
def get(url, t=90, **kw):
    try:
        r = requests.get(url, headers=H, timeout=t, **kw); print(f"  GET {url[:150]} -> {r.status_code} {len(r.content)}B {r.headers.get('content-type','')[:30]}"); return r
    except Exception as e:
        print(f"  GET {url[:150]} -> ERR {str(e)[:150]}"); return None
r = get("https://www.nso.gov.vn/robots.txt"); print(r.text[:600] if r is not None else "")
seen = set()
for u in ["https://www.nso.gov.vn/so-lieu-thong-ke/", "https://www.nso.gov.vn/bao-cao-tinh-hinh-kinh-te-xa-hoi-hang-thang/", "https://www.nso.gov.vn/?s=xu%E1%BA%A5t+kh%E1%BA%A9u+c%C3%A0+ph%C3%AA"]:
    r = get(u)
    if r is None or not r.ok: continue
    for h, tx in re.findall(r'href="([^"]+)"[^>]*>([^<]{4,200})', r.text):
        if h in seen: continue
        seen.add(h)
        if re.search(r"th[aá]ng|xu[aấ]t|kinh t[eế]|th[ôo]ng c[aá]o|s[ốo] li[ệe]u", tx, re.I) and "nso.gov.vn" in h: print("    ", h[:160], "|", html.unescape(tx).strip()[:90])
# latest monthly socio-economic report
r = get("https://www.nso.gov.vn/?s=t%C3%ACnh+h%C3%ACnh+kinh+t%E1%BA%BF+x%C3%A3+h%E1%BB%99i+th%C3%A1ng+10")
L = re.findall(r'href="(https://www\.nso\.gov\.vn/[^"]+(?:thang-10|thang-9)[^"]+)"', r.text if r is not None and r.ok else "")
for u in list(dict.fromkeys(L))[:4]:
    r = get(u)
    if r is None or not r.ok: continue
    t = html.unescape(re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", r.text)))
    for m in re.finditer(r"c[àa] ph[êe]", t, re.I):
        print("     >", t[max(0, m.start()-250): m.start()+250]); break
    for a in sorted(set(re.findall(r'href="([^"]+\.(?:xlsx?|pdf|docx?))"', r.text, re.I)))[:10]: print("     file", a)
print("== Comtrade preview")
for q in ["https://comtradeapi.un.org/public/v1/preview/C/M/HS?reporterCode=704&period=202609,202608,202607&cmdCode=0901&flowCode=X",
          "https://comtradeapi.un.org/public/v1/preview/C/M/HS?reporterCode=704&period=202506&cmdCode=0901&flowCode=X"]:
    r = get(q)
    if r is not None and r.ok:
        J = r.json(); print("   count", J.get("count"), [(d.get("period"), d.get("partnerCode"), d.get("netWgt"), d.get("primaryValue")) for d in (J.get("data") or [])[:5]])
print("== VICOFA listing")
r = get("https://vicofa.org.vn/")
if r is not None and r.ok:
    for h, tx in re.findall(r'href="([^"]+)"[^>]*>([^<]{4,200})', r.text):
        if re.search(r"xu[aấ]t kh[aẩ]u|b[aả]n tin", tx, re.I): print("    ", h[:140], "|", tx.strip()[:90])
