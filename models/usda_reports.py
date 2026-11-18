"""USDA reports for the Reports tabs (probe stage 5)."""
import re, sys, json, requests
H = {"User-Agent": "Mozilla/5.0 (research desk; github actions)", "Accept": "application/json, text/plain, */*"}

def probe():
    t = requests.get("https://gain.fas.usda.gov/main-es2018.js", headers=H, timeout=60).text
    m = t.find("class SearchFilter {"); print("FILTER", t[m: m + 1500].replace("\n", " "))
    for mm in re.finditer(r"GetSearchResults", t):
        print("GSR", t[mm.start() - 1500: mm.end() + 200].replace("\n", " "))
        break
    for mm in list(re.finditer(r"apiEndpoint: '[^']+'|searchApi[^,]{0,120}|publicApi[^,]{0,120}", t))[:10]:
        print("EP", mm.group(0))
    body = {"keyword": "", "fromDate": "2026-08-01T00:00:00", "toDate": "2026-11-18T00:00:00", "countryIds": [], "postNames": [], "categoryIds": [],
            "reportName": "Cotton and Products", "reportHighlights": "", "reportNumber": "", "correctedReport": False}
    for ep in ["https://apps.fas.usda.gov/newgainapi/api/Search/GetSearchResults", "https://apps.fas.usda.gov/newgainapi/api/Report/GetSearchResults",
               "https://apps.fas.usda.gov/newgainapi/api/search/GetSearchResults"]:
        try:
            r = requests.post(ep, json=body, headers=H, timeout=60); print("POST", ep, r.status_code, r.text[:1500])
        except Exception as e:
            print("POST", ep, "ERR", e)
    x = requests.get("https://www.ers.usda.gov/sitemap.xml", headers=H, timeout=60).text
    subs = re.findall(r"<loc>([^<]+)</loc>", x); print("SUBS", subs)
    for u in subs:
        y = requests.get(u, headers=H, timeout=90).text
        locs = re.findall(r"<loc>([^<]+)</loc>", y)
        hits = [l for l in locs if re.search(r"cotton-and-wool-outlook|sugar-and-sweeteners-outlook|cws-|sss-m", l, re.I)]
        print("SUB", u, len(locs), hits[-30:])
        if any("publications/" in l for l in locs):
            print("  pubsample", [l for l in locs if "publications/" in l][-10:])

if __name__ == "__main__":
    probe()
