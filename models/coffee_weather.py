"""Brazil coffee weather weighted by production.

Weights: Conab's latest survey, production by state and by Minas Gerais / Bahia region, separately for arabica and
conilon. Each Conab region is represented by one weather point (two for north Espírito Santo conilon), from
data/geo/weather.json (pipelines/geo_weather.py). Regions whose point has no reading yet drop out and the weights
are rescaled, with the covered share reported.

Writes data/coffee/weather_weighted.json (current reading per type and per region) and appends one row per run to
data/coffee/weather_weighted_hist.csv so the weighted index can be charted over time.
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
# (Conab table, row name) -> [(weather point, share of that row)]
MAP = {
    "arabica": {"Sul e Centro-Oeste": [("br_mg", 1)], "Triângulo, Alto Paranaiba e Noroeste": [("br_cer", 1)],
                "Zona da Mata, Rio Doce e Central": [("br_zm", 1)], "Norte, Jequitinhonha e Mucuri": [("br_nmg", 1)],
                "ES": [("br_esa", 1)], "SP": [("br_spc", 1)], "RJ": [("br_zm", 1)], "PR": [("br_prc", 1)],
                "Cerrado": [("br_bac", 1)], "Planalto": [("br_bapl", 1)], "GO": [("br_cer", 1)]},
    "conilon": {"ES": [("br_esn", 0.6), ("br_es", 0.4)], "RO": [("br_ro", 1)], "AM": [("br_ro", 1)], "MT": [("br_ro", 1)],
                "Atlântico": [("br_baa", 1)], "Zona da Mata, Rio Doce e Central": [("br_zm", 1)]},
}
KEYS = ["r30", "r60", "r90", "rstd", "f16_rain"]   # rain (mm), compared with the same window's 2011-2025 average
PCT = ["r30_p", "r60_p", "r90_p", "rstd_p", "wb60_p", "sm100_p"]


def J(p):
    try:
        return json.loads((D / p).read_text())
    except Exception:
        return None


def daily_rain(pid):
    """Daily rain for one point: 2011-2025 history plus the recent 400-day file (recent wins on overlap)."""
    parts = []
    for f in (D / "geo/weather_hist" / f"{pid}.csv.gz", D / "geo/weather_hist/recent" / f"{pid}.csv.gz"):
        if f.exists():
            x = pd.read_csv(f, index_col=0, parse_dates=True)
            if "rain" in x:
                parts.append(x["rain"])
    if not parts:
        return None
    r = pd.concat(parts)
    return r[~r.index.duplicated(keep="last")].sort_index()


def season_curves(weights):
    """Production-weighted cumulative rain from 1 Sep to 31 May for every season: current, last, average, 10th-90th pct."""
    series = {pid: daily_rain(pid) for pid in weights}
    series = {k: v for k, v in series.items() if v is not None}
    if not series:
        return None
    df = pd.DataFrame(series)
    w = pd.Series({k: weights[k] for k in df.columns})
    wr = df.mul(w, axis=1).sum(axis=1, min_count=1) / df.notna().mul(w, axis=1).sum(axis=1).replace(0, float("nan"))
    today = pd.Timestamp(date.today())
    cur_start = pd.Timestamp(today.year if today.month >= 9 else today.year - 1, 9, 1)
    curves = {}
    for y in range(2011, cur_start.year + 1):
        st = pd.Timestamp(y, 9, 1); en = pd.Timestamp(y + 1, 5, 31)
        s = wr[(wr.index >= st) & (wr.index <= en)]
        if len(s) < 7:
            continue
        idx = (s.index - st).days
        curves[y] = pd.Series(s.cumsum().values, index=idx)
    if not curves:
        return None
    days = list(range(0, 273))
    hist = pd.DataFrame({y: c.reindex(days) for y, c in curves.items() if y < cur_start.year - 1 and c.index.max() >= 270})
    week = list(range(0, 273, 7))
    pick = lambda c: [None if pd.isna(v) else round(float(v), 0) for v in c.reindex(week)]
    lab = [(cur_start + pd.Timedelta(days=d)).strftime("%d %b") for d in week]
    cur = curves.get(cur_start.year); last = curves.get(cur_start.year - 1)
    out = {"labels": lab, "season": f"{cur_start.year}/{str(cur_start.year + 1)[2:]}", "last_season": f"{cur_start.year - 1}/{str(cur_start.year)[2:]}",
           "current": pick(cur) if cur is not None else None, "last": pick(last) if last is not None else None,
           "mean": pick(hist.mean(axis=1)), "p10": pick(hist.quantile(0.1, axis=1)), "p90": pick(hist.quantile(0.9, axis=1)),
           "years": f"{min(hist.columns)}/{str(min(hist.columns) + 1)[2:]}–{max(hist.columns)}/{str(max(hist.columns) + 1)[2:]}" if len(hist.columns) else None,
           "through": str(wr.dropna().index.max().date())}
    if cur is not None and len(cur):
        d = int(cur.index.max())
        m = hist.mean(axis=1).get(d)
        out["to_date"] = {"day": d, "mm": round(float(cur.iloc[-1]), 0), "mean": None if pd.isna(m) else round(float(m), 0),
                          "last": None if last is None or d not in last.index else round(float(last.get(d)), 0),
                          "pct_mean": None if not m else round(100 * float(cur.iloc[-1]) / float(m), 0),
                          "rank": int((hist.loc[d] < cur.iloc[-1]).sum()) + 1 if d in hist.index else None, "n": len(hist.columns)}
    return out


def main():
    C, W = J("coffee/conab_regions.json"), J("geo/weather.json")
    if not C or not W:
        print("coffee weather: need data/coffee/conab_regions.json and data/geo/weather.json")
        return
    S = C["surveys"][C["latest"]]
    wx = {r["id"]: r for r in W["regions"]}
    out = {"generated": date.today().isoformat(), "conab": {"survey": S["survey"], "season": S["season"]}, "weather_through": None, "types": {}}
    hist_row = {"date": date.today().isoformat()}
    for typ, M in MAP.items():
        rows = {r["name"]: r for r in S["tables"][typ]}
        tot = next((r["prod"][1] for r in S["tables"][typ] if r["name"] == "BRASIL"), None)
        pts = {}
        for row, targets in M.items():
            r = rows.get(row)
            if not r or not r["prod"][1]:
                continue
            for pid, sh in targets:
                pts.setdefault(pid, {"weight": 0, "rows": []})
                pts[pid]["weight"] += r["prod"][1] * sh
                pts[pid]["rows"].append(row)
        mapped = sum(p["weight"] for p in pts.values())
        have = {k: v for k, v in pts.items() if k in wx and wx[k].get("r30") is not None}
        cw = sum(p["weight"] for p in have.values())
        agg = {}
        for k in KEYS:
            num = sum(p["weight"] * wx[i][k] for i, p in have.items() if wx[i].get(k) is not None and wx[i].get(k + "_n"))
            den = sum(p["weight"] * wx[i][k + "_n"] for i, p in have.items() if wx[i].get(k) is not None and wx[i].get(k + "_n"))
            agg[k + "_pct_normal"] = round(100 * num / den, 1) if den else None
        for k in PCT + ["sm100", "tmin30", "f16_tmin"]:
            xs = [(p["weight"], wx[i][k]) for i, p in have.items() if wx[i].get(k) is not None]
            agg[k] = round(sum(w * v for w, v in xs) / sum(w for w, _ in xs), 1) if xs else None
        cold = [(i, wx[i].get("f16_tmin")) for i in have if wx[i].get("f16_tmin") is not None]
        agg["coldest_forecast"] = min(cold, key=lambda x: x[1]) if cold else None
        agg["frost_risk_share"] = round(100 * sum(p["weight"] for i, p in have.items() if (wx[i].get("f16_tmin") or 99) <= 3) / cw, 1) if cw else None
        regions = []
        for i, p in sorted(pts.items(), key=lambda x: -x[1]["weight"]):
            w = wx.get(i, {})
            regions.append({"id": i, "name": w.get("name", i), "conab_rows": p["rows"], "prod_k": round(p["weight"], 1), "share": round(100 * p["weight"] / mapped, 1),
                            "has_weather": i in have, **{k: w.get(k) for k in ["r30", "r30_n", "r30_p", "r90", "r90_n", "r90_p", "rstd", "rstd_n", "rstd_p", "season_from",
                                                                                "sm100_p", "wb60_p", "tmin30", "cold30", "f16_rain", "f16_rain_n", "f16_tmin", "f16_cold", "data_through"]}})
        sc = season_curves({i: p["weight"] for i, p in pts.items()})
        out["types"][typ] = {"brazil_prod_k": tot, "season_curve": sc, "mapped_share": round(100 * mapped / tot, 1) if tot else None,
                             "weather_share": round(100 * cw / mapped, 1) if mapped else None, **agg, "regions": regions}
        for k in ["r30_pct_normal", "r90_pct_normal", "rstd_pct_normal", "f16_rain_pct_normal", "sm100_p"]:
            hist_row[f"{typ}_{k}"] = agg.get(k)
        out["weather_through"] = max([wx[i].get("data_through") or "" for i in have] or [""]) or None
    (D / "coffee").mkdir(parents=True, exist_ok=True)
    (D / "coffee" / "weather_weighted.json").write_text(json.dumps(out, ensure_ascii=False))
    hp = D / "coffee" / "weather_weighted_hist.csv"
    h = pd.read_csv(hp) if hp.exists() else pd.DataFrame()
    h = pd.concat([h, pd.DataFrame([hist_row])]).drop_duplicates("date", keep="last")
    h.to_csv(hp, index=False)
    for t, v in out["types"].items():
        print(f"coffee weather {t}: 30d rain {v['r30_pct_normal']}% of normal, season {v['rstd_pct_normal']}%, weather covers {v['weather_share']}% of mapped output")


if __name__ == "__main__":
    main()
