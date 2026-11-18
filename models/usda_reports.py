"""USDA reports for the Reports tabs (probe stage 10)."""
import re, sys, json, subprocess, tempfile, requests
H = {"User-Agent": "Mozilla/5.0 (research desk; github actions)", "Accept": "application/json, text/plain, */*"}
API = "https://apps.fas.usda.gov/newgainapi/"

def probe():
    r = requests.post(API + "token", data="client_id=eAuthClient&client_secret=00000000-0000-0000-0000-00000000000000000000-0000-0000-0000-000000000000&grant_type=client_credentials",
                      headers={**H, "Content-Type": "application/x-www-form-urlencoded"}, timeout=60)
    A = {**H, "Authorization": "Bearer " + r.json()["access_token"]}
    allr = {}
    for cat, fr in [(25, "2026-03-01"), (24, "2026-01-01"), (31, "2026-03-01")]:
        j = requests.post(API + "api/Search/GetSearchResults", json={"categoryIds": [cat], "fromDate": fr, "toDate": "2026-11-19"}, headers=A, timeout=120).json()
        print("CAT", cat, len(j))
        for e in sorted(j, key=lambda e: e["publishDate"]):
            print("  R", cat, e["publishDate"][:10], "|", e["countryName"], "|", e["reportName"], "|", e["reportCategory"].strip()[:60], "|", e["fileName"])
            allr[e["fileName"]] = e
    picks = [n for n in allr if re.search(r"Cotton and Products Update_Brasilia|Coffee Semi-annual_Jakarta|Sugar Semi-annual_|Coffee Annual_Hanoi|Cotton and Products Annual_New Delhi", n)][:6]
    for fn in picks:
        u = API + "api/Report/DownloadReportByFileName?fileName=" + requests.utils.quote(fn + ".pdf")
        x = requests.get(u, headers=H, timeout=120)
        print("PDF", fn, x.status_code, x.headers.get("content-type"), len(x.content))
        if x.status_code == 200 and x.content[:4] == b"%PDF":
            with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
                f.write(x.content); f.flush()
                t = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
            lines = t.splitlines()
            idx = [i for i, l in enumerate(lines) if re.search(r"USDA Official|New Post", l)]
            print("  nlines", len(lines), "tables at", idx[:12])
            print("  HEAD", "\n".join(lines[:40]))
            for i in idx[:2]:
                print("  TABLE\n" + "\n".join(lines[max(0, i - 6): i + 30]))
    for u in ["https://apps.fas.usda.gov/psdonline/circulars/cotton.pdf", "https://www.ers.usda.gov/media/29738/cws-26j.pdf?v=28906"]:
        x = requests.get(u, headers=H, timeout=120)
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(x.content); f.flush()
            t = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
        print("DOC", u, "\n" + "\n".join(t.splitlines()[:90]))

if __name__ == "__main__":
    probe()
