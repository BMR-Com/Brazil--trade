"""USDA reports for the Reports tabs (probe stage 3)."""
import re, sys, json, requests
H = {"User-Agent": "Mozilla/5.0 (research desk; github actions)", "Accept": "application/json, text/plain, */*"}

def probe():
    t = requests.get("https://gain.fas.usda.gov/main-es2018.js", headers=H, timeout=60).text
    for m in re.finditer(r'(\w+Service) = class \1', t):
        name = m.group(1)
        body = t[m.start(): m.start() + 6000]
        calls = re.findall(r'this\.http(?:Client)?\.(get|post|put)\(([^;]{0,220})', body)
        if calls:
            print("SVC", name)
            for c in calls:
                print("   ", c[0], c[1].replace("\n", " ")[:220])
    m = t.find("apps.fas.usda.gov/newgainapi/api")
    print("ENV", t[m - 600: m + 600].replace("\n", " "))
    m = t.find("SearchFilter = class")
    print("FILTER", t[m: m + 1500].replace("\n", " ") if m > 0 else None)
    for u in ["https://www.ers.usda.gov/publications?series=CWS", "https://www.ers.usda.gov/publications?series=SSSM"]:
        r = requests.get(u, headers=H, timeout=60)
        print("==", u, r.status_code)
        print("  ", sorted(set(l for l in re.findall(r'href="([^"]+)"', r.text) if "pub" in l or "pdf" in l.lower()))[:60])

if __name__ == "__main__":
    probe()
