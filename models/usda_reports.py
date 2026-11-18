"""USDA reports for the Reports tabs (probe stage 2)."""
import re, sys, json, requests
H = {"User-Agent": "Mozilla/5.0 (research desk; github actions)", "Accept": "application/json, text/plain, */*"}

def probe():
    t = requests.get("https://gain.fas.usda.gov/main-es2018.js", headers=H, timeout=60).text
    for m in re.finditer(r'(Lookup/|Report/|lookupUrl|reportUrl|apiUrl)', t):
        pass
    seen = set()
    for m in re.finditer(r'[A-Za-z_.]*(?:Url|URL|url)\s*\+\s*["\']([A-Za-z/]+)', t):
        seen.add(m.group(1))
    print("URLPARTS", sorted(seen))
    for kw in ["SearchReport", "GetReport", "GetCommod", "GetCountr", "GetReportType", "Download", "keyword", "Lookup/"]:
        for m in list(re.finditer(kw, t))[:6]:
            print("CTX", kw, "|", t[max(0, m.start() - 250): m.end() + 250].replace("\n", " "))
    for u in ["https://esmis.nal.usda.gov/api-documentation", "https://esmis.nal.usda.gov/publication/cotton-and-wool-outlook?page=1",
              "https://esmis.nal.usda.gov/publication/cotton-and-wool-outlook/2025-09-16",
              "https://www.ers.usda.gov/topics/crops/cotton-and-wool/market-outlook", "https://www.ers.usda.gov/topics/crops/sugar-and-sweeteners/market-outlook"]:
        r = requests.get(u, headers=H, timeout=60)
        print("==", u, r.status_code)
        links = sorted(set(re.findall(r'href="([^"]+)"', r.text)))
        print("  ", [l for l in links if any(k in l.lower() for k in ("pdf", "outlook", "publication", "api", "pub-details", "cws", "sss", "page="))][:80])
        if "api-documentation" in u:
            print(re.sub(r"<[^>]+>", " ", r.text)[:6000])

if __name__ == "__main__":
    probe()
