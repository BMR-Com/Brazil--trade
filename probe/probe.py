import re, io, os, time, traceback, zipfile
import requests
import pandas as pd

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
S = requests.Session(); S.headers.update(H)
OUT = "probe/seed"; os.makedirs(OUT + "/mapa", exist_ok=True)
B = "https://www.gov.br/agricultura/pt-br/assuntos/sustentabilidade/agroenergia/acompanhamento-da-producao-sucroalcooleira/"

# MAPA fortnightly files
for safra in ["2026-2027", "2025-2026", "2024-2025", "2023-2024", "2022-2023", "2021-2022", "2020-2021", "2019-2020", "2018-2019"]:
    try:
        t = S.get(B + safra, timeout=60).text
        links = [l for l in re.findall(r'href="([^"]+\.xlsx?)"', t, re.I) if "basedeconhecimento" not in l]
        print(safra, len(links))
        for u in links:
            fn = OUT + "/mapa/" + safra + "__" + u.rsplit("/", 1)[1]
            if os.path.exists(fn):
                continue
            r = S.get(u, timeout=120)
            if r.ok:
                open(fn, "wb").write(r.content)
            else:
                print("fail", u, r.status_code)
    except Exception:
        traceback.print_exc()

# PSD sugar
try:
    r = S.get("https://apps.fas.usda.gov/psdonline/downloads/psd_sugar_csv.zip", timeout=120)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    d = pd.read_csv(io.BytesIO(z.read("psd_sugar.csv")), dtype={"Commodity_Code": str})
    d.to_csv(OUT + "/psd_sugar.csv.gz", index=False, compression="gzip")
    print("psd", d.shape)
except Exception:
    traceback.print_exc()

# ANP weekly state pump prices: hydrous ethanol and gasoline
try:
    r = S.get("https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/semanal/semanal-estados-desde-2013.xlsx", timeout=180)
    d = pd.read_excel(io.BytesIO(r.content), header=None)
    hdr = d.index[d.iloc[:, 0].astype(str).str.contains("DATA INICIAL", na=False)][0]
    d.columns = [str(c).strip() for c in d.iloc[hdr]]
    d = d.iloc[hdr + 1:]
    print(d.columns.tolist())
    d = d[d["PRODUTO"].isin(["ETANOL HIDRATADO", "GASOLINA COMUM"])]
    d.to_csv(OUT + "/anp_states.csv.gz", index=False, compression="gzip")
    print("anp", d.shape)
except Exception:
    traceback.print_exc()

# TradingView history
try:
    from tvDatafeed import TvDatafeed, Interval
    tv = TvDatafeed()
    def hist(sym, ex, n=5000):
        for k in range(3):
            try:
                d = tv.get_hist(symbol=sym, exchange=ex, interval=Interval.in_daily, n_bars=n)
                if d is not None and len(d):
                    d = d.reset_index()[["datetime", "open", "high", "low", "close", "volume"]]
                    d["datetime"] = d["datetime"].dt.date
                    return d.rename(columns={"datetime": "date"})
            except Exception as e:
                print("err", sym, e)
            time.sleep(2)
        return None
    rows = []
    for sym, ex in [("W1!", "ICEEUR"), ("W2!", "ICEEUR"), ("SB1!", "ICEUS"), ("SB2!", "ICEUS"), ("ETH1!", "BMFBOVESPA"),
                    ("ETH2!", "BMFBOVESPA"), ("USDBRL", "FX_IDC"), ("BRN1!", "ICEEUR"), ("RB1!", "NYMEX"), ("CU1!", "NYMEX")]:
        d = hist(sym, ex)
        print("TV", sym, None if d is None else len(d))
        if d is not None:
            d.insert(0, "symbol", f"{ex}:{sym}"); rows.append(d)
    pd.concat(rows).to_csv(OUT + "/tv_cont.csv.gz", index=False, compression="gzip")
    rows = []
    for y in range(2010, 2028):
        for w, r_, ry in [("H", "H", y), ("K", "K", y), ("Q", "N", y), ("V", "V", y), ("Z", "H", y + 1)]:
            for sym, ex in [(f"W{w}{y}", "ICEEUR"), (f"SB{r_}{ry}", "ICEUS")]:
                if any(sym == x for x in [r["symbol"].iloc[0].split(":")[1] for r in rows]):
                    continue
                d = hist(sym, ex, 900)
                if d is not None:
                    d.insert(0, "symbol", sym); rows.append(d)
                else:
                    print("miss", sym)
    pd.concat(rows).to_csv(OUT + "/tv_contracts.csv.gz", index=False, compression="gzip")
    print("contracts", len(rows))
except Exception:
    traceback.print_exc()
