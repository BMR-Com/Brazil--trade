"""Conab coffee crop survey (Levantamento de Café): area in production, yield and production by state and by
Minas Gerais / Bahia region, for arabica and conilon, this season and last.

Finds the latest survey on Conab's coffee page, downloads its data table (xls) and writes
data/coffee/conab_regions.json. Each survey is kept under its own key so revisions between surveys can be shown.
"""
import io, json, re, sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "coffee" / "conab_regions.json"
BASE = "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/safra-de-cafe"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
SHEETS = {"arabica": "Arábica", "conilon": "Conilon", "total": "Total"}
# rows kept: states plus the regions inside Minas Gerais and Bahia (names as in Conab's table)
STATES = {"RO", "AM", "BA", "MT", "GO", "MG", "ES", "RJ", "SP", "PR", "OUTROS (*)", "BRASIL"}
SUBREG = {"Cerrado": "BA", "Planalto": "BA", "Atlântico": "BA", "Sul e Centro-Oeste": "MG", "Triângulo, Alto Paranaiba e Noroeste": "MG",
          "Zona da Mata, Rio Doce e Central": "MG", "Norte, Jequitinhonha e Mucuri": "MG"}


def get(u):
    return requests.get(u, headers=H, timeout=120, verify=False)


def latest_survey():
    s = BeautifulSoup(get(BASE).text, "html.parser")
    for a in s.find_all("a", href=True):
        t = a.get_text(" ", strip=True)
        m = re.match(r"(\d)º Levantamento de Café - Safra (\d{4})", t)
        if m:
            return int(m.group(1)), int(m.group(2)), a["href"]
    raise RuntimeError("no survey link found")


def table_url(page):
    s = BeautifulSoup(get(page).text, "html.parser")
    for a in s.find_all("a", href=True):
        if re.search(r"\.xlsx?$", a["href"], re.I) and re.search(r"tabela|dados|previs", a.get_text(" ", strip=True) + a["href"], re.I):
            return a["href"]
    raise RuntimeError("no data table on " + page)


def f(x):
    try:
        x = float(x)
        return None if x != x else round(x, 2)
    except (TypeError, ValueError):
        return None


def parse(xls, season):
    book = pd.read_excel(io.BytesIO(xls), sheet_name=None, header=None)
    out = {}
    for key, word in SHEETS.items():
        name = next((n for n in book if word in n and "Área" not in n and "Area" not in n), None)
        if name is None:
            continue
        rows = []
        for _, r in book[name].iterrows():
            lab = str(r[0]).strip() if r[0] == r[0] else ""
            if lab in STATES or lab in SUBREG:
                rows.append({"name": lab, "state": SUBREG.get(lab, lab), "sub": lab in SUBREG,
                             "area": [f(r[1]), f(r[2])], "yield": [f(r[4]), f(r[5])], "prod": [f(r[7]), f(r[8])]})
        out[key] = rows
    return {"seasons": [season - 1, season], "unit": {"area": "ha", "yield": "bags/ha", "prod": "thousand 60-kg bags"}, "tables": out}


def main():
    n, season, page = latest_survey()
    if not page.startswith("http"):
        page = "https://www.gov.br" + page
    xu = table_url(page)
    if not xu.startswith("http"):
        xu = "https://www.gov.br" + xu
    d = parse(get(xu).content, season)
    J = json.loads(OUT.read_text()) if OUT.exists() else {"surveys": {}}
    key = f"{season}-{n}"
    J["surveys"][key] = {"survey": n, "season": season, "page": page, "table": xu, "fetched": date.today().isoformat(), **d}
    J["latest"] = max(J["surveys"], key=lambda k: tuple(map(int, k.split("-"))))
    J["source"] = "Conab, Acompanhamento da Safra Brasileira de Café"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(J, ensure_ascii=False))
    b = next(r for r in d["tables"]["total"] if r["name"] == "BRASIL")
    print(f"conab coffee: survey {n} of {season}; Brazil {b['prod'][1]} k bags (last season {b['prod'][0]})")


if __name__ == "__main__":
    sys.exit(main())
