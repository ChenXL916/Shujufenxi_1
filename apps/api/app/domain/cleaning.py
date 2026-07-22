from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from zoneinfo import ZoneInfo

from openpyxl.utils.datetime import from_excel

SHANGHAI = ZoneInfo("Asia/Shanghai")
EMPTY_NUMBERS = {"", "-", "—", "N/A", "n/a", "None"}
SPECIAL_INVALID_ANCHORS = {"", "用于计算"}
COMBINATION_SEPARATOR = re.compile(r"[+＋/、&]")
DAY_COLUMN = re.compile(r"^(?:[1-9]|[12]\d|3[01])日$")


@dataclass(frozen=True)
class HourSlot:
    label: str
    order: int
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class PersonName:
    raw: str
    canonical: str
    base_name: str
    prefix: str | None
    members: tuple[str, ...]
    note: str | None


@dataclass(frozen=True)
class AnchorScheduleRow:
    room_name: str
    schedule_date: date
    hour_slot: str
    hour_order: int
    planned_anchor_raw: str | None
    planned_anchor_canonical: str | None
    planned_anchor_base_names: tuple[str, ...]
    schedule_status: Literal["scheduled", "combination", "off_air", "unassigned"]


@dataclass(frozen=True)
class ShiftValue:
    name: str | None
    start: time | None
    end: time | None
    crosses_midnight: bool
    is_rest: bool
    time_configured: bool


@dataclass(frozen=True)
class StaffScheduleRow:
    person_name: str
    role: str
    employment_status: str | None
    schedule_date: date
    shift: ShiftValue


def parse_business_datetime(value: Any) -> datetime:
    parsed: datetime
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    elif isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 10_000_000_000:
            parsed = datetime.fromtimestamp(numeric / 1000, tz=SHANGHAI)
        elif numeric > 1_000_000_000:
            parsed = datetime.fromtimestamp(numeric, tz=SHANGHAI)
        else:
            parsed = from_excel(numeric)
    elif isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = datetime.strptime(text, "%Y/%m/%d %H:%M:%S")
    else:
        raise ValueError(f"不支持的日期类型: {type(value).__name__}")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=SHANGHAI)
    return parsed.astimezone(SHANGHAI)


def normalize_hour_slot(value: Any, business_date: date) -> HourSlot:
    text = str(value or "").strip().replace("时段", "").replace("：", ":")
    match = re.fullmatch(r"(\d{1,2})(?::00)?-(\d{1,2})(?::00)?", text)
    if not match:
        raise ValueError("时段格式无法识别")
    start, end = (int(part) for part in match.groups())
    if start == 0 and end == 0:
        raise ValueError("0:00-0:00 不是有效自然小时")
    expected_end = 24 if start == 23 else start + 1
    if not 0 <= start <= 23 or end != expected_end:
        raise ValueError("时段必须是连续一个自然小时")
    start_at = datetime.combine(business_date, time(start), tzinfo=SHANGHAI)
    end_at = start_at + timedelta(hours=1)
    return HourSlot(f"{start:02d}-{end:02d}", start, start_at, end_at)


def normalize_person_name(value: Any) -> PersonName | None:
    raw = plain_text_value(value)
    cleaned = raw.lstrip("@").strip()
    if cleaned in SPECIAL_INVALID_ANCHORS or cleaned == "断播":
        return None
    note_match = re.search(r"[（(]([^）)]+)[）)]\s*$", cleaned)
    note = note_match.group(1).strip() if note_match else None
    canonical = cleaned[: note_match.start()].strip() if note_match else cleaned
    member_values = [
        part.strip() for part in COMBINATION_SEPARATOR.split(canonical) if part.strip()
    ]
    base_members: list[str] = []
    first_prefix: str | None = None
    for member in member_values:
        prefix_match = re.match(r"^([A-Za-z]+)-(.+)$", member)
        if prefix_match:
            first_prefix = first_prefix or prefix_match.group(1).upper()
            base_members.append(prefix_match.group(2).strip())
        else:
            base_members.append(member)
    if not base_members:
        return None
    return PersonName(
        raw=raw,
        canonical=canonical,
        base_name=base_members[0],
        prefix=first_prefix,
        members=tuple(sorted(set(base_members))),
        note=note,
    )


def plain_text_value(value: Any) -> str:
    """Flatten Feishu rich-text field values while preserving ordinary fixture text."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "".join(plain_text_value(item) for item in value).strip()
    if isinstance(value, dict):
        for key in ("text", "name", "value"):
            if key in value:
                return plain_text_value(value[key])
    return str(value).strip()


def parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in EMPTY_NUMBERS:
        return None
    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1].strip()
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"无法解析数字: {value}") from exc
    return result / Decimal(100) if is_percent else result


def invalid_live_record_reason(record: dict[str, Any]) -> str | None:
    if not any(value not in {None, ""} for value in record.values()):
        return "空行"
    anchor = plain_text_value(record.get("主播"))
    if not anchor:
        return "主播为空"
    if anchor == "用于计算":
        return "用于计算"
    if plain_text_value(record.get("自动检查")) == "错误":
        return "自动检查错误"
    try:
        observed = parse_business_datetime(record.get("时间"))
        normalize_hour_slot(record.get("时段"), observed.date())
    except (TypeError, ValueError) as exc:
        return str(exc)
    return None


def month_number(value: Any) -> int:
    match = re.search(r"(1[0-2]|[1-9])", str(value or ""))
    if not match:
        raise ValueError("月份无法解析")
    return int(match.group(1))


def unpivot_anchor_schedule(record: dict[str, Any], year: int) -> list[AnchorScheduleRow]:
    room_name = str(record.get("直播间") or "").strip()
    month = month_number(record.get("月份"))
    slot = normalize_hour_slot(record.get("时段"), date(year, month, 1))
    rows: list[AnchorScheduleRow] = []
    for column, value in record.items():
        if not DAY_COLUMN.fullmatch(column):
            continue
        day = int(column[:-1])
        try:
            schedule_date = date(year, month, day)
        except ValueError:
            continue
        raw = str(value).strip() if value not in {None, ""} else None
        person = normalize_person_name(raw)
        if raw == "断播":
            status: Literal["scheduled", "combination", "off_air", "unassigned"] = "off_air"
        elif person is None:
            status = "unassigned"
        elif len(person.members) > 1:
            status = "combination"
        else:
            status = "scheduled"
        rows.append(
            AnchorScheduleRow(
                room_name=room_name,
                schedule_date=schedule_date,
                hour_slot=slot.label,
                hour_order=slot.order,
                planned_anchor_raw=raw,
                planned_anchor_canonical=person.canonical if person else None,
                planned_anchor_base_names=person.members if person else (),
                schedule_status=status,
            )
        )
    return rows


def parse_shift(value: Any) -> ShiftValue:
    raw = str(value or "").strip()
    if not raw:
        return ShiftValue(None, None, None, False, False, False)
    if raw == "休息":
        return ShiftValue(raw, None, None, False, True, True)
    match = re.fullmatch(r"(\d{2})-(\d{2})", raw)
    if not match:
        return ShiftValue(raw, None, None, False, False, False)
    start_hour, end_hour = (int(part) for part in match.groups())
    if start_hour > 23 or end_hour > 23:
        return ShiftValue(raw, None, None, False, False, False)
    return ShiftValue(
        raw,
        time(start_hour),
        time(end_hour),
        end_hour <= start_hour,
        False,
        True,
    )


def unpivot_staff_schedule(record: dict[str, Any], year: int) -> list[StaffScheduleRow]:
    person_name = str(record.get("姓名") or "").strip()
    if not person_name or person_name == "断播":
        return []
    month = month_number(record.get("月份"))
    rows: list[StaffScheduleRow] = []
    for column, value in record.items():
        if not DAY_COLUMN.fullmatch(column):
            continue
        try:
            schedule_date = date(year, month, int(column[:-1]))
        except ValueError:
            continue
        rows.append(
            StaffScheduleRow(
                person_name=person_name,
                role=str(record.get("岗位") or "").strip(),
                employment_status=str(record.get("状态") or "").strip() or None,
                schedule_date=schedule_date,
                shift=parse_shift(value),
            )
        )
    return rows
