"""Parse MAPA 'Acompanhamento da produção sucroalcooleira' fortnightly spreadsheets (cumulative volumes by region/state)."""
import re, glob, os
import pandas as pd

COLS = {"cane_t": 1, "sugar_t": 2, "ethanol_m3": 5, "anh_prod": 6, "anh_distrib": 8, "anh_export": 9, "anh_stock": 11,
        "hyd_prod": 13, "hyd_distrib": 15, "hyd_export": 16, "hyd_stock": 18}

def _num(v):
    try:
        return float(str(v).replace(".", "").replace(",", ".")) if isinstance(v, str) else float(v)
    except Exception:
        return float("nan")

def parse(path):
    try:
        d = pd.read_excel(path, header=None)
    except Exception as e:
        return [], f"read error {e}"
    out, err = [], None
    for i in range(len(d)):
        row = [str(v) for v in d.iloc[i].tolist()]
        joined = " ".join(row)
        m = re.search(r"Região:\s*([\w\- ]+?)\s{0,}(?:nan|$)", joined)
        if not m or "Safra" not in joined:
            continue
        region = m.group(1).strip()
        safra = re.search(r"Safra:\s*(\d{4}/\d{4})", joined)
        ini = re.search(r"Período inicial:\s*(\d{2}/\d{2}/\d{4})", joined)
        fin = re.search(r"Período final:\s*(\d{2}/\d{2}/\d{4})", joined)
        # header sanity: column 1 'PRODUÇÃO TOTAL'/'Cana', col 13 'HIDRATADO'
        hdr = " ".join(str(v) for v in d.iloc[i + 1:i + 4].values.ravel())
        if "Cana" not in hdr or "HIDRATADO" not in str(d.iat[i + 1, 13]).upper():
            err = f"unexpected header at row {i}"
            continue
        j = i + 4
        while j < len(d) and str(d.iat[j, 0]).strip() not in ("Tot.", "Tot"):
            uf = str(d.iat[j, 0]).strip()
            if len(uf) == 2:
                rec = {"region": region, "uf": uf}
                rec.update({k: _num(d.iat[j, c]) for k, c in COLS.items()})
                out.append(rec)
            j += 1
        if j < len(d):
            rec = {"region": region, "uf": "TOTAL"}
            rec.update({k: _num(d.iat[j, c]) for k, c in COLS.items()})
            out.append(rec)
        for r in out:
            r.setdefault("safra", safra.group(1) if safra else None)
            r.setdefault("start", ini.group(1) if ini else None)
            r.setdefault("end", fin.group(1) if fin else None)
    return out, err

NUM = ["cane_t", "sugar_t", "ethanol_m3", "anh_prod", "anh_distrib", "anh_export", "anh_stock",
       "hyd_prod", "hyd_distrib", "hyd_export", "hyd_stock"]


def fill_totals(df):
    """A region's 'Tot.' row sometimes fails to parse (blank cell in MAPA's sheet): rebuild it from the states.
    Only cells that are missing are filled; a parsed total is kept as published."""
    if df is None or not len(df):
        return df
    df = df.copy()
    keys = ["region", "safra", "end"]
    st = df[df.uf != "TOTAL"].groupby(keys)[NUM].sum(min_count=1)
    tot = df.uf == "TOTAL"
    idx = pd.MultiIndex.from_frame(df.loc[tot, keys])
    for c in NUM:
        if c in df:
            fill = st[c].reindex(idx).values
            cur = df.loc[tot, c].values
            df.loc[tot, c] = [f if pd.isna(v) else v for v, f in zip(cur, fill)]
    return df


def cs_clean(df):
    """Centre-South TOTAL rows, one per season fortnight, with any missing interior fortnight filled by linear
    interpolation of the cumulative figures (column 'interp' = True). MAPA skipped one release (2022/23, 15 Nov)."""
    df = fill_totals(df)
    cs = df[(df.region == "Centro-Sul") & (df.uf == "TOTAL")].copy()
    cs = cs.drop_duplicates(["safra", "end"], keep="last").sort_values("end")
    cs["interp"] = False
    out = []
    for sf, g in cs.groupby("safra"):
        g = g.set_index("end").sort_index()
        a, b = g.index.min(), g.index.max()
        ends, d = [], a
        while d <= b:
            ends.append(d)
            d = pd.Timestamp(d.year, d.month, 15) if d.day < 15 else (pd.Timestamp(d.year, d.month, 1) + pd.offsets.MonthEnd(0))
            if d <= ends[-1]:
                nx = ends[-1] + pd.Timedelta(days=1)
                d = pd.Timestamp(nx.year, nx.month, 15)
        full = g.reindex(sorted(set(ends) | set(g.index)))
        miss = full.cane_t.isna()
        if miss.any():
            num = [c for c in NUM if c in full]
            full[num] = full[num].interpolate(method="time")
            for c in ("region", "uf", "safra", "start"):
                full[c] = full[c].ffill()
            full.loc[miss, "interp"] = True
        out.append(full.reset_index().rename(columns={"index": "end"}))
    return pd.concat(out, ignore_index=True) if out else cs


def build(folder):
    rows, bad = [], []
    for f in sorted(glob.glob(os.path.join(folder, "*.xls*"))):
        r, err = parse(f)
        if not r:
            bad.append((os.path.basename(f), err)); continue
        for x in r:
            x["file"] = os.path.basename(f)
        rows += r
    df = pd.DataFrame(rows)
    if len(df):
        df["end"] = pd.to_datetime(df["end"], dayfirst=True)
        df["start"] = pd.to_datetime(df["start"], dayfirst=True)
        df = fill_totals(df)
    return df, bad

if __name__ == "__main__":
    import sys
    df, bad = build(sys.argv[1])
    print(df.shape, "bad:", len(bad), bad[:10])
    cs = df[(df.region == "Centro-Sul") & (df.uf == "TOTAL")].drop_duplicates(["safra", "end"], keep="last").sort_values("end")
    print(cs[["safra", "start", "end", "cane_t", "sugar_t", "ethanol_m3", "hyd_stock", "file"]].to_string())
