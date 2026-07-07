"""Stop-loss exit simulator (user request).
Strategy: taker-buy at entry offset in a price band, direction from a signal,
rest a maker sell at +delta. If it does NOT fill within `stop_s` seconds, CUT:
taker-sell at the book bid as-of the stop time (pay spread+fee, cap the loss).
Compared against no-stop (hold to expiry). Everything in position-token space;
date-correct entry+exit fees. Train+val only (loader guard blocks holdout).
"""
import sys, datetime as dt, glob
import numpy as np, polars as pl
sys.path.insert(0,"src")
import loader, fees, windows as W

LAT=250_000
ENTRY_OFFS=[-10, 20, 60]
BANDS=[(0.47,0.53)]              # near 50c (fine per-cent already shown flat)
DELTAS=[3,5]
STOPS=[5,10,20,None]            # None = hold to expiry
DIRS=["blind_up","blind_down","binance1m","m15"]

def day_arrays(date):
    try:
        t=loader.load_daily("5m","trades",[date]).collect().sort("wts","local_timestamp_us")
        b=loader.load_daily("5m","bookcurves",[date]).collect().sort("wts","local_timestamp_us")
        f=pl.read_parquet(f"results/features/5m/{date}.parquet")
        x=pl.read_parquet(f"results/xtf/5m/{date}.parquet")
    except (FileNotFoundError, loader.HoldoutViolation):
        return None
    return t,b,f,x

def simulate(date, rows):
    got=day_arrays(date)
    if got is None: return
    t,b,f,x=got
    d0=int(dt.datetime.fromisoformat(date+"T00:00:00+00:00").timestamp())
    meta=W.market_meta("5m",d0,d0+86400).sort("wts")
    if meta.is_empty(): return
    res={int(w):(1.0 if r=="0" else 0.0 if r=="1" else np.nan) for w,r in zip(meta["wts"],meta["result_id"])}
    rate=fees.params(date,"5m")[0]
    tw=t["wts"].to_numpy(); tts=t["local_timestamp_us"].to_numpy(); tpx=t["price"].to_numpy().astype(float)
    bw=b["wts"].to_numpy(); bts=b["local_timestamp_us"].to_numpy()
    b_buy=b["buy_avgpx_50"].to_numpy().astype(float); b_sell=b["sell_avgpx_50"].to_numpy().astype(float)
    for off in ENTRY_OFFS:
        fo=f.filter(pl.col("t_offset")==off); xo=x.filter(pl.col("t_offset")==off)
        wmap={int(w):i for i,w in enumerate(fo["wts"].to_numpy())}
        bret=dict(zip(fo["wts"].to_numpy(), fo["bret_60s"].to_numpy()))
        x15=dict(zip(xo["wts"].to_numpy(), xo["xtf15_mid"].to_numpy()))
        for w_ in meta["wts"].to_numpy():
            w_=int(w_); T=(w_+off)*1_000_000+LAT
            if w_ not in res or np.isnan(res[w_]): continue
            lo=np.searchsorted(bw,w_,"left"); hi=np.searchsorted(bw,w_,"right")
            if hi<=lo: continue
            bseg=slice(lo,hi); bt=bts[lo:hi]
            k=np.searchsorted(bt,T,"right")-1
            if k<0: continue
            up_ask=b_buy[lo+k]; up_bid=b_sell[lo+k]
            if not (np.isfinite(up_ask) and np.isfinite(up_bid)): continue
            mid=(up_ask+up_bid)/2
            for band in BANDS:
                if not (band[0]<=mid<band[1]): continue
                for dname in DIRS:
                    if dname=="blind_up": dir_up=True
                    elif dname=="blind_down": dir_up=False
                    elif dname=="binance1m":
                        s=bret.get(w_,np.nan)
                        if not np.isfinite(s) or s==0: continue
                        dir_up=s>0
                    else:
                        s=x15.get(w_,np.nan)
                        if not np.isfinite(s): continue
                        dir_up=s>0.5
                    entry = up_ask if dir_up else 1.0-up_bid
                    if not (0.02<entry<0.98): continue
                    shares=5.0/entry
                    fee_in=shares*rate*entry*(1-entry)
                    win=res[w_] if dir_up else 1.0-res[w_]
                    # trade path in token space after entry
                    tlo=np.searchsorted(tw,w_,"left"); thi=np.searchsorted(tw,w_,"right")
                    seg_ts=tts[tlo:thi]; seg_px=tpx[tlo:thi]
                    tok_px = seg_px if dir_up else 1.0-seg_px
                    after=seg_ts>T
                    seg_ts2=seg_ts[after]; tok2=tok_px[after]
                    for delta in DELTAS:
                        L=entry+delta/100.0
                        # fill time = first trade >= L (touch)
                        hit=np.where(tok2>=L-1e-9)[0]
                        t_fill=seg_ts2[hit[0]] if len(hit) else None
                        for stop_s in STOPS:
                            if t_fill is not None and (stop_s is None or t_fill<=T+stop_s*1_000_000):
                                pnl=shares*(delta/100.0)-fee_in          # maker sell filled
                            elif stop_s is None:
                                pnl=shares*win-5.0-fee_in                 # hold to expiry
                            else:
                                # STOP OUT: taker-sell at book as-of stop time
                                st=T+stop_s*1_000_000
                                kk=np.searchsorted(bt,st,"right")-1
                                if kk<0: continue
                                ex = b_sell[lo+kk] if dir_up else 1.0-b_buy[lo+kk]  # token bid
                                if not np.isfinite(ex): continue
                                fee_out=shares*rate*ex*(1-ex)
                                pnl=shares*(ex-entry)-fee_in-fee_out
                            key=(off,dname,delta,stop_s)
                            r=rows.setdefault(key,[0,0.0,0,0.0,0,0.0])  # tr_n,tr_p, va_n,va_p
                            istr = date<="2026-03-19"
                            if istr: r[0]+=1; r[1]+=pnl
                            else: r[2]+=1; r[3]+=pnl

def main():
    dates=[d for d in loader.available_dates("5m","trades")]
    rng=loader.holdout_range()
    if rng: dates=[d for d in dates if not(rng[0]<=d<=rng[1])]
    rows={}
    for d in dates: simulate(d,rows)
    out=[]
    for (off,dname,delta,stop),v in rows.items():
        trn,trp,van,vap=v[0],v[1],v[2],v[3]
        out.append({"entry_off":off,"dir":dname,"delta":delta,
                    "stop_s":(stop if stop is not None else -1),
                    "train_n":trn,"train_mean":round(trp/trn,4) if trn else None,
                    "val_n":van,"val_mean":round(vap/van,4) if van else None,
                    "val_pnl":round(vap,2)})
    df=pl.DataFrame(out).sort("val_mean",descending=True)
    df.write_parquet("results/grid_5m_stoploss.parquet")
    print("=== stop-loss exit results, $5/trade, sorted by val mean/trade ===")
    print(df.filter(pl.col("val_n")>=300).head(20))
main()
