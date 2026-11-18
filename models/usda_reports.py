"""USDA reports for the Reports tabs (probe stage)."""
import re, sys, requests
H = {"User-Agent": "Mozilla/5.0 (research desk; github actions)", "Accept": "application/json, text/plain, */*"}

def probe():
    for u in ["https://gain.fas.usda.gov/", "https://apps.fas.usda.gov/psdonline/circulars/cotton.pdf",
              "https://apps.fas.usda.gov/psdonline/circulars/coffee.pdf", "https://apps.fas.usda.gov/psdonline/circulars/sugar.pdf",
              "https://www.fas.usda.gov/data/cotton-world-markets-and-trade", "https://www.ers.usda.gov/publications/",
              "https://esmis.nal.usda.gov/publication/cotton-and-wool-outlook", "https://esmis.nal.usda.gov/publication/sugar-and-sweeteners-outlook",
              "https://www.ers.usda.gov/topics/crops/cotton-and-wool/market-outlook"]:
        try:
            r = requests.get(u, headers=H, timeout=60); print("==", u, r.status_code, r.headers.get("content-type"), len(r.content))
            if "html" in (r.headers.get("content-type") or ""):
                t = r.text
                print("  links:", sorted(set(re.findall(r'(?:href|src)="([^"]+)"', t)))[:120])
        except Exception as e:
            print("==", u, "ERR", e)
    r = requests.get("https://gain.fas.usda.gov/", headers=H, timeout=60)
    for js in re.findall(r'src="([^"]+\.js)"', r.text):
        u = js if js.startswith("http") else "https://gain.fas.usda.gov/" + js.lstrip("/")
        t = requests.get(u, headers=H, timeout=60).text
        print("== JS", u, len(t))
        for m in sorted(set(re.findall(r'["\'`]([^"\'`]{0,80}(?:api|Api|API)/[^"\'`]{0,120})["\'`]', t)))[:200]:
            print("   ", m)
        for m in sorted(set(re.findall(r'https?://[a-zA-Z0-9./_-]*usda[a-zA-Z0-9./_-]*', t)))[:60]:
            print("   url", m)

if __name__ == "__main__":
    probe()
