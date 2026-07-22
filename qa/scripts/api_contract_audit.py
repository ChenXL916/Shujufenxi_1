from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass
class Case:
    id: str
    name: str
    path: str
    expected: list[int]
    forbidden_reflection: str | None = None


CASES = [
    Case("API-001", "健康检查", "/health", [200]),
    Case("API-002", "非法日期格式", "/api/v1/dashboard/overview?start_date=not-a-date", [422]),
    Case(
        "API-003",
        "非法直播间UUID",
        "/api/v1/dashboard/overview?room_ids=not-a-uuid",
        [422],
    ),
    Case(
        "API-004",
        "非法聚合枚举",
        "/api/v1/overview/hourly-comparison?aggregation_mode=invalid",
        [422],
    ),
    Case(
        "API-005",
        "周期0天",
        "/api/v1/overview/hourly-comparison?end_date=2026-07-15&period_days=0",
        [422],
    ),
    Case(
        "API-006",
        "周期31天",
        "/api/v1/overview/hourly-comparison?end_date=2026-07-15&period_days=31",
        [422],
    ),
    Case(
        "API-007",
        "自定义周期缺结束日",
        "/api/v1/overview/hourly-comparison?custom_start_date=2026-07-01",
        [422],
    ),
    Case(
        "API-008",
        "自定义周期开始晚于结束",
        "/api/v1/overview/hourly-comparison?custom_start_date=2026-07-15&custom_end_date=2026-07-01",
        [422],
    ),
    Case(
        "API-009",
        "详情非法自然小时",
        "/api/v1/overview/hourly-comparison/details?natural_hour=24-25&period_days=1&end_date=2026-07-15",
        [422],
    ),
    Case(
        "API-010",
        "详情页码0",
        "/api/v1/overview/hourly-comparison/details?natural_hour=08-09&page=0",
        [422],
    ),
    Case(
        "API-011",
        "详情页大小201",
        "/api/v1/overview/hourly-comparison/details?natural_hour=08-09&page_size=201",
        [422],
    ),
    Case(
        "API-012",
        "未知指标不得静默忽略",
        "/api/v1/overview/hourly-comparison?end_date=2026-07-15&period_days=1&metric_ids=unknown_metric",
        [400, 422],
    ),
    Case(
        "API-013",
        "最多核心2加附加2共4指标",
        "/api/v1/overview/hourly-comparison?end_date=2026-07-15&period_days=1"
        "&metric_ids=period_overall_roi&metric_ids=period_spend"
        "&metric_ids=period_order_count&metric_ids=period_viewers&metric_ids=period_buyers",
        [400, 422],
    ),
    Case(
        "API-014",
        "列表自然小时必须来自24小时字典",
        "/api/v1/overview/hourly-comparison?end_date=2026-07-15&period_days=1&natural_hours=99-00",
        [400, 422],
    ),
    Case(
        "API-015",
        "总览反向日期应拒绝",
        "/api/v1/dashboard/overview?start_date=2026-07-15&end_date=2026-07-01",
        [400, 422],
    ),
    Case(
        "API-016",
        "SQL注入文本参数化处理",
        "/api/v1/dashboard/overview?start_date=2026-07-15&end_date=2026-07-15&anchor_names=%27%20OR%201%3D1%20--",
        [200],
        "' OR 1=1 --",
    ),
    Case(
        "API-017",
        "XSS文本不得原样反射",
        "/api/v1/overview/hourly-comparison?end_date=2026-07-15&period_days=1&anchor_names=%3Cscript%3Eqa%3C%2Fscript%3E",
        [200],
        "<script>qa</script>",
    ),
    Case("API-018", "不存在路由", "/api/v1/not-a-real-route", [404]),
]


def compact_detail(response: httpx.Response) -> Any:
    try:
        payload = response.json()
    except ValueError:
        return None
    if response.status_code >= 400:
        return payload.get("detail") if isinstance(payload, dict) else None
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("qa/results/api_results.json"))
    args = parser.parse_args()
    rows = []
    with httpx.Client(timeout=30.0) as client:
        for case in CASES:
            response = client.get(args.origin + case.path)
            reflected = bool(
                case.forbidden_reflection
                and case.forbidden_reflection in response.text
            )
            passed = response.status_code in case.expected and not reflected
            rows.append(
                {
                    **asdict(case),
                    "method": "GET",
                    "actual_status": response.status_code,
                    "response_bytes": len(response.content),
                    "reflected": reflected,
                    "detail": compact_detail(response),
                    "status": "PASS" if passed else "FAIL",
                }
            )
    result = {
        "safety": "GET-only; response bodies not persisted except validation detail; no secrets",
        "origin": args.origin,
        "cases": rows,
        "summary": {
            "total": len(rows),
            "passed": sum(1 for row in rows if row["status"] == "PASS"),
            "failed": sum(1 for row in rows if row["status"] == "FAIL"),
        },
        "limitations": [
            "本地DEV_AUTH_BYPASS不代表真实飞书会话；认证/CSRF由隔离自动化测试覆盖。",
            "写接口、同步、推送和正式数据导出未在运行库上调用。",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
