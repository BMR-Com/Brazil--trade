"""Sugar weather inputs not covered by geo_weather / wx_ensemble (Open-Meteo, free, no key).

1. Daily ensemble rain for the Centre-South cane points (ECMWF ENS 51 members and GEFS 31 members, next 15 days),
   kept per member so models/sugar_world.py can turn each member into harvest-stoppage days.
   Each run's summary is appended to data/sugar/wx/ens_runs.jsonl, so the page can show the change vs the previous run.
2. EU beet regions: 2011-2025 daily history (fetched once) and the last 400 days of rain and ERA5-Land soil moisture.
3. Extra cane point(s) not in geo_weather (Piracicaba/Jaú, central São Paulo): history once, recent each run.

Outputs (all small): data/sugar/wx/ens_latest.json, data/sugar/wx/ens_runs.jsonl, data/sugar/wx/hist/<id>.csv.gz,
data/sugar/wx/recent/<id>.csv.gz. A rate limit (HTTP 429) stops the run and keeps the previous files.
"""
import json, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sugar" / "wx"
UA = {"User-Agent": "BMR-Com research desk (github.com/BMR-Com)"}
H0, H1 = "2011-01-01", "2025-12-31"
DAILY = "precipitation_sum,soil_moisture_0_to_7cm_mean,soil_moisture_28_to_100cm_mean"

# Centre-South cane points (ids shared with pipelines/geo_weather.py, whose history and recent files are reused) + extras
CANE = [("br_sp", -21.18, -47.81), ("br_spw", -21.21, -50.43), ("su_pi", -22.45, -48.40), ("br_gos", -17.80, -50.92),
        ("br_mgc", -19.75, -47.93), ("br_ms", -21.47, -54.38), ("br_prs", -23.07, -52.46)]
EXTRA_CANE = {"su_pi": ("Piracicaba / Jaú, central São Paulo", -22.45, -48.40)}
# EU beet regions (one representative point each in the main beet areas)
BEET = {"eu_fr_b": ("Picardie / Hauts-de-France (Amiens)", 49.89, 2.30),
        "su_fr_ce": ("Centre-Val de Loire / Beauce (Pithiviers)", 48.17, 2.25),
        "su_de_ns": ("Lower Saxony (Hildesheim)", 52.15, 9.95),
        "su_de_ma": ("Magdeburger Börde, Saxony-Anhalt", 52.05, 11.40),
        "su_pl_ku": ("Kujawy, Poland (Inowrocław)", 52.80, 18.26),
        "su_nl_fl": ("Flevoland, Netherlands", 52.53, 5.60),
        "su_be_ti": ("Hesbaye / Tienen, Belgium", 50.80, 4.94),
        "su_cz_ha": ("Haná, Czechia (Olomouc)", 49.60, 17.25)}
HIT = {"429": False}
log = []


def get(url, params, tries=4, timeout=120):
    if HIT["429"]:
        return None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            log.append([url.split("/")[2], r.status_code, r.text[:120]])
            if r.status_code == 429:
                HIT["429"] = True
                return None
            if r.status_code == 400:
                return None
        except Exception as e:
            log.append([url.split("/")[2], str(e)[:120]])
        time.sleep(10 * (i + 1))
    return None


def daily_df(j):
    if not j or "daily" not in j:
        return None
    d = j["daily"]
    return pd.DataFrame({"rain": d.get("precipitation_sum"), "sm7": d.get("soil_moisture_0_to_7cm_mean"),
                         "sm100": d.get("soil_moisture_28_to_100cm_mean")}, index=pd.to_datetime(d["time"]))


def point_series(pid, lat, lon):
    """History once (2011-2025) and the last 400 days each run, for points this pipeline owns."""
    (OUT / "hist").mkdir(parents=True, exist_ok=True)
    (OUT / "recent").mkdir(parents=True, exist_ok=True)
    hp = OUT / "hist" / f"{pid}.csv.gz"
    if not hp.exists():
        df = daily_df(get("https://archive-api.open-meteo.com/v1/archive",
                          {"latitude": lat, "longitude": lon, "start_date": H0, "end_date": H1, "daily": DAILY, "timezone": "auto"}, timeout=180))
        if df is not None:
            df.round(3).to_csv(hp, compression="gzip")
            print("history", pid, len(df), flush=True)
        time.sleep(45)   # a 15-year call weighs ~390 of the 600 calls/min allowance
    today = date.today()
    rec = daily_df(get("https://archive-api.open-meteo.com/v1/archive",
                       {"latitude": lat, "longitude": lon, "start_date": (today - timedelta(days=400)).isoformat(),
                        "end_date": (today - timedelta(days=1)).isoformat(), "daily": DAILY, "timezone": "auto"}))
    if rec is not None:
        rec.round(3).to_csv(OUT / "recent" / f"{pid}.csv.gz", compression="gzip")
        print("recent", pid, rec.dropna(subset=["rain"]).index.max().date(), flush=True)
    time.sleep(3)


def ensembles():
    out = {}
    lat = ",".join(str(p[1]) for p in CANE)
    lon = ",".join(str(p[2]) for p in CANE)
    for key, model in (("ecmwf_ens", "ecmwf_ifs025"), ("gefs", "gfs05")):
        j = get("https://ensemble-api.open-meteo.com/v1/ensemble",
                {"latitude": lat, "longitude": lon, "models": model, "daily": "precipitation_sum", "forecast_days": 15, "timezone": "auto"}, tries=5, timeout=90)
        if j is None:
            continue
        js = j if isinstance(j, list) else [j]
        for (pid, _, _), r in zip(CANE, js):
            d = r.get("daily", {})
            mem = {k: v for k, v in d.items() if k.startswith("precipitation_sum")}
            if not mem:
                continue
            out.setdefault(pid, {})[key] = {"dates": d["time"], "members": [[None if x is None else round(x, 1) for x in v] for v in mem.values()]}
        time.sleep(8)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for pid, (name, lat, lon) in {**EXTRA_CANE, **BEET}.items():
        if pid == "eu_fr_b" and (ROOT / "data/geo/weather_hist/eu_fr_b.csv.gz").exists():
            continue   # geo_weather already keeps this one
        point_series(pid, lat, lon)
    ens = ensembles()
    gen = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if ens:
        (OUT / "ens_latest.json").write_text(json.dumps({"generated": gen, "points": ens, "log": log}, separators=(",", ":")))
    meta = {"generated": gen, "beet": {k: v[0] for k, v in BEET.items()}, "extra_cane": {k: v[0] for k, v in EXTRA_CANE.items()}, "log": log}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(json.dumps(log)[:600])


if __name__ == "__main__":
    main()
