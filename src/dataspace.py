"""Sync the processed datasets to/from S3-compatible object storage, so any
fresh session can access the downloaded data without re-downloading from the
original sources.

Setup (once): create a DigitalOcean Space (or any S3 bucket) and put in .env:
    DS_KEY=...        # Spaces access key       (NEVER print/commit)
    DS_SECRET=...     # Spaces secret
    DS_REGION=nyc3
    DS_BUCKET=polybtc-data
    DS_ENDPOINT=https://nyc3.digitaloceanspaces.com

Usage:
    .venv/bin/python src/dataspace.py upload      # push data/processed (resumable)
    .venv/bin/python src/dataspace.py download    # pull everything back
    .venv/bin/python src/dataspace.py download data/processed/daily/5m  # subset
    .venv/bin/python src/dataspace.py ls          # what's in the bucket

Resumable both ways: skips files that already exist with the same size.
Only syncs data/processed/daily + coin_prices (Binance is free from
binance.vision — src/mc_campaign.py re-fetches it per day).
"""
from __future__ import annotations

import os
import sys

ROOTS = ["data/processed/daily", "data/processed/coin_prices"]


def _env(k: str) -> str:
    v = os.environ.get(k)
    if not v:
        for line in open(".env"):
            line = line.strip()
            if line.startswith(f"{k}="):
                v = line.split("=", 1)[1].strip()
                break
    if not v:
        raise SystemExit(f"missing {k} (set in .env)")
    return v


def client():
    import boto3
    return boto3.client(
        "s3", region_name=_env("DS_REGION"), endpoint_url=_env("DS_ENDPOINT"),
        aws_access_key_id=_env("DS_KEY"), aws_secret_access_key=_env("DS_SECRET"))


def remote_index(s3, bucket: str) -> dict[str, int]:
    idx = {}
    tok = None
    while True:
        kw = {"Bucket": bucket, "MaxKeys": 1000}
        if tok:
            kw["ContinuationToken"] = tok
        r = s3.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            idx[o["Key"]] = o["Size"]
        if not r.get("IsTruncated"):
            return idx
        tok = r.get("NextContinuationToken")


def upload() -> None:
    s3 = client(); bucket = _env("DS_BUCKET")
    have = remote_index(s3, bucket)
    n = skipped = 0
    for root in ROOTS:
        for dirpath, _, files in os.walk(root):
            for f in sorted(files):
                p = os.path.join(dirpath, f)
                sz = os.path.getsize(p)
                if have.get(p) == sz:
                    skipped += 1; continue
                s3.upload_file(p, bucket, p)
                n += 1
                if n % 25 == 0:
                    print(f"  uploaded {n} (skipped {skipped})", flush=True)
    print(f"DONE: uploaded {n}, skipped {skipped} already-present")


def download(prefix: str | None = None) -> None:
    s3 = client(); bucket = _env("DS_BUCKET")
    n = skipped = 0
    for key, sz in sorted(remote_index(s3, bucket).items()):
        if prefix and not key.startswith(prefix):
            continue
        if os.path.exists(key) and os.path.getsize(key) == sz:
            skipped += 1; continue
        os.makedirs(os.path.dirname(key), exist_ok=True)
        s3.download_file(bucket, key, key)
        n += 1
        if n % 25 == 0:
            print(f"  downloaded {n} (skipped {skipped})", flush=True)
    print(f"DONE: downloaded {n}, skipped {skipped} already-present")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ls"
    if cmd == "upload":
        upload()
    elif cmd == "download":
        download(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        s3 = client(); idx = remote_index(s3, _env("DS_BUCKET"))
        tot = sum(idx.values())
        print(f"{len(idx)} objects, {tot/1e9:.2f} GB")
        roots = {}
        for k, v in idx.items():
            r = "/".join(k.split("/")[:4])
            roots[r] = roots.get(r, 0) + v
        for r, v in sorted(roots.items()):
            print(f"  {r}: {v/1e9:.2f} GB")
