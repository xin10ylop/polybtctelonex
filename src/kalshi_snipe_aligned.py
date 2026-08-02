import polars as pl, glob, math, statistics, datetime as dt, sys
COIN=sys.argv[1]; KLD='data/processed/binance/eth_klines_1s' if COIN=='ETH' else 'data/processed/binance/klines_1s'
MON={'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
def open_ts(m):
    try:
        q=m.split('-')[1]
        et=dt.datetime(2000+int(q[:2]),MON[q[2:5]],int(q[5:7]),int(q[7:9]),int(q[9:11]),
                       tzinfo=dt.timezone(dt.timedelta(hours=-4)))
        return int(et.timestamp())-900
    except Exception: return None
d=pl.concat([pl.read_parquet(f) for f in sorted(glob.glob(f'data/kalshi/{COIN}_settlement_index_*.parquet'))])
d=d.with_columns(pl.col('price').cast(pl.Float64),(pl.col('timestamp_us')//1_000_000).alias('ts'))
ref=dict(zip(d['ts'].to_list(),d['price'].to_list()))
px={}
for f in sorted(glob.glob(f'{KLD}/*.parquet')):
    day=f.split('/')[-1][:-8]
    if not ('2026-05'<=day<='2026-06'): continue
    k=pl.read_parquet(f,columns=['open_time_us','close'])
    px.update(zip((k['open_time_us']//1_000_000).to_list(),k['close'].to_list()))
c=pl.concat([pl.read_parquet(f) for f in sorted(glob.glob(f'data/kalshi/{COIN}_15m_candles_2026-0[56].parquet'))])
c=c.with_columns((pl.col('timestamp_us')//1_000_000).alias('ts'))
for col in ('yes_bid_open','yes_ask_open'):
    c=c.with_columns(pl.col(col).cast(pl.Float64,strict=False))
tmap={m:open_ts(m) for m in c['market_id'].unique().to_list()}
c=c.with_columns(pl.col('market_id').replace_strict(tmap,default=None).alias('T')).drop_nulls('T')
c=c.filter(pl.col('ts')==pl.col('T')+840).drop_nulls(['yes_bid_open','yes_ask_open'])
print(f'{COIN}: candles at T+840 with market_id alignment: {c.height:,}')
rows=[]
for T,b,a in zip(c['T'].to_list(),c['yes_bid_open'].to_list(),c['yes_ask_open'].to_list()):
    K,st,s=ref.get(T),ref.get(T+900),px.get(T+840)
    if None in (K,st,s) or not K: continue
    lead=1e4*math.log(s/K)
    if lead==0: continue
    up=lead>0; price=a if up else 1-b
    if not (0<price<1): continue
    won=up==(st>K); fee=0.07*price*(1-price)
    rows.append({'d':dt.datetime.utcfromtimestamp(T).strftime('%Y-%m-%d'),'lead':abs(lead),
                 'won':won,'price':price,'pnl':(1.0 if won else 0.0)-price-fee})
def rep(lab,rr):
    if len(rr)<30: print('  %-8s n=%d (too few)'%(lab,len(rr))); return
    p=[r['pnl'] for r in rr]; m=statistics.mean(p); sd=statistics.stdev(p)
    by={}
    for r in rr: by.setdefault(r['d'],[]).append(r['pnl'])
    dl=[statistics.mean(v) for v in by.values()]
    dtt=statistics.mean(dl)/(statistics.stdev(dl)/math.sqrt(len(dl))) if len(dl)>1 and statistics.stdev(dl)>0 else float('nan')
    print('  %-8s n=%5d  win %6.2f%%  px %.3f  EV $%+.4f  t=%+5.2f  day-t=%+5.2f'%(
        lab,len(rr),100*sum(r['won'] for r in rr)/len(rr),statistics.mean([r['price'] for r in rr]),m,
        m/(sd/math.sqrt(len(p))),dtt))
ds=sorted(set(r['d'] for r in rows)); h=len(ds)//2
TR,VA=set(ds[:h]),set(ds[h:])
print(f'{len(rows):,} tradeable windows over {len(ds)} days\n')
for lo in (10,20):
    print(' |lead| >= %dbp'%lo)
    rep('TRAIN',[r for r in rows if r['d'] in TR and r['lead']>=lo])
    rep('VAL',[r for r in rows if r['d'] in VA and r['lead']>=lo])
