# 数据字典与 fixture 勘察

更新日期：2026-07-18（Asia/Shanghai）

## Fixture 结构

| 文件/Sheet                         | 范围     | 行列     | 角色                                   |
| ---------------------------------- | -------- | -------- | -------------------------------------- |
| 直播间数据登记系统 / 柏瑞美-散粉   | A1:AZ303 | 303 x 52 | `live_actual`，默认直播间来自 Sheet 名 |
| 直播间数据登记系统 / 柏瑞美-妆前乳 | A1:AZ304 | 304 x 52 | `live_actual`，默认直播间来自 Sheet 名 |
| 直播部门排班系统 / 直播部门排班表  | A1:AI13  | 13 x 35  | `staff_schedule`                       |
| 直播部门排班系统 / 主播直播排班表  | A1:AH73  | 73 x 34  | `anchor_schedule`                      |

直播表 6 个维度字段为主播、场控、月份、自动检查、时间、时段，其余 46 个为数值指标。指标定义、单位、scope 和聚合策略由 `config/metric_seed.yml` 管理，未知字段默认 `LAST` 且待确认。

## 已确认质量样例

- `柏瑞美-散粉`：17 个“用于计算”、18 个“错误”、13 个 `0:00-0:00`、12 个 `0:00-1:00`；含 `Q-李昕` 与 `J-梦丽+菜菜`。
- `柏瑞美-妆前乳`：15 个“用于计算”、15 个“错误”、12 个 `0:00-0:00`、12 个 `0:00-1:00`。
- 主播排班：包含 5 个“断播”、3 个 `00-01时段`，以及带前缀/组合主播。
- 人员排班：包含 `00-08`、`08-17`、`12-20`、`20-05`、`休息` 以及时间待配置的文字班次。

## 标准化字段

- 采集时间：`observed_at` 为带 Asia/Shanghai 时区的真实源时间；`business_date` 为业务日期。
- 自然小时：`00-01` 至 `23-24`，`23-24` 结束时间为次日 00:00。
- 主播：同时保存 raw、canonical、base_name、prefix、members、note。末尾括号备注从 `canonical` 去除；组合成员基础名去重排序后写入 `members`。
- 主播趋势分组使用 `HourlyFact.actual_anchor_canonical`。组合主播保留为一个标准组合展示名，不拆成单人后跨组合合并；`room_id + actual_anchor_canonical` 是趋势隔离维度。
- 场控：保存 raw、canonical、base_name；人员排班只判断是否排班/休息/可能在岗。
- 数值：业务层使用 `Decimal`，数据库金额/比率字段使用 `NUMERIC(24, 8)`；百分比库存比例值，页面按定义格式化。

## 指标 scope 与默认口径

| scope        | 示例                               | 小时内         | 跨小时/筛选汇总                    |
| ------------ | ---------------------------------- | -------------- | ---------------------------------- |
| `period`     | 时段成交金额、时段消耗、时段订单数 | 明确时段值     | `SUM`                              |
| `cumulative` | 直播间成交金额、整体订单数         | 最后有效点     | 每房间每日 `LAST` 后再按定义汇总   |
| `instant`    | 实时在线人数                       | 默认最后有效点 | 默认 `LAST`/明确标注可选 `MAX/AVG` |
| `derived`    | 时段整体 ROI、订单成本             | 分子/分母重算  | `RATIO_OF_SUMS`，不简单平均        |

主播趋势固定读取以下小时指标：

| 指标键                      | 含义               | 周期汇总                                                                    |
| --------------------------- | ------------------ | --------------------------------------------------------------------------- |
| `period_overall_amount`     | 时段整体成交金额   | `SUM(amount)`                                                               |
| `period_spend`              | 时段消耗           | `SUM(spend)`                                                                |
| `period_overall_orders`     | 时段整体成交订单数 | `SUM(orders)`                                                               |
| `period_overall_roi`        | 时段整体支付 ROI   | 周期值重新计算为 `SUM(amount) / SUM(spend)`，不读取/平均已存 ROI 作为汇总值 |
| `period_overall_order_cost` | 时段整体订单成本   | 主播趋势值重新计算为 `SUM(spend) / SUM(orders)`                             |

任一除法的分母为 0 或缺失时结果为 `null`，不生成无穷值。基准 ROI 或基准消耗为 0/空时，趋势状态为 `no_comparable_baseline`，增长率为空。

## 主播趋势周期与样本字段

- 允许周期：`1/3/5/7/15/30` 天。
- 当前周期：`end_date - (period_days - 1)` 至 `end_date`，按完整自然日计算。
- 基准周期：当前周期开始日前一天向前取相同天数，即紧邻等长区间。
- 自动 `end_date`：按 T+1 次日 08:00 截止；08:00 前最后可用日为前天，08:00 起最后可用日为昨天。
- `current_effective_days` / `baseline_effective_days`：当前实现取 24 个自然小时点各自 `effective_days` 的最大值，而不是将各小时天数相加。
- `current_effective_hours` / `baseline_effective_hours`：24 个自然小时点中有效样本数的合计。
- `current_coverage_rate` / `baseline_coverage_rate`：已到填报截止且应有数据的排班小时中，有效小时所占比例。
- 正式判断要求当前与基准周期均完整，且两侧完整率和有效小时达到规则门槛；当前周期还必须达到 `minimum_spend` 与 `minimum_orders`。

## ROI 目标匹配

目标来自 `room_metric_targets`。当前代码读取生效日期内全部 `enabled=true` 的候选（尚未按 `metric_code` 过滤），再由 `select_target` 按以下优先级返回第一个匹配值：

1. `room_id` 精确匹配；
2. `room_name` 精确匹配；
3. `product_category` 匹配；房间未显式设置品类时，可从房间名识别“水散粉/妆前乳/散粉”。

主播趋势按房间+主播分组，因此目标属于该房间，不把其他房间目标带入。无目标时 `roi_target`、`roi_target_gap`、`roi_target_reached` 为 `null`；仍可按当前/基准变化分类，但不得显示伪造的达标结论。由于候选查询当前未按 `metric_code` 过滤，运行库若为同一范围配置非 ROI 目标，存在被优先误选的风险；在代码补齐筛选并回归前保持为待验收。

## 主播趋势状态字典

| 字段         | 值             | 含义/持久化行为                                                            |
| ------------ | -------------- | -------------------------------------------------------------------------- |
| `trend_type` | `rise`         | 上涨榜，保存事件与全量明细，可生成绿色 TopN 卡片                           |
| `trend_type` | `fall`         | 下跌榜，保存事件与全量明细，可生成红色 TopN 卡片                           |
| `trend_type` | `insufficient` | 数据不完整、样本不足、异常或基准不可比；保存系统事件与全量明细，不发业务群 |
| `trend_type` | `neutral`      | 无明显变化；当前计算返回该值，但不创建 `anchor_trend_events`               |

主状态按代码插入顺序选择第一个命中项。五个下跌候选先于上涨候选，因此红色主状态优先：`efficiency_deterioration`、`roi_target_broken`、`roi_fall`、`spend_roi_double_fall`、`below_target_declining`，之后才检查 `spend_roi_double_rise`、`roi_target_breakthrough`、`lower_spend_higher_roi`、`roi_rise`、`spend_rise`。所有命中原因去重后保存在 `reason_codes/reasons`。

## `room_metric_targets`

| 字段                                          | 含义                                                               |
| --------------------------------------------- | ------------------------------------------------------------------ |
| `id`                                          | UUID 主键                                                          |
| `room_id`                                     | 可空房间 UUID，最高匹配优先级                                      |
| `room_name`                                   | 可空精确房间名                                                     |
| `product_category`                            | 可空产品品类                                                       |
| `metric_code`                                 | 标识目标指标；当前主播趋势候选查询尚未按该字段过滤，见下方验收边界 |
| `target_value`                                | `NUMERIC(24, 8)` 目标值，API 校验必须大于 0                        |
| `effective_start_date` / `effective_end_date` | 可空生效日期闭区间                                                 |
| `enabled`                                     | 是否启用                                                           |
| `updated_by`                                  | 最后修改用户                                                       |
| `created_at` / `updated_at`                   | 审计时间                                                           |

## `hourly_comparison_rules` 主播趋势扩展字段

迁移 `0005_anchor_trend_summaries` 在原小时比较规则上增加/使用以下字段：

| 字段                                                      | 含义                                                               |
| --------------------------------------------------------- | ------------------------------------------------------------------ |
| `rule_type`                                               | 主播趋势规则为 `anchor_trend_summary`；用于与旧小时规则隔离        |
| `period_days`                                             | `1/3/5/7/15/30` 之一                                               |
| `spend_increase_threshold` / `spend_decrease_threshold`   | 消耗上涨/下跌增长率阈值，默认 `0.30/-0.30`                         |
| `roi_increase_threshold` / `roi_decrease_threshold`       | ROI 上涨/下跌增长率阈值，默认 `0.30/-0.30`                         |
| `minimum_spend` / `minimum_orders`                        | 当前周期最低消耗/最低订单门槛                                      |
| `minimum_coverage_rate`                                   | 当前与基准周期最低完整率，默认 `0.80`                              |
| `minimum_effective_hours`                                 | 当前与基准周期最低有效小时数，默认 1                               |
| `evaluation_delay_minutes`                                | 继承字段；主播趋势当前未单独消费该值                               |
| `push_schedule`                                           | `manual`、`daily@HH:MM` 或 `weekly:1-7@HH:MM`                      |
| `schedule_timezone`                                       | 持久化规则时区，默认 `Asia/Shanghai`；当前调度实际读取全局系统时区 |
| `applicable_rooms` / `applicable_anchors`                 | 规则房间 UUID / 标准主播名范围                                     |
| `enabled` / `push_enabled`                                | 计算启用 / 推送启用                                                |
| `push_chat_id`                                            | 可空应用机器人目标群；空时回退系统默认群配置                       |
| `send_rise` / `send_fall`                                 | 是否发送上涨/下跌卡片                                              |
| `rise_limit` / `fall_limit`                               | 卡片展示数量；服务另有硬上限 10                                    |
| `send_empty_summary`                                      | 已持久化；当前服务不发送空榜卡片                                   |
| `allow_force_resend`                                      | 是否允许管理员强制重发                                             |
| `push_retry_limit`                                        | 单事件最大尝试次数，默认 3                                         |
| `cooldown_minutes`                                        | 继承字段；主播趋势当前主要依赖事件唯一键去重                       |
| `created_by` / `updated_by` / `created_at` / `updated_at` | 规则审计字段                                                       |

迁移默认插入：

- `主播3天趋势通知`：`period_days=3`、`daily@09:30`；
- `主播7天趋势通知`：`period_days=7`、`weekly:1@09:40`（ISO 周一）；
- 两者 `schedule_timezone=Asia/Shanghai`、上涨/下跌均启用、TopN 默认 10、样本不足不推送。

## `alert_rules` 数据质量隔离字段

| 字段                     | 含义                                                     |
| ------------------------ | -------------------------------------------------------- |
| `system_record_enabled`  | 是否保留系统事件，默认 `true`                            |
| `business_push_enabled`  | 是否允许业务群推送；迁移将已知数据质量规则改为 `false`   |
| `technical_push_enabled` | 技术群开关，默认 `false`；当前发送路径尚未实现技术群路由 |
| `technical_chat_id`      | 可空技术群 ID；当前仅持久化                              |

当前代码对 `data_delay`、`missing_data`、`unentered_data`、`delayed_entry`、`missing_hourly_record` 采用硬隔离：事件可在 `alert_events` 留存，但发送/重试会设置 `push_status=skipped`，不进入业务运营群。

## `anchor_trend_events`

一行代表“一个规则、一个当前周期、一个通知类型、一个目标群”的主播趋势汇总事件。

| 字段                                            | 含义                                                                          |
| ----------------------------------------------- | ----------------------------------------------------------------------------- |
| `id`                                            | UUID 主键                                                                     |
| `rule_id`                                       | 外键 `hourly_comparison_rules.id`                                             |
| `period_days`                                   | 周期天数                                                                      |
| `current_period_start` / `current_period_end`   | 当前完整自然日区间                                                            |
| `baseline_period_start` / `baseline_period_end` | 紧邻等长基准区间                                                              |
| `notification_type`                             | `anchor_rise_summary`、`anchor_fall_summary` 或 `anchor_insufficient_summary` |
| `destination_group`                             | 可空目标飞书群 ID                                                             |
| `room_scope`                                    | 本事件全量项目涉及的房间 UUID JSON 数组                                       |
| `anchor_count`                                  | 该事件全量主播项目数，不是卡片 TopN 数                                        |
| `message_snapshot`                              | 发送时的飞书卡片 JSON；样本不足事件为空对象                                   |
| `dedup_key`                                     | 64 位 SHA-256，唯一约束                                                       |
| `push_status`                                   | `pending/sending/sent/failed/skipped`                                         |
| `push_attempts`                                 | 已认领发送次数                                                                |
| `pushed_at` / `push_error`                      | 真实发送时间 / 最后错误或跳过原因                                             |
| `manual_resend`                                 | 是否为强制重发新事件                                                          |
| `source_event_id`                               | 强制重发时指向原事件，可空                                                    |
| `resend_reason`                                 | 强制重发原因，可空；API 强制重发时要求非空                                    |
| `operated_by`                                   | 重算/重发操作用户，可空（自动任务为空）                                       |
| `created_at`                                    | 事件创建时间                                                                  |

普通去重键原始维度为：

```text
rule_id | period_days | current_period_start | current_period_end |
destination_group（空时为 __default_group__） | notification_type | suffix
```

普通事件 `suffix` 为空；强制重发使用随机 `force:<uuid>` 后缀，因此创建新事件并保留 `source_event_id/resend_reason`，不覆盖原事件。

## `anchor_trend_items`

一行代表某个汇总事件中的一个 `room_id + anchor_name` 项目。唯一约束为：

```text
event_id + room_id + anchor_name
```

| 字段组     | 字段                                                                                                       | 含义                                                             |
| ---------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| 标识与排名 | `id`, `event_id`, `rank`                                                                                   | UUID、所属事件、该分类全量排名                                   |
| 房间/人员  | `room_id`, `room_name`, `anchor_id`, `anchor_name`, `control_names`                                        | 房间与标准主播/组合名；人员 ID 可空；场控为周期内去重排序列表    |
| 分类       | `trend_type`, `primary_status`, `primary_status_name`                                                      | 上涨/下跌/样本不足及主状态                                       |
| 成交额     | `current_amount`, `baseline_amount`                                                                        | 当前/基准 `SUM(amount)`                                          |
| 消耗       | `current_spend`, `baseline_spend`, `spend_growth_rate`                                                     | 当前/基准 `SUM(spend)` 及增长率                                  |
| ROI        | `current_roi`, `baseline_roi`, `roi_growth_rate`                                                           | 当前/基准 ratio-of-sums 及增长率                                 |
| 订单与成本 | `current_orders`, `baseline_orders`, `current_order_cost`, `baseline_order_cost`                           | 订单合计及 `SUM(spend)/SUM(orders)`                              |
| 目标       | `roi_target`, `roi_target_gap`, `roi_target_reached`                                                       | 匹配目标、当前 ROI 减目标、是否达标；无目标为空                  |
| 原因       | `reason_codes`, `reasons`                                                                                  | 全部命中原因代码与中文说明 JSON 数组                             |
| 小时贡献   | `major_rise_hours`, `major_fall_hours`, `major_spend_hours`, `hourly_details`                              | ROI 上涨/下跌及消耗差异最大的最多 3 个自然小时和 24 小时明细快照 |
| 样本       | `current_effective_days`, `baseline_effective_days`, `current_effective_hours`, `baseline_effective_hours` | 两周期有效日/小时数                                              |
| 完整率     | `current_coverage_rate`, `baseline_coverage_rate`                                                          | 两周期有效样本/应有样本                                          |
| 说明       | `comparison_basis`, `suggestion`, `created_at`                                                             | 比较口径、复盘建议、创建时间                                     |

事件明细保存全量 `items`；仅 `message_snapshot` 在生成上涨/下跌卡片时按 `rise_limit/fall_limit` 截断，并受硬上限 10 约束。

## 迁移与验收状态说明

- 源码模型与迁移文件已经定义上述表和字段；2026-07-18 迁移往返测试和完整后端测试均通过。
- 实际运行数据库已经执行迁移 0005，`alembic current` 为 `0005_anchor_trend_summaries (head)`；两张新表、扩展列和默认规则已由当前 API/实时任务读取。
- 前端已新增 `apps/web/src/types/anchorTrends.ts`、主播趋势 API client，并把榜单、筛选、三类全局计数、详情与按角色显示的发送操作接入 `AlertsPage`；字段使用由 10 个定向前端测试及实际运行库浏览器回归佐证。
- 完整 `make.cmd check` 已通过：134 个后端测试、33 个前端单测、1 个 Playwright E2E，后端覆盖率 86.87%；实际运行 API 的桌面端榜单、详情和规则配置无控制台或 HTTP 错误。真实飞书趋势卡与移动端截图仍不属于已验收范围。
