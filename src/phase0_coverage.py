"""Phase 0.2 — Coverage audit of Telonex data for BTC up/down markets.

Reads the free markets metadata parquet (already downloaded), enumerates every
BTC up/down market family, validates deterministic slug timestamps, finds
per-day gaps, and writes reports/phase0_coverage.md. Free API only — no
authenticated downloads happen here.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.request

import polars as pl

MARKETS = "data/raw/telonex/polymarket_markets.parquet"
OUT = "reports/phase0_coverage.md"

FAMILIES = {
    "btc-updown-5m": (r"^btc-updown-5m-(\d+)$", 300, 288),
    "btc-updown-15m": (r"^btc-updown-15m-(\d+)$", 900, 96),
    "btc-updown-4h": (r"^btc-updown-4h-(\d+)$", 14400, 6),
    "btc-up-or-down-15m (legacy)": (r"^btc-up-or-down-15m-(\d+)$", 900, 96),
}
HOURLY_RE = r"^bitcoin-up-or-down-[a-z]+-\d+(-\d+)?-?(am|pm)-et$"

CHANNELS = ["trades", "quotes", "book_snapshot_25", "book_snapshot_full", "onchain_fills"]


def crypto_prices_availability() -> dict:
    url = "https://api.telonex.io/v1/availability/polymarket?asset_id=btcusd"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def audit_family(lf: pl.LazyFrame, name: str, pattern: str, step: int, per_day: int) -> dict:
    df = (
        lf.filter(pl.col("slug").str.contains(pattern))
        .with_columns(pl.col("slug").str.extract(pattern, 1).cast(pl.Int64).alias("wts"))
        .collect()
    )
    n = len(df)
    if n == 0:
        return {"name": name, "n": 0}
    bad_mod = int((df["wts"] % step != 0).sum())
    ts_min, ts_max = int(df["wts"].min()), int(df["wts"].max())
    dup = n - df["wts"].n_unique()
    status_counts = dict(df.group_by("status").len().iter_rows())
    resolved = df.filter(pl.col("status") == "resolved")
    res_with_id = int((resolved["result_id"].is_in(["0", "1"])).sum())

    # Per-UTC-day window counts -> gap detection
    daily = (
        df.with_columns(
            pl.from_epoch("wts", time_unit="s").dt.date().alias("day")
        )
        .group_by("day")
        .len()
        .sort("day")
    )
    days = daily["day"].to_list()
    counts = dict(zip(daily["day"].to_list(), daily["len"].to_list()))
    full_range = [days[0] + dt.timedelta(days=i) for i in range((days[-1] - days[0]).days + 1)]
    missing_days = [d for d in full_range if d not in counts]
    partial_days = [
        (d, counts[d]) for d in full_range
        if d in counts and counts[d] < per_day and d not in (days[0], days[-1])
    ]

    # Channel coverage: share of markets with data per channel
    chan = {}
    for c in CHANNELS:
        col = f"{c}_from"
        has = int((df[col].fill_null("") != "").sum())
        nonempty = df.filter(pl.col(col).fill_null("") != "")
        chan[c] = {
            "have": has,
            "pct": 100.0 * has / n,
            "first": nonempty[col].min() if has else None,
            "last": nonempty[f"{c}_to"].max() if has else None,
        }

    return {
        "name": name, "n": n, "bad_mod": bad_mod, "dup": dup,
        "ts_min": ts_min, "ts_max": ts_max,
        "first": dt.datetime.fromtimestamp(ts_min, dt.UTC),
        "last": dt.datetime.fromtimestamp(ts_max, dt.UTC),
        "status": status_counts, "resolved_with_result": res_with_id,
        "n_resolved": len(resolved),
        "missing_days": missing_days, "partial_days": partial_days,
        "channels": chan,
    }


def audit_hourly(lf: pl.LazyFrame) -> dict:
    df = lf.filter(pl.col("slug").str.contains(HOURLY_RE)).collect()
    n = len(df)
    if n == 0:
        return {"n": 0}
    df = df.with_columns((pl.col("end_date_us") // 1_000_000).alias("end_s"))
    status_counts = dict(df.group_by("status").len().iter_rows())
    first = dt.datetime.fromtimestamp(int(df["end_s"].min()), dt.UTC)
    last = dt.datetime.fromtimestamp(int(df["end_s"].max()), dt.UTC)
    chan = {}
    for c in ("trades", "quotes", "book_snapshot_25"):
        col = f"{c}_from"
        has = int((df[col].fill_null("") != "").sum())
        chan[c] = {"have": has, "pct": 100.0 * has / n}
    return {"n": n, "first": first, "last": last, "status": status_counts, "channels": chan}


def main() -> None:
    lf = pl.scan_parquet(MARKETS)
    total = lf.select(pl.len()).collect().item()

    results = [audit_family(lf, name, *spec) for name, spec in FAMILIES.items()]
    hourly = audit_hourly(lf)
    cp = crypto_prices_availability()["channels"]["crypto_prices"]

    lines = [
        "# Phase 0.2 — Telonex coverage audit",
        "",
        f"Generated: {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC. "
        f"Source: free markets dataset ({total:,} markets) + public availability endpoint.",
        "",
        "## Chainlink resolution feed (`crypto_prices`, asset_id=`btcusd`)",
        "",
        f"- Available **{cp['from_date']} → {cp['to_date']}** (~3 months).",
        "- This is the feed Polymarket uses to resolve these markets. Windows-table",
        "  open/close reconstruction (0.5) is only possible inside this range; outside it,",
        "  outcomes come from market metadata `result_id` and Binance-proxy prices are",
        "  diagnostics only.",
        "",
    ]

    for r in results:
        lines.append(f"## {r['name']}")
        lines.append("")
        if r["n"] == 0:
            lines.append("- No markets found.")
            lines.append("")
            continue
        lines += [
            f"- Markets: **{r['n']:,}** ({r['first']:%Y-%m-%d %H:%M} → {r['last']:%Y-%m-%d %H:%M} UTC)",
            f"- Slug timestamp modulo violations: {r['bad_mod']} | duplicate timestamps: {r['dup']}",
            f"- Status: { {k: f'{v:,}' for k, v in sorted(r['status'].items())} }",
            f"- Resolved with result_id in {{0,1}}: {r['resolved_with_result']:,} / {r['n_resolved']:,}",
            f"- Missing whole days inside range: {len(r['missing_days'])}"
            + (f" → {[str(d) for d in r['missing_days'][:15]]}" if r["missing_days"] else ""),
            f"- Partial days (fewer windows than expected, excl. endpoints): {len(r['partial_days'])}"
            + (f" → first 10: {[(str(d), c) for d, c in r['partial_days'][:10]]}" if r["partial_days"] else ""),
            "",
            "| channel | markets with data | % | first | last |",
            "|---|---|---|---|---|",
        ]
        for c, v in r["channels"].items():
            lines.append(f"| {c} | {v['have']:,} | {v['pct']:.1f}% | {v['first']} | {v['last']} |")
        lines.append("")

    lines += ["## Hourly BTC up/down (`bitcoin-up-or-down-*-et`)", ""]
    if hourly["n"]:
        lines += [
            f"- Markets: **{hourly['n']:,}** (window ends {hourly['first']:%Y-%m-%d} → {hourly['last']:%Y-%m-%d} UTC)",
            f"- Status: { {k: f'{v:,}' for k, v in sorted(hourly['status'].items())} }",
            "- Channel presence: "
            + ", ".join(f"{c}: {v['pct']:.0f}%" for c, v in hourly["channels"].items()),
            "",
        ]
    else:
        lines.append("- No hourly markets matched the pattern — INVESTIGATE.")

    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
