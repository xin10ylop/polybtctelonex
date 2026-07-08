"""Reverse-engineer real profitable bots from on-chain fills (train+val 5m).
For every wallet: realized P&L as taker and as maker (incl. ~20% maker rebate
approximation), trades, active days, and consistency (mean/day / std/day).
Answers 'consistent profitable bots exist' with direct evidence + a profile
of what the top wallets actually do (side, entry price, time-in-window)."""
import sys, glob, datetime as dt
import numpy as np, polars as pl
sys.path.insert(0,"src")
import loader

REBATE=0.20
def main():
    wins=pl.read_parquet("data/processed/windows.parquet").filter(pl.col("family")=="5m")
    up=dict(zip(wins["wts"].to_list(),(wins["result_id"]=="0").cast(pl.Float64).to_list()))
    dates=[d for d in loader.available_dates("5m","fills")]
    rng=loader.holdout_range()
    if rng: dates=[d for d in dates if not(rng[0]<=d<=rng[1])]
    # accumulate per wallet: pnl, n, set of days, and daily pnl for consistency
    from collections import defaultdict
    mk=defaultdict(lambda:[0.0,0,0.0])   # pnl, n, fees_as_counterparty
    tk=defaultdict(lambda:[0.0,0])
    mk_day=defaultdict(lambda:defaultdict(float))
    tk_day=defaultdict(lambda:defaultdict(float))
    prof={}  # top-wallet behavioural profile accumulators
    for date in dates:
        f=(loader.load_daily("5m","fills",[date]).filter(~pl.col("mirrored")).collect())
        if f.is_empty(): continue
        f=f.with_columns(pl.when(pl.col("token")=="Up").then(pl.col("price")).otherwise(1-pl.col("price")).alias("p_up"),
                         pl.when((pl.col("taker_side")=="buy")==(pl.col("token")=="Up")).then(1).otherwise(-1).alias("tdir"))
        f=f.with_columns(pl.col("wts").replace_strict(up,default=None).alias("up_pay")).drop_nulls("up_pay")
        f=f.with_columns((pl.col("tdir")*(pl.col("up_pay")-pl.col("p_up"))*pl.col("amount")-pl.col("taker_fee")).alias("tk_pnl"),
                         (-pl.col("tdir")*(pl.col("up_pay")-pl.col("p_up"))*pl.col("amount")+REBATE*pl.col("taker_fee")).alias("mk_pnl"))
        for h,p,fee in zip(f["taker_h"],f["tk_pnl"],f["taker_fee"]):
            r=tk[h]; r[0]+=p; r[1]+=1; tk_day[h][date]+=p
        for h,p in zip(f["maker_h"],f["mk_pnl"]):
            r=mk[h]; r[0]+=p; r[1]+=1; mk_day[h][date]+=p
    def top(d,day,label):
        rows=[]
        for h,(pnl,n,*_) in d.items():
            if n<200: continue
            dp=np.array(list(day[h].values()))
            days=len(dp)
            if days<20: continue
            sharpe=dp.mean()/dp.std() if dp.std()>0 else 0
            pos_days=(dp>0).mean()
            rows.append({"wallet":str(h)[:10],"role":label,"pnl":round(pnl,0),"n":n,
                         "days":days,"pnl_per_day":round(pnl/days,2),
                         "day_sharpe":round(sharpe,3),"pos_days":round(pos_days,3)})
        return pl.DataFrame(rows).sort("pnl",descending=True) if rows else pl.DataFrame()
    tkr=top(tk,tk_day,"taker"); mkr=top(mk,mk_day,"maker")
    print(f"=== analyzed {len(dates)} days, {len(tk)} taker wallets, {len(mk)} maker wallets (>=200 fills,>=20 days) ===")
    print("\n--- TOP 12 TAKER wallets by total realized P&L ---")
    print(tkr.head(12))
    print("\n--- TOP 12 MAKER wallets (incl 20% rebate) by total P&L ---")
    print(mkr.head(12))
    print("\n--- how many wallets are CONSISTENTLY profitable? ---")
    for nm,d in (("takers",tkr),("makers",mkr)):
        if len(d)==0: continue
        prof_pos=d.filter((pl.col("pnl")>0)&(pl.col("pos_days")>=0.55)&(pl.col("day_sharpe")>=0.3))
        print(f"  {nm}: {len(d)} active; {len(d.filter(pl.col('pnl')>0))} net-positive; "
              f"{len(prof_pos)} 'consistent' (pnl>0, >55% green days, day-Sharpe>=0.3)")
    pl.concat([tkr,mkr],how="diagonal").write_parquet("results/wallet_pnl.parquet")
main()
