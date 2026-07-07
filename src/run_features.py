"""Phase 2 runner — build the feature store over all non-holdout dates.
Resumable: skips dates whose output parquet already exists. Chunk-friendly
(run under `timeout 570`, repeat until it prints FEATURES DONE).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, "src")
import features
import loader


def main() -> None:
    pending = []
    for family in ("5m", "15m"):
        for date in loader.available_dates(family, "quotes"):
            out = f"results/features/{family}/{date}.parquet"
            if not os.path.exists(out):
                pending.append((family, date))
    if not pending:
        print("FEATURES DONE")
        return
    for family, date in pending:
        features.build_day(family, date)
        print(f"{family} {date} ok", flush=True)
    print("FEATURES DONE")


if __name__ == "__main__":
    main()
