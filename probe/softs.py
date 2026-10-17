import pandas as pd, time
from tvDatafeed import TvDatafeed, Interval
tv=TvDatafeed(); out=[]; log=[]
for root,months in [('KC','HKNUZ'),('SB','HKNV')]:
  for y in range(2005,2028):
    for m in months:
        s=f'{root}{m}{y}'
        for k in range(3):
            try:
                d=tv.get_hist(symbol=s,exchange='ICEUS',interval=Interval.in_daily,n_bars=900)
                if d is not None and len(d):
                    d=d.reset_index(); d['contract']=s; out.append(d[['datetime','contract','open','high','low','close','volume']]); log.append(f'{s} {len(d)}'); break
            except Exception as e: log.append(f'{s} err {e}')
            time.sleep(2)
        else: log.append(f'{s} none')
        time.sleep(0.5)
pd.concat(out).to_csv('probe/softs_contracts.csv',index=False)
open('probe/out_softs.txt','w').write('\n'.join(log))
