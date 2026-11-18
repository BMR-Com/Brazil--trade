"""USDA reports for the Reports tabs (probe stage 6)."""
import re, sys, json, requests
H = {"User-Agent": "Mozilla/5.0 (research desk; github actions)", "Accept": "application/json, text/plain, */*"}

def probe():
    t = requests.get("https://gain.fas.usda.gov/main-es2018.js", headers=H, timeout=60).text
    m = t.find("AuthTokenService = class"); print("AUTH", t[m - 200: m + 3500].replace("\n", " "))
    for mm in list(re.finditer(r"tempToken|anonymous|publicToken|client_secret", t))[:12]:
        print("TOK", t[mm.start() - 400: mm.end() + 300].replace("\n", " "))
    x = requests.get("https://www.ers.usda.gov/sitemap.xml?page=7", headers=H, timeout=90).text
    print("SM7", x[:1200])
    ids = sorted(set(int(i) for i in re.findall(r"/publications/(\d+)</loc>", x)))
    print("IDS", len(ids), ids[-60:])
    for i in ids[-40:]:
        r = requests.get(f"https://www.ers.usda.gov/publications/{i}", headers=H, timeout=60)
        tt = re.search(r"<title>([^<]+)</title>", r.text)
        pdfs = sorted(set(re.findall(r'href="([^"]+\.pdf)"', r.text)))
        print("PUB", i, r.status_code, tt.group(1) if tt else None, pdfs[:3])

if __name__ == "__main__":
    probe()
