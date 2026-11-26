"""Inputs for the sugarcane crop model (models/cane_model.py), fetched on GitHub runners.

- USDA PSD sugar, all years (production, cane, beet) -> data/sugar/cane_model/psd_full.csv
- NASA POWER daily point weather 1981->present for cane regions (rain, tmax, tmin, root-zone wetness)
  -> data/sugar/cane_model/wx/<id>.csv.gz   (Open-Meteo ERA5 archive as fallback)
- ONI (NOAA CPC) -> data/sugar/cane_model/oni.csv
- CHIRPS daily rain 1981->present (ClimateSERV API), 0.5-degree box per India/Thailand point, as monthly totals
  -> data/sugar/cane_model/chirps.csv
- ERA5 daily rain/temperature 1981->present for the same points -> data/sugar/cane_model/era5/<id>.csv.gz (--only era5;
  heavy on the Open-Meteo quota, so it runs as its own step and keeps whatever points it finished)
- USD/THB and USD/INR daily (FRED DEXTHUS, DEXINUS) -> data/sugar/cane_model/fx_thb.csv, fx_inr.csv;
  India CPI (FRED INDCPIALLMINMEI) -> cpi_in.csv
- FAOSTAT sugar cane area, yield and production by origin -> data/sugar/cane_model/faostat_cane.csv (monthly at most)
Re-runs fetch only what is missing or stale (weather: last 120 days refreshed).
"""
import argparse, gzip, io, json, os, sys, time, zipfile
import numpy as np
from datetime import date, timedelta
import pandas as pd, requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "sugar", "cane_model")
WX = os.path.join(OUT, "wx")
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (research data client)"

# id: (country code, region label, lat, lon, weight within country)
POINTS = {
    # Brazil Centre-South (weights ~ MAPA cane share by state)
    "br_sp_rp": ("BR", "SP Ribeirão Preto", -21.2, -47.8, 0.16), "br_sp_pi": ("BR", "SP Piracicaba/Jaú", -22.5, -48.3, 0.12),
    "br_sp_ar": ("BR", "SP Araçatuba", -21.2, -50.4, 0.10), "br_sp_pp": ("BR", "SP Pres. Prudente", -22.1, -51.4, 0.07),
    "br_sp_sjr": ("BR", "SP S.J. Rio Preto", -20.8, -49.4, 0.08), "br_go_rv": ("BR", "GO Rio Verde/Quirinópolis", -18.4, -50.5, 0.11),
    "br_mg_ub": ("BR", "MG Uberaba/Triângulo", -19.7, -48.2, 0.11), "br_ms_do": ("BR", "MS Dourados", -22.2, -54.8, 0.08),
    "br_pr_ma": ("BR", "PR Maringá/NW", -23.4, -52.0, 0.06), "br_mt_ta": ("BR", "MT Tangará", -14.6, -57.5, 0.03),
    "br_ne_al": ("BRNE", "AL Zona da Mata", -9.6, -36.0, 0.6), "br_ne_pe": ("BRNE", "PE Zona da Mata", -8.3, -35.2, 0.4),
    # India
    "in_up_w": ("IN", "UP west (Muzaffarnagar)", 29.5, 77.7, 0.25), "in_up_c": ("IN", "UP central (Lakhimpur)", 28.0, 80.8, 0.20),
    "in_mh_w": ("IN", "Maharashtra west (Kolhapur/Pune)", 17.7, 74.2, 0.18), "in_mh_m": ("IN", "Maharashtra Marathwada", 19.0, 76.0, 0.10),
    "in_ka_n": ("IN", "Karnataka north (Belagavi)", 16.2, 75.0, 0.15), "in_tn": ("IN", "Tamil Nadu", 11.4, 78.7, 0.05),
    "in_gj": ("IN", "Gujarat south (Surat)", 21.2, 73.0, 0.07),
    # Thailand
    "th_kk": ("TH", "Khon Kaen", 16.4, 102.8, 0.25), "th_ud": ("TH", "Udon Thani", 17.4, 102.8, 0.15),
    "th_ns": ("TH", "Nakhon Sawan", 15.7, 100.1, 0.20), "th_kb": ("TH", "Kanchanaburi/Suphanburi", 14.3, 99.8, 0.25),
    "th_cy": ("TH", "Chaiyaphum/Nakhon Ratchasima", 15.6, 102.0, 0.15),
    # China
    "cn_nn": ("CH", "Guangxi Nanning", 22.8, 108.3, 0.3), "cn_cz": ("CH", "Guangxi Chongzuo", 22.4, 107.4, 0.3),
    "cn_lb": ("CH", "Guangxi Laibin", 23.7, 109.2, 0.2), "cn_yn": ("CH", "Yunnan Lincang", 23.9, 100.1, 0.2),
    # Mexico
    "mx_ver": ("MX", "Veracruz (Córdoba)", 18.9, -96.9, 0.4), "mx_slp": ("MX", "SLP Huasteca", 22.0, -99.0, 0.2),
    "mx_jal": ("MX", "Jalisco (Ameca)", 20.5, -104.0, 0.2), "mx_oax": ("MX", "Oaxaca (Tuxtepec)", 18.1, -96.1, 0.2),
    # Australia
    "au_mk": ("AS", "Mackay", -21.1, 149.1, 0.35), "au_bu": ("AS", "Burdekin (Ayr)", -19.6, 147.4, 0.3),
    "au_he": ("AS", "Herbert (Ingham)", -18.6, 146.2, 0.2), "au_bd": ("AS", "Bundaberg", -24.9, 152.3, 0.15),
    # Pakistan
    "pk_ry": ("PK", "Punjab Rahim Yar Khan", 28.4, 70.3, 0.4), "pk_fs": ("PK", "Punjab Faisalabad", 31.4, 73.1, 0.3),
    "pk_hy": ("PK", "Sindh Hyderabad", 25.4, 68.4, 0.3),
    # Others
    "gt_es": ("GT", "Guatemala Escuintla", 14.2, -90.9, 1.0), "co_cv": ("CO", "Colombia Cauca valley", 3.6, -76.3, 1.0),
    "za_kzn": ("SF", "South Africa KZN coast", -29.6, 31.0, 1.0), "ph_ng": ("RP", "Philippines Negros", 10.4, 123.0, 1.0),
    "id_ej": ("ID", "Indonesia East Java", -7.8, 112.4, 0.7), "id_lp": ("ID", "Indonesia Lampung", -4.6, 105.3, 0.3),
    "ar_tu": ("AR", "Argentina Tucumán", -26.9, -65.2, 0.8), "ar_ju": ("AR", "Argentina Jujuy", -24.0, -64.8, 0.2),
    "us_la": ("US", "Louisiana cane belt", 30.0, -91.2, 0.5), "us_fl": ("US", "Florida EAA", 26.6, -80.6, 0.5),
    "eg_up": ("EG", "Egypt Upper (Qena)", 26.1, 32.7, 1.0),
}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def get(url, tries=4, timeout=180, **kw):
    for k in range(tries):
        try:
            r = S.get(url, timeout=timeout, **kw)
            if r.ok:
                return r
            log("http", r.status_code, url[:120])
            if r.status_code == 429:   # Open-Meteo rate limit: wait out the minute
                time.sleep(65)
        except Exception as e:
            log("err", type(e).__name__, url[:120])
        time.sleep(5 * (k + 1))
    return None


def psd():
    r = get("https://apps.fas.usda.gov/psdonline/downloads/psd_sugar_csv.zip")
    if r is None:
        return False
    z = zipfile.ZipFile(io.BytesIO(r.content))
    d = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), dtype={"Commodity_Code": str})
    keep = ["Production", "Cane Sugar Production", "Beet Sugar Production", "Exports", "Imports", "Ending Stocks",
            "Human Dom. Consumption", "Total Disappearance"]
    d = d[d.Attribute_Description.isin(keep)][["Country_Code", "Country_Name", "Market_Year", "Attribute_Description", "Value"]]
    d.to_csv(os.path.join(OUT, "psd_full.csv"), index=False)
    log("psd", d.shape, d.Market_Year.min(), d.Market_Year.max())
    return True


def oni():
    r = get("https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt")
    if r is None:
        return False
    rows = [ln.split() for ln in r.text.splitlines()[1:] if ln.strip()]
    d = pd.DataFrame(rows, columns=["season", "year", "total", "anom"])
    d.to_csv(os.path.join(OUT, "oni.csv"), index=False)
    log("oni", len(d))
    return True


def power(lat, lon, d0, d1):
    u = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters=PRECTOTCORR,T2M_MAX,T2M_MIN,GWETROOT"
         f"&community=AG&longitude={lon}&latitude={lat}&start={d0:%Y%m%d}&end={d1:%Y%m%d}&format=JSON")
    r = get(u, timeout=300)
    if r is None:
        return None
    p = r.json()["properties"]["parameter"]
    d = pd.DataFrame({"rain": p["PRECTOTCORR"], "tmax": p["T2M_MAX"], "tmin": p["T2M_MIN"], "gwr": p["GWETROOT"]})
    d.index = pd.to_datetime(d.index, format="%Y%m%d"); d.index.name = "date"
    d = d.mask(d <= -998)
    return d.dropna(how="all")


def openmeteo(lat, lon, d0, d1):
    u = ("https://archive-api.open-meteo.com/v1/archive?latitude=%s&longitude=%s&start_date=%s&end_date=%s"
         "&daily=precipitation_sum,temperature_2m_max,temperature_2m_min,soil_moisture_28_to_100cm_mean&timezone=GMT") % (lat, lon, d0, d1)
    r = get(u, timeout=300)
    if r is None:
        return None
    j = r.json()["daily"]
    d = pd.DataFrame({"rain": j["precipitation_sum"], "tmax": j["temperature_2m_max"], "tmin": j["temperature_2m_min"],
                      "gwr": j.get("soil_moisture_28_to_100cm_mean")}, index=pd.to_datetime(j["time"]))
    d.index.name = "date"
    return d.dropna(how="all")


def weather(only=None):
    os.makedirs(WX, exist_ok=True)
    end = date.today() - timedelta(days=2)
    status = {}
    for pid, (cc, lab, lat, lon, w) in POINTS.items():
        if only and pid not in only:
            continue
        fn = os.path.join(WX, pid + ".csv.gz")
        old = pd.read_csv(fn, index_col=0, parse_dates=True) if os.path.exists(fn) else None
        start = date(1981, 1, 1) if old is None or old.empty else (old.index.max() - pd.Timedelta(days=120)).date()
        new = power(lat, lon, start, end)
        src = "power"
        if new is None or new.empty:
            new = openmeteo(lat, lon, start, end); src = "era5"
        if new is None or new.empty:
            status[pid] = "fail"; log("wx fail", pid); continue
        new["src"] = src
        d = new if old is None else pd.concat([old[old.index < pd.Timestamp(start)], new])
        d = d[~d.index.duplicated(keep="last")].sort_index()
        with gzip.open(fn, "wt") as f:
            d.round(3).to_csv(f)
        status[pid] = f"{src} {d.index.min().date()}..{d.index.max().date()}"
        log("wx", pid, status[pid])
        time.sleep(1)
    meta = {"generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "points": {k: list(v) for k, v in POINTS.items()},
            "status": status}
    json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), indent=1, ensure_ascii=False)
    return sum(v != "fail" for v in status.values())


def openmeteo_light(lat, lon, d0, d1):
    u = ("https://archive-api.open-meteo.com/v1/archive?latitude=%s&longitude=%s&start_date=%s&end_date=%s"
         "&daily=precipitation_sum,temperature_2m_max,temperature_2m_min&timezone=GMT") % (lat, lon, d0, d1)
    r = get(u, tries=2, timeout=300)
    if r is None:
        return None
    j = r.json()["daily"]
    d = pd.DataFrame({"rain": j["precipitation_sum"], "tmax": j["temperature_2m_max"], "tmin": j["temperature_2m_min"]},
                     index=pd.to_datetime(j["time"]))
    d.index.name = "date"
    return d.dropna(how="all")


def chirps_hist(ccs=("IN", "TH")):
    """CHIRPS daily rain (station-blended, 0.05 deg) averaged over a 0.5-degree box around each India/Thailand point, from
    the ClimateSERV API (SERVIR/NASA), 1981 on, summed to months -> data/sugar/cane_model/chirps.csv. ClimateSERV takes
    at most 20 years per job, so each point is three jobs; all jobs are submitted first, then collected."""
    api = "https://climateserv.servirglobal.net/api/"
    end = date.today() - timedelta(days=3)
    spans = [(date(1981, 1, 1), date(2000, 12, 31)), (date(2001, 1, 1), date(2020, 12, 31)), (date(2021, 1, 1), end)]
    fn = os.path.join(OUT, "chirps.csv")
    old = pd.read_csv(fn) if os.path.exists(fn) else None
    jobs = []
    for pid, (cc, lab, lat, lon, w) in POINTS.items():
        if cc not in ccs:
            continue
        ring = [[lon - .25, lat - .25], [lon + .25, lat - .25], [lon + .25, lat + .25], [lon - .25, lat + .25], [lon - .25, lat - .25]]
        geo = json.dumps({"type": "Polygon", "coordinates": [ring]}, separators=(",", ":"))
        have = old is not None and (old.point == pid).any() and old[old.point == pid].month.min() <= "1981-01"
        for d0, d1 in (spans[-1:] if have else spans):
            q = {"datatype": 0, "begintime": d0.strftime("%m/%d/%Y"), "endtime": d1.strftime("%m/%d/%Y"), "intervaltype": 0,
                 "operationtype": 5, "dateType_Category": "default", "isZip_CurrentDataType": "false", "geometry": geo}
            r = get(api + "submitDataRequest/", tries=3, timeout=60, params=q)
            try:
                jid = r.json()[0] if r is not None else None
            except Exception:
                jid = None
            if not jid:
                log("chirps submit fail", pid, d0, (r.text[:120] if r is not None else "")); continue
            jobs.append((pid, d0, jid)); time.sleep(2)
    log("chirps jobs", len(jobs))
    rows, t0 = [], time.time()
    pending = list(jobs)
    while pending and time.time() - t0 < 1800:
        time.sleep(15)
        for job in list(pending):
            pid, d0, jid = job
            r = get(api + "getDataRequestProgress/", tries=2, timeout=60, params={"id": jid})
            try:
                prog = float(r.json()[0]) if r is not None else 0.0
            except Exception:
                prog = 0.0
            if prog < 0:
                log("chirps job error", pid, d0); pending.remove(job); continue
            if prog < 100:
                continue
            r = get(api + "getDataFromRequest/", tries=3, timeout=120, params={"id": jid})
            pending.remove(job)
            try:
                dd = r.json()["data"]
            except Exception:
                log("chirps data fail", pid, d0); continue
            for it in dd:
                v = list(it["value"].values())[0]
                if v is None or v < -1:
                    continue
                rows.append((pid, pd.Timestamp(int(float(it["epochTime"])), unit="s").normalize() + pd.Timedelta(hours=12), float(v)))
            log("chirps", pid, d0, len(dd))
    if pending:
        log("chirps: jobs not finished", len(pending))
    if not rows:
        return False
    d = pd.DataFrame(rows, columns=["point", "day", "rain"])
    d["month"] = d.day.dt.strftime("%Y-%m")
    m = d.groupby(["point", "month"]).agg(rain_mm=("rain", "sum"), days=("rain", "count")).reset_index()
    m["rain_mm"] = m.rain_mm.round(1)
    if old is not None:
        if "days" not in old:
            old["days"] = np.nan
        m = pd.concat([old[~old.set_index(["point", "month"]).index.isin(m.set_index(["point", "month"]).index)], m])
    m.sort_values(["point", "month"]).to_csv(fn, index=False)
    log("chirps saved", m.point.nunique(), "points", m.month.min(), m.month.max())
    return True


def era5_hist(ccs=("IN", "TH")):
    """ERA5 (Open-Meteo archive) for the India and Thailand points, 1981 on."""
    d5 = os.path.join(OUT, "era5"); os.makedirs(d5, exist_ok=True)
    end = date.today() - timedelta(days=7)
    n = 0
    for pid, (cc, lab, lat, lon, w) in POINTS.items():
        if cc not in ccs:
            continue
        fn = os.path.join(d5, pid + ".csv.gz")
        old = pd.read_csv(fn, index_col=0, parse_dates=True) if os.path.exists(fn) else None
        if old is not None and not old.empty and old.index.min() <= pd.Timestamp("1981-01-05"):
            pieces = [((old.index.max() - pd.Timedelta(days=120)).date(), end)]
        else:
            old, pieces = None, [(date(y, 1, 1), min(date(y + 9, 12, 31), end)) for y in range(1981, end.year + 1, 10)]
        got = []
        for d0, d1 in pieces:
            x = openmeteo_light(lat, lon, d0, d1)
            if x is None or x.empty:
                log("era5 fail", pid, d0); got = None; break
            got.append(x); time.sleep(8)
        if not got:
            log("era5: stopping for this run (quota); finished points are kept"); break
        new = pd.concat(got)
        d = new if old is None else pd.concat([old[old.index < new.index.min()], new])
        d = d[~d.index.duplicated(keep="last")].sort_index()
        with gzip.open(fn, "wt") as f:
            d.round(3).to_csv(f)
        log("era5", pid, d.index.min().date(), d.index.max().date()); n += 1
        time.sleep(20)
    return n


def fx_series(sid, col, fn):
    r = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", timeout=150)
    if r is None:
        return False
    d = pd.read_csv(io.StringIO(r.text))
    d.columns = ["date", col]
    d = d[pd.to_numeric(d[col], errors="coerce").notna()]
    d.to_csv(os.path.join(OUT, fn), index=False)
    log("fx", sid, d.date.iloc[0], d.date.iloc[-1]); return True


def fx_thb():
    ok = fx_series("DEXTHUS", "thb_per_usd", "fx_thb.csv")
    ok &= fx_series("DEXINUS", "inr_per_usd", "fx_inr.csv")
    ok &= fx_series("INDCPIALLMINMEI", "cpi", "cpi_in.csv")      # India CPI, to put the cane price in real terms
    return ok


FAO_AREAS = {"India": "IN", "Thailand": "TH", "Brazil": "BR", "Pakistan": "PK", "Mexico": "MX", "China, mainland": "CN",
             "Australia": "AU", "Philippines": "PH", "Indonesia": "ID", "Egypt": "EG", "United States of America": "US"}


def _fao_tidy(df):
    """FAOSTAT rows (API or bulk) -> cc, year, area_ha, yield_t_ha, prod_t for sugar cane."""
    cols = {c.lower(): c for c in df.columns}
    A, I, E, Y, U, V = (cols.get(k) for k in ("area", "item", "element", "year", "unit", "value"))
    df = df[df[A].isin(FAO_AREAS) & df[I].astype(str).str.lower().str.startswith("sugar cane")]
    df = df[df[E].isin(["Area harvested", "Yield", "Production"])].copy()
    df["v"] = pd.to_numeric(df[V], errors="coerce")
    unit = df[U].astype(str).str.lower()
    df.loc[(df[E] == "Yield") & unit.str.startswith("100 g"), "v"] /= 10000.0     # 100 g/ha -> t/ha
    df.loc[(df[E] == "Yield") & unit.str.startswith("kg"), "v"] /= 1000.0         # kg/ha -> t/ha
    w = df.pivot_table(index=[A, Y], columns=E, values="v", aggfunc="first").reset_index()
    w = w.rename(columns={A: "country", Y: "year", "Area harvested": "area_ha", "Yield": "yield_t_ha", "Production": "prod_t"})
    w["cc"] = w.country.map(FAO_AREAS)
    return w[["cc", "country", "year", "area_ha", "yield_t_ha", "prod_t"]].sort_values(["cc", "year"])


def faostat():
    """FAOSTAT sugar cane area harvested, yield and production (QCL), main origins, 1961->latest
    -> data/sugar/cane_model/faostat_cane.csv. FAO updates once a year, so it refetches at most monthly."""
    fn = os.path.join(OUT, "faostat_cane.csv")
    if os.path.exists(fn) and time.time() - os.path.getmtime(fn) < 30 * 86400 and os.path.getsize(fn) > 1000:
        log("faostat: fresh"); return True
    w = None
    yrs = ",".join(str(y) for y in range(1961, date.today().year + 1))
    r = get("https://fenixservices.fao.org/faostat/api/v1/en/data/QCL?item=156&year=" + yrs +
            "&output_type=csv&show_flags=false&null_values=false", timeout=300, tries=3)
    if r is not None and len(r.text) > 1000:
        try:
            w = _fao_tidy(pd.read_csv(io.StringIO(r.text)))
        except Exception as e:
            log("faostat api parse", e)
    if w is None or w.empty:
        r = get("https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip",
                timeout=900, tries=2)
        if r is None:
            return False
        z = zipfile.ZipFile(io.BytesIO(r.content))
        name = [n for n in z.namelist() if n.lower().endswith(".csv") and "all_data" in n.lower()][0]
        parts = []
        for ch in pd.read_csv(z.open(name), encoding="latin-1", chunksize=500000, low_memory=False):
            ic = [c for c in ch.columns if c.lower() == "item"][0]
            parts.append(ch[ch[ic].astype(str).str.lower().str.startswith("sugar cane")])
        w = _fao_tidy(pd.concat(parts))
    if w is None or w.empty:
        return False
    w.to_csv(fn, index=False)
    log("faostat", w.shape, w.year.min(), w.year.max(), sorted(w.cc.dropna().unique()))
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--only", default=""); ap.add_argument("--points", default="")
    a = ap.parse_args()
    os.makedirs(WX, exist_ok=True)
    steps = a.only.split(",") if a.only else ["psd", "oni", "wx", "chirps", "fx", "fao"]
    ok = True
    for k, f in (("psd", psd), ("oni", oni), ("chirps", chirps_hist), ("era5", era5_hist), ("fx", fx_thb), ("fao", faostat)):
        if k in steps:
            try:
                ok &= bool(f())
            except Exception as e:
                log(k, "failed", e); ok = False
    if "wx" in steps:
        n = weather(a.points.split(",") if a.points else None)
        ok &= n > 0
    sys.exit(0 if ok else 1)
