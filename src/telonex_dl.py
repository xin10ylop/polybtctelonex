"""Thin async Telonex download client used by all phases.

Design (mirrors the official SDK's endpoint semantics, verified against
telonex==0.4.0 source):
  GET {API}/v1/downloads/{exchange}/{channel}/{YYYY-MM-DD}?asset_id=... | slug=...&outcome=...
  Authorization: Bearer $TELONEX_API_KEY
  200 -> parquet bytes (after redirect), 404 -> no data for that day (fine),
  401 auth, 403 entitlement, 429 rate-limit w/ Retry-After.

Resumable: a task whose output file already exists is skipped.
The API key is read from .env and never logged.
"""
from __future__ import annotations

import asyncio
import dataclasses
import os
import pathlib
import random

import httpx

API = "https://api.telonex.io"


def api_key() -> str:
    for line in pathlib.Path(".env").read_text().splitlines():
        if line.startswith("TELONEX_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("TELONEX_API_KEY not found in .env")


@dataclasses.dataclass
class Task:
    channel: str
    date: str  # YYYY-MM-DD
    out_path: str
    asset_id: str | None = None
    slug: str | None = None
    outcome: str | None = None

    def params(self) -> dict:
        p: dict = {}
        if self.asset_id:
            p["asset_id"] = self.asset_id
        if self.slug:
            p["slug"] = self.slug
        if self.outcome:
            p["outcome"] = self.outcome
        return p


@dataclasses.dataclass
class Result:
    task: Task
    status: str  # ok | exists | missing | error
    bytes: int = 0
    detail: str = ""


async def _fetch_one(client: httpx.AsyncClient, sem: asyncio.Semaphore, task: Task,
                     max_attempts: int = 5) -> Result:
    if os.path.exists(task.out_path):
        return Result(task, "exists", os.path.getsize(task.out_path))
    url = f"{API}/v1/downloads/polymarket/{task.channel}/{task.date}"
    async with sem:
        for attempt in range(1, max_attempts + 1):
            try:
                r = await client.get(url, params=task.params())
                if r.status_code == 404:
                    return Result(task, "missing")
                if r.status_code == 401:
                    return Result(task, "error", detail="401 auth")
                if r.status_code == 403:
                    return Result(task, "error", detail=f"403 entitlement: {r.text[:200]}")
                if r.status_code == 429:
                    delay = int(r.headers.get("Retry-After", "30"))
                    await asyncio.sleep(delay + random.random())
                    continue
                r.raise_for_status()
                pathlib.Path(task.out_path).parent.mkdir(parents=True, exist_ok=True)
                tmp = f"{task.out_path}.tmp{random.randrange(1 << 30)}"
                with open(tmp, "wb") as f:
                    f.write(r.content)
                os.replace(tmp, task.out_path)
                return Result(task, "ok", len(r.content))
            except (httpx.HTTPError, OSError) as e:
                if attempt == max_attempts:
                    return Result(task, "error", detail=f"{type(e).__name__}: {e}"[:200])
                await asyncio.sleep(2 ** attempt + random.random())
    return Result(task, "error", detail="unreachable")


async def download_tasks(tasks: list[Task], concurrency: int = 8,
                         on_result=None) -> list[Result]:
    headers = {"Authorization": f"Bearer {api_key()}"}
    sem = asyncio.Semaphore(concurrency)
    timeout = httpx.Timeout(300)
    results: list[Result] = []
    async with httpx.AsyncClient(timeout=timeout, headers=headers,
                                 follow_redirects=True) as client:
        for coro in asyncio.as_completed(
                [_fetch_one(client, sem, t) for t in tasks]):
            res = await coro
            results.append(res)
            if on_result:
                on_result(res)
    return results


def run(tasks: list[Task], concurrency: int = 8, on_result=None) -> list[Result]:
    return asyncio.run(download_tasks(tasks, concurrency, on_result))
