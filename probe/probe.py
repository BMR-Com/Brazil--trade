import requests, pandas as pd
for name, lat, lon in [("Varginha", -21.55, -45.43), ("Sorriso", -12.55, -55.71)]:
    u = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date=2015-01-01&end_date=2026-10-10&daily=precipitation_sum&timezone=America%2FSao_Paulo"
    r = requests.get(u, timeout=120); d = r.json()["daily"]
    s = pd.Series(d["precipitation_sum"], index=pd.to_datetime(d["time"]))
    print(name, "ERA5", s.groupby(s.index.year).sum().round(0).to_dict())
    u = f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters=PRECTOTCORR,PRECTOT&community=AG&longitude={lon}&latitude={lat}&start=20150101&end=20261010&format=JSON"
    p = requests.get(u, timeout=120).json()["properties"]["parameter"]
    for k in p:
        s2 = pd.Series(list(p[k].values()), index=pd.to_datetime(list(p[k].keys()), format="%Y%m%d")).mask(lambda x: x < -900)
        print(name, k, s2.groupby(s2.index.year).sum().round(0).to_dict())
    try:
        u = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date=2024-01-01&end_date=2026-10-10&daily=precipitation_sum&models=era5_land&timezone=America%2FSao_Paulo"
        d = requests.get(u, timeout=120).json()["daily"]; s = pd.Series(d["precipitation_sum"], index=pd.to_datetime(d["time"]))
        print(name, "ERA5-land", s.groupby(s.index.year).sum().round(0).to_dict())
    except Exception as e: print(e)
