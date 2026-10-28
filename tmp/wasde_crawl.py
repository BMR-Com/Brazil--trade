import re, time, os, requests, pandas as pd
from urllib.parse import urljoin
S=requests.Session(); S.headers['User-Agent']='Mozilla/5.0 (research crawler)'
os.makedirs('wout/txt',exist_ok=True)
r=S.get('https://usda.library.cornell.edu/concern/publications/3t945q76s?locale=en',timeout=60); base=r.url.split('?')[0]; print('base',base)
rows=[]; seen=set()
for p in range(0,120):
    for a in range(4):
        try: h=S.get(base,params={'page':p},timeout=60).text; break
        except Exception as e: print('retry',p,e); time.sleep(5)
    tr=re.split(r'<tr', h); new=0
    for t in tr:
        dt=re.search(r'datetime="(\d{4}-\d{2}-\d{2})',t)
        for f in re.findall(r'href="(/sites/default/release-files/[^"]+)"',t):
            u=urljoin(base,f)
            if u in seen: continue
            seen.add(u); new+=1; rows.append(dict(date=dt.group(1) if dt else None,url=u))
    print(p,new,flush=True)
    if new==0 and p>0: break
    time.sleep(0.5)
L=pd.DataFrame(rows); L.to_csv('wout/esmis_links.csv',index=False); print('links',len(L))
L['d']=pd.to_datetime(L.date,errors='coerce'); L['ext']=L.url.str.extract(r'\.(\w+)$')[0]
sel=L[(L.d.dt.year.between(2000,2008))&(L.d.dt.month.between(4,10))]
for (d),g in sel.groupby('date'):
    pick=g[g.ext=='txt']; pick=pick if len(pick) else g[g.ext=='pdf']
    for u in pick.url.head(1):
        try:
            c=S.get(u,timeout=120).content; fn=f"wout/txt/{d}_{os.path.basename(u)}"; open(fn,'wb').write(c); print('got',fn,len(c))
        except Exception as e: print('fail',u,e)
