from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path

from app.integrations.feishu.base_export import read_base_export


def _write_export(path: Path) -> None:
    fields = {
        "anchor": {
            "name": "主播",
            "type": 3,
            "property": {"options": [{"id": "anchor-1", "name": "J-兰婷"}]},
        },
        "control": {
            "name": "场控",
            "type": 3,
            "property": {"options": [{"id": "control-1", "name": "杨奇文"}]},
        },
        "check": {"name": "自动检查", "type": 1, "property": None},
        "time": {"name": "时间", "type": 5, "property": None},
        "slot": {"name": "时段", "type": 1, "property": None},
        "amount": {"name": "时段成交金额", "type": 2, "property": None},
        "room_amount": {"name": "直播间成交金额", "type": 2, "property": None},
    }
    schema = {
        "schema": {
            "base": {"token": "base-token", "name": "直播数据"},
            "tableMap": {"table-1": {"id": "table-1", "name": "柏瑞美-散粉"}},
            "data": {
                "table": {
                    "meta": {"id": "table-1", "recordsNum": 2},
                    "fieldMap": fields,
                    "viewMap": {"view-1": {"name": "默认视图"}},
                },
                "recordMap": {
                    "record-1": {
                        "anchor": {"value": "anchor-1"},
                        "control": {"value": "control-1"},
                        "check": {"value": [{"type": "text", "text": "正确"}]},
                        "time": {"value": 1783616400000},
                        "slot": {"value": [{"type": "text", "text": "1:00-2:00"}]},
                        "room_amount": {"value": 1000},
                    },
                    "record-2": {
                        "anchor": {"value": "anchor-1"},
                        "control": {"value": "control-1"},
                        "check": {"value": [{"type": "text", "text": "正确"}]},
                        "time": {"value": 1783620000000},
                        "slot": {"value": [{"type": "text", "text": "2:00-3:00"}]},
                        "room_amount": {"value": 1300},
                    },
                },
                "recordMeta": {},
            },
            "owner": "owner",
            "structVersion": 1,
        }
    }
    encoded = base64.b64encode(
        gzip.compress(json.dumps([schema], ensure_ascii=False).encode())
    ).decode()
    path.write_text(json.dumps({"gzipSnapshot": encoded}), encoding="utf-8")


def test_reads_feishu_base_snapshot_and_decodes_cells(tmp_path: Path) -> None:
    path = tmp_path / "live.base"
    _write_export(path)

    snapshot = read_base_export(path)

    assert snapshot.base_token == "base-token"  # noqa: S105 - synthetic fixture identifier
    assert snapshot.base_name == "直播数据"
    assert len(snapshot.tables) == 1
    table = snapshot.tables[0]
    assert table.name == "柏瑞美-散粉"
    assert table.source_role == "live_actual"
    assert table.declared_records == 2
    assert table.view_names == {"view-1": "默认视图"}
    record = table.records[0]
    assert record.source_record_id == "record-1"
    assert record.default_room_name == "柏瑞美-散粉"
    assert record.raw_fields["主播"] == "J-兰婷"
    assert record.raw_fields["场控"] == "杨奇文"
    assert record.raw_fields["自动检查"] == "正确"
    assert record.raw_fields["时段"] == "1:00-2:00"
    assert record.raw_fields["时段成交金额"] == "300"
