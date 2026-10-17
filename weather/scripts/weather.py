"""
Brazil crop-region weather (ERA5 reanalysis history and 16-day forecast via Open-Meteo) and ENSO (NOAA CPC Niño 3.4).
Writes weather/data/br_weather.json used by the coffee, sugar and cotton pages.
"""
import os, io, json, time, math
from datetime import date, timedelta
import requests
import pandas as pd
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(ROOT, "data"); os.makedirs(DATA, exist_ok=True)
H = {"User-Agent": "BMR-Com research (github.com/BMR-Com)"}

REGIONS = [
    # crop, region, town, lat, lon
    # Minas Gerais coffee belt, by Conab region: Sul e Centro-Oeste (~half of MG output), Cerrado Mineiro
    # (Triângulo/Alto Paranaíba/Noroeste), Zona da Mata/Rio Doce/Central (Matas de Minas), Norte/Jequitinhonha
    ("coffee", "Sul de Minas", "Varginha MG", -21.55, -45.43),
    ("coffee", "Sul de Minas", "Guaxupé MG", -21.30, -46.71),
    ("coffee", "Sul de Minas", "Três Pontas MG", -21.37, -45.51),
    ("coffee", "Sul de Minas", "Machado MG", -21.67, -45.92),
    ("coffee", "Cerrado Mineiro", "Patrocínio MG", -18.94, -46.99),
    ("coffee", "Cerrado Mineiro", "Araguari MG", -18.65, -48.19),
    ("coffee", "Cerrado Mineiro", "Carmo do Paranaíba MG", -19.00, -46.32),
    ("coffee", "Matas de Minas", "Manhuaçu MG", -20.26, -42.03),
    ("coffee", "Matas de Minas", "Viçosa MG", -20.75, -42.88),
    ("coffee", "Norte / Jequitinhonha", "Capelinha MG", -17.69, -42.52),
    ("coffee", "Mogiana", "Franca SP", -20.54, -47.40),
    ("coffee", "Espírito Santo (conilon)", "Linhares ES", -19.39, -40.07),
    ("coffee", "Rondônia (robusta)", "Cacoal RO", -11.44, -61.45),
    ("coffee", "Bahia Cerrado", "Luís Eduardo Magalhães BA", -12.09, -45.79),
    ("sugar", "São Paulo — north", "Ribeirão Preto SP", -21.18, -47.81),
    ("sugar", "São Paulo — centre", "Piracicaba SP", -22.73, -47.65),
    ("sugar", "Triângulo Mineiro", "Uberaba MG", -19.75, -47.93),
    ("sugar", "Goiás", "Rio Verde GO", -17.79, -50.93),
    ("sugar", "Mato Grosso do Sul", "Dourados MS", -22.22, -54.81),
    ("sugar", "Paraná", "Maringá PR", -23.42, -51.94),
    ("cotton", "Mato Grosso — west", "Sapezal MT", -13.54, -58.82),
    ("cotton", "Mato Grosso — north", "Sorriso MT", -12.55, -55.71),
    ("cotton", "Mato Grosso — south-east", "Primavera do Leste MT", -15.56, -54.30),
    ("cotton", "Bahia West", "Luís Eduardo Magalhães BA", -12.09, -45.79),
    ("cotton", "Goiás / MS", "Chapadão do Céu GO", -18.40, -52.55),
]
CLIM = (1991, 2020)


def get(url, tries=5):
    for k in range(tries):
        try:
            r = requests.get(url, headers=H, timeout=120)
            if r.ok:
                return r
            print("http", r.status_code, r.text[:160], url[:100], flush=True)
            if r.status_code == 429:
                time.sleep(65); continue
        except Exception as e:
            print("err", e, flush=True)
        time.sleep(5 + 10 * k)
    return None


def archive(lat, lon, start, end):
    """Daily ERA5 reanalysis via the Open-Meteo archive API (rain and max temperature)."""
    u = (f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start}&end_date={end}"
         "&daily=precipitation_sum,temperature_2m_max&timezone=America%2FSao_Paulo")
    r = get(u)
    if r is None:
        return None
    d = r.json()["daily"]
    df = pd.DataFrame({"p": d["precipitation_sum"], "tmax": d["temperature_2m_max"]}, index=pd.to_datetime(d["time"]))
    df.index.name = "date"
    return df


NEW_BUDGET = {"left": 8}   # full-history downloads per run (free-tier rate limits); the rest follow on later runs


def history(lat, lon, town):
    """Daily history cached in weather/data/hist/<town>.csv: fetched once in full (1991 on), then topped up."""
    hd = os.path.join(DATA, "hist"); os.makedirs(hd, exist_ok=True)
    fn = os.path.join(hd, "".join(c for c in town if c.isalnum()) + ".csv")
    today = date.today()
    old = pd.read_csv(fn, parse_dates=["date"]).set_index("date").drop(columns=["src_era5"], errors="ignore") if os.path.exists(fn) else None
    if old is None or old.index.min() > pd.Timestamp(f"{CLIM[0]}-01-02") or "src_era5" not in open(fn).readline() if os.path.exists(fn) else True:
        parts = []
        # one-off full history; ~180 API-call units each on the free tier, so pace requests (600/min, 5000/h)
        if NEW_BUDGET["left"] <= 0:
            print("history deferred to a later run:", town, flush=True)
            return None
        NEW_BUDGET["left"] -= 1
        new = archive(lat, lon, f"{CLIM[0]}-01-01", str(today - timedelta(days=1)))
        time.sleep(25)
        if new is None:
            return None
    else:
        x = archive(lat, lon, str((old.index.max() - timedelta(days=60)).date()), str(today - timedelta(days=1)))
        new = old if x is None else x.combine_first(old)
        # reanalysis lags a few days; the last values get revised, so the fresh pull overwrites them
        if x is not None:
            new.loc[x.index] = x
    new = new[~new.index.duplicated(keep="last")].sort_index().round(1)
    new.reset_index().rename(columns={"date": "date"}).assign(src_era5=1).to_csv(fn, index=False)
    return new


def forecast(lat, lon):
    u = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=precipitation_sum,temperature_2m_max"
         "&past_days=10&forecast_days=16&timezone=America%2FSao_Paulo")
    r = get(u)
    if r is None:
        return None
    d = r.json()["daily"]
    return pd.DataFrame({"date": pd.to_datetime(d["time"]), "p": d["precipitation_sum"], "tmax": d["temperature_2m_max"]}).set_index("date")


def window_stats(df, end, days):
    """Sum of rain over the window ending `end` and the 1991–2020 normal for the same calendar window."""
    start = end - timedelta(days=days - 1)
    cur = df.loc[start:end]
    vals = []
    for y in range(CLIM[0], CLIM[1] + 1):
        try:
            s = pd.Timestamp(start.year - (end.year - y), start.month, start.day) if not (start.month == 2 and start.day == 29) else pd.Timestamp(y, 2, 28)
        except ValueError:
            continue
        e = s + timedelta(days=days - 1)
        w = df.loc[s:e]
        if len(w) >= days - 2:
            vals.append(w.p.sum())
    norm = float(np.mean(vals)) if vals else None
    rain = float(cur.p.sum())
    pctile = float((np.array(vals) <= rain).mean() * 100) if vals else None
    return {"rain": round(rain, 1), "normal": round(norm, 1) if norm else None, "pct_normal": round(rain / norm * 100, 0) if norm else None,
            "pctile": round(pctile, 0) if pctile is not None else None,
            "tmax": round(float(cur.tmax.mean()), 1), "hot_days": int((cur.tmax >= 34).sum()), "rain_days": int((cur.p >= 5).sum())}


def season_curve(df, start_md=(9, 1)):
    """Cumulative rain since 1 Sep (coffee flowering / cane & cotton planting window): this season, last season, normal."""
    today = df.index.max()
    y0 = today.year if (today.month, today.day) >= start_md else today.year - 1
    s0 = pd.Timestamp(y0, *start_md)
    cur = df.loc[s0:today].p.cumsum()
    prev = df.loc[pd.Timestamp(y0 - 1, *start_md):pd.Timestamp(y0, *start_md) - timedelta(days=1)].p.cumsum()
    norms = []
    for y in range(CLIM[0], CLIM[1] + 1):
        w = df.loc[pd.Timestamp(y, *start_md):pd.Timestamp(y + 1, *start_md) - timedelta(days=1)].p.cumsum().values[:212]
        if len(w) >= 200:
            norms.append(np.pad(w, (0, 212 - len(w)), mode="edge"))
    norm = np.mean(norms, axis=0) if norms else None
    n = 212   # Sep..Mar
    return {"start": str(s0.date()), "cur": [round(v, 1) for v in cur.values[:n]], "prev": [round(v, 1) for v in prev.values[:n]],
            "normal": [round(v, 1) for v in norm[:n]] if norm is not None else []}


def enso():
    import re
    out = {}
    r = get("https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for")
    if r is not None:
        recs = []
        for ln in r.text.splitlines():
            m = re.match(r"\s*(\d{2}[A-Z]{3}\d{4})(.*)", ln)
            if not m:
                continue
            nums = [float(x) for x in re.findall(r"-?\d+\.\d", m.group(2))]
            if len(nums) >= 8:
                recs.append({"week": str(pd.to_datetime(m.group(1), format="%d%b%Y").date()), "nino34": nums[5]})
        out["weekly"] = recs[-104:]
    r = get("https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt")
    if r is not None:
        rows = [ln.split() for ln in r.text.splitlines()[1:] if len(ln.split()) == 4]
        out["oni"] = [{"season": a, "year": int(b), "anom": float(d)} for a, b, c, d in rows][-36:]
    return out


def main():
    today = date.today()
    out = {"built": str(today), "regions": [], "enso": None}
    cache = {}
    for crop, region, town, lat, lon in REGIONS:
        key = (lat, lon)
        if key not in cache:
            hist = history(lat, lon, town)
            fc = forecast(lat, lon)
            time.sleep(1)
            if hist is None:
                cache[key] = None
            else:
                if fc is not None:
                    hist = hist.combine_first(fc[fc.index <= pd.Timestamp(today)])
                cache[key] = (hist, fc)
        if cache[key] is None:
            print("no data", town); continue
        hist, fc = cache[key]
        hist = hist.dropna(subset=["p"])
        end = hist.index.max()
        rec = {"crop": crop, "region": region, "town": town, "lat": lat, "lon": lon, "asof": str(end.date()),
               "d7": window_stats(hist, end, 7), "d30": window_stats(hist, end, 30), "d90": window_stats(hist, end, 90),
               "season": season_curve(hist)}
        if fc is not None:
            f = fc[fc.index > end]
            rec["fc16"] = {"rain": round(float(f.p.sum()), 1), "days": len(f), "tmax": round(float(f.tmax.max()), 1),
                           "hot_days": int((f.tmax >= 34).sum()),
                           "daily": {"date": [str(x.date()) for x in f.index], "p": [round(v, 1) for v in f.p], "tmax": [round(v, 1) for v in f.tmax]}}
            # normal for the forecast window
            s, e = f.index.min(), f.index.max()
            vals = []
            for y in range(CLIM[0], CLIM[1] + 1):
                ss = pd.Timestamp(y, s.month, min(s.day, 28)); ee = ss + (e - s)
                w = hist.loc[ss:ee]
                if len(w) > 10:
                    vals.append(w.p.sum())
            rec["fc16"]["normal"] = round(float(np.mean(vals)), 1) if vals else None
        out["regions"].append(rec)
        print(town, rec["d30"])
    # Minas Gerais coffee belt index: region averages weighted by approximate Conab production shares
    W = {"Sul de Minas": 0.50, "Cerrado Mineiro": 0.25, "Matas de Minas": 0.22, "Norte / Jequitinhonha": 0.03}
    def agg(key, field):
        tot, wt = 0.0, 0.0
        for reg, w in W.items():
            vals = [r[key][field] for r in out["regions"] if r["region"] == reg and r.get(key) and r[key].get(field) is not None]
            if vals:
                tot += w * float(np.mean(vals)); wt += w
        return round(tot / wt, 1) if wt else None
    mg = {"weights": W}
    for key in ["d7", "d30", "d90"]:
        mg[key] = {f: agg(key, f) for f in ["rain", "normal", "tmax", "hot_days"]}
        mg[key]["pct_normal"] = round(mg[key]["rain"] / mg[key]["normal"] * 100, 0) if mg[key]["normal"] else None
    mg["fc16"] = {f: agg("fc16", f) for f in ["rain", "normal", "hot_days"]}
    curves = {}
    for part in ["cur", "prev", "normal"]:
        acc, wt = None, 0.0
        for reg, w in W.items():
            arrs = [np.array(r["season"][part]) for r in out["regions"] if r["region"] == reg and r["season"][part]]
            if not arrs:
                continue
            n = min(len(a) for a in arrs); m = np.mean([a[:n] for a in arrs], axis=0) * w
            acc = m if acc is None else acc[:n] + m[:len(acc[:n])]
            wt += w
        curves[part] = [round(v / wt, 1) for v in acc] if acc is not None else []
    mg["season"] = {"start": out["regions"][0]["season"]["start"], **curves}
    out["mg_index"] = mg
    try:
        out["enso"] = enso()
    except Exception as e:
        print("enso", e)
    json.dump(out, open(os.path.join(DATA, "br_weather.json"), "w"), separators=(",", ":"))
    print("saved", len(out["regions"]))


if __name__ == "__main__":
    main()
