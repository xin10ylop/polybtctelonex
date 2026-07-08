"""The quant's trade, reconstructed: final-seconds oracle-feed latency arbitrage.
Signal: private (zero-latency) Chainlink source feed vs window open — in the
last 2-6s the resolution print is nearly known. Buy the predicted winner if
the book still prices it below fair minus costs (his 'fee-adjusted edge' gate),
with a vol-scaled z-threshold (his 'z-score gate') and spread sanity.
Fills: real book as-of T+latency (250ms / 1s). Fees date-correct. $5 stakes
(scale-free stats; $50-bucket fill prices bound the $5 fill).
NOTE: crypto_prices exists only from Apr 2 -> the whole testable sample is the
validation era (Apr 2 - May 12). Pre-registered bars: n>=300, t>=3, pf>=1.15;
if passed, the sealed HOLDOUT (May 13 - Jul 5) is the one-shot confirmation.
"""
import sys, datetime as dt, math
import numpy as np, polars as pl
sys.path.insert(0,"src")
import loader, fees, windows as W
from scipy.stats import norm

T_OFFS=[294,296,297,298]; Z_THR=[1.5,2.5,4.0]; EV_MARGIN=[0.005,0.01,0.02]
LATS={"l250":250_000,"l1s":1_000_000}

def run(dates, tag):
    res={}
    for date in dates:
        try:
            cp=(loader.load_crypto_prices([date]).collect().sort("timestamp_us"))
            b=(loader.load_daily("5m","bookcurves",[date]).collect().sort("wts","local_timestamp_us"))
        except (FileNotFoundError, loader.HoldoutViolation): continue
        d0=int(dt.datetime.fromisoformat(date+"T00:00:00+00:00").timestamp())
        meta=W.market_meta("5m",d0,d0+86400).sort("wts")
        ct=cp["timestamp_us"].to_numpy(); cpx=cp["price"].to_numpy().astype(float)
        clog=np.log(cpx)
        # rolling 5-min sigma of 1s returns on the chainlink feed (per-sqrt-second)
        bw=b["wts"].to_numpy(); bts=b["local_timestamp_us"].to_numpy()
        b_buy=b["buy_avgpx_50"].to_numpy().astype(float); b_sell=b["sell_avgpx_50"].to_numpy().astype(float)
        rate=fees.params(date,"5m")[0]
        for r_ in meta.iter_rows(named=True):
            w_=r_["wts"]; rid=r_["result_id"]
            if rid not in ("0","1"): continue
            up_won=1.0 if rid=="0" else 0.0
            i_open=np.searchsorted(ct,w_*1_000_000,"left")
            if i_open>=len(ct): continue
            # sigma from prior 300s of feed
            j0=np.searchsorted(ct,(w_-300)*1_000_000,"left")
            if i_open-j0>=30:
                seg=clog[j0:i_open]; sg_t=ct[j0:i_open]
                rets=np.diff(seg); dts=np.diff(sg_t)/1e6
                sig=np.std(rets/np.sqrt(np.maximum(dts,1e-3)))  # per-sqrt-second logret vol
            else: sig=np.nan
            if not (np.isfinite(sig) and sig>0): continue
            open_px=cpx[i_open]
            lo=np.searchsorted(bw,w_,"left"); hi=np.searchsorted(bw,w_,"right")
            if hi<=lo: continue
            bt_seg=bts[lo:hi]
            for toff in T_OFFS:
                T=(w_+toff)*1_000_000
                k=np.searchsorted(ct,T,"right")-1
                if k<i_open: continue
                cur=cpx[k]; delta=math.log(cur/open_px)
                t_rem=300-toff
                z=delta/(sig*math.sqrt(t_rem))
                fair_up=norm.cdf(z)
                dir_up = z>0
                fair = fair_up if dir_up else 1-fair_up
                for lname,lus in LATS.items():
                    kk=np.searchsorted(bt_seg,T+lus,"right")-1
                    if kk<0: continue
                    ask = b_buy[lo+kk] if dir_up else 1-b_sell[lo+kk]
                    if not (np.isfinite(ask) and 0.02<ask<0.995): continue
                    fee_ps = rate*ask*(1-ask)
                    ev = fair-ask-fee_ps
                    win = up_won if dir_up else 1-up_won
                    shares=5.0/ask
                    pnl = shares*win-5.0-shares*fee_ps
                    for zt in Z_THR:
                        if abs(z)<zt: continue
                        for m in EV_MARGIN:
                            if ev<m: continue
                            key=(toff,lname,zt,m)
                            a=res.setdefault(key,[0,0.0,0.0,0,0.0])
                            a[0]+=1; a[1]+=pnl; a[2]+=pnl*pnl; a[3]+=(pnl>0); a[4]+=ask
    rows=[]
    for (toff,lname,zt,m),(n,s,s2,w,ask_s) in res.items():
        if n<2: continue
        mu=s/n; var=max(s2/n-mu*mu,1e-12); t=mu/math.sqrt(var/n)
        rows.append({"toff":toff,"lat":lname,"z_thr":zt,"margin":m,"n":n,
                     "pnl":round(s,2),"mean":round(mu,4),"t":round(t,2),
                     "wr":round(w/n,3),"avg_entry":round(ask_s/n,3)})
    df=pl.DataFrame(rows).sort("t",descending=True)
    df.write_parquet(f"results/oracle_lastsec_{tag}.parquet")
    return df

if __name__=="__main__":
    dates=[d for d in loader.available_dates("5m","bookcurves") if d>="2026-04-02"]
    df=run(dates,"val")
    print(f"=== final-seconds oracle trade, DEV sample (Apr 2 - May 12), $5/trade ===")
    print(df.head(14))
