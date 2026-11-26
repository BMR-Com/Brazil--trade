"""Brazil coffee stocks for the Coffee > Differentials tab: data/coffee/diffs/brazil_stocks.csv.

  IBGE Pesquisa de Estoques (SIDRA table 254): green coffee ("café em grão") declared in storage on the last day of each
    half-year (30 Jun, 31 Dec), with arabica and canephora (conilon/robusta) split from 2014; tonnes -> million 60-kg bags.
    Read each run through the IBGE aggregates API (servicodados.ibge.gov.br); IBGE releases each half-year about four
    months later.
  CONAB private stocks survey (estoques privados, 31 Mar): annual results as published, kept in the file (CONAB's site
    cannot be read from GitHub's runners; no survey after 2020 has been found).
  USDA PSD Brazil ending stocks (coffee/data/psd_coffee.csv, refreshed by the coffee fetch).
"""
import csv, sys, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "coffee" / "diffs" / "brazil_stocks.csv"
AGENT = "BMR-Com research desk (github.com/BMR-Com)"
API = "https://servicodados.ibge.gov.br/api/v3/agregados/254/periodos/all/variaveis/150"
CATS = {"3042": "total", "33467": "arabica", "33468": "canephora"}
# CONAB, Levantamento de estoques privados de café, position 31 March (million 60-kg bags, all types), as published
CONAB = [("2013-03-31", 13.938), ("2016-03-31", 9.86), ("2019-03-31", 12.8), ("2020-03-31", 13.1)]
FIELDS = ["date", "source", "series", "m_bags", "note"]


def ibge():
    for i in range(4):
        try:
            r = requests.get(API, params={"localidades": "N1[all]", "classificacao": "162[" + ",".join(CATS) + "]"},
                             headers={"User-Agent": AGENT}, timeout=180)
            r.raise_for_status()
            out = []
            for res in r.json()[0]["resultados"]:
                cat = next(iter(res["classificacoes"][0]["categoria"]))
                for per, v in res["series"][0]["serie"].items():
                    try:
                        t = float(v)
                    except ValueError:
                        continue
                    d = f"{per[:4]}-06-30" if per[4:] == "01" else f"{per[:4]}-12-31"
                    out.append({"date": d, "source": "IBGE", "series": CATS[cat], "m_bags": round(t / 60000, 3), "note": "declared storage, last day of the half-year"})
            return out
        except Exception as e:
            print("IBGE retry", i + 1, str(e)[:160]); time.sleep(20 * (i + 1))
    return None


def usda():
    p = ROOT / "coffee" / "data" / "psd_coffee.csv"
    if not p.exists():
        return []
    out = []
    with open(p) as f:
        for r in csv.DictReader(f):
            if r["Country_Code"] == "BR" and r["Attribute_Description"] == "Ending Stocks":
                y = int(r["Market_Year"])
                out.append({"date": f"{y + 1}-06-30", "source": "USDA", "series": "ending", "m_bags": round(float(r["Value"]) / 1000, 3),
                            "note": f"PSD ending stocks, marketing year {y}/{str(y + 1)[2:]} (Jul-Jun)"})
    return out


def main():
    old = []
    if OUT.exists():
        with open(OUT) as f:
            old = list(csv.DictReader(f))
    ib = ibge()
    if ib is None:
        ib = [r for r in old if r["source"] == "IBGE"]
        print("IBGE not reachable; kept the rows already in the file")
    rows = ib + [{"date": d, "source": "CONAB", "series": "private", "m_bags": v, "note": "private stocks survey, 31 March"} for d, v in CONAB] + usda()
    rows.sort(key=lambda r: (r["date"], r["source"], r["series"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS); w.writeheader(); w.writerows(rows)
    last = max((r["date"] for r in rows if r["source"] == "IBGE"), default="-")
    print(f"Brazil stocks: {len(rows)} rows, IBGE latest {last}")
    if not ib:
        sys.exit(1)


if __name__ == "__main__":
    main()
