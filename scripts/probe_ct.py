"""Temporary probe: ICE cotton certificated-stock reports and USDA AMS Contract No. 2 premiums/discounts."""
import json, os, requests, datetime as dt
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research)"}
os.makedirs("data/probe", exist_ok=True); out = {}
B = "https://www.ice.com/publicdocs/futures_us_reports/cotton/"
days = [dt.date.today() - dt.timedelta(days=k) for k in range(0, 8)]
for pat in ["cotton_cert_stock_{}.xls", "cotton_certstock_{}.xls", "cotton_cert_stocks_{}.xls", "cotton_certificated_stock_{}.xls", "cotton_cert_stock_{}.xlsx", "ct_cert_stock_{}.xls"]:
    for d in days:
        u = B + pat.format(d.strftime("%Y%m%d"))
        try: r = requests.get(u, headers=H, timeout=30)
        except Exception as e: out[u] = str(e)[:80]; continue
        out[u] = [r.status_code, len(r.content), r.headers.get("content-type")]
        if r.status_code == 200 and len(r.content) > 2000 and b"<html" not in r.content[:300].lower():
            open("data/probe/" + u.rsplit("/", 1)[1], "wb").write(r.content); break
K = os.environ.get("AMS_API_KEY", "").strip()
if K:
    r = requests.get("https://marsapi.ams.usda.gov/services/v1.2/reports", auth=(K, ""), timeout=60)
    rep = r.json() if r.status_code == 200 else []
    ct = [x for x in rep if "otton" in (x.get("report_title") or "")]
    out["mars_cotton_reports"] = [{k: x.get(k) for k in ("slug_id", "slug_name", "report_title", "published_date")} for x in ct]
    for x in ct:
        t = (x.get("report_title") or "").lower()
        if any(w in t for w in ("premium", "certif", "tenderable", "differential")):
            s = x.get("slug_id")
            r2 = requests.get(f"https://marsapi.ams.usda.gov/services/v1.2/reports/{s}", params={"allSections": "true", "lastReports": "1"}, auth=(K, ""), timeout=120)
            open(f"data/probe/mars_{s}.json", "w").write(r2.text[:400000])
            out[f"mars_{s}"] = [r2.status_code, len(r2.text), x.get("report_title")]
for u in ["https://www.ams.usda.gov/mnreports/mp_cn051.txt", "https://www.ams.usda.gov/mnreports/cnddsq.pdf"]:
    try:
        r = requests.get(u, headers=H, timeout=30); out[u] = [r.status_code, len(r.content)]
        if r.status_code == 200: open("data/probe/" + u.rsplit("/", 1)[1], "wb").write(r.content)
    except Exception as e: out[u] = str(e)[:80]
json.dump(out, open("data/probe/ct_probe.json", "w"), indent=1)
