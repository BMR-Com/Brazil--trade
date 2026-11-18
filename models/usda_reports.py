"""USDA reports for the Reports tabs (probe stage 7)."""
import re, sys, json, requests
H = {"User-Agent": "Mozilla/5.0 (research desk; github actions)", "Accept": "application/json, text/plain, */*"}

def probe():
    t = requests.get("https://gain.fas.usda.gov/main-es2018.js", headers=H, timeout=60).text
    for kw in ["onymous user token", "function getFixedToken", "getFixedToken()", "Authorization", "class SearchFilter {"]:
        for mm in list(re.finditer(re.escape(kw), t))[:2]:
            print("CTX", kw, "|", t[mm.start() - 1200: mm.end() + 1200].replace("\n", " "))
    r = requests.get("https://www.ers.usda.gov/publications/115624", headers=H, timeout=60)
    print("PUBLINKS", sorted(set(re.findall(r'(?:href|src)="([^"]+)"', r.text))))

if __name__ == "__main__":
    probe()
