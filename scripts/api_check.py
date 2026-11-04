"""One-off check that the USDA API secrets work. Writes status only (never key values) to data/probe/api_check.json."""
import json, os, time, requests
out = {"checked_utc": time.strftime("%Y-%m-%d %H:%M")}
def run(name, key, fn):
    k = (os.environ.get(key) or "").strip()
    if not k:
        out[name] = {"secret_present": False}; return
    try:
        r = fn(k)
        body = r.text[:300] if r.status_code != 200 else ""
        try: n = len(r.json()) if r.status_code == 200 else None
        except Exception: n = None
        out[name] = {"secret_present": True, "key_length": len(k), "http": r.status_code, "items": n, "error": body}
    except Exception as e:
        out[name] = {"secret_present": True, "key_length": len(k), "exception": str(e)[:300]}
run("FAS_API_KEY", "FAS_API_KEY", lambda k: requests.get("https://api.fas.usda.gov/api/esr/commodities", headers={"X-Api-Key": k}, timeout=60))
run("NASS_API_KEY", "NASS_API_KEY", lambda k: requests.get("https://quickstats.nass.usda.gov/api/get_counts/", params={"key": k, "commodity_desc": "COTTON", "year": 2025, "statisticcat_desc": "PRODUCTION"}, timeout=60))
run("AMS_API_KEY", "AMS_API_KEY", lambda k: requests.get("https://marsapi.ams.usda.gov/services/v1.2/reports", auth=(k, ""), timeout=60))
os.makedirs("data/probe", exist_ok=True)
json.dump(out, open("data/probe/api_check.json", "w"), indent=1)
print(json.dumps(out, indent=1))
