import os, requests, datetime as dt, json
os.makedirs('data/probe', exist_ok=True)
H = {'User-Agent': 'Mozilla/5.0'}
out = {}
d = dt.date.today()
for k in range(0, 8):
    day = d - dt.timedelta(days=k)
    ds = day.strftime('%Y%m%d')
    for base in ('https://www.ice.com/publicdocs/futures_us_reports/coffee/coffee_cert_stock_%s.xls',
                 'https://www.theice.com/publicdocs/futures_us_reports/coffee/coffee_cert_stock_%s.xls'):
        u = base % ds
        try:
            r = requests.get(u, headers=H, timeout=30)
            out[u] = [r.status_code, len(r.content), r.headers.get('content-type')]
            if r.ok and len(r.content) > 2000:
                open(f'data/probe/coffee_cert_{ds}.xls', 'wb').write(r.content)
                break
        except Exception as e:
            out[u] = str(e)[:120]
for u in ['https://www.ice.com/report/9', 'https://www.ice.com/marketdata/reports/9']:
    try:
        r = requests.get(u, headers=H, timeout=30); out[u] = [r.status_code, len(r.content)]
        open('data/probe/report9.html', 'w').write(r.text[:200000])
    except Exception as e:
        out[u] = str(e)[:120]
json.dump(out, open('data/probe/certs_probe.json', 'w'), indent=1)
print(json.dumps(out, indent=1))
