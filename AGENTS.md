# Repository instructions

## Mission
Build and maintain the production-ready Chinese application “多直播间小时数据驾驶舱”. Read `MASTER_PROMPT.md` and `docs/EXEC_PLAN.md` before changing code.

## Non-negotiable business rules
- Hourly charts use period/hour fields, not cumulative fields disguised as hourly increments.
- Aggregated ROI is ratio of summed numerator and summed spend; never simple-average ROI.
- Cumulative fields use the latest valid point in the selected room/day/time range; never sum hourly snapshots.
- Preserve real sample timestamps; never fabricate minute-level data.
- ROI 3.00 vs 1.50 means 200% of baseline and +100% growth.
- Do not infer a planned controller without an explicit source.
- Do not hard-code rooms, anchors, controllers, or metric lists outside seed/config data.
- Never expose or commit secrets.

## Workflow
1. Keep `docs/EXEC_PLAN.md` and `docs/PROGRESS.md` current.
2. Make small, reviewable changes.
3. Add or update tests with every behavior change.
4. Run `make check` before finishing.
5. If credentials are unavailable, use fixture and mock integrations and continue.
6. Do not leave core paths as TODOs or placeholders.

## Backend conventions
- Python type hints are required.
- Use Decimal for business values.
- Use timezone-aware datetimes and Asia/Shanghai business dates.
- Domain calculations live in services, not route handlers.
- Database changes require Alembic migrations.
- External HTTP calls require timeout, retry policy, structured logging, and tests.

## Frontend conventions
- TypeScript strict mode.
- Shared filters are URL-addressable.
- All pages handle loading, empty, error, and permission states.
- ECharts series must group compatible units and preserve readable axes.
- Accessibility: keyboard focus, labels, and non-color-only status indicators.

## Required commands
- `make format`
- `make lint`
- `make typecheck`
- `make test`
- `make test-e2e`
- `make check`
