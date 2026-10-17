import re, io, json, requests
import pandas as pd
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
S = requests.Session(); S.headers.update(H)
NA = "https://www.noticiasagricolas.com.br/cotacoes/cafe/"
for s in ["cafe-arabica-mercado-fisico-tipo-6-7", "cafe-arabica-4-5-b3-prego-regular", "cafe-cereja-descascado-mercado-fisico"]:
    r = S.get(NA + s, timeout=60); print("\n===", s, r.status_code)
    t = pd.read_html(io.StringIO(r.text), thousands=".", decimal=",")
    for x in t[:2]: print(x.to_string()[:1500])
r = S.get("https://www.noticiasagricolas.com.br/cotacoes/", timeout=60)
print("ALL CAFE", sorted(set(re.findall(r'href="(/cotacoes/cafe/[^"]+)"', r.text))))
for q in ["bebida fina", "bebida boa", "cafe-arabica-bebida", "fino"]:
    pass
# other possible fine-cup sources
for u in ["https://www.noticiasagricolas.com.br/cotacoes/cafe/cafe-arabica-mercado-fisico-tipo-6-bebida-boa", "https://www.cccmg.com.br/cotacao/", "https://www.cooxupe.com.br/", "https://hubdocafe.cooxupe.com.br/"]:
    try:
        r = S.get(u, timeout=40); print("\n===", u, r.status_code, len(r.text))
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text)); i = txt.lower().find("fina"); print(txt[max(0,i-300):i+600] if i>=0 else txt[:300])
    except Exception as e: print(u, e)
# GAIN search API
for u in ["https://apps.fas.usda.gov/newgainapi/api/Report/GetReports?commodityId=&countryId=&dateFrom=2026-10-01&dateTo=2026-10-17",
          "https://www.fas.usda.gov/data/search?f%5B0%5D=data_type%3AGAIN%20Report",
          "https://gain.fas.usda.gov/#/search", "https://apps.fas.usda.gov/newgainapi/api/Report/GetAllReports"]:
    try:
        r = S.get(u, timeout=60); print("\n===", u, r.status_code, r.headers.get("content-type"), len(r.content)); print(r.text[:600])
    except Exception as e: print(u, e)
r = S.get("https://www.fas.usda.gov/data/search?f%5B0%5D=data_type%3AGAIN%20Report&f%5B1%5D=commodities%3ACoffee", timeout=60)
print("FAS coffee search", r.status_code, sorted(set(re.findall(r'href="(/data/[^"]+)"', r.text)))[:40])
r = S.get("https://www.fas.usda.gov/rss.xml", timeout=60); print("rss", r.status_code, r.text[:500])
# Open-Meteo
r = S.get("https://archive-api.open-meteo.com/v1/archive?latitude=-21.55&longitude=-45.43&start_date=2026-09-01&end_date=2026-10-10&daily=precipitation_sum,temperature_2m_max&timezone=America/Sao_Paulo", timeout=60)
print("\nopenmeteo archive", r.status_code, r.text[:400])
r = S.get("https://api.open-meteo.com/v1/forecast?latitude=-21.55&longitude=-45.43&daily=precipitation_sum,temperature_2m_max&past_days=14&forecast_days=16&timezone=America/Sao_Paulo", timeout=60)
print("openmeteo fc", r.status_code, r.text[:400])
r = S.get("https://climate-api.open-meteo.com/v1/climate?latitude=-21.55&longitude=-45.43&start_date=2026-10-01&end_date=2027-03-31&models=EC_Earth3P_HR&daily=precipitation_sum", timeout=60)
print("climate", r.status_code, r.text[:200])
r = S.get("https://seasonal-api.open-meteo.com/v1/seasonal?latitude=-21.55&longitude=-45.43&daily=precipitation_sum&forecast_days=183", timeout=60)
print("seasonal", r.status_code, r.text[:300])
