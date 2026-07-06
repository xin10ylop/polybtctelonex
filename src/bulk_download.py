"""Phase 0.4 — bulk download+consolidate loop. Background job, resumable, quiet.

Usage: nohup .venv/bin/python src/bulk_download.py > logs/bulk_download.log 2>&1 &

Iterates UTC dates oldest->newest over the full tick-data range, running
download_day.process_day(date, rm_raw=True) for each. A per-day marker file
(data/processed/daily/.done_{date}) makes completed days no-ops, so the job
can be killed/restarted freely. Status: logs/bulk_status.json.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import traceback

sys.path.insert(0, "src")
from download_day import process_day

START = dt.date(2025, 10, 11)   # first 15m tick-data date (coverage audit)
END = dt.date(2026, 7, 5)       # last complete UTC day before run date
STATUS = "logs/bulk_status.json"


def main() -> None:
    day = START
    stats_total = {"days_done": 0, "days_skipped": 0, "raw_mb": 0.0, "errors": []}
    while day <= END:
        date = day.isoformat()
        try:
            s = process_day(date, rm_raw=True, concurrency=8)
            if s.get("skipped"):
                stats_total["days_skipped"] += 1
            else:
                stats_total["days_done"] += 1
                stats_total["raw_mb"] += s.get("raw_mb", 0)
                print(f"{date}: {s}", flush=True)
        except Exception as e:
            stats_total["errors"].append({"date": date, "error": str(e)[:300]})
            print(f"{date}: ERROR {e}", flush=True)
            traceback.print_exc()
            if len(stats_total["errors"]) >= 10:
                print("too many errors, aborting", flush=True)
                break
        with open(STATUS, "w") as f:
            json.dump({**stats_total, "last_date": date,
                       "updated": dt.datetime.now(dt.UTC).isoformat()}, f, indent=1)
        day += dt.timedelta(days=1)
    print("BULK DONE", stats_total["days_done"], "days,",
          len(stats_total["errors"]), "errors", flush=True)


if __name__ == "__main__":
    main()
