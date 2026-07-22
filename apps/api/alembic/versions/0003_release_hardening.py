"""Apply release-hardening metric metadata fixes.

Revision ID: 0003_release_hardening
Revises: 0002_hourly_comparison
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_release_hardening"
down_revision = "0002_hourly_comparison"
branch_labels = None
depends_on = None

METRIC_KEY = "period_view_conversion_rate"


def _metric_definitions() -> sa.TableClause:
    return sa.table(
        "metric_definitions",
        sa.column("metric_key", sa.String(100)),
        sa.column("scope", sa.String(30)),
        sa.column("aggregation_strategy", sa.String(40)),
        sa.column("numerator_metric_key", sa.String(100)),
        sa.column("denominator_metric_key", sa.String(100)),
        sa.column("comparable", sa.Boolean()),
        sa.column("supports_hourly_trend", sa.Boolean()),
        sa.column("supports_kline", sa.Boolean()),
        sa.column("is_cumulative", sa.Boolean()),
        sa.column("description", sa.Text()),
    )


def upgrade() -> None:
    metrics = _metric_definitions()
    op.get_bind().execute(
        metrics.update()
        .where(metrics.c.metric_key == METRIC_KEY)
        .values(
            scope="derived",
            aggregation_strategy="RATIO_OF_SUMS",
            numerator_metric_key="period_buyers",
            denominator_metric_key="period_viewers",
            comparable=True,
            supports_hourly_trend=True,
            supports_kline=True,
            is_cumulative=False,
            description="derived 指标，汇总口径 RATIO_OF_SUMS",
        )
    )


def downgrade() -> None:
    metrics = _metric_definitions()
    op.get_bind().execute(
        metrics.update()
        .where(metrics.c.metric_key == METRIC_KEY)
        .values(
            scope="period",
            aggregation_strategy="NONE",
            numerator_metric_key=None,
            denominator_metric_key=None,
            comparable=False,
            supports_hourly_trend=False,
            supports_kline=False,
            is_cumulative=False,
            description="period 指标，汇总口径 NONE",
        )
    )
