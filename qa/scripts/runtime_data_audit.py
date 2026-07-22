from __future__ import annotations

import argparse
import json
import sqlite3
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from typing import Any

import yaml

ZERO = Decimal(0)
METRICS = (
    "period_overall_roi",
    "period_spend",
    "period_overall_amount",
    "period_net_roi",
    "period_net_amount",
    "period_overall_orders",
    "period_net_orders",
    "period_overall_order_cost",
    "period_net_order_cost",
    "period_gmv",
    "period_paid_amount",
    "period_order_count",
    "period_viewers",
    "period_buyers",
)


def decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def close(left: Decimal | None, right: Decimal | None, tolerance: Decimal = Decimal("1e-10")) -> bool:
    if left is None or right is None:
        return left is right
    return abs(left - right) <= tolerance * max(Decimal(1), abs(left), abs(right))


def request_json(url: str, parameters: list[tuple[str, str]]) -> tuple[int, dict[str, Any], int]:
    full_url = f"{url}?{urllib.parse.urlencode(parameters)}"
    with urllib.request.urlopen(full_url, timeout=30) as response:
        body = response.read()
        return response.status, json.loads(body.decode("utf-8")), len(body)


def load_catalog(path: Path) -> dict[str, dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {str(item["key"]): item for item in payload["metrics"]}


def aggregate(
    key: str,
    fact_ids: list[str],
    values_by_fact: dict[str, dict[str, Decimal | None]],
    catalog: dict[str, dict[str, Any]],
) -> Decimal | None:
    spec = catalog[key]
    kind = str(spec["aggregation"])
    if kind == "RATIO_OF_SUMS":
        numerator = str(spec.get("numerator") or "")
        denominator = str(spec.get("denominator") or "")
        if not numerator or not denominator:
            return None
        top = aggregate(numerator, fact_ids, values_by_fact, catalog)
        bottom = aggregate(denominator, fact_ids, values_by_fact, catalog)
        return None if top is None or bottom in {None, ZERO} else top / bottom
    values = [values_by_fact.get(fact_id, {}).get(key) for fact_id in fact_ids]
    present = [value for value in values if value is not None]
    if not present:
        return None
    if kind == "SUM":
        return sum(present, ZERO)
    if kind == "MAX":
        return max(present)
    if kind == "AVG":
        return sum(present, ZERO) / Decimal(len(present))
    if kind == "LAST":
        return present[-1]
    return None


def expected_kline(daily_values: list[tuple[date, Decimal]]) -> dict[str, Any] | None:
    if not daily_values:
        return None
    ordered = sorted(daily_values, key=lambda item: item[0])
    values = [item[1] for item in ordered]
    high_item = max(ordered, key=lambda item: item[1])
    low_item = min(ordered, key=lambda item: item[1])
    total = sum(values, ZERO)
    return {
        "open": values[0],
        "close": values[-1],
        "high": high_item[1],
        "low": low_item[1],
        "average": total / Decimal(len(values)),
        "median": median(values),
        "total": total,
        "effective_days": len(values),
        "first_date": ordered[0][0].isoformat(),
        "last_date": ordered[-1][0].isoformat(),
        "high_date": high_item[0].isoformat(),
        "low_date": low_item[0].isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--end-date", default="2026-07-15")
    parser.add_argument("--period-days", type=int, default=7)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--network-output", required=True)
    args = parser.parse_args()

    parameters: list[tuple[str, str]] = [
        ("end_date", args.end_date),
        ("period_days", str(args.period_days)),
        ("compare_enabled", "true"),
        ("aggregation_mode", "sum"),
        ("series_dimension", "summary"),
        ("include_today", "false"),
        ("include_in_progress", "true"),
    ]
    parameters.extend(("metric_ids", key) for key in METRICS)
    status, payload, payload_bytes = request_json(
        f"{args.api}/overview/hourly-comparison", parameters
    )
    overview_status, overview, overview_bytes = request_json(
        f"{args.api}/dashboard/overview",
        [("start_date", payload["current_period"]["start"]), ("end_date", payload["current_period"]["end"])],
    )
    targets_status, targets, targets_bytes = request_json(
        f"{args.api}/settings/room-metric-targets", []
    )

    database = Path(args.database).resolve()
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    catalog = load_catalog(Path(args.catalog))
    current_start = date.fromisoformat(payload["current_period"]["start"])
    current_end = date.fromisoformat(payload["current_period"]["end"])
    comparison_start = date.fromisoformat(payload["comparison_period"]["start"])
    comparison_end = date.fromisoformat(payload["comparison_period"]["end"])

    facts = list(
        connection.execute(
            """
            SELECT id, business_date, hour_order, hour_slot, data_status,
                   actual_anchor_canonical, anchor_schedule_status, latest_point_id,
                   latest_observed_at
            FROM hourly_facts
            WHERE business_date BETWEEN ? AND ?
            ORDER BY business_date, hour_order, room_id
            """,
            (comparison_start.isoformat(), current_end.isoformat()),
        )
    )
    valid_facts = [
        row
        for row in facts
        if row["data_status"] == "complete"
        and row["actual_anchor_canonical"]
        and row["actual_anchor_canonical"] != "用于计算"
    ]
    valid_ids = [str(row["id"]) for row in valid_facts]
    placeholders = ",".join("?" for _ in valid_ids)
    metric_keys_needed = set(METRICS)
    for key in tuple(metric_keys_needed):
        spec = catalog[key]
        if spec.get("numerator"):
            metric_keys_needed.add(str(spec["numerator"]))
        if spec.get("denominator"):
            metric_keys_needed.add(str(spec["denominator"]))
    values_by_fact: dict[str, dict[str, Decimal | None]] = defaultdict(dict)
    if valid_ids:
        key_placeholders = ",".join("?" for _ in metric_keys_needed)
        query = f"""
            SELECT hourly_fact_id, metric_key, numeric_value
            FROM hourly_metrics
            WHERE hourly_fact_id IN ({placeholders})
              AND metric_key IN ({key_placeholders})
              AND quality_status = 'valid'
        """
        for row in connection.execute(query, (*valid_ids, *sorted(metric_keys_needed))):
            values_by_fact[str(row["hourly_fact_id"])][str(row["metric_key"])] = decimal(
                row["numeric_value"]
            )

    points = payload["series"][0]["points"]
    comparisons: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    for point in points:
        hour_order = int(point["sort"])
        for period_name, start, end, api_values in (
            ("current", current_start, current_end, point["current"]),
            ("comparison", comparison_start, comparison_end, point["comparison"]),
        ):
            period_ids = [
                str(row["id"])
                for row in valid_facts
                if start <= date.fromisoformat(row["business_date"]) <= end
                and int(row["hour_order"]) == hour_order
            ]
            for key in METRICS:
                expected = aggregate(key, period_ids, values_by_fact, catalog)
                if key == "period_overall_roi":
                    actual = decimal(api_values.get("roi"))
                elif key == "period_spend":
                    actual = decimal(api_values.get("spend"))
                else:
                    actual = decimal((api_values.get("metrics") or {}).get(key))
                matched = close(expected, actual)
                row = {
                    "period": period_name,
                    "hour": point["hour"],
                    "metric": key,
                    "database": None if expected is None else str(expected),
                    "api": None if actual is None else str(actual),
                    "matched": matched,
                    "fact_count": len(period_ids),
                }
                comparisons.append(row)
                if not matched:
                    mismatches.append(row)

    kline_checks: list[dict[str, Any]] = []
    kline_mismatches: list[dict[str, Any]] = []
    for point in points:
        hour_order = int(point["sort"])
        for period_name, start, end, api_values in (
            ("current", current_start, current_end, point["current"]),
            ("comparison", comparison_start, comparison_end, point["comparison"]),
        ):
            period_rows = [
                row
                for row in valid_facts
                if start <= date.fromisoformat(row["business_date"]) <= end
                and int(row["hour_order"]) == hour_order
            ]
            by_date: dict[date, list[str]] = defaultdict(list)
            for row in period_rows:
                by_date[date.fromisoformat(row["business_date"])].append(str(row["id"]))
            for key, response_key in (
                ("period_overall_roi", "roi_ohlc"),
                ("period_spend", "spend_ohlc"),
            ):
                daily_values: list[tuple[date, Decimal]] = []
                for business_date, fact_ids in by_date.items():
                    value = aggregate(key, fact_ids, values_by_fact, catalog)
                    if value is not None:
                        daily_values.append((business_date, value))
                expected = expected_kline(daily_values)
                actual = api_values.get(response_key)
                for field in (
                    "open", "close", "high", "low", "average", "median", "total",
                    "effective_days", "first_date", "last_date", "high_date", "low_date",
                ):
                    expected_value = None if expected is None else expected[field]
                    actual_value = None if actual is None else actual.get(field)
                    if field in {"open", "close", "high", "low", "average", "median", "total"}:
                        matched = close(decimal(expected_value), decimal(actual_value))
                    else:
                        matched = expected_value == actual_value
                    check = {
                        "period": period_name,
                        "hour": point["hour"],
                        "metric": key,
                        "field": field,
                        "database": None if expected_value is None else str(expected_value),
                        "api": None if actual_value is None else str(actual_value),
                        "matched": matched,
                    }
                    kline_checks.append(check)
                    if not matched:
                        kline_mismatches.append(check)

    overview_by_key = {item["metric_key"]: item for item in overview.get("kpis", [])}
    overview_checks: list[dict[str, Any]] = []
    current_ids = [
        str(row["id"])
        for row in valid_facts
        if current_start <= date.fromisoformat(row["business_date"]) <= current_end
    ]
    for key in overview_by_key:
        if key not in catalog:
            continue
        expected = aggregate(key, current_ids, values_by_fact, catalog)
        actual = decimal(overview_by_key[key].get("value"))
        overview_checks.append(
            {
                "metric": key,
                "database": None if expected is None else str(expected),
                "api": None if actual is None else str(actual),
                "matched": close(expected, actual),
            }
        )

    all_metric_rows = list(
        connection.execute(
            """
            SELECT hm.hourly_fact_id, hm.metric_key, hm.numeric_value, hm.value_source,
                   hf.data_status, hf.latest_point_id, hf.latest_observed_at,
                   lp.observed_at AS point_observed_at, lp.valid AS point_valid,
                   lpm.numeric_value AS point_value
            FROM hourly_metrics hm
            JOIN hourly_facts hf ON hf.id = hm.hourly_fact_id
            LEFT JOIN live_points lp ON lp.id = hf.latest_point_id
            LEFT JOIN live_point_metrics lpm
              ON lpm.live_point_id = hf.latest_point_id AND lpm.metric_key = hm.metric_key
            """
        )
    )
    direct_source_mismatches = 0
    timestamp_mismatches = 0
    invalid_latest_points = 0
    for row in all_metric_rows:
        spec = catalog.get(str(row["metric_key"]))
        if not spec:
            continue
        if row["latest_point_id"] and row["point_valid"] != 1:
            invalid_latest_points += 1
        if row["latest_point_id"] and row["latest_observed_at"] != row["point_observed_at"]:
            timestamp_mismatches += 1
        if (
            str(spec["aggregation"]) != "RATIO_OF_SUMS"
            and row["value_source"] == "latest_point"
        ):
            if not close(
                decimal(row["numeric_value"]),
                decimal(row["point_value"]),
                tolerance=Decimal("1e-8"),
            ):
                direct_source_mismatches += 1

    noncomplete_metrics = connection.execute(
        """
        SELECT COUNT(*)
        FROM hourly_metrics hm JOIN hourly_facts hf ON hf.id=hm.hourly_fact_id
        WHERE hf.data_status <> 'complete'
        """
    ).fetchone()[0]
    duplicate_facts = connection.execute(
        """
        SELECT COUNT(*) FROM (
          SELECT room_id,business_date,hour_slot,COUNT(*) c FROM hourly_facts
          GROUP BY room_id,business_date,hour_slot HAVING c>1
        )
        """
    ).fetchone()[0]
    duplicate_metrics = connection.execute(
        """
        SELECT COUNT(*) FROM (
          SELECT hourly_fact_id,metric_key,COUNT(*) c FROM hourly_metrics
          GROUP BY hourly_fact_id,metric_key HAVING c>1
        )
        """
    ).fetchone()[0]

    coverage_denominator_differences: list[dict[str, Any]] = []
    for hour in range(24):
        period_rows = [
            row
            for row in facts
            if current_start <= date.fromisoformat(row["business_date"]) <= current_end
            and int(row["hour_order"]) == hour
        ]
        hourly_comparison_expected = sum(
            row["anchor_schedule_status"] not in {None, "off_air"} for row in period_rows
        )
        overview_expected = sum(
            row["anchor_schedule_status"] not in {None, "unassigned", "off_air"}
            for row in period_rows
        )
        if hourly_comparison_expected != overview_expected:
            coverage_denominator_differences.append(
                {
                    "hour": f"{hour:02d}-{hour + 1:02d}",
                    "hourly_comparison_expected": hourly_comparison_expected,
                    "overview_expected": overview_expected,
                    "difference": hourly_comparison_expected - overview_expected,
                }
            )

    db_targets = [
        {
            "room_name": row[0],
            "category": row[1],
            "value": str(decimal(row[2])),
            "enabled": bool(row[3]),
        }
        for row in connection.execute(
            "SELECT room_name,product_category,target_value,enabled FROM room_metric_targets ORDER BY room_name"
        )
    ]
    connection.close()

    expected_targets = {
        "柏瑞美-散粉": "1.81",
        "柏瑞美-妆前乳": "1.82",
        "Mistine-水散粉": "2",
    }
    target_checks = [
        {
            "room_name": item["room_name"],
            "actual": item["value"],
            "expected": expected_targets.get(item["room_name"]),
            "matched": decimal(item["value"]) == decimal(expected_targets.get(item["room_name"])),
            "enabled": item["enabled"],
        }
        for item in db_targets
        if item["room_name"] in expected_targets
    ]

    result = {
        "environment": {
            "database": database.name,
            "api": args.api,
            "http_status": status,
            "overview_http_status": overview_status,
            "targets_http_status": targets_status,
            "response_bytes": payload_bytes,
            "overview_response_bytes": overview_bytes,
            "targets_response_bytes": targets_bytes,
        },
        "periods": {
            "current": [str(current_start), str(current_end)],
            "comparison": [str(comparison_start), str(comparison_end)],
        },
        "hour_axis": {
            "count": len(payload.get("hours", [])),
            "point_count": len(points),
            "first": points[0]["hour"] if points else None,
            "last": points[-1]["hour"] if points else None,
            "sorts": [point["sort"] for point in points],
        },
        "database_api_comparisons": {
            "checks": len(comparisons),
            "mismatches": len(mismatches),
            "mismatch_details": mismatches[:100],
            "rows": comparisons,
        },
        "database_api_kline_comparisons": {
            "checks": len(kline_checks),
            "mismatches": len(kline_mismatches),
            "mismatch_details": kline_mismatches[:100],
            "rows": kline_checks,
        },
        "overview_checks": overview_checks,
        "database_integrity": {
            "all_hourly_metric_rows": len(all_metric_rows),
            "direct_latest_point_mismatches": direct_source_mismatches,
            "latest_observed_timestamp_mismatches": timestamp_mismatches,
            "invalid_latest_points_referenced": invalid_latest_points,
            "noncomplete_fact_metrics": noncomplete_metrics,
            "duplicate_facts": duplicate_facts,
            "duplicate_metrics": duplicate_metrics,
        },
        "coverage_denominator_differences": coverage_denominator_differences,
        "target_checks": target_checks,
        "conversion_metric_capabilities": {
            key: {
                "aggregation": catalog[key]["aggregation"],
                "supports_hourly_trend": bool(
                    catalog[key].get(
                        "supports_hourly_trend",
                        catalog[key]["scope"] in {"period", "derived"}
                        and catalog[key]["aggregation"] != "NONE",
                    )
                ),
                "numerator": catalog[key].get("numerator"),
                "denominator": catalog[key].get("denominator"),
            }
            for key in catalog
            if "conversion_rate" in key
        },
        "api_target_count": len(targets),
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    safe_network = {
        "request": {
            "path": "/api/v1/overview/hourly-comparison",
            "end_date": args.end_date,
            "period_days": args.period_days,
            "metric_ids": list(METRICS),
        },
        "response": {
            "status": status,
            "bytes": payload_bytes,
            "current_period": payload["current_period"],
            "comparison_period": payload["comparison_period"],
            "hours": payload["hours"],
            "points": points,
        },
    }
    Path(args.network_output).write_text(
        json.dumps(safe_network, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "checks": len(comparisons),
                "mismatches": len(mismatches),
                "kline_checks": len(kline_checks),
                "kline_mismatches": len(kline_mismatches),
                "integrity": result["database_integrity"],
                "coverage_difference_hours": len(coverage_denominator_differences),
                "target_checks": target_checks,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
