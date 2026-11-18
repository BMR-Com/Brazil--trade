"""USDA reports for the Reports tabs (probe stage 9)."""
import re, sys, json, requests
H = {"User-Agent": "Mozilla/5.0 (research desk; github actions)", "Accept": "application/json, text/plain, */*"}
API = "https://apps.fas.usda.gov/newgainapi/"

def probe():
    r = requests.post(API + "token", data="client_id=eAuthClient&client_secret=00000000-0000-0000-0000-00000000000000000000-0000-0000-0000-000000000000&grant_type=client_credentials",
                      headers={**H, "Content-Type": "application/x-www-form-urlencoded"}, timeout=60)
    A = {**H, "Authorization": "Bearer " + r.json()["access_token"]}
    variants = [
        {"categoryIds": [25], "fromDate": "2026-08-01T05:00:00.000Z", "toDate": "2026-11-18T05:00:00.000Z", "countryIds": [], "postNames": [], "postIds": []},
        {"keyword": "cotton", "categoryIds": [], "fromDate": "2026-08-01T05:00:00.000Z", "toDate": "2026-11-18T05:00:00.000Z", "countryIds": [], "postNames": [], "postIds": [],
         "reportName": None, "reportHighlights": None, "reportNumber": None, "correctedReport": None},
        {"categoryIds": ["25"], "fromDate": "2026-08-01", "toDate": "2026-11-18"},
        {"categoryIds": [25], "countryIds": [2057], "fromDate": "2026-01-01T00:00:00", "toDate": "2026-11-18T00:00:00", "postNames": [], "postIds": []},
        {"keyword": "coffee"},
        {"reportName": "Coffee"},
    ]
    for v in variants:
        x = requests.post(API + "api/Search/GetSearchResults", json=v, headers=A, timeout=120)
        print("VAR", json.dumps(v)[:200], x.status_code, len(x.text), x.text[:300])
        try:
            j = x.json()
            if j:
                print("  keys", list(j[0].keys())); [print("   ", json.dumps(e)[:900]) for e in j[:3]]
        except Exception:
            pass

if __name__ == "__main__":
    probe()
