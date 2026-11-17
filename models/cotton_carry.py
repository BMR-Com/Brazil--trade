"""Cotton spread vs full carry, one row per day: data/cotton/carry_history.csv.

Same calculation as the certs tab (assets/cotton.js: pair(), carry(), the premium table): the carry a long needs to stop the
front contract (October skipped) and redeliver against the next one = storage + financing + over-age + weight-date +
year-of-growth, against the actual next-minus-front spread.

Inputs: data/technicals/CT.json (today's closes, as the page uses), data/contracts/CT.csv (settlements for past days),
data/cotton/ice_diffs.csv (ICE grid by date), data/cotton/ice/*.csv (ICE certs files), data/cotton/ref/ice_tariffs_2026-27.csv,
data/specs/calendar.json (delivery pair; past days use the contract rule in models/contract_calendar.py).
Past days use the grid and certs files dated on or before that day (column `inputs` says which; before the first certs file
the carry is for base-grade cotton at the default storage rate, with no over-age or year-of-growth).

  python models/cotton_carry.py              # append/replace today's row
  python models/cotton_carry.py --backfill   # rebuild every day since the first stored grid
  python models/cotton_carry.py --check S F  # assert today's spread S and full carry F (¢/lb, as the page shows them)
"""
import csv, io, json, re, sys
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))
ICE = ROOT / "data" / "cotton" / "ice"
OUT = ROOT / "data" / "cotton" / "carry_history.csv"
IR, BW, ST_DEFAULT = 5.0, 500, 5.0          # financing %/yr, lb/bale, storage $/bale/month when no tariff weighting (page defaults)
MON = {c: i + 1 for i, c in enumerate("FGHJKMNQUVXZ")}
COLS = ["date", "front", "next", "front_close", "next_close", "spread", "full_carry", "pct_of_full_carry", "storage", "financing",
        "over_age", "weight_date", "year_of_growth", "storage_rate", "cert_total", "avg_premium_pts", "carry_basis", "inputs"]


def rows(text):
    return list(csv.reader(io.StringIO(text.strip())))


def ym(c):
    return int(c[3:]), MON[c[2]]


def mdiff(a, b):
    return (b[0] - a[0]) * 12 + (b[1] - a[1])


def age_sched(m):                            # ICE over-age allowance, lb/bale, by months after the month of certification
    return 0 if m < 4 else 3 * (m - 3) if m <= 10 else 21 + 4 * (m - 10) if m <= 16 else 45 + 5 * (m - 16) if m <= 22 else 75 + 6 * (m - 22)


def yog_pen(crop, yr):
    return max(0, 2 * (yr - crop - 1))


# ---------- inputs ----------
def ice_files():
    """{kind: [(date, path)]} for the ICE certs files in the repo."""
    K = {"stock": "stock_", "grade": "grade_staple_", "warehouse": "warehouse_", "strength": "strength_", "year_of_growth": "year_of_growth_"}
    out = {}
    for k, pre in K.items():
        fs = []
        for f in ICE.glob(pre + "*.csv"):
            m = re.match(re.escape(pre) + r"(\d{4}-\d{2}-\d{2})\.csv$", f.name)
            if m:
                fs.append((m.group(1), f))
        out[k] = sorted(fs)
    return out


def on_or_before(fs, d):
    x = [f for f in fs if f[0] <= d]
    return x[-1] if x else None


def grid_history():
    g = pd.read_csv(ROOT / "data" / "cotton" / "ice_diffs.csv", dtype=str)
    g["points"] = g.points.astype(int)
    cls, st = g[g.kind == "cls"], g[g.kind == "str"]
    grids = {d: {f"{r.color}|{r.leaf}|{r.staple}": r.points for r in x.itertuples()} for d, x in cls.groupby("date")}
    strength = {d: x.sort_values("staple").points.iloc[0] for d, x in st.groupby("date")}
    return grids, strength


def tariff_rates():
    R = rows((ROOT / "data" / "cotton" / "ref" / "ice_tariffs_2026-27.csv").read_text())
    h = R[0]; iC, iS = h.index("code"), h.index("storage_c_per_bale_month")
    return {r[iC]: float(r[iS]) for r in R[1:] if r[iS]}


def gk(c, l, st):
    return f"{c}|{'1 & 2' if str(l) in ('1', '2') else l}|{str(st).replace('+', '')}"


def grade_premium(text, G):
    """Average grid points of the bales in the grade/staple file (bales without a grid value left out), as the page does."""
    R = rows(text); h = [x.strip() for x in R[0]]
    sc = [(re.sub(r"(?i)staple\s*", "", x), i) for i, x in enumerate(h) if re.match(r"(?i)^(staple\s*)?3\d\+?$", x)]
    iCo = next(i for i, x in enumerate(h) if re.match(r"(?i)^color", x)); iLf = next(i for i, x in enumerate(h) if re.match(r"(?i)^leaf", x))
    n = v = 0
    for r in R[1:]:
        c, l = r[iCo].strip(), r[iLf].strip()
        if not (c.isdigit() and l.isdigit()):
            continue
        for s, i in sc:
            b = float(str(r[i]).replace(",", "") or 0)
            p = G.get(gk(c, l, s))
            if b and p is not None:
                n += b; v += b * p
    return (v / n if n else None), n


def strength_share(text):
    R = rows(text); h = R[0]
    rr = [r for r in R[1:] if r and r[0].strip() and not re.match(r"(?i)^totals?:?$", r[0].strip())]
    cols = [(x, i) for i, x in enumerate(h) if i > 0 and "total" not in x.lower()]
    tc = [sum(float(str(r[i]).replace(",", "") or 0) for r in rr) for _, i in cols]
    T = sum(tc); lo = next((k for k, (x, _) in enumerate(cols) if x.strip().startswith("25")), None)
    return (tc[lo] / T if T and lo is not None else 0.0)


def yog_crops(text):
    R = rows(text); h = [x.lower() for x in R[0]]
    iY = next(i for i, x in enumerate(h) if re.search(r"crop|year", x)); iB = next(i for i, x in enumerate(h) if re.search(r"receipt|bales", x))
    return [(int(r[iY]), float(str(r[iB]).replace(",", "") or 0)) for r in R[1:] if re.fullmatch(r"\d{4}", r[iY].strip())]


def wh_total(path):
    """Total bales in a warehouse report: sum of the last field of every row (same naive split as the page)."""
    t = 0.0
    for line in path.read_text().strip().splitlines()[1:]:
        try:
            t += float(line.split(",")[-1] or 0)
        except ValueError:
            pass
    return t


def wh_storage(text, rate):
    R = rows(text); h = [x.lower() for x in R[0]]
    jC = next(i for i, x in enumerate(h) if re.search(r"number|code", x)); jB = next(i for i, x in enumerate(h) if re.search(r"receipt|bales|stock", x))
    n = v = 0
    for r in R[1:]:
        b = float(r[jB] or 0) if r[jB].strip() else 0; c = rate.get(r[jC])
        if b and c:
            n += b; v += b * c
    return v / n / 100 if n else None


def cohorts(hist):
    """Certification-month cohorts from the weekly warehouse totals: increases are new certs dated a week before the report,
    decreases come out of the oldest cohort first."""
    co, prev = [], 0.0
    for d, tot in sorted(hist):
        x = date.fromisoformat(d) - timedelta(days=7)
        if tot > prev:
            co.append([(x.year, x.month), tot - prev])
        else:
            out = prev - tot
            for c in co:
                t = min(c[1], out); c[1] -= t; out -= t
                if not out:
                    break
        prev = tot
    return [c for c in co if c[1] > 0]


# ---------- delivery pair ----------
def pair_today(cal, px, today):
    C = [c for c in cal["markets"]["CT"]["contracts"] if not c["contract"].startswith("CTV")]
    i = next((k for k, c in enumerate(C) if c["ltd"] >= today), None)
    if i is None or i + 1 >= len(C):
        return None
    return C[i]["contract"], C[i + 1]["contract"]


def ltd_rule():
    from contract_calendar import MKT
    rule = MKT["CT"][1]
    cache = {}
    def ltd(code):
        if code not in cache:
            y, m = ym(code)
            cache[code] = str(rule(pd.Period(year=y, month=m, freq="M"))["ltd"].date())
        return cache[code]
    return ltd


def pair_on(day, codes, ltd):
    C = sorted((c for c in codes if c[2] in "HKNZ"), key=ym)
    i = next((k for k, c in enumerate(C) if ltd(c) >= day), None)
    return (C[i], C[i + 1]) if i is not None and i + 1 < len(C) else None


# ---------- the calculation ----------
def carry_row(day, f, n, F, N, files, grids, strength, rates, src="settlements (data/contracts/CT.csv)"):
    F, N = float(F), float(N)
    gd = max((d for d in grids if d <= day), default=None)
    G = grids[gd] if gd else {}
    gr, wh, sr, yg = (on_or_before(files[k], day) for k in ("grade", "warehouse", "strength", "year_of_growth"))
    used = [f"prices: {src}", f"grid {gd}"]
    prem, bales = 0.0, None
    if gr:
        w0, bales = grade_premium(gr[1].read_text(), G)
        sp = 0.0
        if sr:
            sd = max((d for d in strength if d <= day), default=None)
            sp = strength_share(sr[1].read_text()) * (strength[sd] if sd else 0)
            used.append(f"strength {sr[0]}")
        fq_y = ym(f)[0]
        Y = yog_crops(yg[1].read_text()) if yg else []
        YT = sum(b for _, b in Y) or 1
        yog_front = -sum(b * yog_pen(c, fq_y) for c, b in Y) / YT * 100        # pts; 0 when the front is free of the penalty
        prem = float((w0 or 0) + sp + yog_front)
        used.append(f"grade {gr[0]}")
    st = (wh_storage(wh[1].read_text(), rates) if wh else None) or ST_DEFAULT
    if wh:
        used.append(f"warehouse {wh[0]}")
    fq, nq = ym(f), ym(n)
    months = mdiff(fq, nq)
    spread = N - F
    inv, invN = F + prem / 100, N + prem / 100
    storage = st * months / BW * 100
    interest = inv * IR / 100 * months / 12
    hist = [(d, wh_total(p)) for d, p in files["warehouse"] if d <= day]
    co = cohorts(hist); T = sum(c[1] for c in co) or 1
    ageF = sum(c[1] * age_sched(mdiff(c[0], fq)) for c in co) / T
    ageN = sum(c[1] * age_sched(mdiff(c[0], nq)) for c in co) / T
    age = (ageN - ageF) / BW * invN
    wda = 0.5 * months / BW * invN
    Y = yog_crops(yg[1].read_text()) if yg else []
    YT = sum(b for _, b in Y) or 1
    yog = sum(b * (yog_pen(c, nq[0]) - yog_pen(c, fq[0])) for c, b in Y) / YT
    tot = storage + interest + age + wda + yog
    cert_total = wh_total(wh[1]) if wh else None
    if not gr:
        used.append("no certs file on or before this day: base grade, default storage")
    return {"date": day, "front": f, "next": n, "front_close": round(F, 2), "next_close": round(N, 2), "spread": round(spread, 2),
            "full_carry": round(tot, 2), "pct_of_full_carry": round(spread / tot * 100, 1) if tot else None,
            "storage": round(storage, 2), "financing": round(interest, 2), "over_age": round(age, 2), "weight_date": round(wda, 2),
            "year_of_growth": round(yog, 2), "storage_rate": round(st, 2), "cert_total": int(cert_total) if cert_total is not None else None,
            "avg_premium_pts": round(prem, 0) if gr else None, "carry_basis": "certs on board" if gr else "base grade", "inputs": "; ".join(used)}


def today_row():
    cal = json.loads((ROOT / "data" / "specs" / "calendar.json").read_text())
    T = json.loads((ROOT / "data" / "technicals" / "CT.json").read_text())
    px = {s["ticker"]: (s["bars"][-1][0], s["bars"][-1][4]) for s in T["series"]}
    today = date.today().isoformat()
    p = pair_today(cal, px, today)
    if not p or p[0] not in px or p[1] not in px:
        print("no delivery pair priced"); return None
    f, n = p
    day = max(px[f][0], px[n][0])
    grids, strength = grid_history()
    return carry_row(day, f, n, px[f][1], px[n][1], ice_files(), grids, strength, tariff_rates(), src="latest bar in data/technicals/CT.json, as the page")


def backfill():
    c = pd.read_csv(ROOT / "data" / "contracts" / "CT.csv", dtype={"date": str})
    grids, strength = grid_history()
    start = min(grids)
    c = c[c.date >= start]
    px = {(r.contract, r.date): r.close for r in c.itertuples()}
    ltd = ltd_rule(); files = ice_files(); rates = tariff_rates()
    out = []
    for day, g in c.groupby("date"):
        p = pair_on(day, set(g.contract), ltd)
        if not p or (p[0], day) not in px or (p[1], day) not in px:
            continue
        out.append(carry_row(day, p[0], p[1], px[(p[0], day)], px[(p[1], day)], files, grids, strength, rates))
    return out


def write(new):
    old = pd.read_csv(OUT, dtype=str) if OUT.exists() else pd.DataFrame(columns=COLS)
    df = pd.DataFrame(new, columns=COLS)
    df["cert_total"] = pd.to_numeric(df.cert_total, errors="coerce").astype("Int64")
    df = df.astype(str).replace({"None": "", "<NA>": "", "nan": ""})
    allr = pd.concat([old, df]).drop_duplicates("date", keep="last").sort_values("date")
    allr[COLS].to_csv(OUT, index=False)
    return allr


def main():
    a = sys.argv[1:]
    rows_ = backfill() if "--backfill" in a else []
    r = today_row()
    if r:
        rows_.append(r)
    allr = write(rows_)
    print(f"{len(allr)} rows in {OUT.relative_to(ROOT)}; latest", r)
    if "--check" in a:
        i = a.index("--check"); S, F = float(a[i + 1]), float(a[i + 2])
        assert r and abs(r["spread"] - S) < 0.006 and abs(r["full_carry"] - F) < 0.006, f"page spread {S} carry {F} vs model {r}"
        print("check ok: matches the page")


if __name__ == "__main__":
    main()
