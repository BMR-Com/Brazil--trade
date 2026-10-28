import time, pandas as pd
from tvDatafeed import TvDatafeed, Interval
tv=TvDatafeed(); out=[]
for root,months in [('KC','HKNUZ'),('CC','HKNUZ')]:
    for y in range(2007,2028):
        for m in months:
            sym=f'{root}{m}{y}'; d=None
            for a in range(3):
                try:
                    d=tv.get_hist(symbol=sym,exchange='ICEUS',interval=Interval.in_daily,n_bars=900)
                    if d is not None and len(d): break
                except Exception as e: print('err',sym,e)
                time.sleep(2)
            if d is None or not len(d): print('MISSING',sym); continue
            d=d.reset_index(); d['date']=d['datetime'].dt.date; d['symbol']=sym
            out.append(d[['symbol','date','close','volume']]); print(sym,len(d),d.date.min(),d.date.max(),flush=True)
pd.concat(out).to_csv('kc_cc_contracts.csv',index=False)
