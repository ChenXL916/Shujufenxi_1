from __future__ import annotations

import base64
import gzip
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any, cast

from app.domain.cleaning import parse_business_datetime
from app.integrations.excel.reader import FixtureRecord, SourceRole, detect_source_role

MAX_EXPORT_BYTES = 50 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class BaseExportTable:
    table_id: str
    name: str
    declared_records: int
    field_names: tuple[str, ...]
    view_names: dict[str, str]
    source_role: SourceRole
    records: tuple[FixtureRecord, ...]


@dataclass(frozen=True)
class BaseExportSnapshot:
    filename: str
    base_token: str
    base_name: str
    tables: tuple[BaseExportTable, ...]


def read_base_export(path: Path) -> BaseExportSnapshot:
    if path.stat().st_size > MAX_EXPORT_BYTES:
        raise ValueError("飞书 .base 导出文件超过 50 MiB 安全上限")
    try:
        outer = json.loads(path.read_text(encoding="utf-8"))
        encoded_snapshot = outer["gzipSnapshot"]
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("不是可识别的飞书 .base 导出文件") from exc
    if not isinstance(encoded_snapshot, str):
        raise ValueError("飞书 .base 导出缺少 gzipSnapshot")

    try:
        compressed = base64.b64decode(encoded_snapshot, validate=True)
        with gzip.GzipFile(fileobj=BytesIO(compressed)) as stream:
            raw_snapshot = stream.read(MAX_SNAPSHOT_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise ValueError("飞书 .base 快照解压失败") from exc
    if len(raw_snapshot) > MAX_SNAPSHOT_BYTES:
        raise ValueError("飞书 .base 快照解压后超过 100 MiB 安全上限")
    try:
        schemas = json.loads(raw_snapshot)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("飞书 .base 快照不是有效 JSON") from exc
    if not isinstance(schemas, list) or not schemas:
        raise ValueError("飞书 .base 快照中没有数据表")

    first_schema = _schema(schemas[0])
    base = _mapping(first_schema.get("base"))
    base_token = str(base.get("token") or "")
    base_name = str(base.get("name") or path.stem)
    tables: dict[str, BaseExportTable] = {}
    for item in schemas:
        schema = _schema(item)
        table = _decode_table(schema)
        if table is None:
            continue
        previous = tables.get(table.table_id)
        if previous is None or len(table.records) > len(previous.records):
            tables[table.table_id] = table
    if not tables:
        raise ValueError("飞书 .base 快照中没有可识别的数据表结构")
    return BaseExportSnapshot(
        filename=path.name,
        base_token=base_token,
        base_name=base_name,
        tables=tuple(tables.values()),
    )


def _schema(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict) or not isinstance(item.get("schema"), dict):
        raise ValueError("飞书 .base 快照的数据表结构无效")
    return cast(dict[str, Any], item["schema"])


def _mapping(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _decode_table(schema: dict[str, Any]) -> BaseExportTable | None:
    data = _mapping(schema.get("data"))
    table = _mapping(data.get("table"))
    meta = _mapping(table.get("meta"))
    table_id = str(meta.get("id") or "")
    if not table_id:
        return None
    table_map = _mapping(schema.get("tableMap"))
    table_entry = _mapping(table_map.get(table_id))
    table_name = str(table_entry.get("name") or meta.get("name") or table_id)
    field_map = _mapping(table.get("fieldMap"))
    field_names = tuple(
        str(field.get("name"))
        for field in field_map.values()
        if isinstance(field, dict) and field.get("name")
    )
    role = detect_source_role(set(field_names))
    record_map = _mapping(data.get("recordMap"))
    decoded_records = tuple(
        _decode_record(record_id, cells, field_map, role, table_name)
        for record_id, cells in record_map.items()
        if isinstance(cells, dict)
    )
    records = (
        _enrich_live_formula_fields(decoded_records) if role == "live_actual" else decoded_records
    )
    view_map = _mapping(table.get("viewMap"))
    view_names = {
        str(view_id): str(view.get("name") or view_id)
        for view_id, view in view_map.items()
        if isinstance(view, dict)
    }
    return BaseExportTable(
        table_id=table_id,
        name=table_name,
        declared_records=int(meta.get("recordsNum") or len(records)),
        field_names=field_names,
        view_names=view_names,
        source_role=role,
        records=records,
    )


def _decode_record(
    record_id: Any,
    cells: dict[str, Any],
    field_map: dict[str, Any],
    role: SourceRole,
    table_name: str,
) -> FixtureRecord:
    fields: dict[str, Any] = {}
    for field_id, definition in field_map.items():
        if not isinstance(definition, dict) or not definition.get("name"):
            continue
        fields[str(definition["name"])] = _decode_cell(cells.get(field_id), definition)
    return _fixture_record(str(record_id), role, table_name, fields)


def _fixture_record(
    record_id: str, role: SourceRole, table_name: str, fields: dict[str, Any]
) -> FixtureRecord:
    encoded = json.dumps(
        fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return FixtureRecord(
        source_record_id=record_id,
        source_role=role,
        default_room_name=table_name if role == "live_actual" else None,
        raw_fields=fields,
        payload_hash=hashlib.sha256(encoded).hexdigest(),
    )


def _decode_cell(cell: Any, definition: dict[str, Any]) -> Any:
    if cell is None:
        return None
    value = cell.get("value") if isinstance(cell, dict) and "value" in cell else cell
    if value is None:
        return None
    property_value = definition.get("property")
    field_property = property_value if isinstance(property_value, dict) else {}
    options = field_property.get("options")
    if isinstance(options, list):
        option_names = {
            str(option.get("id")): option.get("name")
            for option in options
            if isinstance(option, dict) and option.get("id")
        }
        if isinstance(value, str) and value in option_names:
            return option_names[value]
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return [option_names.get(item, item) for item in value]
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        parts = [
            item.get("text") or item.get("name") or item.get("value")
            for item in value
            if item.get("text") or item.get("name") or item.get("value")
        ]
        if len(parts) == 1:
            return parts[0]
        if parts:
            return "".join(str(part) for part in parts)
    return value


def _enrich_live_formula_fields(
    records: tuple[FixtureRecord, ...],
) -> tuple[FixtureRecord, ...]:
    by_day: dict[Any, list[FixtureRecord]] = defaultdict(list)
    updated = {record.source_record_id: dict(record.raw_fields) for record in records}
    for record in records:
        value = record.raw_fields.get("时间")
        if value is None:
            continue
        try:
            observed_at = parse_business_datetime(value)
        except ValueError:
            continue
        by_day[observed_at.date()].append(record)

    cumulative_sources = {
        "整体成交金额（元）": "时段整体成交金额",
        "整体成交订单数": "时段整体成交订单数",
        "消耗": "时段消耗",
        "净成交金额": "时段净成交金额",
        "净成交订单数": "时段净成交订单数",
    }
    difference_sources = {
        "时段成交金额": "直播间成交金额",
        "时段支付金额": "直播间用户支付金额",
        "时段成交单数": "成交订单数",
        "时段成交人数": "成交人数",
        "时段观看人数": "直播间观看人数",
        "_时段曝光人数": "直播间曝光人数",
        "_时段商品曝光人数": "商品曝光人数",
        "_时段商品点击人数": "商品点击人数",
    }
    for day_records in by_day.values():
        day_records.sort(key=lambda item: parse_business_datetime(item.raw_fields["时间"]))
        cumulative = {name: Decimal(0) for name in cumulative_sources}
        for index, record in enumerate(day_records):
            fields = updated[record.source_record_id]
            for target, source in cumulative_sources.items():
                value = _decimal(fields.get(source))
                if value is not None:
                    cumulative[target] += value
                _set_if_empty(fields, target, cumulative[target])

            next_fields = (
                updated[day_records[index + 1].source_record_id]
                if index + 1 < len(day_records)
                else None
            )
            differences: dict[str, Decimal | None] = {}
            if next_fields is not None:
                for target, source in difference_sources.items():
                    current = _decimal(fields.get(source))
                    following = _decimal(next_fields.get(source))
                    differences[target] = (
                        following - current
                        if current is not None and following is not None
                        else None
                    )
                    if not target.startswith("_"):
                        _set_if_empty(fields, target, differences[target])

            _set_if_empty(
                fields,
                "时段笔单价",
                _ratio(differences.get("时段支付金额"), differences.get("时段成交单数")),
            )
            period_buyers = differences.get("时段成交人数")
            period_viewers = differences.get("时段观看人数")
            period_impressions = differences.get("_时段曝光人数")
            period_product_impressions = differences.get("_时段商品曝光人数")
            period_clickers = differences.get("_时段商品点击人数")
            _set_if_empty(
                fields,
                "时段观看-成交率（人数）",
                _ratio(period_buyers, period_viewers),
            )
            _set_if_empty(
                fields,
                "时段曝光-观看率(人数）",
                _ratio(period_viewers, period_impressions),
            )
            _set_if_empty(
                fields,
                "时段观看-商品曝光率(人数）",
                _ratio(period_product_impressions, period_viewers),
            )
            _set_if_empty(
                fields,
                "时段商品曝光-点击率(人数）",
                _ratio(period_clickers, period_product_impressions),
            )
            _set_if_empty(
                fields,
                "时段商品点击-成交转化率(人数）",
                _ratio(period_buyers, period_clickers),
            )
            _set_if_empty(
                fields,
                "时段曝光-成交转化率（人数）",
                _ratio(period_buyers, period_impressions),
            )
            spend = cumulative["消耗"]
            overall_amount = cumulative["整体成交金额（元）"]
            overall_orders = cumulative["整体成交订单数"]
            net_amount = cumulative["净成交金额"]
            net_orders = cumulative["净成交订单数"]
            _set_if_empty(fields, "整体支付ROI", _ratio(overall_amount, spend))
            _set_if_empty(fields, "整体成交订单成本（元）", _ratio(spend, overall_orders))
            _set_if_empty(fields, "净支付ROI", _ratio(net_amount, spend))
            _set_if_empty(fields, "净成交订单成本（元）", _ratio(spend, net_orders))

    return tuple(
        _fixture_record(
            record.source_record_id,
            record.source_role,
            record.default_room_name or "",
            updated[record.source_record_id],
        )
        for record in records
    )


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == Decimal(0):
        return None
    return numerator / denominator


def _set_if_empty(fields: dict[str, Any], name: str, value: Decimal | None) -> None:
    if fields.get(name) is None and value is not None:
        fields[name] = str(value)
