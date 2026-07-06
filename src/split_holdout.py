"""Phase 0.7 — chronological 60/20/20 split with physical holdout quarantine.

Computes the split over all processed daily dates, MOVES the last ~20% of
daily files to data/HOLDOUT/daily/, and writes configs/holdout.json (read by
loader.py's guard) + configs/split.json. Run once, after bulk download.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys

sys.path.insert(0, "src")
import loader


def main() -> None:
    if loader.holdout_range() is not None:
        print("holdout already split — refusing to re-split")
        return
    dates = sorted({os.path.basename(p)[:-8]
                    for p in glob.glob("data/processed/daily/*/*/*.parquet")})
    n = len(dates)
    i_train = int(n * 0.60)
    i_val = int(n * 0.80)
    train, val, hold = dates[:i_train], dates[i_train:i_val], dates[i_val:]
    moved = 0
    for p in glob.glob("data/processed/daily/*/*/*.parquet"):
        if os.path.basename(p)[:-8] in hold:
            dest = p.replace("data/processed/daily", "data/HOLDOUT/daily")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(p, dest)
            moved += 1
    with open("configs/holdout.json", "w") as f:
        json.dump({"from_date": hold[0], "to_date": hold[-1]}, f, indent=1)
    with open("configs/split.json", "w") as f:
        json.dump({"train": [train[0], train[-1]], "validation": [val[0], val[-1]],
                   "holdout": [hold[0], hold[-1]], "n_dates": n}, f, indent=1)
    print(f"split: train {train[0]}..{train[-1]} ({len(train)}d), "
          f"val {val[0]}..{val[-1]} ({len(val)}d), "
          f"HOLDOUT {hold[0]}..{hold[-1]} ({len(hold)}d); moved {moved} files")


if __name__ == "__main__":
    main()
