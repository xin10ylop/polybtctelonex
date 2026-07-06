"""Data loader with the HOLDOUT guard (Hard Rule 2).

All research code MUST read processed data through this module. After the
Phase 0.7 split, configs/holdout.json records the holdout boundary; any
attempt to load a date inside it raises unless holdout_final_run=True
(passed exactly once, by the Phase 5 runner, with --holdout-final-run).
"""
from __future__ import annotations

import glob
import json
import os

import polars as pl

_HOLDOUT_CONFIG = "configs/holdout.json"


class HoldoutViolation(RuntimeError):
    pass


def holdout_range() -> tuple[str, str] | None:
    if not os.path.exists(_HOLDOUT_CONFIG):
        return None
    with open(_HOLDOUT_CONFIG) as f:
        c = json.load(f)
    return c["from_date"], c["to_date"]


def _check(dates: list[str], holdout_final_run: bool) -> None:
    rng = holdout_range()
    if rng is None or holdout_final_run:
        return
    lo, hi = rng
    bad = [d for d in dates if lo <= d <= hi]
    if bad:
        raise HoldoutViolation(
            f"Refusing to load HOLDOUT dates {bad[:3]}{'...' if len(bad) > 3 else ''} "
            f"(holdout={lo}..{hi}). Only the Phase 5 runner may pass --holdout-final-run."
        )


def load_daily(family: str, channel: str, dates: list[str],
               holdout_final_run: bool = False) -> pl.LazyFrame:
    """Scan processed daily parquets for a family/channel over given dates."""
    _check(dates, holdout_final_run)
    root = "data/HOLDOUT/daily" if holdout_final_run else "data/processed/daily"
    paths = []
    for d in dates:
        for base in ("data/processed/daily", root):
            p = f"{base}/{family}/{channel}/{d}.parquet"
            if os.path.exists(p):
                paths.append(p)
                break
    if not paths:
        raise FileNotFoundError(f"no {family}/{channel} data for {dates[:3]}...")
    return pl.scan_parquet(paths)


def load_crypto_prices(dates: list[str], holdout_final_run: bool = False) -> pl.LazyFrame:
    _check(dates, holdout_final_run)
    paths = []
    for d in dates:
        for base in ("data/processed/daily", "data/HOLDOUT/daily"):
            p = f"{base}/crypto_prices/{d}.parquet"
            if os.path.exists(p):
                if base.startswith("data/HOLDOUT") and not holdout_final_run:
                    raise HoldoutViolation(f"{d} is in HOLDOUT")
                paths.append(p)
                break
    if not paths:
        raise FileNotFoundError(f"no crypto_prices for {dates[:3]}...")
    return pl.scan_parquet(paths)


def available_dates(family: str, channel: str) -> list[str]:
    return sorted(os.path.basename(p)[:-8]
                  for p in glob.glob(f"data/processed/daily/{family}/{channel}/*.parquet"))
