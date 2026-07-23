from __future__ import annotations

import csv
import io
import uuid
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Any, Literal

from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AccessScope
from app.domain.aggregation import MetricObservation, aggregate_metric
from app.domain.metrics import MetricCatalog
from app.models.entities import HourlyFact, HourlyMetric, Room
from app.services.comparison_service import ComparisonService
from app.services.dashboard_query_service import DashboardFilters, DashboardQueryService

Dimension = Literal["anchor", "control", "pairing"]


class AnalysisService:
    DEFAULT_METRICS = (
        "period_overall_amount",
        "period_spend",
        "period_overall_roi",
        "period_net_roi",
        "period_order_count",
        "period_overall_order_cost",
        "period_viewers",
        "period_buyers",
    )
    METRICS = DEFAULT_METRICS

    def __init__(
        self,
        session: Session,
        catalog: MetricCatalog,
        access: AccessScope,
    ) -> None:
        self.session = session
        self.catalog = catalog
        self.access = access
        self.dashboard = DashboardQueryService(session, catalog, access)

    def summary(
        self,
        dimension: Dimension,
        filters: DashboardFilters,
        metric_keys: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        selected_metrics = self._selected_metrics(metric_keys)
        facts = self.dashboard._facts(filters)
        grouped: dict[str, list[HourlyFact]] = defaultdict(list)
        for fact in facts:
            key = self._dimension_key(fact, dimension)
            if key:
                grouped[key].append(fact)
        rows: list[dict[str, Any]] = []
        for label, group in grouped.items():
            observations = self.dashboard._observations(group)
            row: dict[str, Any] = {"key": label, "name": label, "valid_hours": len(group)}
            for metric in selected_metrics:
                row[metric] = aggregate_metric(metric, observations, self.catalog)
            rooms = {str(fact.room_id) for fact in group}
            row["room_count"] = len(rooms)
            rows.append(row)
        return sorted(
            rows,
            key=lambda row: self._sort_value(row, selected_metrics),
            reverse=True,
        )

    def _selected_metrics(self, metric_keys: tuple[str, ...]) -> tuple[str, ...]:
        requested = metric_keys or self.DEFAULT_METRICS
        return tuple(dict.fromkeys(key for key in requested if key in self.catalog.by_key))

    def anchor_hours(
        self,
        filters: DashboardFilters,
        metric_keys: tuple[str, ...] = (),
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        selected_metrics = self._selected_metrics(metric_keys)
        if filters.anchor_members:
            matching_facts = [
                fact
                for fact in self.dashboard._facts(filters)
                if fact.actual_anchor_canonical is not None
            ]
            total = len(matching_facts)
            start = (page - 1) * page_size
            page_facts = matching_facts[start : start + page_size]
        else:
            query = self.dashboard._fact_query(filters).where(
                HourlyFact.actual_anchor_canonical.is_not(None)
            )
            total = int(
                self.session.scalar(
                    select(func.count()).select_from(query.order_by(None).subquery())
                )
                or 0
            )
            page_facts = list(
                self.session.scalars(
                    query.order_by(
                        HourlyFact.business_date.desc(),
                        HourlyFact.hour_order,
                        HourlyFact.room_id,
                        HourlyFact.id,
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )

        room_names = self.room_names()
        observations: dict[uuid.UUID, list[MetricObservation]] = defaultdict(list)
        if page_facts:
            facts_by_id = {fact.id: fact for fact in page_facts}
            for metric in self.session.scalars(
                select(HourlyMetric).where(HourlyMetric.hourly_fact_id.in_(facts_by_id))
            ):
                fact = facts_by_id[metric.hourly_fact_id]
                observations[fact.id].append(
                    MetricObservation(
                        room_id=str(fact.room_id),
                        business_date=fact.business_date,
                        hour_order=fact.hour_order,
                        metric_key=metric.metric_key,
                        value=metric.numeric_value,
                    )
                )

        items = [
            {
                "key": str(fact.id),
                "fact_id": fact.id,
                "business_date": fact.business_date,
                "hour_slot": fact.hour_slot,
                "hour_order": fact.hour_order,
                "room_id": fact.room_id,
                "room_name": room_names.get(fact.room_id, "未知直播间"),
                "anchor_name": fact.actual_anchor_canonical or "未标记主播",
                "control_name": fact.actual_control_canonical,
                "latest_observed_at": fact.latest_observed_at,
                "anchor_match_status": fact.anchor_match_status,
                "data_status": fact.data_status,
                "metrics": {
                    metric: aggregate_metric(metric, observations[fact.id], self.catalog)
                    for metric in selected_metrics
                },
            }
            for fact in page_facts
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "metric_keys": list(selected_metrics),
        }

    @staticmethod
    def _sort_value(row: dict[str, Any], metric_keys: tuple[str, ...]) -> Decimal:
        preferred = "period_overall_amount"
        if preferred in row:
            return row[preferred] or Decimal(0)
        if metric_keys:
            return row.get(metric_keys[0]) or Decimal(0)
        return Decimal(row["valid_hours"])

    def comparisons(
        self,
        filters: DashboardFilters,
        comparison_type: Literal["previous_day", "previous_week", "previous_month"],
        metric_keys: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        current = self.dashboard._observations(self.dashboard._facts(filters))
        baseline_filters = self._baseline_filters(filters, comparison_type)
        baseline = self.dashboard._observations(self.dashboard._facts(baseline_filters))
        rows: list[dict[str, Any]] = []
        for key in metric_keys:
            if key not in self.catalog.by_key:
                continue
            spec = self.catalog.by_key[key]
            result = ComparisonService().compare(
                aggregate_metric(key, current, self.catalog),
                aggregate_metric(key, baseline, self.catalog),
                metric_label=spec.field,
                baseline_label=self._baseline_label(comparison_type),
            )
            rows.append(
                {
                    "metric_key": key,
                    "name": spec.field,
                    "unit": spec.unit,
                    **result.__dict__,
                }
            )
        return rows

    def pivot(self, filters: DashboardFilters) -> list[dict[str, Any]]:
        facts = self.dashboard._facts(filters)
        anchors: dict[str, list[HourlyFact]] = defaultdict(list)
        for fact in facts:
            anchors[fact.actual_anchor_canonical or "未标记主播"].append(fact)
        return [
            self._pivot_node(anchor, group, "anchor") for anchor, group in sorted(anchors.items())
        ]

    def export_pivot(
        self, filters: DashboardFilters, file_format: Literal["csv", "xlsx"]
    ) -> tuple[bytes, str, str]:
        self.assert_export_allowed(filters)
        rows = self._flat_export_rows(filters)
        headers = [
            "直播间ID",
            "直播间",
            "主播",
            "场控",
            "日期",
            "自然小时",
            "时段整体成交金额",
            "时段消耗",
            "时段整体支付ROI",
            "时段成交订单数",
        ]
        if file_format == "csv":
            stream = io.StringIO(newline="")
            writer = csv.writer(stream)
            writer.writerow(headers)
            for row in rows:
                writer.writerow([self._safe_cell(value) for value in row])
            return stream.getvalue().encode("utf-8-sig"), "text/csv", "live-ops-pivot.csv"
        workbook = Workbook()
        sheet = workbook.active
        assert sheet is not None
        sheet.title = "主播场控时间汇总"
        sheet.append(headers)
        for row in rows:
            sheet.append([self._safe_cell(value) for value in row])
        stream_bytes = io.BytesIO()
        workbook.save(stream_bytes)
        return (
            stream_bytes.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "live-ops-pivot.xlsx",
        )

    def assert_export_allowed(self, filters: DashboardFilters) -> None:
        if not self.access.can_export:
            raise PermissionError("当前账号没有导出权限")
        if self.access.export_room_ids is None:
            return
        requested = set(filters.room_ids)
        if self.access.room_ids is None:
            selected = requested or None
        elif requested:
            selected = set(self.access.room_ids).intersection(requested)
        else:
            selected = set(self.access.room_ids)
        if selected is None or not selected.issubset(self.access.export_room_ids):
            raise PermissionError("所选范围包含无导出权限的直播间")

    def _pivot_node(self, label: str, facts: list[HourlyFact], level: str) -> dict[str, Any]:
        node = self._summary_values(label, facts, level)
        if level == "anchor":
            controls: dict[str, list[HourlyFact]] = defaultdict(list)
            for fact in facts:
                controls[fact.actual_control_canonical or "未标记场控"].append(fact)
            node["children"] = [
                self._pivot_node(control, group, "control")
                for control, group in sorted(controls.items())
            ]
        elif level == "control":
            dates: dict[str, list[HourlyFact]] = defaultdict(list)
            for fact in facts:
                dates[fact.business_date.isoformat()].append(fact)
            node["children"] = [
                self._pivot_node(day, group, "date") for day, group in sorted(dates.items())
            ]
        elif level == "date":
            node["children"] = [
                self._summary_values(fact.hour_slot, [fact], "hour")
                for fact in sorted(facts, key=lambda item: item.hour_order)
            ]
        return node

    def _summary_values(self, label: str, facts: list[HourlyFact], level: str) -> dict[str, Any]:
        observations = self.dashboard._observations(facts)
        return {
            "key": f"{level}:{label}:{facts[0].id}",
            "level": level,
            "label": label,
            "valid_hours": len(facts),
            **{
                metric: aggregate_metric(metric, observations, self.catalog)
                for metric in self.METRICS
            },
        }

    def _flat_export_rows(self, filters: DashboardFilters) -> list[list[Any]]:
        facts = self.dashboard._facts(filters)
        room_names = self.room_names()
        rows = []
        for fact in facts:
            observations = self.dashboard._observations([fact])
            rows.append(
                [
                    str(fact.room_id),
                    room_names.get(fact.room_id, "未知直播间"),
                    fact.actual_anchor_canonical,
                    fact.actual_control_canonical,
                    fact.business_date.isoformat(),
                    fact.hour_slot,
                    aggregate_metric("period_overall_amount", observations, self.catalog),
                    aggregate_metric("period_spend", observations, self.catalog),
                    aggregate_metric("period_overall_roi", observations, self.catalog),
                    aggregate_metric("period_order_count", observations, self.catalog),
                ]
            )
        return rows

    def room_names(self) -> dict[uuid.UUID, str]:
        query = select(Room)
        if self.access.room_ids is not None:
            query = query.where(Room.id.in_(self.access.room_ids))
        return {room.id: room.name for room in self.session.scalars(query)}

    @staticmethod
    def _dimension_key(fact: HourlyFact, dimension: Dimension) -> str | None:
        if dimension == "anchor":
            return fact.actual_anchor_canonical
        if dimension == "control":
            return fact.actual_control_canonical
        if not fact.actual_anchor_canonical and not fact.actual_control_canonical:
            return None
        return (
            f"{fact.actual_anchor_canonical or '未标记主播'} × "
            f"{fact.actual_control_canonical or '未标记场控'}"
        )

    @staticmethod
    def _baseline_filters(
        filters: DashboardFilters,
        comparison_type: Literal["previous_day", "previous_week", "previous_month"],
    ) -> DashboardFilters:
        start, end = filters.start_date, filters.end_date or filters.start_date
        if not start or not end:
            return filters
        if comparison_type == "previous_week":
            delta = timedelta(days=7)
        elif comparison_type == "previous_month":
            previous_end = start.replace(day=1) - timedelta(days=1)
            days = (end - start).days
            return DashboardFilters(
                start_date=previous_end.replace(day=1),
                end_date=min(previous_end, previous_end.replace(day=1) + timedelta(days=days)),
                room_ids=filters.room_ids,
                anchor_names=filters.anchor_names,
                anchor_members=filters.anchor_members,
                control_names=filters.control_names,
                hour_slots=filters.hour_slots,
            )
        else:
            delta = timedelta(days=1)
        return DashboardFilters(
            start_date=start - delta,
            end_date=end - delta,
            room_ids=filters.room_ids,
            anchor_names=filters.anchor_names,
            anchor_members=filters.anchor_members,
            control_names=filters.control_names,
            hour_slots=filters.hour_slots,
        )

    @staticmethod
    def _baseline_label(comparison_type: str) -> str:
        return {
            "previous_day": "昨日同小时",
            "previous_week": "上周同小时",
            "previous_month": "上月同期",
        }.get(comparison_type, "基准同小时")

    @staticmethod
    def _safe_cell(value: Any) -> Any:
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
            return f"'{value}"
        return value
