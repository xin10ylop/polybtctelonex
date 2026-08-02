"""KALSHI TERMINAL SNIPE — the one thing on Kalshi that does work.

nix2's own signal is untradeable on Kalshi: the book is empty at the boundary
and only opens at T+120s, by which time the market has priced it (see
src/kalshi_zresponse.py). But Kalshi's contract structure creates a DIFFERENT
opportunity that Polymarket's does not.

Kalshi settles on the SIMPLE AVERAGE OF THE SIXTY SECONDS of CF Benchmarks'
index before the close, against the same average before the open. So with 60s
left the strike is fully known and only one minute of averaging remains: a
spot-vs-strike lead of 20bp is several standard deviations of what is left.
The outcome is effectively decided while the market still quotes it below
certainty.

  side  = sign( spot(T+840) - strike )   [strike = index at the window open]
  entry = take the lead side at T+840, 60s before close
  hold  = to settlement
  fee   = Kalshi quadratic taker, 0.07*p*(1-p), charged in the P&L below

Ground truth is exact and externally validated: the settlement-index file
carries the real index value at every boundary, and 40/40 sampled windows
matched Kalshi's own settled `result` from the public API.

  .venv/bin/python src/kalshi_snipe.py BTC
  .venv/bin/python src/kalshi_snipe.py ETH

CAVEAT THAT DECIDES EVERYTHING: candles carry top-of-book PRICE but no SIZE.
This shows the edge exists at the touch; it does NOT show you can fill at it.
The book files (370MB BTC / 222MB ETH) are needed to settle depth, and July is
still an untouched holdout (local spot klines currently end 2026-07-07).
"""
import polars as pl, glob, math, statistics, datetime as dt, sys
COIN=sys.argv[1]; KLD='data/processed/binance/eth_klines_1s' if COIN=='ETH' else 'data/processed/binance/klines_1s'
d=pl.concat([pl.read_parquet(f) for f in sorted(glob.glob(f'data/kalshi/{COIN}_settlement_index_*.parquet'))])
d=d.with_columns(pl.col('price').cast(pl.Float64),(pl.col('timestamp_us')//1_000_000).alias('ts'))
brti=dict(zip(d['ts'].to_list(),d['price'].to_list()))
px={}
for f in sorted(glob.glob(f'{KLD}/*.parquet')):
    day=f.split('/')[-1][:-8]
    if not ('2026-05'<=day<='2026-07'): continue
    k=pl.read_parquet(f,columns=['open_time_us','close'])
    px.update(zip((k['open_time_us']//1_000_000).to_list(),k['close'].to_list()))
c=pl.concat([pl.read_parquet(f) for f in sorted(glob.glob(f'data/kalshi/{COIN}_15m_candles_*.parquet'))])
c=c.with_columns((pl.col('timestamp_us')//1_000_000).alias('ts'))
for col in ('yes_bid_open','yes_ask_open'):
    c=c.with_columns(pl.col(col).cast(pl.Float64,strict=False))
c14=c.filter(pl.col('ts')%900==840).drop_nulls(['yes_bid_open','yes_ask_open'])
rows=[]
for ts,b,a in zip(c14['ts'].to_list(),c14['yes_bid_open'].to_list(),c14['yes_ask_open'].to_list()):
    T=ts-840; K=brti.get(T); st=brti.get(T+900); s=px.get(T+840)
    if None in (K,st,s) or not K: continue
    lead=1e4*math.log(s/K)
    if lead==0: continue
    up=lead>0; price=a if up else 1-b
    if price<=0 or price>=1: continue
    won=up==(st>K); fee=0.07*price*(1-price)
    rows.append({'d':dt.datetime.utcfromtimestamp(T).strftime('%Y-%m-%d'),'lead':abs(lead),
                 'up':up,'won':won,'price':price,'pnl':(1.0 if won else 0.0)-price-fee})
def rep(lab,rr):
    if len(rr)<30: print('  %-24s n=%d (too few)'%(lab,len(rr))); return
    p=[r['pnl'] for r in rr]; m=statistics.mean(p); sd=statistics.stdev(p)
    by={}
    for r in rr: by.setdefault(r['d'],[]).append(r['pnl'])
    dl=[statistics.mean(v) for v in by.values()]
    dtt=statistics.mean(dl)/(statistics.stdev(dl)/math.sqrt(len(dl))) if len(dl)>1 and statistics.stdev(dl)>0 else float('nan')
    print('  %-24s n=%5d  win %6.2f%%  px %.3f  EV $%+.4f  t=%+5.2f  day-t=%+5.2f'%(
        lab,len(rr),100*sum(r['won'] for r in rr)/len(rr),statistics.mean([r['price'] for r in rr]),m,
        m/(sd/math.sqrt(len(p))),dtt))
ds=sorted(set(r['d'] for r in rows)); h=len(ds)//2
TR,VA=set(ds[:h]),set(ds[h:])
print('=== KALSHI %s 15m — terminal snipe T+840, fee-inclusive ==='%COIN)
print('%d windows / %d days  (TRAIN %s..%s | VAL %s..%s)\n'%(len(rows),len(ds),ds[0],ds[h-1],ds[h],ds[-1]))
for lo in (10,20):
    print(' |lead| >= %dbp'%lo)
    rep('TRAIN',[r for r in rows if r['d'] in TR and r['lead']>=lo])
    rep('VAL',[r for r in rows if r['d'] in VA and r['lead']>=lo])
print('\n === basis check: is the edge symmetric in direction? ===')
for lo in (10,20):
    for lab,f in (('UP-leads',True),('DOWN-leads',False)):
        rep('|lead|>=%d %s'%(lo,lab),[r for r in rows if r['lead']>=lo and r['up']==f])
