"""USDA reports for the Reports tabs (probe stage 4)."""
import re, sys, json, requests
H = {"User-Agent": "Mozilla/5.0 (research desk; github actions)", "Accept": "application/json, text/plain, */*"}

def probe():
    t = requests.get("https://gain.fas.usda.gov/main-es2018.js", headers=H, timeout=60).text
    m = t.find("SearchService = class SearchService"); print("SEARCHSVC", t[m - 300: m + 2500].replace("\n", " "))
    m = t.find("this.searchFilter = new"); print("SEARCHFN", t[m - 200: m + 4000].replace("\n", " "))
    m = t.find("class SearchFilter"); print("FILTER", t[m - 100: m + 1500].replace("\n", " "))
    for kw in ["apiEndpoint:", "searchEndpoint", "DownloadReportByFileName", "GetReportByReportId", "fileName"]:
        for mm in list(re.finditer(kw, t))[:3]:
            print("KW", kw, "|", t[mm.start() - 300: mm.end() + 300].replace("\n", " "))
    sm = requests.get("https://www.ers.usda.gov/index/sitemap.xml", headers=H, timeout=60)
    print("SITEMAP", sm.status_code, len(sm.text), sm.text[:600])
    locs = re.findall(r"<loc>([^<]+)</loc>", sm.text)
    print("LOCS", len(locs), [l for l in locs if "sitemap" in l][:30])
    for u in [l for l in locs if "sitemap" in l][:12]:
        x = requests.get(u, headers=H, timeout=60).text
        hits = [l for l in re.findall(r"<loc>([^<]+)</loc>", x) if re.search(r"cotton-and-wool-outlook|sugar-and-sweeteners-outlook|cws-2|sss-m|sssm", l, re.I)]
        print("SUB", u, len(x), hits[:40])
    for u in ["https://www.ers.usda.gov/publications/pub-details?pubid=113226", "https://www.ers.usda.gov/api/publications?series=CWS",
              "https://www.ers.usda.gov/jsonapi/node/publication?filter[series]=CWS&sort=-created&page[limit]=5"]:
        r = requests.get(u, headers=H, timeout=60); print("==", u, r.status_code, r.headers.get("content-type"), r.text[:400].replace("\n", " "))

if __name__ == "__main__":
    probe()
