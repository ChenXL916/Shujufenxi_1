from __future__ import annotations

import argparse
import asyncio
import json
import math
import sqlite3
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass
class Sample:
    duration_ms: float
    status: int | None
    bytes: int
    error: str | None


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, math.ceil(p * len(ordered)) - 1)
    return round(ordered[rank], 2)


async def benchmark(
    client: httpx.AsyncClient,
    url: str,
    concurrency: int,
    requests: int,
) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(concurrency)

    async def one() -> Sample:
        async with semaphore:
            started = time.perf_counter()
            try:
                response = await client.get(url)
                elapsed = (time.perf_counter() - started) * 1000
                return Sample(elapsed, response.status_code, len(response.content), None)
            except Exception as exc:  # noqa: BLE001 - QA records transport failures
                elapsed = (time.perf_counter() - started) * 1000
                return Sample(elapsed, None, 0, f"{type(exc).__name__}: {exc}")

    wall_started = time.perf_counter()
    tasks = [asyncio.create_task(one()) for _ in range(requests)]
    done, pending = await asyncio.wait(tasks, timeout=90)
    samples = [task.result() for task in done]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
        samples.extend(
            Sample(90_000.0, None, 0, "ScenarioTimeout: request unfinished after 90 seconds")
            for _ in pending
        )
    wall_seconds = time.perf_counter() - wall_started
    successes = [item for item in samples if item.status == 200 and item.error is None]
    durations = [item.duration_ms for item in successes]
    errors = [item for item in samples if item.status != 200 or item.error is not None]
    return {
        "concurrency": concurrency,
        "requests": requests,
        "successes": len(successes),
        "errors": len(errors),
        "error_rate": round(len(errors) / requests, 6),
        "wall_seconds": round(wall_seconds, 3),
        "throughput_rps": round(len(successes) / wall_seconds, 2) if wall_seconds else None,
        "latency_ms": {
            "min": round(min(durations), 2) if durations else None,
            "mean": round(statistics.fmean(durations), 2) if durations else None,
            "p50": percentile(durations, 0.50),
            "p95": percentile(durations, 0.95),
            "p99": percentile(durations, 0.99),
            "max": round(max(durations), 2) if durations else None,
        },
        "response_bytes": {
            "min": min((item.bytes for item in successes), default=None),
            "max": max((item.bytes for item in successes), default=None),
        },
        "error_samples": [asdict(item) for item in errors[:10]],
    }


def query_plans(database: Path) -> list[dict[str, Any]]:
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        queries = {
            "hourly_facts_range": (
                "SELECT id, room_id, business_date, hour_order FROM hourly_facts "
                "WHERE business_date BETWEEN ? AND ? AND data_status = 'complete'",
                ("2026-07-09", "2026-07-15"),
            ),
            "hourly_metrics_join": (
                "SELECT hm.hourly_fact_id, hm.metric_key, hm.numeric_value "
                "FROM hourly_metrics hm JOIN hourly_facts hf ON hf.id = hm.hourly_fact_id "
                "WHERE hf.business_date BETWEEN ? AND ? AND hm.metric_key IN (?, ?)",
                ("2026-07-09", "2026-07-15", "period_overall_roi", "period_spend"),
            ),
            "room_hour_range": (
                "SELECT id FROM hourly_facts WHERE room_id = (SELECT id FROM rooms LIMIT 1) "
                "AND business_date BETWEEN ? AND ? AND hour_order = ?",
                ("2026-07-09", "2026-07-15", 8),
            ),
        }
        rows: list[dict[str, Any]] = []
        for name, (query, params) in queries.items():
            plan = connection.execute(f"EXPLAIN QUERY PLAN {query}", params).fetchall()
            rows.append(
                {
                    "name": name,
                    "plan": [item[3] for item in plan],
                    "uses_index": any("INDEX" in str(item[3]).upper() for item in plan),
                    "full_scan": any(
                        str(item[3]).upper().startswith("SCAN ")
                        and "USING" not in str(item[3]).upper()
                        for item in plan
                    ),
                }
            )
        return rows
    finally:
        connection.close()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--database", type=Path, default=Path("live_ops_test.db"))
    parser.add_argument("--output", type=Path, default=Path("qa/results/performance_results.json"))
    args = parser.parse_args()
    endpoints = {
        "overview": "/dashboard/overview?start_date=2026-07-09&end_date=2026-07-15",
        "hourly_comparison": (
            "/overview/hourly-comparison?end_date=2026-07-15&period_days=7"
            "&metric_ids=period_overall_roi&metric_ids=period_spend"
            "&series_dimension=summary"
        ),
        "timeline": (
            "/charts/timeline?start_date=2026-07-09&end_date=2026-07-15"
            "&grain=hour&metric_keys=period_overall_roi&metric_keys=period_spend"
        ),
        "pivot": "/pivot/anchor-control?start_date=2026-07-09&end_date=2026-07-15",
    }
    levels = ((1, 3), (10, 10), (50, 50))
    results: dict[str, list[dict[str, Any]]] = {}
    async with httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=60)) as client:
        health = await client.get(args.api.rsplit("/api/v1", 1)[0] + "/health")
        if health.status_code != 200:
            raise RuntimeError(f"health status {health.status_code}")
        for name, path in endpoints.items():
            url = args.api + path
            warm = await client.get(url)
            if warm.status_code != 200:
                raise RuntimeError(f"warmup {name}: {warm.status_code}")
            results[name] = []
            for concurrency, requests in levels:
                profile = await benchmark(client, url, concurrency, requests)
                results[name].append(profile)
                print(
                    json.dumps(
                        {
                            "endpoint": name,
                            "concurrency": concurrency,
                            "requests": requests,
                            "errors": profile["errors"],
                            "p95_ms": profile["latency_ms"]["p95"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

    threshold_results = []
    for endpoint, levels_result in results.items():
        for item in levels_result:
            target = 1000 if item["concurrency"] <= 10 else 3000
            p95 = item["latency_ms"]["p95"]
            threshold_results.append(
                {
                    "endpoint": endpoint,
                    "concurrency": item["concurrency"],
                    "target_p95_ms": target,
                    "actual_p95_ms": p95,
                    "error_rate": item["error_rate"],
                    "passed": bool(p95 is not None and p95 <= target and item["error_rate"] == 0),
                }
            )
    output = {
        "safety": "GET-only local API load; SQLite query plans opened mode=ro",
        "api": args.api,
        "database": str(args.database),
        "profiles": results,
        "thresholds": threshold_results,
        "query_plans": query_plans(args.database),
        "summary": {
            "profiles": len(threshold_results),
            "passed": sum(1 for item in threshold_results if item["passed"]),
            "failed": sum(1 for item in threshold_results if not item["passed"]),
            "total_requests": sum(
                level["requests"] for endpoint in results.values() for level in endpoint
            ),
            "total_errors": sum(
                level["errors"] for endpoint in results.values() for level in endpoint
            ),
        },
        "limitations": [
            "本机Windows、SQLite、单API进程结果，不代表生产PostgreSQL/Redis/容器。",
            "未执行会产生文件或业务写入的并发导出/同步/预警推送。",
            "未持续运行30分钟以上，不能替代长时间稳定性测试。",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))
    for item in threshold_results:
        print(json.dumps(item, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
