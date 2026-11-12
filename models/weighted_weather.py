"""Production-weighted weather by country for sugar and coffee.

Each producing country is split into its main cane / coffee states or regions, each represented by one Open-Meteo
point from data/geo/weather.json (pipelines/geo_weather.py). The country index weights every point by its share of
national output and compares rain with the same window's 2011-2025 average (weighted sum of rain / weighted sum of
normals), so a dry big region counts for more than a wet small one.

Weights (approximate shares of national output, updated by hand when a new season's numbers settle):
  Brazil sugar    Conab 2025/26 cane by state (SP ~50%, GO ~12%, MG ~10%, MS ~8%, PR ~5%, North-North-East ~8%)
  India sugar     ISMA 2024/25 sugar by state (UP ~36%, Maharashtra ~31%, Karnataka ~16%, Gujarat ~3.5%, Tamil Nadu ~2.5%)
  Thailand sugar  cane area by region (Northeast ~45%, North ~27%, West ~14%, Central ~9%, East ~5%)
  Brazil coffee   Conab's latest survey by state/region (arabica + conilon), via models/coffee_weather.py
  Vietnam coffee  output by Central Highlands province (Dak Lak ~31%, Lam Dong ~27%, Dak Nong ~19%, Gia Lai/Kon Tum ~18%)
  Colombia coffee FNC 2024/25 output by department (Huila ~20%, Antioquia ~14%, Tolima ~12%, Cauca ~10%, coffee axis ~15%)
Points without a reading drop out and the rest are re-weighted; the covered share is reported. Percent-of-normal needs
the point's 2011-2025 history, which pipelines/geo_weather.py downloads a few points per day.

Writes data/geo/weighted.json and appends one row per run to data/geo/weighted_hist.csv.
"""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))
D = ROOT / "data"

# commodity -> country -> {source, season (start month, day, label), weights: [(point, region label, share %)]}
CFG = {
    "sugar": {
        "Brazil": {"source": "Conab 2025/26 cane by state (approx.)", "season": (10, 1, "rainy season from 1 Oct"),
                   "weights": [("br_sp", "São Paulo north-east (Ribeirão Preto, Piracicaba)", 30), ("br_spw", "São Paulo west (Araçatuba, Pres. Prudente)", 20),
                               ("br_gos", "Goiás", 12), ("br_mgc", "Minas Gerais (Triângulo)", 10), ("br_ms", "Mato Grosso do Sul", 8),
                               ("br_prs", "Paraná", 5), ("br_al", "Alagoas (N-NE)", 3.5), ("br_pe", "Pernambuco (N-NE)", 2.5)],
                   "note": "Mato Grosso and the rest of the North-North-East (~10%) are not mapped. Centre-South: Oct-Mar rain grows next year's cane; dry weather Apr-Nov speeds the crush. N-NE runs a year behind (rains Apr-Aug, crush Sep-Mar)."},
        "India": {"source": "ISMA 2024/25 sugar output by state (approx.)", "season": (6, 1, "monsoon from 1 Jun"),
                  "weights": [("in_up", "Uttar Pradesh west (Muzaffarnagar, Meerut)", 18), ("in_lk", "Uttar Pradesh central/east (Lakhimpur)", 18),
                              ("in_kol", "Maharashtra south (Kolhapur, Sangli)", 12), ("in_sl", "Maharashtra Solapur/Marathwada", 10), ("in_ah", "Maharashtra Pune/Ahilyanagar", 9),
                              ("in_bg", "Karnataka north (Belagavi)", 16), ("in_su", "Gujarat south", 3.5), ("in_er", "Tamil Nadu", 2.5)],
                  "note": "Cane is mostly irrigated: the Jun-Sep monsoon refills the dams and groundwater that water it, and decides next season's planting in Maharashtra and Karnataka. Other states (~11%) not mapped."},
        "Thailand": {"source": "cane area by region (Krungsri Research)", "season": (5, 1, "rainy season from 1 May"),
                     "weights": [("th_kk", "Northeast upper (Khon Kaen, Udon Thani)", 25), ("th_kr", "Northeast lower (Korat, Buriram, Surin)", 20),
                                 ("th_ns", "North lower (Nakhon Sawan)", 15), ("th_kp", "North (Kamphaeng Phet, Sukhothai)", 12),
                                 ("th_kb", "West (Kanchanaburi, Ratchaburi)", 14), ("th_sp", "Central (Suphan Buri, Saraburi)", 9), ("th_sk", "East (Sa Kaeo, Chonburi)", 5)],
                     "note": "Cane is rain-fed: May-Oct monsoon sets tonnage, the crush runs Dec-Apr."},
    },
    "coffee": {
        "Brazil": {"source": "Conab, latest coffee survey, by state/region (arabica + conilon)", "season": (9, 1, "flowering rains from 1 Sep"), "weights": "conab",
                   "note": "Arabica and conilon separately: see the Coffee tab's weighted-weather cards. Frost season Jun-Aug."},
        "Vietnam": {"source": "provincial output, Central Highlands (approx.)", "season": (5, 1, "rainy season from 1 May"),
                    "weights": [("vn_dl", "Đắk Lắk", 31), ("vn_ld", "Lâm Đồng", 27), ("vn_dn", "Đắk Nông", 19), ("vn_gl", "Gia Lai and Kon Tum", 18)],
                    "note": "Robusta: rainy season May-Oct fills the cherries; harvest Nov-Jan; flowering Feb-Apr depends on irrigation water stored from the rains. Other provinces (~5%) not mapped."},
        "Colombia": {"source": "FNC 2024/25 output by department", "season": (1, 1, "calendar year"),
                     "weights": [("co_hu", "Huila", 19.7), ("co_an", "Antioquia", 14.2), ("co_to", "Tolima", 12.5), ("co_ca", "Cauca and Nariño", 14.4),
                                 ("co_cz", "Caldas, Risaralda, Quindío (coffee axis)", 14.5)],
                     "note": "Two crops: main crop Oct-Jan in the centre/north, Apr-Jul in the south; too much rain cuts flowering (La Niña), too little cuts cherry fill (El Niño). Santander, Valle and others (~25%) not mapped."},
    },
}
KEYS = ["r30", "r60", "r90", "rstd", "f16_rain"]
PCT = ["r30_p", "r60_p", "r90_p", "rstd_p", "wb60_p", "sm100_p"]
REG_FIELDS = ["name", "r30", "r30_n", "r30_p", "r60_p", "r90", "r90_n", "rstd", "rstd_n", "rstd_p", "season_from", "sm100_p", "wb60_p",
              "tmax30", "tmax30_n", "tmin30", "f16_rain", "f16_rain_n", "f16_tmin", "data_through", "history"]


def J(p):
    try:
        return json.loads((D / p).read_text())
    except Exception:
        return None


def conab_coffee():
    """Brazil coffee weights from Conab (arabica + conilon) through coffee_weather.MAP, as % of mapped output."""
    from coffee_weather import MAP
    C = J("coffee/conab_regions.json")
    if not C:
        return []
    S = C["surveys"][C["latest"]]
    pts = {}
    for typ, M in MAP.items():
        rows = {r["name"]: r for r in S["tables"][typ]}
        for row, targets in M.items():
            r = rows.get(row)
            if r and r["prod"][1]:
                for pid, sh in targets:
                    pts[pid] = pts.get(pid, 0) + r["prod"][1] * sh
    tot = sum(pts.values()) or 1
    return [(pid, None, round(100 * w / tot, 1)) for pid, w in sorted(pts.items(), key=lambda x: -x[1])]


def daily_rain(pid):
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


def season_curve(weights, sm, sd):
    """Weighted cumulative rain over a 365-day season starting (sm, sd): current, last, mean, 10th-90th pct of 2011+ seasons.
    Only points with history enter, so the curve is like-for-like across years."""
    series = {}
    for pid, w in weights.items():
        if not (D / "geo/weather_hist" / f"{pid}.csv.gz").exists():
            continue
        s = daily_rain(pid)
        if s is not None:
            series[pid] = s
    if not series:
        return None
    df = pd.DataFrame(series)
    w = pd.Series({k: weights[k] for k in df.columns})
    wr = df.mul(w, axis=1).sum(axis=1, min_count=1) / df.notna().mul(w, axis=1).sum(axis=1).replace(0, float("nan"))
    today = pd.Timestamp(date.today())
    cy = today.year if (today.month, today.day) >= (sm, sd) else today.year - 1
    cur_start = pd.Timestamp(cy, sm, sd)
    curves = {}
    for y in range(2011, cy + 1):
        st = pd.Timestamp(y, sm, sd)
        s = wr[(wr.index >= st) & (wr.index < st + pd.Timedelta(days=365))]
        if len(s) < 7:
            continue
        curves[y] = pd.Series(s.cumsum().values, index=(s.index - st).days)
    days = list(range(0, 365))
    hist = pd.DataFrame({y: c.reindex(days) for y, c in curves.items() if y < cy - 1 and c.index.max() >= 360})
    if hist.empty:
        return None
    week = list(range(0, 365, 7))
    pick = lambda c: [None if pd.isna(v) else round(float(v), 0) for v in c.reindex(week)]
    lab = [(cur_start + pd.Timedelta(days=d)).strftime("%d %b") for d in week]
    cur, last = curves.get(cy), curves.get(cy - 1)
    yl = lambda y: f"{y}/{str(y + 1)[2:]}" if (sm, sd) != (1, 1) else str(y)
    out = {"labels": lab, "season": yl(cy), "last_season": yl(cy - 1), "current": pick(cur) if cur is not None else None, "last": pick(last) if last is not None else None,
           "mean": pick(hist.mean(axis=1)), "p10": pick(hist.quantile(0.1, axis=1)), "p90": pick(hist.quantile(0.9, axis=1)),
           "years": f"{yl(min(hist.columns))}–{yl(max(hist.columns))}", "points": list(df.columns), "through": str(wr.dropna().index.max().date())}
    if cur is not None and len(cur):
        d = int(cur.index.max())
        m = hist.mean(axis=1).get(d)
        out["to_date"] = {"day": d, "mm": round(float(cur.iloc[-1]), 0), "mean": None if pd.isna(m) else round(float(m), 0),
                          "last": None if last is None or d not in last.index else round(float(last.get(d)), 0),
                          "pct_mean": None if not m else round(100 * float(cur.iloc[-1]) / float(m), 0),
                          "rank": int((hist.loc[d] < cur.iloc[-1]).sum()) + 1, "n": len(hist.columns)}
    return out


def read(agg):
    """One-line verdict from the weighted numbers."""
    r90, r30, f16, sm = agg.get("r90_pct_normal"), agg.get("r30_pct_normal"), agg.get("f16_rain_pct_normal"), agg.get("sm100_p")
    if r90 is None and r30 is None:
        return "history pending", 0
    bits, sc = [], 0
    ordn = lambda v: f"{v:.0f}" + ("th" if 10 <= round(v) % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(round(v) % 10, "th"))
    dry_season = (agg.get("r30_normal_mm") or 99) < 25
    if r90 is not None:
        bits.append(f"90-day rain {r90:.0f}% of normal")
        sc += -1 if r90 < 75 else 1 if r90 > 125 else 0
    if r30 is not None:
        bits.append(f"30-day {r30:.0f}%")
    if sm is not None:
        bits.append(f"deep soil moisture {ordn(sm)} pct")
        sc += -1 if sm < 25 else 1 if sm > 75 else 0
    if f16 is not None:
        bits.append(f"next 16 days {f16:.0f}% of normal")
    word = "dry" if sc <= -1 else "wet" if sc >= 1 else "near normal"
    if dry_season:
        bits.append(f"dry season now (30-day normal {agg['r30_normal_mm']:.0f} mm), so % of normal swings on a few showers")
    return f"{word}: " + ", ".join(bits), sc


def main():
    W = J("geo/weather.json")
    if not W:
        print("weighted weather: data/geo/weather.json missing")
        return
    wx = {r["id"]: r for r in W["regions"]}
    out = {"generated": date.today().isoformat(), "history": "2011–2025", "commodities": {}}
    hist_row = {"date": date.today().isoformat()}
    for com, countries in CFG.items():
        out["commodities"][com] = {}
        for cty, cfg in countries.items():
            wts = conab_coffee() if cfg["weights"] == "conab" else cfg["weights"]
            if not wts:
                continue
            tot = sum(s for _, _, s in wts)
            have = [(p, s) for p, _, s in wts if p in wx and wx[p].get("r30") is not None]
            hw = sum(s for _, s in have)
            normal = [(p, s) for p, s in have if wx[p].get("r30_n")]
            agg = {}
            for k in KEYS:
                xs = [(s, wx[p][k], wx[p].get(k + "_n")) for p, s in have if wx[p].get(k) is not None and wx[p].get(k + "_n")]
                den = sum(s * n for s, _, n in xs)
                agg[k + "_pct_normal"] = round(100 * sum(s * v for s, v, _ in xs) / den, 1) if den else None
                xm = [(s, wx[p][k]) for p, s in have if wx[p].get(k) is not None]
                agg[k + "_mm"] = round(sum(s * v for s, v in xm) / sum(s for s, _ in xm), 1) if xm else None
                agg[k + "_normal_mm"] = round(den / sum(s for s, _, _ in xs), 1) if xs else None
            for k in PCT + ["tmin30", "f16_tmin"]:
                xs = [(s, wx[p][k]) for p, s in have if wx[p].get(k) is not None]
                agg[k] = round(sum(s * v for s, v in xs) / sum(s for s, _ in xs), 1) if xs else None
            ta = [(s, wx[p]["tmax30"] - wx[p]["tmax30_n"]) for p, s in have if wx[p].get("tmax30") is not None and wx[p].get("tmax30_n") is not None]
            agg["tmax30_anom"] = round(sum(s * v for s, v in ta) / sum(s for s, _ in ta), 1) if ta else None
            txt, sc = read(agg)
            sm, sd, slab = cfg["season"]
            regions = []
            for p, lab, s in wts:
                r = wx.get(p, {})
                regions.append({"id": p, "label": lab or r.get("name", p), "share": round(100 * s / tot, 1), "has_weather": p in dict(have),
                                "has_history": bool(r.get("r30_n")), **{k: r.get(k) for k in REG_FIELDS}})
            out["commodities"][com][cty] = {"source": cfg["source"], "note": cfg["note"], "season_label": slab, "mapped_pct": round(tot, 1),
                                            "weather_share": round(100 * hw / tot, 1), "normal_share": round(100 * sum(s for _, s in normal) / tot, 1),
                                            **agg, "read": txt, "score": sc, "regions": regions,
                                            "season_curve": season_curve({p: s for p, _, s in wts}, sm, sd)}
            for k in ["r30_pct_normal", "r90_pct_normal", "rstd_pct_normal", "f16_rain_pct_normal", "sm100_p"]:
                hist_row[f"{com}_{cty}_{k}".replace(" ", "_")] = agg.get(k)
            print(f"{com} {cty}: {txt} | weather {out['commodities'][com][cty]['weather_share']}%, normals {out['commodities'][com][cty]['normal_share']}% of mapped output")
    (D / "geo" / "weighted.json").write_text(json.dumps(out, ensure_ascii=False))
    hp = D / "geo" / "weighted_hist.csv"
    h = pd.read_csv(hp) if hp.exists() else pd.DataFrame()
    pd.concat([h, pd.DataFrame([hist_row])]).drop_duplicates("date", keep="last").to_csv(hp, index=False)


if __name__ == "__main__":
    main()
