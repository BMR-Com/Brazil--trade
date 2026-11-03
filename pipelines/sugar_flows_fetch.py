"""Public sugar flow data:
  1. SECEX weekly products file (MDIC) -> month-to-date Brazil exports of 'Açúcares e melaços' (tonnes, daily average,
     working days), snapshotted every run into data/sugar/secex_weekly.csv (MDIC only publishes the current month, so
     history builds up from these snapshots).
  2. UN Comtrade public preview -> China monthly imports of HS 1701 from the world and from Brazil
     into data/sugar/china_imports.csv (China customs data reach Comtrade with a lag of one to three months).
"""
import io, json, os, sys, time
from datetime import date
import pandas as pd, requests, urllib3
urllib3.disable_warnings()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'sugar')
H = {'User-Agent': 'Mozilla/5.0 (BMR-Com research)'}
MESES = {'Jan': 1, 'Fev': 2, 'Mar': 3, 'Abr': 4, 'Mai': 5, 'Jun': 6, 'Jul': 7, 'Ago': 8, 'Set': 9, 'Out': 10, 'Nov': 11, 'Dez': 12}


def secex_weekly():
    for url in ('https://balanca.economia.gov.br/balanca/semanal/Setores_Produtos.xlsx',
                'https://balanca.mdic.gov.br/balanca/semanal/Setores_Produtos.xlsx'):
        try:
            r = requests.get(url, headers=H, timeout=90, verify=False)
            if r.ok and len(r.content) > 5000:
                break
        except Exception as e:
            print('secex weekly', url, e)
    else:
        return
    d = pd.read_excel(io.BytesIO(r.content), sheet_name='EXP', header=None)
    title = str(d.iloc[3, 0]).replace('\n', ' ')
    lab = str(d.iloc[6, 1])                       # e.g. 'Out/2026'
    mon, yr = MESES[lab.split('/')[0]], int(lab.split('/')[1])
    row = d[d[0].astype(str).str.strip().str.lower() == 'açúcares e melaços'].iloc[0]
    t, t_ly, avg, avg_ly = float(row[5]), float(row[6]), float(row[7]), float(row[8])
    days = round(t / avg) if avg else None
    days_ly = round(t_ly / avg_ly) if avg_ly else None
    rec = {'asof': date.today().isoformat(), 'month': f'{yr}-{mon:02d}', 'title': title[:160], 'mtd_t': t, 'days': days,
           'avg_t_day': avg, 'ly_month_t': t_ly, 'ly_days': days_ly, 'ly_avg_t_day': avg_ly, 'usd_t': float(row[9]) if pd.notna(row[9]) else None}
    p = os.path.join(OUT, 'secex_weekly.csv')
    old = pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()
    new = pd.concat([old, pd.DataFrame([rec])]).drop_duplicates(['month', 'days'], keep='last')
    new.to_csv(p, index=False)
    print('secex weekly', rec)


def comtrade_china(months=60):
    p = os.path.join(OUT, 'china_imports.csv')
    old = pd.read_csv(p, dtype={'period': str}) if os.path.exists(p) else pd.DataFrame(columns=['period', 'partner', 'kg', 'usd'])
    have = set(old.period) if len(old) else set()
    today = pd.Period(date.today(), 'M')
    want = [str(today - k).replace('-', '') for k in range(1, months + 1)]
    recent = set(want[:4])                         # refetch the last 4 months (late data, revisions)
    rows = []
    for per in want:
        if per in have and per not in recent:
            continue
        for attempt in range(3):
            try:
                r = requests.get('https://comtradeapi.un.org/public/v1/preview/C/M/HS',
                                 params={'reporterCode': 156, 'period': per, 'cmdCode': '1701', 'flowCode': 'M'}, headers=H, timeout=60)
                if r.status_code == 429:
                    time.sleep(5); continue
                js = r.json().get('data') or []
                for x in js:
                    if x.get('partnerCode') in (0, 76):
                        rows.append({'period': per, 'partner': 'World' if x['partnerCode'] == 0 else 'Brazil',
                                     'kg': x.get('netWgt') or x.get('qty'), 'usd': x.get('primaryValue')})
                break
            except Exception as e:
                print('comtrade', per, e); time.sleep(3)
        time.sleep(1.5)
    if rows:
        new = pd.DataFrame(rows)
        old = old[~old.period.isin(new.period)]
        out = pd.concat([old, new]).sort_values(['period', 'partner'])
        out.to_csv(p, index=False)
        print('comtrade china rows', len(new), 'periods', new.period.nunique())


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    jobs = [secex_weekly]
    if not os.path.exists(os.path.join(OUT, 'china_imports.csv')):
        jobs.append(comtrade_china)                # history only: Comtrade has no China monthly data after Dec 2024
    for f in jobs:
        try:
            f()
        except Exception as e:
            print(f.__name__, 'failed', e)
