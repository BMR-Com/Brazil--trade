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
    return df, bad

if __name__ == "__main__":
    import sys
    df, bad = build(sys.argv[1])
    print(df.shape, "bad:", len(bad), bad[:10])
    cs = df[(df.region == "Centro-Sul") & (df.uf == "TOTAL")].drop_duplicates(["safra", "end"], keep="last").sort_values("end")
    print(cs[["safra", "start", "end", "cane_t", "sugar_t", "ethanol_m3", "hyd_stock", "file"]].to_string())
