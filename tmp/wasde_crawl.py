import requests, zipfile, io, os, pandas as pd
os.makedirs('wout',exist_ok=True)
z=requests.get('https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip',timeout=300,headers={'User-Agent':'Mozilla/5.0'}).content
zf=zipfile.ZipFile(io.BytesIO(z)); d=pd.read_csv(zf.open(zf.namelist()[0]))
print(sorted(x for x in d.Commodity_Description.unique() if 'oy' in x or 'heat' in x or 'otton' in x or 'orn' in x))
d=d[(d.Country_Name=='United States')&(d.Commodity_Description.str.contains('Soybean|Cotton|Corn|Wheat'))]
d.to_csv('wout/psd_us.csv.gz',index=False); print(len(d))
