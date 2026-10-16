import re, io, traceback
import requests
import pandas as pd

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
S = requests.Session(); S.headers.update(H)
B = "https://www.gov.br/agricultura/pt-br/assuntos/sustentabilidade/agroenergia/acompanhamento-da-producao-sucroalcooleira/"

for safra in ["2026-2027", "2025-2026", "2024-2025", "2018-2019"]:
    try:
        t = S.get(B + safra, timeout=60).text
        links = re.findall(r'href="([^"]+\.xlsx?)"', t, re.I)
        print("\n####", safra, len(links), links[:3], links[-2:])
        if safra in ("2026-2027", "2025-2026"):
            u = links[-1] if safra == "2026-2027" else links[len(links)//2]
            # choose the newest-looking for 2026/27
            r = S.get(u, timeout=120)
            print("GET", u, r.status_code, len(r.content))
            x = pd.ExcelFile(io.BytesIO(r.content))
            print("sheets", x.sheet_names)
            for sh in x.sheet_names[:6]:
                d = x.parse(sh, header=None)
                print(f"\n== sheet {sh} shape {d.shape}")
                with pd.option_context("display.width", 250, "display.max_columns", 30):
                    print(d.head(45).to_string()[:7000])
                    print("...")
                    print(d.tail(8).to_string()[:2500])
    except Exception:
        traceback.print_exc()
