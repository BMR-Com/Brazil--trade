"""USDA reports for the Reports tabs (probe stage 8)."""
import re, sys, json, requests
H = {"User-Agent": "Mozilla/5.0 (research desk; github actions)", "Accept": "application/json, text/plain, */*"}
API = "https://apps.fas.usda.gov/newgainapi/"

def probe():
    r = requests.post(API + "token", data="client_id=eAuthClient&client_secret=00000000-0000-0000-0000-00000000000000000000-0000-0000-0000-000000000000&grant_type=client_credentials",
                      headers={**H, "Content-Type": "application/x-www-form-urlencoded"}, timeout=60)
    print("TOKEN", r.status_code, r.text[:300])
    tok = r.json()["access_token"]
    A = {**H, "Authorization": "Bearer " + tok}
    for p in ["api/Lookup/GetAllActiveReportCategories", "api/Lookup/GetAllCountries", "api/Lookup/GetReportCategoryHierarchy?includeAll=true"]:
        x = requests.get(API + p, headers=A, timeout=60); print("GET", p, x.status_code, x.text[:200])
        try:
            j = x.json()
            for e in (j if isinstance(j, list) else [j])[:400]:
                s = json.dumps(e)
                if re.search(r"cotton|coffee|sugar|grain|tropical", s, re.I) or "Countries" in p:
                    print("   ", s[:300])
        except Exception as e:
            print("  nojson", e)
    body = {"keyword": "", "fromDate": "2026-08-01T00:00:00", "toDate": "2026-11-18T23:59:59", "countryIds": [], "postNames": [], "postIds": [], "categoryIds": []}
    for kw in ["cotton", "coffee", "sugar"]:
        b = dict(body, keyword=kw)
        x = requests.post(API + "api/Search/GetSearchResults", json=b, headers=A, timeout=90)
        print("SEARCH", kw, x.status_code, len(x.text))
        try:
            j = x.json(); print("  n", len(j)); [print("   ", json.dumps(e)[:700]) for e in j[:4]]
            print("  names", sorted(set(e.get("reportName") or e.get("ReportName") or "" for e in j))[:80])
        except Exception as e:
            print("  ", x.text[:500])

if __name__ == "__main__":
    probe()
