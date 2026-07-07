"""Build data/processed/windows.parquet — one row per market window, all families,
full history. Chainlink open/close + reconstructed outcome where the feed exists
(2026-04-02+); metadata result_id everywhere. Adds per-window traded volume and
the date-correct fee rate. Prints GATE-0 reconciliation stats.
"""
from __future__ import annotations

import datetime as dt
import sys

import polars as pl

sys.path.insert(0, "src")
import fees
import loader
import windows as W

OUT = "data/processed/windows.parquet"


def all_dates(family: str) -> list[str]:
    return loader.available_dates(family, "quotes")


def volumes(family: str, dates: list[str]) -> pl.DataFrame:
    vols = []
    for i in range(0, len(dates), 62):
        chunk = dates[i:i + 62]
        vols.append(
            loader.load_daily(family, "trades", chunk)
            .group_by("wts").agg(pl.col("size").sum().alias("volume_shares"),
                                 (pl.col("size") * pl.col("price")).sum().alias("volume_usdc"))
            .collect()
        )
    return pl.concat(vols).group_by("wts").sum()


def main() -> None:
    frames = []
    for family in ("5m", "15m", "4h"):
        dates = all_dates(family)
        if not dates:
            continue
        w = []
        for i in range(0, len(dates), 31):
            w.append(W.build_windows(family, dates[i:i + 31]))
        wf = pl.concat(w).unique(subset="wts", keep="first")
        wf = wf.join(volumes(family, dates), on="wts", how="left")
        wf = wf.with_columns(
            pl.lit(family).alias("family"),
            pl.from_epoch("wts", time_unit="s").dt.date().cast(pl.String).alias("date"),
        )
        wf = wf.with_columns(
            pl.col("date").map_elements(lambda d, f=family: fees.params(d, f)[0],
                                        return_dtype=pl.Float64).alias("fee_rate"))
        m, n = W.reconciliation_rate(wf)
        print(f"{family}: {len(wf):,} windows | volume rows matched "
              f"{wf['volume_shares'].is_not_null().sum():,} | "
              f"chainlink-reconstructable {n:,} | outcome match {m:,}/{n:,} "
              f"({100*m/max(n,1):.3f}%)", flush=True)
        frames.append(wf)
    full = pl.concat(frames)
    full.write_parquet(OUT, compression="zstd")
    print(f"wrote {OUT}: {len(full):,} rows")


if __name__ == "__main__":
    main()
