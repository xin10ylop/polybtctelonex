"""Profile the top consistent taker wallets: is their edge a DATA signal
(replicable at home) or SPEED (sub-250ms reaction to Binance, not replicable)?
Key diagnostic: Binance return in the ~1s window straddling each of their fills,
signed by their trade direction. If strongly positive at short lead, they are
faster than home latency = latency arbitrage."""
import sys, glob, datetime as dt
import numpy as np, polars as pl
sys.path.insert(0,"src")
import loader

TARGETS = {  # hashes truncated in print; match on full hash prefix
    "1590158696":"consistent (sharpe .70, 84% green)",
    "7108302125":"biggest (496k fills, likely HFT)",
    "1534100583":"consistent (sharpe .36, 72% green)",
}
def load_binance():
    fs=sorted(glob.glob("data/processed/binance/aggTrades/*.parquet"))
    b=pl.concat([pl.read_parquet(p) for p in fs]).sort("ts_us")
    return b["ts_us"].to_numpy(), b["price"].to_numpy().astype(float)

def main():
    bt,bp=load_binance()
    wins=pl.read_parquet("data/processed/windows.parquet").filter(pl.col("family")=="5m")
    up=dict(zip(wins["wts"].to_list(),(wins["result_id"]=="0").cast(pl.Float64).to_list()))
    dates=[d for d in loader.available_dates("5m","fills")]
    rng=loader.holdout_range()
    if rng: dates=[d for d in dates if not(rng[0]<=d<=rng[1])]
    acc={k:{"n":0,"entry":[],"sec_in":[],"lead":{ -0.5:[],-0.2:[],0.1:[],0.3:[],1.0:[]},"dirwin":0} for k in TARGETS}
    for date in dates:
        f=(loader.load_daily("5m","fills",[date]).filter(~pl.col("mirrored")).collect())
        if f.is_empty(): continue
        th=f["taker_h"].cast(pl.Utf8).to_numpy()
        for key in TARGETS:
            m=np.char.startswith(th,key)
            if m.sum()==0: continue
            sub=f.filter(pl.Series(m))
            ts=sub["timestamp_us"].to_numpy()
            wts=sub["wts"].to_numpy()
            tside=sub["taker_side"].to_numpy(); tok=sub["token"].to_numpy()
            price=sub["price"].to_numpy().astype(float)
            dir_up=((tside=="buy")==(tok=="Up"))
            p_up=np.where(tok=="Up",price,1-price)
            a=acc[key]; a["n"]+=len(sub)
            a["entry"].extend(p_up.tolist())
            a["sec_in"].extend(((ts/1e6).astype(int)-wts).tolist())
            for w_,d_,dr in zip(wts,ts,dir_up):
                pay=up.get(int(w_))
                if pay is not None: a["dirwin"]+= (1 if (pay==1)==dr else 0)
            # binance signed return at several leads relative to fill
            i0=np.searchsorted(bt,ts,"right")-1
            for lead in a["lead"]:
                iL=np.searchsorted(bt,ts+int(lead*1e6),"right")-1
                ok=(i0>=0)&(iL>=0)
                r=np.where(ok, bp[np.clip(iL,0,len(bp)-1)]/bp[np.clip(i0,0,len(bp)-1)]-1, np.nan)
                signed=np.where(dir_up, r, -r)   # + means Binance moved their way
                a["lead"][lead].extend(signed[np.isfinite(signed)].tolist())
    for key,desc in TARGETS.items():
        a=acc[key]
        if a["n"]==0: print(f"\n{key} ({desc}): no fills found"); continue
        entry=np.array(a["entry"]); sec=np.array(a["sec_in"])
        print(f"\n=== {key} — {desc} ===")
        print(f"  fills profiled: {a['n']:,} | direction-correct (won): {a['dirwin']/a['n']*100:.1f}%")
        print(f"  entry price: median {np.median(entry):.3f}, "
              f"% at extremes(<.15 or >.85): {np.mean((entry<.15)|(entry>.85))*100:.0f}%, "
              f"% near 50c(.4-.6): {np.mean((entry>.4)&(entry<.6))*100:.0f}%")
        print(f"  seconds-into-window: median {np.median(sec):.0f}s, %in last 30s: {np.mean(sec>=270)*100:.0f}%")
        print(f"  Binance move in their favor around fill (bps, mean):")
        for lead in sorted(a["lead"]):
            v=np.array(a["lead"][lead])
            tag="BEFORE fill" if lead<0 else "AFTER fill"
            print(f"    lead {lead:+.1f}s ({tag}): {np.mean(v)*1e4:+.2f} bps  (n={len(v):,})")
main()
