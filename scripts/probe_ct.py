"""Temporary probe 2: MARS report list (futures/certificated), Daily Spot Cotton Quotations structure, ICE file names."""
import json, os, time, requests, datetime as dt
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research)"}
os.makedirs("data/probe", exist_ok=True); out = {}
K = os.environ.get("AMS_API_KEY", "").strip()
M = "https://marsapi.ams.usda.gov/services/v1.2/reports"
rep = requests.get(M, auth=(K, ""), timeout=60).json()
out["mars_match"] = [{k: x.get(k) for k in ("slug_id", "slug_name", "report_title", "published_date")} for x in rep
                     if any(w in (x.get("report_title") or "").lower() for w in ("futures", "certif", "tender", "contract no", "premium", "spot cotton", "cotton"))]
for q in ["report_begin_date=07/31/2025:07/31/2025", None]:
    p = {"allSections": "true"}
    if q: p["q"] = q
    else: p["lastReports"] = "1"
    r = requests.get(f"{M}/3804", params=p, auth=(K, ""), timeout=180)
    nm = "mars_3804_" + ("20250731" if q else "latest") + ".json"
    open("data/probe/" + nm, "w").write(r.text[:3000000]); out[nm] = [r.status_code, len(r.text)]
B = "https://www.ice.com/publicdocs/futures_us_reports/cotton/"
d = dt.date.today() - dt.timedelta(days=1)
for name in [f"cotton_cert_stock_{d:%Y%m%d}.pdf", f"Cotton_Cert_Stock_{d:%Y%m%d}.xls", f"cotton_certificated_stocks_{d:%Y%m%d}.xls", f"cotton_daily_cert_stock_{d:%Y%m%d}.xls",
             f"cotton_cert_{d:%Y%m%d}.xls", f"ct_certs_{d:%Y%m%d}.xls", "Cotton_Premiums_and_Discounts.pdf", "cotton_premiums_discounts.xls", "Cotton_Certificated_Stock.xls"]:
    try: r = requests.get(B + name, headers=H, timeout=30); out[name] = [r.status_code, len(r.content)]
    except Exception as e: out[name] = str(e)[:60]
    if out[name][0] == 200 and len(r.content) > 2000: open("data/probe/" + name, "wb").write(r.content)
    time.sleep(3)
json.dump(out, open("data/probe/ct_probe2.json", "w"), indent=1)
