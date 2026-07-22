# 预警与主播趋势汇总说明

更新日期：2026-07-18（Asia/Shanghai）

本文记录当前代码已经实现的行为及尚未验收项。它不把迁移文件、Mock 卡片或历史机器人测试消息当作运行库升级、真实主播趋势投递或前端交付证明。

## 1. 预警类型与群消息边界

### 1.1 经营/排班小时预警

现有小时规则包括 ROI 优秀上涨、ROI 暴跌、ROI 低于底线、主播排班不一致和数据延迟。规则可限定直播间/主播/场控，配置严重级别、阈值、最小消耗/订单/金额、冷却时间、启用和推送开关。

- ROI 比较使用 `Decimal`；倍率为 `当前/基准`，增幅为 `当前/基准 - 1`。
- 基准为空或 0 时不计算倍率/增幅，也不能把缺失值按 0 伪造成跌幅。
- 主播排班组合比较使用标准成员集合；不存在明确来源的计划场控不推断。

### 1.2 数据质量事件只做系统记录

以下 `rule_type/alert_type` 被当前代码硬隔离为数据质量事件：

```text
data_delay
missing_data
unentered_data
delayed_entry
missing_hourly_record
```

处理规则：

1. 数据质量事件可以写入 `alert_events`，用于后台列表、审计、恢复和完整率排查。
2. 数据质量事件不进入业务运营群。即使旧事件处于 `pending/failed/sending`，迁移会改为 `skipped`；运行时手动重试也会再次阻断并写入“数据质量事件仅系统记录，业务群推送已关闭”。
3. `alert_rules.system_record_enabled=true`、`business_push_enabled=false` 表达该边界；`push_enabled` 对默认 `data_delay` 也被关闭。
4. `technical_push_enabled/technical_chat_id` 目前只完成模型和迁移，发送服务尚未实现技术群路由，因此不能称为“已发技术群”。
5. 数据质量事件的系统留存不得混入主播经营上涨/下跌业务卡片。

## 2. T+1 和完整自然日

- 实绩采用 T+1 补录，默认截止时间为业务日次日 08:00（Asia/Shanghai）。
- 截止前的未录入状态为“待补录”：不降低完整率，不触发数据延迟、ROI 或排班不一致告警。
- 截止后仍无有效实绩，且该小时排班状态确实期待数据时，才创建数据延迟系统事件；断播和未分配时段不触发。
- 截止前已录入的有效实绩统一在截止后进入自动趋势比较；截止后晚到的数据会关闭对应缺失事件，并重评估原业务小时的经营规则。
- 主播趋势自动任务只取完整自然日。08:00 前最近可用日为前天，08:00 起最近可用日为昨天。

## 3. 主播趋势汇总口径

### 3.1 周期和隔离键

- 固定周期只支持 `1/3/5/7/15/30` 天。
- 当前周期为截至 `end_date` 的连续自然日闭区间；基准周期紧邻当前周期、等长且无重叠。
- 示例：3 天当前周期 `07-13—07-15`，基准周期为 `07-10—07-12`。
- 每个系列按 `room_id + actual_anchor_canonical` 隔离。相同主播在不同房间不合并，相同房间内不同主播不合并。
- 主播名使用清洗后的标准展示名。组合主播使用标准组合名作为一个系列，不按单个成员拆分并跨组合汇总。

### 3.2 汇总公式

```text
当前 ROI = SUM(当前周期 period_overall_amount) / SUM(当前周期 period_spend)
基准 ROI = SUM(基准周期 period_overall_amount) / SUM(基准周期 period_spend)
当前订单成本 = SUM(当前周期 period_spend) / SUM(当前周期 period_overall_orders)
基准订单成本 = SUM(基准周期 period_spend) / SUM(基准周期 period_overall_orders)
```

禁止简单平均小时 ROI 或订单成本。分母为 0/空时返回空值。

### 3.3 ROI 目标

当前目标选择顺序为：有效日期内 `room_id` 精确匹配 > `room_name` 精确匹配 > `product_category` 匹配。品类为空时可从房间名识别水散粉、妆前乳、散粉。

- `roi_target_gap = current_roi - roi_target`。
- `roi_target_reached = current_roi >= roi_target`。
- 无目标时两者为空，卡片显示“目标未配置”，不得伪造达标/未达标。
- 当前候选查询没有按 `room_metric_targets.metric_code` 过滤；在代码补齐该约束前，运行库应避免为同一房间混存会被误选的非 ROI 目标，且该风险保留为待验收项。

### 3.4 完整率和最低样本

正式榜单判断依次检查：

1. 当前周期与基准周期都是完整自然日；
2. 当前和基准 `coverage_rate` 都达到规则的 `minimum_coverage_rate`；
3. 当前和基准 `effective_hours` 都达到 `minimum_effective_hours`；
4. 当前周期 `SUM(spend)` 达到 `minimum_spend`；
5. 当 `minimum_orders > 0` 时，当前周期 `SUM(orders)` 达到门槛；
6. 当前/基准 ROI 可计算，且基准 ROI、基准消耗不为 0。

任一条件不满足时进入 `insufficient`，原因细分为数据不完整、样本不足、异常数据或无有效可比基准。基准为 0 时不显示虚假百分比。

## 4. 分类、红色优先与排名

### 4.1 主状态优先级

代码先追加下跌候选，再追加上涨候选，并取第一个命中项为 `primary_status`，因此红色风险优先于绿色上涨：

1. `efficiency_deterioration`：消耗达到上涨阈值但 ROI 下降；
2. `roi_target_broken`：ROI 从达标跌到未达标；
3. `roi_fall`：ROI 下跌达到阈值；
4. `spend_roi_double_fall`：消耗和 ROI 双降；
5. `below_target_declining`：未达标且继续下跌；
6. `spend_roi_double_rise`：消耗和 ROI 双涨；
7. `roi_target_breakthrough`：ROI 从未达标提升为达标；
8. `lower_spend_higher_roi`：降耗提效；
9. `roi_rise`：ROI 上涨达到阈值；
10. `spend_rise`：消耗上涨且 ROI 未下降。

主状态之外的其他命中仍保存在 `reason_codes/reasons`，不能只保留一条原因。

### 4.2 结果类型

| 类型           | 系统事件           | 业务群卡片    | 排序                         |
| -------------- | ------------------ | ------------- | ---------------------------- |
| `rise`         | 保存全量           | 绿色上涨 TopN | ROI 增长率降序               |
| `fall`         | 保存全量           | 红色下跌 TopN | ROI 增长率升序，跌幅更大优先 |
| `insufficient` | 保存全量           | 不发送        | 直播间、主播名排序           |
| `neutral`      | 当前不创建汇总事件 | 不发送        | 不适用                       |

## 5. TopN、全量事件和单次卡片数

- `rise_limit/fall_limit` 控制卡片展示条数，服务端另设硬上限 10；因此规则即使配置大于 10，卡片也最多显示 10 个主播。
- `anchor_trend_items` 不按 TopN 截断：同一上涨/下跌/样本不足事件保存该类全部房间+主播项目和排名。
- 卡片尾部的“本次主播数”使用全量数，“展示”使用卡片实际 TopN 数。
- 一次 `run_rule` 最多发送两张业务卡：先上涨、后下跌。样本不足只记录，`neutral` 不建事件；不会发送第三张样本不足卡。
- 当前实现没有跨规则合并卡片；同一时刻若多条规则到期，每条规则独立运行并各自遵守最多两卡。

## 6. 默认调度

迁移 0005 默认创建：

| 规则            | 调度表达式       | 业务含义                             |
| --------------- | ---------------- | ------------------------------------ |
| 主播3天趋势通知 | `daily@09:30`    | 每日 09:30 检查最近 3 个完整自然日   |
| 主播7天趋势通知 | `weekly:1@09:40` | 每周一 09:40 检查最近 7 个完整自然日 |

Celery Beat 每 300 秒运行 `anchor_trend_summary_job`。规则在目标时刻起 15 分钟窗口内视为到期，事件去重键避免 5 分钟轮询重复创建。

- 业务时区要求为 `Asia/Shanghai`。
- `schedule_timezone` 字段已存储为 `Asia/Shanghai`，但当前 `due_rules()` 实际使用全局 `settings.timezone`，没有逐规则切换时区；运行配置必须保持 Asia/Shanghai。

## 7. 汇总去重键

普通事件的 `dedup_key` 是以下维度拼接后计算的 SHA-256：

```text
rule_id
period_days
current_period_start
current_period_end
destination_group（空时使用 __default_group__）
notification_type
suffix（普通事件为空）
```

注意：房间和主播不直接进入汇总去重键；它们由规则范围和事件内全量 `room_scope/items` 表达。同一规则、周期、目标群和通知类型重复重算会返回原事件，不重复插入明细。

## 8. 普通发送、强制重发与状态

### 8.1 普通发送

- 只认领 `pending/failed/skipped` 且未达到 `push_retry_limit` 的事件。
- 已 `sent`、正在 `sending` 或达到重试上限时拒绝重复发送。
- `anchor_insufficient_summary` 明确禁止发送到业务群。
- 发送真实 transport 成功后才写 `sent` 和 `pushed_at`；异常写 `failed/push_error`。

### 8.2 `force_resend`

- 仅管理员可调用，规则必须 `allow_force_resend=true`，且必须填写非空 `resend_reason`。
- 系统创建新的 `anchor_trend_events`，不修改原事件；新事件记录 `manual_resend=true`、`source_event_id`、原因和操作人。
- 新事件复制原事件的全部 `anchor_trend_items` 和卡片快照，并使用随机 `force:<uuid>` 后缀生成新去重键。
- 强制重发失败时失败状态留在新事件上，原事件审计状态不变。

### 8.3 Mock 不得记为已发送

- `AlertService.send_card()` 返回 `mocked=true` 时，主播趋势事件写为 `skipped`，错误说明为“未配置可用的飞书机器人，消息未真实发送”。
- 测试推送 API 也返回 `push_status=skipped`，不得把“卡片 JSON 已生成”记为真实飞书成功。
- 只有飞书 transport 返回且 `mocked=false` 才写 `sent`。真实验收还必须保留飞书返回回执；数据库状态本身不是外部送达证明。

## 9. API 与权限

| 方法与路径                                      | 参数/用途                                                                             | 当前权限                                                                                                                                                                         |
| ----------------------------------------------- | ------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /api/v1/alerts/anchor-trends`              | 周期、结束日、房间、主播 ID/名、场控、趋势、目标状态、推送状态、目标群、完整率、limit | 任意登录角色；服务端将请求房间与用户房间权限相交                                                                                                                                 |
| `GET /api/v1/alerts/anchor-trends/{event_id}`   | 事件、全量明细、日/小时/原始事实详情                                                  | 任意登录角色；当前只过滤 `items/details`，无可见项目时返回 404。事件级 `room_scope/anchor_count/message_snapshot` 没有按授权房间重建，混合房间事件存在泄露风险，尚未通过权限验收 |
| `POST /api/v1/alerts/anchor-trends/recalculate` | 按规则/周期/日期/房间/主播重算并落事件                                                | `OperatorAccess`，即 Operator/Admin；规则范围、请求范围和用户房间权限取交集                                                                                                      |
| `POST /api/v1/alerts/anchor-trends/send`        | 发送已有上涨/下跌事件，或 `force_resend`                                              | 仅 Admin；强制重发原因必填                                                                                                                                                       |
| `POST /api/v1/alerts/anchor-trends/test-push`   | 生成并发送测试上涨/下跌卡，不创建业务事件                                             | 仅 Admin                                                                                                                                                                         |

当前路由已注册到 FastAPI，但返回类型仍为普通 `dict`，没有主播趋势专用 Pydantic `response_model`。列表/详情按房间权限过滤明细，并从可见明细重建 `room_scope/anchor_count`；混合房间事件不向受限用户返回原始 `message_snapshot`。Operator/Admin/Viewer、未授权房间与混合房间元数据裁剪已有回归测试；严格响应模型仍是后续 API 契约增强项。

## 10. 现有前端状态

截至 2026-07-18 当前源码：

- 已新增 `apps/web/src/types/anchorTrends.ts` 以及查询、重算、事件详情、发送和测试推送 client；多选筛选沿用 FastAPI 重复同名参数。
- `AlertsPage` 默认打开上涨榜，另有下跌榜、样本不足和按需历史预警页签；支持 `1/3/5/7/15/30`、截止日期、房间、标准主播名、场控、ROI 目标状态、最低完整率和发送状态 URL 筛选。
- 榜单展示红/绿/橙状态、当前/基准 ROI 和消耗、目标、完整率、有效小时、主要变化时段、推送状态；详情抽屉包含逐日汇总、24 小时明细、ROI 分子/分母和原始事实。
- UI 按当前用户角色显示操作：Operator/Admin 可重算，仅 Admin 可测试、发送和填写原因强制重发；样本不足页没有业务发送按钮，历史数据质量告警默认不请求。
- 定向 Mock 单测 `client.test.ts`、`AlertsPage.test.tsx` 与 `HourlyComparisonRuleSettings.test.tsx` 为 3 文件、10 测试通过；完整前端为 33 个单测。
- ESLint、TypeScript、Prettier、33 个全量单测、生产 build 和 Playwright E2E 已全部通过；build 仍有非阻断大 chunk 警告。实际运行 API/数据库的桌面端榜单、详情和规则页已完成截图与无错误控制台回归，飞书内移动端及真实趋势卡实收仍待完成。

## 11. 当前验证与待验收

已实际运行：

```text
python -m pytest tests/test_anchor_trends.py tests/test_alerts.py \
  tests/test_migrations.py tests/test_health.py tests/test_celery_tasks.py -q
```

2026-07-18 初始定向结果：`29 passed, 1 warning in 13.71s`。随后完整 `make.cmd check` 通过：134 个后端测试、33 个前端单测、1 个 Playwright E2E，后端覆盖率 86.87%，且 Ruff/ESLint/mypy/TypeScript/Prettier/生产构建全部通过。第三方 SQLite/构建大 chunk 提示为非阻断警告。

仍待验收：

- [x] 实际运行数据库已升级到迁移 0005 head，并由当前 API/实时任务读取；
- [x] 主播趋势 API 的真实请求、角色权限、未授权房间和混合房间元数据裁剪回归；
- [ ] 3 天/7 天任务在常驻 Celery/Beat 运行态的到期与去重；
- [ ] 指定业务群的真实上涨/下跌卡片回执，确认 Mock 从不记 `sent`；
- [x] 前端 lint/typecheck/33 个单测/格式/构建/E2E 和完整 `make.cmd check` 已通过；
- [x] 实际运行库桌面端榜单、三类计数、详情、筛选、规则配置及管理操作入口浏览器验收，无控制台或 HTTP 错误；
- [x] 桌面端榜单、详情和规则配置截图；
- [x] 使用实际运行配置通过 App Bot 发送上涨与下跌测试卡：接口均为 HTTP 200、`push_status=sent`；抽查上涨卡飞书原始回执为 `code=0`、`msg=success`、`message_id=om_x100b6a9bebea813cc44e2f0b9060101`。测试接口不创建业务事件，不能替代正式趋势汇总卡验收；
- [ ] 飞书内移动端及空态、错误态、Viewer/Operator 权限态截图。
