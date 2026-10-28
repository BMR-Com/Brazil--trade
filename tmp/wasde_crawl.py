import re, time, json, requests, zipfile, io, os, pandas as pd
S=requests.Session(); S.headers['User-Agent']='Mozilla/5.0 (research crawler)'
os.makedirs('wout/html',exist_ok=True); links=[]
for p in range(1,80):
    url=f'https://usda.library.cornell.edu/concern/publications/3t945q76s?locale=en&page={p}'
    for a in range(4):
        try: r=S.get(url,timeout=60); break
        except Exception as e: print('retry',p,e); time.sleep(5)
    h=r.text
    if p in (1,2,30,40): open(f'wout/html/page{p}.html','w').write(h)
    files=re.findall(r'href="(https://downloads\.usda\.library\.cornell\.edu/usda-esmis/files/[^"]+)"',h)
    dates=re.findall(r'(\w+ \d{1,2}, \d{4})',h)
    print(p,len(files),dates[:2],flush=True)
    # pair each file link with the nearest preceding date text
    for m in re.finditer(r'href="(https://downloads\.usda\.library\.cornell\.edu/usda-esmis/files/[^"]+)"',h):
        pre=h[max(0,m.start()-4000):m.start()]; ds=re.findall(r'([A-Z][a-z]+ \d{1,2}, \d{4})',pre)
        links.append(dict(page=p,url=m.group(1),date=ds[-1] if ds else None))
    if not files: break
    time.sleep(1)
pd.DataFrame(links).drop_duplicates('url').to_csv('wout/esmis_links.csv',index=False); print('links',len(links))
# PSD all data (finals)
try:
    z=S.get('https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip',timeout=300).content
    zf=zipfile.ZipFile(io.BytesIO(z)); n=zf.namelist()[0]; d=pd.read_csv(zf.open(n))
    d=d[(d.Country_Name=='United States')&(d.Commodity_Description.isin(['Cotton','Corn','Soybeans','Wheat']))]
    d.to_csv('wout/psd_us.csv.gz',index=False); print('psd rows',len(d))
except Exception as e: print('psd failed',e)
