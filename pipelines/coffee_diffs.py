"""Coffee > Differentials view: builds data/coffee/diffs/diffs.json from the desk's own files (no downloads).

Inputs (each written by its own pipeline):
  Honduras   data/coffee/diffs/honduras_ihcafe_daily.csv     pipelines/honduras_ihcafe.py (IHCAFE daily figures)
  Colombia   data/coffee/colombia/internal_price_daily.csv,  pipelines/colombia_fnc.py (FNC price per carga, monthly
             usdcop.csv, monthly_report.csv                  differential from the Informe mensual)
  Brazil     data/coffee/diffs/safras_quotes.csv              pipelines/safras_quotes.py (SAFRAS & Mercado quotes by quality),
             data/coffee/manual/brazil_export_diffs.csv       earlier quotes entered by hand
             data/coffee/diffs/brazil_stocks.csv              pipelines/brazil_stocks.py (IBGE, CONAB, USDA)
  Vietnam    data/coffee/diffs/vietnam_exports.csv            pipelines/vietnam_exports.py; coffee/data/psd_coffee.csv
  ICE        data/coffee/kc_spreads_history.csv (KC front, 2nd, 3rd), coffee/data/prices_cont.csv (RC1!, USDVND)
Units: US cents/lb. A Honduras sack is 46 kg (101.41 lb); an FNC carga is 125 kg parchment = 93.09 kg green at
factor 94; a 60-kg bag is 132.277 lb.
"""
import json, math, os, re
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "coffee"
OUT = D / "diffs"
LB46 = 46 * 2.2046226
LB_CARGA = 93.09 * 2.2046226
LB_BAG = 132.277


def r1(x, n=1):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), n)


def kc():
    k = pd.read_csv(D / "kc_spreads_history.csv", parse_dates=["date"]).set_index("date")
    k["k23"] = (k.f2 + k.f3) / 2
    return k


def honduras(K):
    p = OUT / "honduras_ihcafe_daily.csv"
    if not p.exists():
        return None
    h = pd.read_csv(p, parse_dates=["date"]).set_index("date").sort_index()
    h["price_c_lb"] = h.avg_export_price_usd_46kg / LB46 * 100
    k = K.reindex(h.index, method="ffill", tolerance=pd.Timedelta(days=5))
    # crop-to-date realized price vs the KC front average since the crop began (Oct 1)
    prem, marg, margp = [], [], []
    val = h.avg_export_price_usd_46kg * h.exports_cum_46kg
    for d, row in h.iterrows():
        cs = pd.Timestamp(year=d.year if d.month >= 10 else d.year - 1, month=10, day=1)
        kk = K.loc[cs:d, "f1"]
        prem.append(row.price_c_lb - kk.mean() if len(kk) else float("nan"))
        # marginal: exports registered over the last ~10 business days, priced from the change in export value
        w = h.loc[:d].tail(11)
        w = w[w.crop == row.crop] if "crop" in w else w
        dv, dq = (val.loc[w.index].iloc[-1] - val.loc[w.index].iloc[0]), (w.exports_cum_46kg.iloc[-1] - w.exports_cum_46kg.iloc[0])
        m = dv / dq / LB46 * 100 if len(w) >= 6 and dq > 25000 else float("nan")
        marg.append(m)
        kw = K.loc[w.index[0]:d, "f1"]
        margp.append(m - kw.mean() if len(kw) and m == m else float("nan"))
    h["prem_ctd"], h["marg_c_lb"], h["marg_prem"] = prem, marg, margp
    # contracts by price band: band-midpoint average price per quality, crop to date (US$/46kg -> c/lb)
    mids = {"0-100": 50, "101-150": 125.5, "151-200": 175.5, "201-250": 225.5, "251-300": 275.5, "301-350": 325.5, "351-400": 375.5, ">400": 425}
    for q in ("shg", "hg"):
        num = sum(h[f"b{b}_{q}"].fillna(0) * m for b, m in mids.items())
        den = sum(h[f"b{b}_{q}"].fillna(0) for b in mids)
        h[f"band_{q}_c_lb"] = (num / den.where(den > 0)) / LB46 * 100
    last = h.iloc[-1]
    ser = lambda c: [r1(x) for x in h[c]]
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in h.index], "crop": list(h.crop.fillna("")),
        "price_c_lb": ser("price_c_lb"), "prem_ctd": ser("prem_ctd"), "marg_c_lb": ser("marg_c_lb"), "marg_prem": ser("marg_prem"),
        "band_shg_c_lb": ser("band_shg_c_lb"), "band_hg_c_lb": ser("band_hg_c_lb"), "kc_front": [r1(x) for x in k.f1],
        "latest": {"date": h.index[-1].strftime("%Y-%m-%d"), "crop": last.crop, "price_c_lb": r1(last.price_c_lb),
                   "prem_ctd": r1(last.prem_ctd), "marg_c_lb": r1(last.marg_c_lb), "marg_prem": r1(last.marg_prem),
                   "exports_k": r1(last.exports_cum_46kg / 1000, 0), "sales_k": r1(last.sales_cum_46kg / 1000, 0),
                   "shg_share_sales": r1(100 * last.sales_shg / last.sales_cum_46kg) if last.sales_cum_46kg else None,
                   "band_shg_c_lb": r1(last.band_shg_c_lb), "band_hg_c_lb": r1(last.band_hg_c_lb)},
        "notes": {"price_c_lb": "IHCAFE average price per 46-kg bag exported, crop to date",
                  "prem_ctd": "crop-to-date export price minus the KC front average since 1 Oct",
                  "marg_c_lb": "exports registered over the last ~2 weeks, priced from the change in export value",
                  "marg_prem": "that price minus the KC front average over the same days (contracts are fixed earlier, so a proxy)",
                  "band_shg_c_lb": "contracted SHG/HG sales, US$ price-band midpoints, crop to date"}}


def colombia(K):
    c = D / "colombia"
    ip = pd.read_csv(c / "internal_price_daily.csv", parse_dates=["date"]).set_index("date").cop_per_carga
    fx = pd.read_csv(c / "usdcop.csv", parse_dates=["date"]).set_index("date").cop_per_usd
    df = pd.DataFrame({"cop": ip}).join(fx.rename("trm"), how="left")
    df["trm"] = df.trm.ffill(limit=4)
    df = df.dropna()
    df["f1"] = K.f1.reindex(df.index, method="ffill", tolerance=pd.Timedelta(days=4))
    df = df.dropna()
    df["usd_c_lb"] = df.cop / df.trm / LB_CARGA * 100
    df["net_prem"] = df.usd_c_lb - df.f1
    # calibration: FNC's published monthly differential vs the month's average internal price (ratio of the internal
    # US$ price to NY + differential); the latest published month's ratio carries forward, earlier months use the nearest
    mr = pd.read_csv(c / "monthly_report.csv")
    mr = mr[mr.differential_c_lb.notna()]
    mon = df.resample("MS").mean()
    cal = {}
    for _, r in mr.iterrows():
        mo = pd.Timestamp(r.month + "-01")
        if mo in mon.index:
            m = mon.loc[mo]
            cal[mo] = m.usd_c_lb / (m.f1 + r.differential_c_lb)
    if cal:
        cs = pd.Series(cal).sort_index()
        ratio = cs.reindex(df.index.to_period("M").to_timestamp(), method="nearest").values
        df["ratio"] = ratio
        df["fob_prem"] = df.usd_c_lb / df.ratio - df.f1
    else:
        df["ratio"], df["fob_prem"] = float("nan"), float("nan")
    tail = df[df.index >= df.index[-1] - pd.DateOffset(years=12)]
    w = tail.resample("W-FRI").last()
    last = df.iloc[-1]
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in w.index], "net_prem": [r1(x) for x in w.net_prem],
        "fob_prem": [r1(x) for x in w.fob_prem], "usd_c_lb": [r1(x) for x in w.usd_c_lb],
        "monthly": [{"month": r.month, "differential_c_lb": r1(r.differential_c_lb)} for _, r in mr.iterrows()],
        "latest": {"date": df.index[-1].strftime("%Y-%m-%d"), "usd_c_lb": r1(last.usd_c_lb), "kc_front": r1(last.f1),
                   "net_prem": r1(last.net_prem), "fob_prem": r1(last.fob_prem),
                   "calib_months": len(cal), "fnc_diff_last": r1(mr.differential_c_lb.iloc[-1]) if len(mr) else None,
                   "fnc_diff_month": mr.month.iloc[-1] if len(mr) else None},
        "notes": {"net_prem": "FNC internal price per carga in US$ (TRM) and c/lb green, minus KC front: premium net of internal costs",
                  "fob_prem": "the same scaled by the ratio implied by FNC's latest published monthly differential: FOB-equivalent premium",
                  "history": "weekly (Friday) points, last 12 years; daily from 2003 in the CSV"}}


def csv_or_none(name):
    p = OUT / name
    return pd.read_csv(p) if p.exists() else None


QUAL = [("fine_cup_1718", r"fine"), ("good_cup_mtgb", r"good cup"), ("semi_washed", r"semi.?washed"), ("rio", r"\brio\b"),
        ("conillon", r"conil")]
LABEL = {"fine_cup_1718": "Fine cup 17/18", "good_cup_mtgb": "Good cup 3/4 MTGB", "semi_washed": "Semi-washed", "rio": "Rio",
         "conillon": "Conilon", "sul_minas_boa": "Sul de Minas, bebida boa", "cerrado_dura": "Cerrado, bebida dura",
         "mogiana_boa": "Mogiana, bebida boa", "zona_mata_rio": "Zona da Mata, rio", "conilon_t78": "Conilon tipo 7/8 (ES)",
         "conilon_t7": "Conilon tipo 7 (ES)", "good_cup_domestic": "Good cup (domestic, English desk)",
         "fine_cup_domestic": "Fine cup (domestic, English desk)"}


def _manual():
    p = D / "manual" / "brazil_export_diffs.csv"
    if not p.exists():
        return pd.DataFrame()
    m = pd.read_csv(p)
    rows = []
    for _, r in m.iterrows():
        key = next((k for k, rx in QUAL if re.search(rx, str(r.quality), re.I)), None)
        v = str(r.value).replace(",", "")
        rng = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*(?:-|to)\s*(-?\d+(?:\.\d+)?)\s*$", v)
        lo, hi = (float(rng.group(1)), float(rng.group(2))) if rng else ((float(v),) * 2 if re.match(r"^-?\d+(\.\d+)?$", v.strip()) else (None, None))
        if key is None or lo is None:
            continue
        dom = str(r.basis).startswith("domestic")
        if dom:
            key = {"fine_cup_1718": "fine_cup_domestic", "good_cup_mtgb": "good_cup_domestic"}.get(key, key)
        rows.append({"quote_date": r.quote_date, "site": "manual", "series": key, "basis": "domestic" if dom else r.basis,
                     "low": lo, "high": hi, "unit": "R$/60kg" if dom else "c/lb", "shipment": r.shipment, "ambiguous": 0})
    return pd.DataFrame(rows)


def brazil(K):
    """SAFRAS quotes by quality: FOB differentials vs ICE (English desk, about monthly) and domestic prices by region
    (Portuguese desk, 2-3 times a week) turned into US cents/lb and a basis to KC's 2nd/3rd-position average."""
    out = {}
    q = csv_or_none("safras_quotes.csv")
    q = pd.concat([x for x in (q, _manual()) if x is not None and len(x)], ignore_index=True) if (q is not None and len(q)) or len(_manual()) else None
    if q is not None and len(q):
        q["quote_date"] = pd.to_datetime(q.quote_date)
        q["mid"] = q[["low", "high"]].mean(axis=1)
        q = q.dropna(subset=["mid"]).sort_values(["quote_date", "site"])
        q = q.drop_duplicates(["quote_date", "series", "basis"], keep="first")
        px = pd.read_csv(D / "usdbrl_ptax.csv", parse_dates=["date"]).set_index("date").usdbrl.sort_index()
        k23 = K.k23.dropna().sort_index()
        dom = q[q.unit.str.startswith("R$")].copy()
        if len(dom):
            # drop misread prices: under 40% or over 250% of the series' rolling median (about a month of quotes either side)
            med = dom.groupby("series").mid.transform(lambda x: x.rolling(15, center=True, min_periods=3).median())
            bad = (dom.mid < 0.4 * med) | (dom.mid > 2.5 * med)
            if bad.any():
                print(f"brazil: dropped {int(bad.sum())} domestic quotes far from their series' median")
            dom = dom[~bad]
            dom["usdbrl"] = px.reindex(dom.quote_date, method="ffill").values
            dom["c_lb"] = dom.mid / dom.usdbrl / LB_BAG * 100
            dom["kc23"] = k23.reindex(dom.quote_date, method="ffill").values
            dom["basis_kc"] = dom.c_lb - dom.kc23
        fob = q[(q.unit == "c/lb") & (q.mid.abs() < 100)].copy()
        # publish a quality only while it is current: quoted in the last 35 days and at least 3 times in the last 90
        # (so at least monthly). Older or thinner series stay in safras_quotes.csv but are left off the page.
        now = pd.Timestamp(datetime.now(timezone.utc).date())
        def current(d):
            g = d.groupby("series").quote_date
            keep = [k for k, x in g if x.max() >= now - pd.Timedelta(days=35) and (x >= now - pd.Timedelta(days=90)).sum() >= 3]
            return d[d.series.isin(keep)], sorted(set(d.series) - set(keep))
        fob, fob_off = current(fob)
        dom, dom_off = current(dom)
        out["not_current"] = {"fob": [LABEL.get(k, k) for k in fob_off], "domestic": [LABEL.get(k, k) for k in dom_off]}
        mo = lambda d, col: (d.assign(month=d.quote_date.dt.strftime("%Y-%m")).groupby(["series", "month"])[col].mean().round(1)
                             .reset_index().rename(columns={col: "v"}))
        ser = {}
        for name, d, col in (("fob", fob, "mid"), ("domestic_brl", dom, "mid"), ("domestic_c_lb", dom, "c_lb"), ("domestic_basis", dom, "basis_kc")):
            if not len(d):
                continue
            m = mo(d, col)
            ser[name] = {s: [[r.month, r1(r.v)] for r in g.itertuples()] for s, g in m.groupby("series")}
        out["monthly"] = ser
        last = {}
        for name, d, cols in (("fob", fob, ["mid", "low", "high", "shipment", "basis"]), ("domestic", dom, ["mid", "c_lb", "basis_kc", "usdbrl"])):
            for s, g in d.groupby("series"):
                r = g.iloc[-1]
                last[f"{name}:{s}"] = {"series": s, "label": LABEL.get(s, s), "kind": name, "date": r.quote_date.strftime("%Y-%m-%d"),
                                       **{c: (r1(r[c], 3 if c == "usdbrl" else 1) if c not in ("shipment", "basis") else (None if pd.isna(r[c]) else r[c])) for c in cols}}
        out["latest"] = sorted(last.values(), key=lambda x: (x["kind"], x["series"]))
        out["labels"] = LABEL
        shown = pd.concat([fob, dom])
        out["counts"] = {"quotes": int(len(shown)), "first": shown.quote_date.min().strftime("%Y-%m-%d") if len(shown) else None,
                         "last": shown.quote_date.max().strftime("%Y-%m-%d") if len(shown) else None,
                         "ambiguous": int(q.get("ambiguous", pd.Series(dtype=float)).fillna(0).astype(int).sum())}
        out["notes"] = {"fob": "FOB differential to the ICE contract named in the report (KC for arabica, London for conilon where stated), c/lb, mid of range",
                        "domestic": "spot R$ per 60-kg bag at origin (SAFRAS), converted at BCB PTAX; basis = that price in c/lb minus KC 2nd/3rd-position average",
                        "monthly": "monthly average of the quotes in that month"}
    s = csv_or_none("brazil_stocks.csv")
    if s is not None and len(s):
        out["stocks"] = {f"{src}:{ser}": [[r.date, r1(r.m_bags, 2)] for r in g.sort_values("date").itertuples()]
                         for (src, ser), g in s.groupby(["source", "series"]) if src != "CONAB"}  # CONAB: no survey since 2020
    return out or None


def vietnam():
    out = {}
    e = csv_or_none("vietnam_exports.csv")
    # NSO publishes about the 6th of the next month, so a current series ends no more than about two months back
    if e is not None and len(e) and pd.Period(e.month.max(), "M") >= pd.Period(datetime.now(timezone.utc).strftime("%Y-%m"), "M") - 2:
        e = e.tail(72)
        out["exports"] = [{"month": r.month, "k_t": r1(r.k_t), "k_bags": r1(r.k_t / 0.06, 0), "usd_m": r1(r.usd_m),
                           "usd_t": r1(r.usd_t, 0), "basis": r.basis} for r in e.itertuples()]
        out["exports_note"] = ("NSO monthly socio-economic report, export annex: coffee, thousand tonnes (all types, green and processed "
                               "as NSO counts them) and average value in US$ per tonne. Each month is the year-to-date total less the "
                               "previous report's, so it carries NSO's revision; the latest month is the first estimate.")
    p = ROOT / "coffee" / "data" / "psd_coffee.csv"
    if p.exists():
        d = pd.read_csv(p)
        v = d[(d.Country_Code == "VM") & d.Attribute_Description.isin(["Ending Stocks", "Production", "Bean Exports", "Domestic Consumption"])]
        v = v.pivot_table(index="Market_Year", columns="Attribute_Description", values="Value").tail(12)
        out["psd"] = [{"year": int(y), **{k: r1(x, 0) for k, x in r.items()}} for y, r in v.iterrows()]
    return out or None


def main():
    K = kc()
    J = {"built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
    for name, f in (("honduras", lambda: honduras(K)), ("colombia", lambda: colombia(K)), ("brazil", lambda: brazil(K)), ("vietnam", vietnam)):
        try:
            J[name] = f()
        except Exception as e:
            print(f"{name}: {e}"); J[name] = None
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "diffs.json").write_text(json.dumps(J, separators=(",", ":"), default=str))
    for k in ("honduras", "colombia"):
        print(k, (J[k] or {}).get("latest"))


if __name__ == "__main__":
    main()
