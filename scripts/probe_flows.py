"""Temporary probe: SECEX weekly products file and UN Comtrade China sugar imports reachable from runners?"""
import json, os, requests
os.makedirs('data/probe', exist_ok=True)
H = {'User-Agent': 'Mozilla/5.0'}
out = {}
for name, url in [('secex_weekly', 'https://balanca.economia.gov.br/balanca/semanal/Setores_Produtos.xlsx'),
                  ('secex_weekly_alt', 'https://balanca.mdic.gov.br/balanca/semanal/Setores_Produtos.xlsx')]:
    try:
        r = requests.get(url, headers=H, timeout=60, verify=False)
        out[name] = [r.status_code, len(r.content), r.headers.get('content-type')]
        if r.ok and len(r.content) > 5000:
            open(f'data/probe/{name}.xlsx', 'wb').write(r.content)
    except Exception as e:
        out[name] = str(e)[:200]
periods = ','.join(f'{y}{m:02d}' for y in (2025, 2026) for m in range(1, 13))
for name, url in [('comtrade_cn', f'https://comtradeapi.un.org/public/v1/preview/C/M/HS?reporterCode=156&period={periods}&cmdCode=1701&flowCode=M'),
                  ('comtrade_cn_2024', 'https://comtradeapi.un.org/public/v1/preview/C/M/HS?reporterCode=156&period=' + ','.join(f'2024{m:02d}' for m in range(1, 13)) + '&cmdCode=1701&flowCode=M')]:
    try:
        r = requests.get(url, headers=H, timeout=60)
        out[name] = [r.status_code, len(r.content)]
        open(f'data/probe/{name}.json', 'w').write(r.text[:400000])
    except Exception as e:
        out[name] = str(e)[:200]
json.dump(out, open('data/probe/flows_probe.json', 'w'), indent=1)
print(out)
