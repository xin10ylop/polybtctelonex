"""Phase 0.6 — empirically fit the fee-regime table from on-chain fills.

For each processed day and family, computes r_hat = median(taker_fee /
(amount * p * (1-p))) over taker fills with fee > 0, plus the share of fills
carrying any fee. Detects regime-switch dates (no-fee -> fee, rate changes)
and writes configs/fee_regimes.json consumed by src/fees.py.

Run after (or during) bulk download: .venv/bin/python src/fit_fee_history.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys

import polars as pl

sys.path.insert(0, "src")
import loader

FAMILIES = ("5m", "15m", "4h")


def fit_day(family: str, date: str) -> dict | None:
    try:
        f = loader.load_daily(family, "fills", [date]).collect()
    except FileNotFoundError:
        return None
    if f.is_empty():
        return None
    tot = len(f)
    fee = f.filter(pl.col("taker_fee") > 0)
    row = {"date": date, "family": family, "n_fills": tot,
           "share_with_fee": len(fee) / tot}
    if len(fee) >= 20:
        r = (fee["taker_fee"] / (fee["amount"] * fee["price"] * (1 - fee["price"]))).median()
        row["r_hat"] = round(float(r), 4)
    else:
        row["r_hat"] = 0.0
    return row


def main() -> None:
    rows = []
    for fam in FAMILIES:
        for date in loader.available_dates(fam, "fills"):
            r = fit_day(fam, date)
            if r:
                rows.append(r)
    df = pl.DataFrame(rows).sort("family", "date")
    df.write_parquet("results/fee_fit_by_day.parquet")

    # build regime table per family: contiguous runs of (rounded) r_hat
    regimes: dict[str, list] = {}
    for fam in FAMILIES:
        d = df.filter((pl.col("family") == fam) & (pl.col("n_fills") >= 50))
        runs: list = []
        for row in d.iter_rows(named=True):
            r = round(row["r_hat"], 3) if row["share_with_fee"] > 0.5 else 0.0
            if runs and runs[-1]["r"] == r:
                runs[-1]["to"] = row["date"]
            else:
                runs.append({"from": row["date"], "to": row["date"], "r": r})
        # squash flickers shorter than 3 days into neighbors
        table = []
        for i, run in enumerate(runs):
            days = (dt.date.fromisoformat(run["to"]) - dt.date.fromisoformat(run["from"])).days + 1
            if days < 3 and table:
                table[-1]["to"] = run["to"]
            else:
                table.append(run)
        regimes[fam] = [
            [None if i == 0 else t["from"],
             None if i == len(table) - 1 else table[i + 1]["from"],
             t["r"], 1.0]
            for i, t in enumerate(table)
        ]
    regimes["1h"] = regimes.get("15m", [])  # hourly follows 15m crypto rules
    with open("configs/fee_regimes.json", "w") as f:
        json.dump(regimes, f, indent=1)
    print("wrote configs/fee_regimes.json")
    for fam, t in regimes.items():
        print(fam, t)


if __name__ == "__main__":
    main()
