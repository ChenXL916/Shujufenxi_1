# 经营总览 24 小时 ROI / 消耗周期对比实施文档

更新日期：2026-07-16（Asia/Shanghai）

## 1. 目标与边界

本次是在现有“多直播间小时数据驾驶舱”上增量增加经营总览的 24 小时周期对比、业务 K 线、ROI 目标、状态判断、详情、导出和飞书推送。保留现有经营总览模块、小时趋势、分析、透视、预警、管理、权限、同步和迁移历史；现有小时趋势的“自然小时 + 主播”和真实采集点能力不改为新图表。

## 2. 当前项目结构

- 后端：`apps/api/app`，FastAPI、SQLAlchemy 2、Pydantic 2、Alembic、Decimal 业务计算。
- 数据链路：`RawSourceRecord -> LivePoint/LivePointMetric -> HourlyFact/HourlyMetric`。
- 当前聚合：`app/domain/aggregation.py` 按指标字典执行 SUM、LAST、LAST_PER_ROOM_DAY、RATIO_OF_SUMS；分母为 0 返回 null。
- 当前查询：`app/services/dashboard_query_service.py` 统一应用日期、房间、主播、主播成员、场控、小时和后端房间权限。
- 前端：`apps/web/src`，React、严格 TypeScript、Ant Design、TanStack Query、ECharts。
- 当前经营总览：`apps/web/src/pages/OverviewPage.tsx`，顺序为全局筛选、标题、8 个 KPI、直播间表现、数据与排班质量。
- 当前小时趋势：`TimelinePage` + `MetricChart`，保持原职责和 X 轴定义。
- 预警：`AlertRule`、`AlertEvent`、`AlertService`、Celery/本机轮询、飞书机器人，已有去重、有限重试和 T+1 08:00 防误报。
- 权限：`AccessScope.room_ids` 在服务端查询和导出层过滤；管理写接口仅管理员。

参考 JPG 是主播/场控透视表，不是 24 小时曲线；本次只复用白色卡片、浅蓝表头、轻边框和圆角视觉，不复用其多指标挤在同一坐标轴的布局。

## 3. 修改前基线

- 当前系统：前端 `127.0.0.1:5173`、API `127.0.0.1:8000` 可访问；经营总览真实数据已验证，浏览器控制台无错误。
- lint：Ruff 与 ESLint 通过。
- typecheck：mypy（49 个源文件）与 TypeScript `tsc -b` 通过。
- 前端单测：6 个测试文件、10 个测试通过；现有 jsdom/act 警告不影响断言。
- 后端单测：56 通过、1 失败。失败为此前安全修复后“已发送事件禁止再次重推”的旧断言未更新，不是本次 24 小时功能引入；在进入最终门禁前修正测试契约。
- Git：仓库根在上一级目录，当前应用目录整体为未跟踪状态；不执行 commit/push，不改写历史。

## 4. 本次修改位置

### 后端

- `apps/api/app/models/entities.py`：ROI 目标、小时周期规则、事件周期上下文、指标能力字段。
- `apps/api/alembic/versions/0002_hourly_comparison.py`：可回滚正式迁移、索引和已有房间目标初始化。
- `apps/api/app/domain/hourly_comparison.py`：周期、OHLC、对比公式、目标与综合状态纯函数。
- `apps/api/app/services/hourly_comparison_service.py`：权限过滤、批量查询、每日小时聚合、固定 24 小时响应、详情与导出。
- `apps/api/app/api/schemas.py`、`apps/api/app/api/router.py`：小时对比、详情、导出和目标管理契约。
- `apps/api/app/services/alert_service.py`、`app/tasks/jobs.py`：默认 1 天、小时结束 15 分钟后、合并原因、去重和推送。
- `apps/api/app/services/seed_service.py`、`config/metric_seed.yml`：指标能力和三类目标幂等初始化。

### 前端

- `apps/web/src/types/dashboard.ts`、`apps/web/src/api/client.ts`：严格类型与请求。
- `apps/web/src/features/hourly-comparison/`：周期工具栏、双图、业务 K 线、目标线、状态、表格、详情抽屉、导出。
- `apps/web/src/pages/OverviewPage.tsx`：只在 KPI 与直播间表现之间增量插入，并实现 KPI 点击联动。
- `apps/web/src/styles/`：响应式和现有视觉风格。

## 5. 数据字段映射

默认图只使用指标字典中的真实时段字段：

| 业务值 | 指标键 | 聚合口径 |
| --- | --- | --- |
| ROI 分子 | `period_overall_amount` | SUM |
| ROI / 消耗分母 | `period_spend` | SUM |
| 时段整体支付 ROI | `period_overall_roi` | `sum(period_overall_amount) / sum(period_spend)` |
| 净 ROI | `period_net_roi` | `sum(period_net_amount) / sum(period_spend)` |
| 整体订单成本 | `period_overall_order_cost` | `sum(period_spend) / sum(period_overall_orders)` |
| 净订单成本 | `period_net_order_cost` | `sum(period_spend) / sum(period_net_orders)` |
| 时段笔单价 | `period_avg_order_value` | `sum(period_gmv) / sum(period_order_count)` |

累计 scope 不进入默认 24 小时指标选择器。指标响应由统一字典返回名称、分类、单位、精度、scope、聚合、分子/分母、方向、小时/K 线/预警支持能力，不在多个前端组件重复中文字段。

## 6. 日期周期算法

业务时区固定为 `Asia/Shanghai`。预设仅允许 1、3、5、7、15、30 天，默认 7 天；默认截止日为权限范围内数据库最新完整自然日，默认不含今日。

```text
current_end = end_date
current_start = current_end - (period_days - 1) days
comparison_end = current_start - 1 day
comparison_start = comparison_end - (period_days - 1) days
```

自定义日期首尾均包含，周期天数为 `(end-start)+1`，对比周期自动取前一段相同天数。使用 Python `date/timedelta`，自然处理跨月、跨年和闰年。小时标准键为整数顺序 0..23 映射 `00-01`..`23-24`；`23-24` 属于开始日期。

实时开关关闭时只使用最新完整自然日。开启时，以 Asia/Shanghai 当前时间判断：已结束小时可比较；当前小时标记 `in_progress`；未来小时返回 null；进行中和未来小时不触发正式 30% 规则。

## 7. ROI、消耗和日均口径

- sum：可求和指标按周期有效数据合计。
- daily_average：该自然小时合计除以该小时实际有效数据天数，不固定除以周期天数。
- ROI/成本/转化率：始终使用合计分子除以合计分母，禁止简单平均日 ROI。
- 分母为 null 或 0：结果、比率和增幅均为 null；页面显示“—”；不产生 Infinity/NaN，不触发百分比状态或预警。
- null 与真实 0 分离，缺失小时不补 0、不连接曲线。

## 8. 业务 K 线定义

每个自然小时基于周期内“每日该小时重算后的业务值”形成 OHLC：

- open：最早有效完整日期值。
- close：最后有效完整日期值。
- high：有效日期最大值。
- low：有效日期最小值。
- 同时返回 average、median、total、effective_days、first/last/high/low date、coverage。

ROI 的每日基础值为当日/房间/小时成交金额合计除以消耗合计；消耗为当日/房间/小时消耗合计。1 天模式四价可以相同，不制造波动。对比周期默认用虚线 close 曲线，Tooltip 保留完整 OHLC，避免双 K 线遮挡。

## 9. ROI 目标值配置

新增 `room_metric_targets`，字段包括 room、名称/品类兜底、metric_code、Decimal target、有效期、启用、审计时间和修改人。优先级：房间 ID > 精确名称 > 品类 > null。名称兜底先识别“水散粉”再识别“散粉”。

初始化：

- 柏瑞美-散粉：1.81
- 柏瑞美-妆前乳：1.82
- Mistine-水散粉：2.00

多房间相同目标可显示共同线；目标不同则默认按房间拆图，强制汇总时不计算简单平均目标，只返回各房间达标数/总数/达标率和提示。

## 10. 30% 判断规则

新增可配置小时周期规则，默认：消耗增长阈值 0.30、ROI 增长 0.30、ROI 下降 -0.30、最低覆盖率 0.80；最小消耗/订单可配置。判断使用未格式化 Decimal。

前置条件：小时结束、同步完成、达到最小消耗/订单、覆盖率达标、基准有效且非 0、数据未标无效、目标存在。前置不满足时仍显示数值，主状态为无法完整判断/样本不足，不推送严重或优秀消息。

优先级依次实现：消耗效率恶化、ROI 严重下降、消耗异常、优秀放量时段、ROI 优秀提升、放量正常、改善中但未达标、ROI 达标、ROI 未达标、无法完整判断。一个点保留全部 `reasons`，页面显示最高优先级主状态。

比较公式：

```text
difference = current - baseline
current_to_baseline_ratio = current / baseline
current_to_baseline_percentage = ratio * 100%
growth_rate = (current - baseline) / baseline
growth_percentage = growth_rate * 100%
```

因此 3.00 vs 1.50 为基准的 200%，较基准提升 100%。

## 11. 接口设计

- `GET /api/v1/overview/hourly-comparison`：周期/筛选/图表参数，返回 meta、周期、固定 24 小时、按维度系列、ROI/消耗/指标、当前/基准/差值/增幅、OHLC、目标、状态、样本和更新时间。
- `GET /api/v1/overview/hourly-comparison/details`：单小时的逐日、按房间、K 线和分页原始记录引用。
- `GET /api/v1/overview/hourly-comparison/export`：权限过滤后的 CSV/XLSX。
- `GET/POST/PUT /api/v1/settings/room-metric-targets`：管理员写，运营可查；查看者只通过聚合结果看到已应用目标。

所有接口先求 `requested room_ids ∩ access.room_ids`；详情、原始记录和导出复用同一权限范围。固定 24 小时响应中无数据值为 null。

## 12. 数据库迁移与性能

迁移新增目标/规则表，扩展指标能力和预警事件周期上下文，并为事实表增加：

- `(business_date, hour_order, room_id)`
- `(room_id, business_date, hour_order)`
- `(business_date, actual_anchor_canonical, hour_order)`
- `(business_date, actual_control_canonical, hour_order)`

当前实库约 2,424 小时事实，首版无需复制出第二份聚合事实表；服务使用固定次数批量查询，先按日/房间/小时聚合后再计算周期，不执行每小时/每指标查询。最终用 SQLite `EXPLAIN QUERY PLAN` 和实库计时验证 7/30 天查询；超过目标再引入 `agg_live_hour_daily`，避免过早复制口径。

## 13. 前端组件与交互

新增区域位于 KPI 后、直播间表现前：

1. `HourlyComparisonToolbar`：1/3/5/7/15/30天/自定义、截止日、合计/日均、折线/K线/柱状、对比、实时、波动区间、标签、拆分维度、刷新/导出/全屏。
2. `HourlyRoiSpendChart`：上下两网格、独立 Y 轴、共享 24 小时 X 轴/十字准星、高亮和点击；line/bar/candlestick；`connectNulls=false`；ROI 目标 markLine。
3. `HourlyComparisonTable`：固定 24 行，图表双向联动，null 显示“—”。
4. `HourlyDetailDrawer`：按日期、按直播间、K 线明细、分页原始记录四页签。
5. `DataCoverageBadge`、`ComparisonValue`、`HourlyStatusMarker`：颜色外同时提供文字/图标。

KPI 中 ROI/消耗点击滚动并选中对应图表；其他 KPI 保持导航至原小时趋势。局部 Loading/Empty/Error/Retry 不让整个经营总览白屏。筛选与周期状态写入 URL。

## 14. 飞书预警流程

默认只启用 1 天当前日同小时 vs 上一日同小时，小时结束后 15 分钟执行。其他周期默认页面可用、推送关闭，管理员可配置。

去重内容至少包含 room_id、period_days、current_start/end、hour、alert_type、metric_code。一个小时多个命中原因合并为一张卡片，标题取最高优先级，列出全部原因和建议。复用现有机器人、push_status、重试次数、失败原因、确认和处理闭环；不写入或返回 Webhook/密钥。测试只用 MockTransport，不向真实群发送。

## 15. 测试计划

- 领域：1/3/5/7/15/30、自定义、跨月/年/闰年、23-24；sum/日均、ratio-of-sums、分母 0、null/0；OHLC、1 天、缺失日；目标优先级与水散粉；全部 30% 状态和前置条件；3/1.5 公式。
- API：默认 7 天、固定 24、筛选/权限、多目标、详情分页、导出权限、目标 CRUD 权限。
- 前端：周期、图表类型、目标线、Tooltip、状态、表格/图表联动、抽屉、KPI、Loading/Empty/Error。
- E2E：三个直播间目标、24 小时、7 天当前/对比、点击 08-09 抽屉、K 线/折线、权限。
- 性能：7 天单房间、30 天多房间、详情和 EXPLAIN。
- 全门禁：format、lint、mypy/tsc、pytest/Vitest、build、Playwright、`check`、生产静态验证。

## 16. 实施进度

- [x] 读取规则、README、主文档、模型、路由、经营总览、小时趋势、指标字典、权限、预警、测试和参考图。
- [x] 安装依赖状态确认、启动系统、经营总览可访问、记录修改前基线。
- [x] 完成字段/日期/ROI/OHLC/目标/状态/API/迁移/前端/预警/测试设计。
- [ ] 创建失败测试和正式迁移。
- [ ] 实现领域服务与 API。
- [ ] 实现经营总览前端。
- [ ] 实现飞书周期预警。
- [ ] 全量门禁、实库迁移、性能、浏览器/E2E、截图和最终报告。
