# 开发进度

## 2026-07-20：阶段 18 — 五角色 RBAC 与直播间数据隔离（进行中）

- 已审计现有 `User.role_name + UserRoomPermission + AccessScope` 权限链路，确认可增量扩展，无需新建第二套认证系统。
- 已确认当前缺口：角色仍为 `admin/operator/viewer`，没有正式权限点、角色房间范围、直播间资源、飞书群范围及独立权限审计；前端管理菜单和路由未按角色保护。
- 已确认现有总览、图表、分析、详情、导出与预警服务大多在查询前使用服务端 `AccessScope.room_ids`，本阶段将在该单一入口补齐五角色解析、显式越权 403 和全路由权限点。
- 下一步：先写迁移与五角色越权失败测试，再逐个纵向切片实现模型、后端、飞书群范围、前端权限页和截图验收。

最后更新：2026-07-18（Asia/Shanghai）

## 当前状态

阶段 0-14 的历史交付和阶段 15 的 T+1 纠正记录保留如下。当前阶段 16“主播趋势汇总”已完成源码、运行库迁移、严格 Pydantic/OpenAPI 响应契约、API/权限回归、正式上涨/下跌业务卡发送，以及桌面、390px 飞书 UA 移动、真实空态、隔离错误态和 Viewer/Operator 显隐验收。运行库位于迁移 0005 head，实际页面计数为上涨 4、下跌 2、样本不足 10；移动榜单已由 2300px 横向表格改为无裁切的指标卡片。正式事件各发送一次并持久化为 `sent`，API 日志记录两次飞书消息 POST HTTP 200；原始 provider JSON 正文未被应用持久化，因此证据文件不冒充原始响应或 `message_id`。当前唯一阶段 16 基础设施阻塞是常驻 Celery Worker/Beat：任务注册通过，但本机无 Redis/Docker/Podman、WSL 无发行版，`localhost:6379` 拒绝连接，不能把本地轮询冒充 Celery 验收。

阶段 17“Index 暖白 BI 视觉重构”已完成：应用外壳、总览、全部分析/预警/管理路由、Ant Design 与 ECharts 已统一为暖白高对比主题；响应式、键盘、Reduced Motion、WCAG 色彩、页面级溢出、生产 Chunk 和性能均纳入自动化门禁。最新 `make.cmd check` 退出 0，136 个后端测试、13 个前端文件/41 个单测、6 项 Playwright 全部通过；22 个 JS Chunk 均不超过 650 KiB且无循环输出 Chunk 警告。最终 `dist` 三次性能中位数为业务就绪 990ms、FCP 156ms、LCP 612ms、CLS 0、阻塞时间 86ms。37 张最新截图及 SHA-256 清单已生成，联系表、关键原图与真实图表导出复核未发现 P0/P1/P2。

2026-07-18 本地运行修复：确认数据未丢失，故障来自未登记 Alembic 版本的旧 `live_ops.db` 被当前 ORM 部分补建后形成混合结构，`alert_events` 缺少 0002/0004 列并令总览返回 500。迁移前已生成 41,181,184 bytes 的一致性备份 `backups/runtime/live_ops_pre_alembic_20260718T114100Z.db`；新增“旧 0001 + 当前 metadata bootstrap + 无版本表”的回归用例，并令 0002 种子插入兼容后续表必填列。真实库现为 `0005_anchor_trend_summaries`，SQLite integrity 为 `ok`，1047 条小时事实和最新日期 2026-07-17 保持不变；真实总览显示 8 个 KPI、小时曲线、24 小时明细和 3 个直播间排行，浏览器控制台无错误。

2026-07-19 飞书手动同步修复：根因是四源真实同步需 29–49 秒，而 Axios 全局 15 秒超时令页面先显示“同步失败”，后端随后才完成。`syncFeishuNow` 现单独使用 120 秒超时并有回归测试；真实浏览器在旧 15 秒边界后保持 loading，最终收到 `/auth/feishu/sync` HTTP 200，状态刷新为 `realtime_ready=true`、`last_error=null`。飞书 OAuth、表清单和记录分页均真实 HTTP 200；当前四源返回 527、530、0、52 条，全部 unchanged、无 invalid，说明本次飞书 API 没有提供新增/变更行。自动 5 分钟周期仍未冒充已恢复：本机无 Redis/Valkey 且无 Celery Worker/Beat，当前恢复的是可验证的手动同步链路。

## 阶段记录

### 阶段 0：项目初始化

- [x] 完整读取 `AGENTS.md` 和 `MASTER_PROMPT.md`。
- [x] 检查两份 Excel fixture 的 Sheet、范围、字段数、关键异常和排班样例。
- [x] 检查参考截图的蓝色圆角透视表视觉结构。
- [x] 确认飞书应用与机器人凭据当前均未配置，切换到 fixture + Mock 路径。
- [x] 创建 `docs/EXEC_PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DATA_DICTIONARY.md`、`docs/PROGRESS.md`。
- [x] 创建 FastAPI、React/Vite、基础设施、跨平台任务入口与 CI 骨架。
- [x] 运行阶段 0 测试并记录结果。

### 阶段 1：数据源与 fixture

- [x] 实现 Feishu Bitable token、分页、字段/表扫描、健康检查和重试。
- [x] 实现 Mock Feishu API 集成测试。
- [x] 实现 Excel fixture 扫描、payload hash 与幂等同步入口。
- [x] 运行阶段 1 测试并记录结果。

### 阶段 2：数据模型与清洗

- [x] 实现 SQLAlchemy 模型和 Alembic 初始迁移。
- [x] 实现日期/时段/主播/场控/数字清洗与异常判定。
- [x] 实现主播小时排班和人员日排班宽转长。
- [x] 创建完整指标与班次 seed。
- [x] 运行阶段 2 测试并记录结果。

### 阶段 3：小时事实与聚合

- [x] 将 fixture 幂等写入 raw、采集点、指标和排班表。
- [x] 构建小时事实并关联主播/场控排班。
- [x] 实现 Decimal 指标聚合、累计 LAST、比较引擎和除零口径。
- [x] 运行阶段 3 测试并记录结果。

### 阶段 4：总览和小时趋势

- [x] 实现按房间权限过滤的筛选、总览、小时/采集点 API 与详情 API。
- [x] 实现 URL 可寻址全局筛选、KPI 和单位分组 ECharts。
- [x] 实现小时/采集点切换、Tooltip、详情抽屉与全部指标选择。
- [x] 运行阶段 4 API/前端/E2E 测试并记录结果。

### 阶段 5：主播、场控、透视和对比

- [x] 实现主播、场控和主播场控搭配分析 API/页面。
- [x] 实现昨日/上周/月度比较 API/页面。
- [x] 实现参考截图风格的树形透视表和明细/CSV/XLSX/图表图片导出。
- [x] 运行阶段 5 测试并记录结果。

### 阶段 6：预警与飞书推送

- [x] 实现阈值、防误报、去重、冷却和数据延迟/排班/经营规则。
- [x] 实现 Feishu Bot 签名、互动卡片、有限重试和 Mock 测试。
- [x] 实现预警列表、确认闭环、手动重推和带 Redis 防重锁的 Celery Beat 任务；阶段 16 加入主播趋势后当前共 10 个任务。
- [x] 运行阶段 6 测试并记录结果。

### 阶段 7：登录、权限与管理后台

- [x] 实现飞书 OAuth、state 校验、开发登录旁路、签名会话与 CSRF。
- [x] 实现 Viewer/Operator/Admin 与直播间级服务端数据权限和导出权限。
- [x] 实现数据源、指标、班次、权限、加密系统设置和审计管理 API/页面。
- [x] 运行阶段 7 测试并记录结果。

### 阶段 8：生产化与最终验收

- [x] 完成性能、安全、备份恢复、部署运维文档与生产配置校验。
- [x] 完成最终 E2E、86.55% 领域/服务覆盖率和 Docker Compose 静态验收。
- [x] 运行 `make check` 与 `make verify-production` 并生成 `docs/TEST_REPORT.md`。

### 阶段 9：真实 Base 用户 OAuth 实时同步

- [x] 根据外部 Base 跨租户限制，将在线读取改为 `user_access_token` 用户身份模式。
- [x] 授权范围加入 `bitable:app:readonly` 与 `offline_access`，令牌在数据库内加密保存。
- [x] 实现 access token 到期前刷新、refresh token 单次轮换保存和重新授权状态。
- [x] 将原占位 Celery 任务替换为真实 Base 分页读取、幂等入库和小时事实重建。
- [x] 实绩表与排班表独立同步；尚未提供排班链接不再阻断实绩数据。
- [x] 页面增加授权状态、立即同步按钮和分钟级自动刷新；本机轮询与生产 Celery Beat 均为 5 分钟。
- [x] 运行阶段 9 OAuth、加密轮换、用户令牌和单数据源同步测试。
- [x] 已开通离线访问、登记回调 URL并完成真实账号授权；目标 Base 表列表和记录接口均返回 HTTP 200。
- [x] 自动发现并同步同一 Base 下 4 张直播间表，共在线读取 857 条记录；未产生重复数据，小时事实成功重建。

### 阶段 10：完整功能与真实数据回归

- [x] 测试前备份正式 SQLite 数据库到 `backups/live_ops_20260714T080440Z.sqlite3`。
- [x] 对健康检查、授权状态、总览、小时/采集点趋势与详情、主播/场控/搭配分析、昨日/上周/月度对比、透视、CSV/XLSX 导出、预警、权限和管理后台执行 37 项实库 API 冒烟检查。
- [x] 修复管理后台“连接测试/扫描字段”误用租户令牌的问题，统一改用已授权的用户令牌并覆盖刷新流程；4 张真实飞书表连接测试与字段扫描全部返回成功。
- [x] 对真实 Base 执行手动全量同步，4 个在线数据源、2827 条指标事实同步成功，页面数据模式保持 `feishu`。
- [x] 修复后重新运行 `make check` 与 `make verify-production`，全量回归和生产静态验收均通过。

### 阶段 11：真实排班与应用机器人群推送

- [x] 测试前备份正式数据库到 `backups/live_ops_20260714T084631Z.sqlite3`。
- [x] 只读扫描排班 Base，自动解析页面块链接并发现“主播直播排班表”与“直播部门排班表”两张真实 `tbl...` 表。
- [x] 使用用户访问令牌同步主播排班 72 条、场控排班 19 条；第二次同步 91 条全部 unchanged。
- [x] 将 2026 年 7 月真实排班展开为 2232 条主播小时排班和 689 条人员日排班，并重建 2827 条小时事实。
- [x] 新增应用机器人按群 `chat_id` 发送、tenant token、有限重试和事件 UUID 去重；真实测试卡片返回 `code=0` 并创建消息。
- [x] 本机轮询增加每 30 分钟同步排班，生产 Celery Beat 同样保持每 30 分钟同步。
- [x] 运行 `make check` 与 `make verify-production`；43 个后端测试、3 个前端单测和 1 个 Playwright E2E 全部通过，覆盖率 86.56%。

### 阶段 12：日/月曲线与自动预警闭环

- [x] 修改前备份正式数据库到 `backups/live_ops_20260714T092014Z.sqlite3`。
- [x] 为全局筛选增加明确的“按日/范围”和“按月”模式；月份选择自动展开为月初至月末，并写入 URL 以支持刷新和分享。
- [x] 保持曲线 X 轴为“自然小时 + 主播”，46 个数值指标均可作为 Y 轴，日/月筛选覆盖总览、趋势、分析、对比和透视页面。
- [x] 将预警评估、事件创建和飞书推送串成自动闭环；新事件立即推送，pending/failed 事件每 5 分钟恢复重试，事件 UUID 保证飞书侧幂等。
- [x] 在隔离内存数据库模拟 7 日 ROI=1.5、8 日 ROI=3.0，真实应用机器人自动创建并向指定群成功发送 1 条预警，结果为当前值是基准值的 200%、较基准提升 100%。
- [x] 首次常驻评估暴露历史数据延迟事件补发问题；已改为只评估 Asia/Shanghai 时区最近结束的自然小时，重启不会回填历史预警，并增加专门回归测试。
- [x] 运行 `make check`；45 个后端测试、4 个前端单测和 1 个 Playwright E2E 全部通过，领域/服务覆盖率 87.38%。
- [x] 运行 `make verify-production`；7 服务、21 表、迁移、生产强密钥和 Docker 构建路径静态验收通过。

### 阶段 13：小时趋势多选筛选修复

- [x] 复现并定位 Axios 默认将数组序列化为 `room_ids[]=...`、`metric_keys[]=...`，FastAPI 因参数名不匹配而忽略直播间、主播、场控、小时和指标筛选。
- [x] 增加统一查询参数序列化器，将多选值编码为 FastAPI 可识别的重复同名参数，并自动忽略空值。
- [x] 增加前端单测覆盖全部五类多选参数；Playwright 选择 `08-09` 后验证实际请求无方括号、URL 更新且响应所有 X 轴点均为 `08-09`。
- [x] 运行 `make check`；45 个后端测试、5 个前端单测和 1 个 Playwright E2E 全部通过，领域/服务覆盖率 87.38%。

### 阶段 14：预警数据纠正与晚到实绩恢复

- [x] 修改前备份正式数据库到 `backups/live_ops_20260715T101133.sqlite3`。
- [x] 修复在线实绩表从通用名称“直播实绩”升级为真实表名后，payload 未变化导致旧采集点不重新归属的问题；同步时以直播间表名为权威来源，并回算未变化记录。
- [x] 清除房间映射变化后残留的空小时事实；“直播实绩”房间已确认 0 采集点、0 小时事实并停用。
- [x] 兼容飞书富文本“自动检查”字段，正确识别并排除 `错误` 行；同时去除人员排班姓名开头的 `@`，避免生成重复人员。
- [x] 数据延迟卡片改为显示直播间名称、计划主播、排班场控、中文等级和最近有效实绩，不再向群内展示 UUID 或笼统的“未标记”。
- [x] 实绩晚到后自动补全事件主播/场控并关闭对应数据延迟预警；正式库初次回算恢复 135 条，随后实时同步又恢复 4 条，共 139 条，其中包含截图中的两条 2026-07-14 18-19 预警。
- [x] 真实 Base 重新同步：散粉 453 条、妆前乳 454 条、达尔肤 0 条、Mistine 2 条；2026-07-14 18-19 两个直播间小时事实均为 complete。
- [x] 数值核对：散粉为主播 Q-陈莹、场控陈铭玉、ROI 1.92143331、消耗 7720.32；妆前乳为主播 J-琼文、场控陈铭玉、ROI 1.80785087、消耗 2828.22。
- [x] 本机 SQLite 启用 WAL、30 秒 busy timeout 和外键检查；实时同步写入期间连续请求概览 15 次均返回 HTTP 200，不再出现 `database is locked`。
- [x] 运行 `make check`；47 个后端测试、5 个前端单测和 1 个 Playwright E2E 全部通过，领域/服务覆盖率 88.11%。
- [x] 运行 `make verify-production`；7 服务、21 表、迁移、强密钥策略和 Docker 构建路径验证通过。

### 阶段 15：深度审计与 T+1 填报口径

- [x] 修复对比、分析、透视和导出接口遗漏全局筛选的问题，并补齐主播成员筛选链路。
- [x] 修复总览完整率只统计 complete 事实而恒为 100%、活动预警数固定为 0 的问题。
- [x] 修复事实从 complete 变为 missing 时残留旧小时指标，以及同采集时间记录依赖数据库返回顺序的问题。
- [x] 确认实绩为 T+1 补录，新增 `DATA_SUBMISSION_DEADLINE_HOUR=8`：次日 08:00 前不计缺失、不触发数据延迟或 ROI 告警。
- [x] 截止前总览显示“待次日 08:00 补录”；旧版截止前数据延迟误报会自动撤销，截止后晚到实绩仍会重评估原业务小时。
- [ ] 完成直播间通用别名归并、完整质量门禁、服务重启、浏览器回归及最终验收报告。

### 阶段 16：主播趋势汇总与分组推送（基础设施验收受阻）

- [x] 新增 `apps/api/app/domain/anchor_trends.py`：使用未舍入 `Decimal` 判断上涨、下跌、样本不足和无明显变化；基准 ROI/消耗为 0 时标记“无有效可比基准”。
- [x] 新增 `AnchorTrendService`：仅支持 `1/3/5/7/15/30` 天，以完整自然日当前周期对比紧邻等长基准周期，按 `room_id + actual_anchor_canonical` 隔离标准主播/组合名。
- [x] 周期 ROI 按 `SUM(period_overall_amount) / SUM(period_spend)` 重算，订单成本按 `SUM(period_spend) / SUM(period_overall_orders)` 重算；当前/基准完整率、有效小时和当前最低消耗/订单共同参与样本门槛。
- [x] 接入房间 ROI 目标匹配、目标差和达标状态；目标候选强制限定 `metric_code=period_overall_roi`，同房间/品类的非 ROI 目标不会误入，并有回归测试。
- [x] 下跌候选先于上涨候选，主状态红色优先；上涨/下跌/样本不足事件保存该类全量 `anchor_trend_items`，卡片仅展示 TopN（硬上限 10），一次规则运行最多发送上涨和下跌两张卡。
- [x] 新增迁移 `0005_anchor_trend_summaries`、`anchor_trend_events`、`anchor_trend_items`、规则扩展字段和默认 3 天每日 09:30 / 7 天周一 09:40 规则；业务时区要求 Asia/Shanghai。
- [x] 普通汇总去重键包含规则、周期天数、当前周期起止、目标群和通知类型；`force_resend` 要求原因并创建带 `source_event_id` 的新事件，复制全量明细，不覆盖原事件。
- [x] 数据质量规则硬隔离为仅系统记录：不进入业务运营群，手动重试也转为 `skipped`；Mock 卡片不记 `sent`。技术群字段只完成建模，尚未实现发送。
- [x] 新增并注册主播趋势 API：登录用户可查且按房间权限过滤，Operator/Admin 可重算，仅 Admin 可发送、强制重发和测试推送。
- [x] 新增 `anchor_trend_summary_job`，Celery Beat 每 5 分钟检查一次；3 天/7 天默认规则分别在 09:30 和周一 09:40 的 15 分钟窗口内到期。
- [x] 2026-07-18 实际运行领域/服务、旧预警隔离、迁移往返、健康和任务注册定向测试，结果 `29 passed, 1 warning in 13.71s`。
- [x] 迁移 0005 已应用于实际运行数据库；`alembic current` 为 `0005_anchor_trend_summaries (head)`，两张新表、扩展列和默认规则已由当前 API/实时任务读取。
- [x] 已补充主播趋势 API、Operator/Admin/Viewer、未授权房间及混合房间回归；`room_scope/anchor_count` 按可见明细重建，受限用户不返回混合事件原始 `message_snapshot`。5 个 JSON 路由现已绑定列表、重算、详情和推送专用严格 Pydantic `response_model`，OpenAPI 顶层及嵌套模型均拒绝未知字段。
- [x] 前端已新增主播趋势专用类型、API client，并在 `AlertsPage` 实现 URL 筛选、上涨/下跌/样本不足榜、状态/目标/完整率/有效小时、逐日/24 小时/原始事实详情，以及按角色显示的重算、测试、发送和强制重发原因表单。
- [x] 主播趋势前端定向单测实际结果：`client.test.ts`、`AlertsPage.test.tsx` 与 `HourlyComparisonRuleSettings.test.tsx` 原 10 测试通过；移动卡片回归加入后 `AlertsPage.test.tsx` 单文件为 5 测试通过。
- [x] 阶段 16 当时的前端 ESLint、TypeScript、Prettier、33 个全量单测、生产 build 和 Playwright E2E 均通过；阶段 17 已将测试扩展为 40 个，并用 650 KiB Chunk 硬门禁关闭原大 Chunk 提示。
- [ ] 在常驻 Celery/Beat 环境验证实际到期窗口、去重和单次最多两卡。当前阻塞证据：10 个任务注册测试通过；`celery inspect ping` 退出 69，`localhost:6379` 拒绝连接；本机无 Redis/Docker/Podman，WSL 无发行版。正式启用前还必须停止与 Beat 重叠的 `realtime_sync.py`。
- [x] 已向授权业务群各发送一次正式上涨/下跌业务卡：事件 `c3a93ebf-2a19-4dd9-a7b8-024f84d4c8e6` 与 `b4dda74d-3d1c-4ca4-9f32-391911e00049` 均为 `sent`、`push_attempts=1`；API 日志显示两次 token POST、两次消息 POST 和业务接口均 HTTP 200。去敏证据见 `artifacts/formal-anchor-trend-delivery-evidence.json`；原始 provider JSON 未持久化，证据文件明确不声称包含 `message_id`。
- [x] 在实际运行 API/数据库上完成桌面端浏览器回归并保留榜单、全量详情和规则配置截图；页签全局计数为上涨 4、下跌 2、样本不足 10，控制台 warning/error 与 HTTP 4xx/5xx 均为 0。
- [x] 通过当前实际 App Bot 配置发送上涨/下跌测试卡：两次均为 HTTP 200、`push_status=sent`；抽查原始回执 `code=0`、`msg=success`、`message_id=om_x100b6a9bebea813cc44e2f0b9060101`。测试卡不创建业务事件，不替代正式汇总卡实收。
- [x] 已补充 390×844 飞书 UA 移动、真实不存在主播筛选空态、隔离 API 500 错误态及 Viewer/Operator 身份 fixture 截图。移动 DOM 验收为 `scrollWidth=clientWidth=390`、4 张卡、0 个桌面表格、4 个详情按钮均在视口内；角色截图只证明前端显隐，服务端 RBAC 由 API 权限测试覆盖，不冒充真实飞书角色会话。
- [x] 完整 `make.cmd check` 通过：134 backend、33 frontend unit、1 Playwright E2E，覆盖率 86.87%。

### 阶段 17：Index 暖白 BI 视觉重构

- [x] 采用增量重构而非新建第二套应用；`data-theme="index-warm-bi"`、Ant Design 浅色算法、CSS Design Token 和 ECharts 主题为统一入口。
- [x] 外壳、桌面侧栏、移动 Drawer、顶部栏、PageHeader、筛选、KPI、卡片、表格、表单、Drawer/Modal 和所有既有路由已统一为暖白画布、白卡、近黑文字与橙蓝数据语义。
- [x] 经营总览保留全部业务能力并形成约 8/4 主图/摘要区；小时明细与直播间表现继续全宽。1920px 管理凭据表单限制为实测 1120px，下方 ROI 目标表继续全宽。
- [x] 主题单测验证主/次/muted 文字和完整数据色板在暖白/白底均达到 4.5:1；控件边界达到 3:1；浏览器 E2E 阻止 CSS Token 自引用回归。
- [x] 四个目标视口 390×844、1366×768、1440×900、1920×1080 均验证暖白主题、导航形态、页面级无横向溢出；Reduced Motion 同时关闭 CSS 过渡和 ECharts 动画。
- [x] 最新 `make.cmd check` 退出 0：Ruff、mypy、ESLint、TypeScript、Prettier、136 个后端测试、13 个前端文件/41 个单测、生产构建和 6 项 Playwright 全部通过；后端覆盖率 86.87%。
- [x] 生产构建转换 5559 modules；22 个 JS Chunk 全部 ≤650 KiB，无循环输出 Chunk 警告；最大 AntD 535.55 KiB / gzip 164.03 KiB，ECharts 464.61 KiB / gzip 162.88 KiB。
- [x] 最终 `dist` 严格端口运行探针通过：经营总览、小时趋势、Select Portal 和管理设置均业务就绪；page error、失败资源、console error、HTTP 4xx/5xx 全为 0；页面无横向溢出。
- [x] 生产 Preview 三次性能采样全部通过：中位数业务就绪 990ms、FCP 156ms、LCP 612ms、CLS 0、阻塞时间 86ms、24 个资源、807502 bytes。
- [x] 37 张最终截图覆盖四个目标视口与全部主要路由；`screenshot-manifest.json` 记录 fixture 来源、通过状态、时间戳和关键源码 SHA-256。已重建并检查顶部/全页联系表和关键原图，无 P0/P1 阻断、深色残留、重叠或页面级裁切。
- [x] 使用最终生产 `dist` 的真实“导出图片”动作生成 2038×1360 PNG；四角和 Alpha 通道均完全不透明，图例与第二行 Toolbox 不重叠，DataZoom 完整；SHA-256 已纳入清单。
- [x] 本地真实库运行故障已闭环：迁移前备份与副本演练通过，未版本化混合结构已升级至 0005；总览原始 500 请求现为 200，真实数据量、最新日期与 SQLite 完整性保持正常。
- [x] 飞书手动同步前端误超时已闭环：同步请求单独使用 120 秒，真实浏览器越过 15 秒旧边界并在 29.66 秒后收到 HTTP 200；状态、筛选与总览随后自动失效重取。

## 测试记录

| 时间       | 阶段                   | 命令                                                                                                                                            | 结果                                                                                                                                                    |
| ---------- | ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-07-13 | 输入勘察               | openpyxl 只读结构/样例扫描                                                                                                                      | 通过：2 个 52 字段直播 Sheet、2 个排班 Sheet 与关键样例均确认                                                                                           |
| 2026-07-13 | 阶段 0                 | `pytest tests/test_health.py -q`                                                                                                                | 通过：2 tests                                                                                                                                           |
| 2026-07-13 | 阶段 0                 | `npm run lint && npm run typecheck && npm run test:unit && npm run build`                                                                       | 通过：1 unit test，生产构建成功                                                                                                                         |
| 2026-07-13 | 阶段 1                 | `ruff + mypy + pytest -m integration`                                                                                                           | 通过：6 tests；fixture 脚本成功扫描并同步                                                                                                               |
| 2026-07-13 | 阶段 2                 | `ruff + mypy + pytest cleaning/models + alembic upgrade x2`                                                                                     | 通过：8 tests；21 表、52 字段与重复迁移通过                                                                                                             |
| 2026-07-13 | 阶段 3                 | `pytest aggregation + fixture database sync`                                                                                                    | 通过：6 tests；689 raw 幂等、小时事实与关键 Decimal 口径通过                                                                                            |
| 2026-07-13 | 阶段 3                 | `seed_demo + import_excel_fixture x2`                                                                                                           | 通过：seed、持久化同步和重复小时事实重建成功                                                                                                            |
| 2026-07-13 | 阶段 4                 | `pytest dashboard_api + npm lint/typecheck/unit/build`                                                                                          | 通过：1 API test、3 前端 tests、生产构建成功                                                                                                            |
| 2026-07-13 | 阶段 4                 | `playwright test`                                                                                                                               | 通过：1 E2E；生成 `artifacts/playwright-dashboard.png`                                                                                                  |
| 2026-07-13 | 阶段 5                 | `pytest dashboard/export + npm lint/typecheck/unit/build`                                                                                       | 通过：2 API/security tests、3 frontend tests                                                                                                            |
| 2026-07-13 | 阶段 5                 | `playwright test`                                                                                                                               | 通过：主播分析、数据对比、四层透视页面浏览器流程                                                                                                        |
| 2026-07-13 | 阶段 6                 | `ruff + mypy + pytest`                                                                                                                          | 通过：28 tests；预警防误报/去重/确认与机器人重试覆盖                                                                                                    |
| 2026-07-13 | 阶段 6                 | `npm lint + typecheck + test:unit + build + playwright`                                                                                         | 通过：3 frontend tests、生产构建、预警中心 Mock 评估/推送 E2E                                                                                           |
| 2026-07-13 | 阶段 7                 | `ruff + mypy + pytest`                                                                                                                          | 通过：31 tests；OAuth、签名会话、CSRF 与按直播间服务端隔离覆盖                                                                                          |
| 2026-07-13 | 阶段 7                 | `npm lint + typecheck + build + playwright`                                                                                                     | 通过：管理后台数据源扫描、预警与密钥掩码浏览器流程                                                                                                      |
| 2026-07-13 | 阶段 8                 | `make sync-feishu` 连续两次                                                                                                                     | 通过：无凭据自动 fallback；第二次 689 raw 全部 unchanged，小时事实稳定                                                                                  |
| 2026-07-13 | 阶段 8                 | `make check`                                                                                                                                    | 通过：34 backend、3 frontend unit、1 Playwright E2E，覆盖率 86.55%                                                                                      |
| 2026-07-13 | 阶段 8                 | `make verify-production`                                                                                                                        | 通过：7 服务、21 表、迁移、强密钥与 Docker 路径静态校验；Docker CLI 不可用                                                                              |
| 2026-07-14 | 飞书真实数据接入       | 主播数据源只读连通测试                                                                                                                          | 应用令牌获取成功；Base API 返回 HTTP 403 / 飞书错误码 91403，等待为应用开通多维表格读取权限并授权当前 Base                                              |
| 2026-07-14 | 飞书真实数据接入       | 权限开通后复测与邀请排障                                                                                                                        | 仍返回 HTTP 403 / 91403；截图确认目标 Base 标记为“外部”，企业自建应用跨租户邀请失败                                                                     |
| 2026-07-14 | 飞书真实数据接入       | `.base` 快照结构与数据质量检查                                                                                                                  | 通过：4 个数据表、52/53 字段、857 条记录；811 条有效业务记录，44 条计算辅助行和 2 条空行按规则排除                                                      |
| 2026-07-14 | 飞书真实数据接入       | `.base` 导入连续两次                                                                                                                            | 通过：首次创建 857 raw，第二次 857 条全部 unchanged；2424 小时事实稳定                                                                                  |
| 2026-07-14 | 飞书真实数据接入       | `make check`                                                                                                                                    | 通过：35 backend、3 frontend unit、1 Playwright E2E，覆盖率 86.37%                                                                                      |
| 2026-07-14 | 飞书真实数据接入       | `make verify-production`                                                                                                                        | 通过：7 服务、21 表、迁移、强密钥与 Docker 路径静态校验；Docker CLI 不可用                                                                              |
| 2026-07-14 | 阶段 9 OAuth           | `pytest test_auth_permissions + test_feishu_client + test_feishu_sync_service`                                                                  | 通过：9 tests；令牌加密、刷新轮换、用户令牌读取及缺少排班源不阻断均覆盖                                                                                 |
| 2026-07-14 | 阶段 9 静态与前端      | `ruff + mypy + eslint + tsc + vitest`                                                                                                           | 通过：Python 严格类型无错误，3 个前端单测通过                                                                                                           |
| 2026-07-14 | 阶段 9 最终验收        | `make check`                                                                                                                                    | 通过：41 backend、3 frontend unit、1 Playwright E2E，覆盖率 86.90%                                                                                      |
| 2026-07-14 | 阶段 9 生产验收        | `make verify-production`                                                                                                                        | 通过：7 服务、21 表、迁移、强密钥与 Docker 路径静态校验；Docker CLI 不可用                                                                              |
| 2026-07-14 | 阶段 9 真实 OAuth      | 用户授权 + Base API + 正式同步                                                                                                                  | 通过：令牌含 `bitable:app:readonly`、`offline_access`；表/记录接口 HTTP 200；426 条在线记录全部幂等 unchanged，页面切换为 `feishu`                      |
| 2026-07-14 | 阶段 9 多表实时        | Base 自动发现 + 4 表同步                                                                                                                        | 通过：柏瑞美-散粉 426、柏瑞美-妆前乳 429、达尔肤-洁面乳 0、Mistine 水散粉 2，共 857 条；页面与 5 分钟轮询使用真实用户令牌                               |
| 2026-07-14 | 阶段 10 实库完整功能   | 37 项真实 API 冒烟 + 4 表连接/字段扫描 + 手动同步                                                                                               | 通过：37/37；4 个在线源、2827 条指标事实同步成功；管理后台连接/扫描已改用用户令牌                                                                       |
| 2026-07-14 | 阶段 10 修复后全量回归 | `make check`                                                                                                                                    | 通过：41 backend、3 frontend unit、1 Playwright E2E，覆盖率 86.90%                                                                                      |
| 2026-07-14 | 阶段 10 修复后生产验收 | `make verify-production`                                                                                                                        | 通过：7 服务、21 表、迁移、强密钥与 Docker 路径静态校验；Docker CLI 不可用                                                                              |
| 2026-07-14 | 阶段 11 真实排班       | Base 扫描 + 在线同步连续两次                                                                                                                    | 通过：主播 72、场控 19；第二次 91 条全部 unchanged；2232 主播小时排班、689 人员日排班                                                                   |
| 2026-07-14 | 阶段 11 真实群预警     | 应用机器人 + `chat_id` 测试卡片                                                                                                                 | 通过：tenant token 鉴权成功，返回 `code=0` 并创建消息                                                                                                   |
| 2026-07-14 | 阶段 11 完整回归       | `make check`                                                                                                                                    | 通过：43 backend、3 frontend unit、1 Playwright E2E，覆盖率 86.56%                                                                                      |
| 2026-07-14 | 阶段 11 生产验收       | `make verify-production`                                                                                                                        | 通过：7 服务、21 表、迁移、强密钥与 Docker 路径静态校验；Docker CLI 不可用                                                                              |
| 2026-07-14 | 阶段 12 自动预警闭环   | 隔离数据库 1.5→3.0 + 真实应用机器人                                                                                                             | 通过：created 1、queued 1、sent 1、failed 0；正式业务数据库未写入测试数据                                                                               |
| 2026-07-14 | 阶段 12 历史补发保护   | 最近小时范围 + Asia/Shanghai 时间判断                                                                                                           | 通过：旧小时 created 0、queued 0；服务重启不回填历史预警                                                                                                |
| 2026-07-14 | 阶段 12 完整回归       | `make check`                                                                                                                                    | 通过：45 backend、4 frontend unit、1 Playwright E2E，覆盖率 87.38%                                                                                      |
| 2026-07-14 | 阶段 12 生产验收       | `make verify-production`                                                                                                                        | 通过：7 服务、21 表、迁移、强密钥与 Docker 路径静态校验；Docker CLI 不可用                                                                              |
| 2026-07-14 | 阶段 13 筛选回归       | Axios 参数序列化单测 + Playwright                                                                                                               | 通过：直播间/主播/场控/小时/指标使用重复参数；选择 08-09 后响应点全部为 08-09                                                                           |
| 2026-07-14 | 阶段 13 完整回归       | `make check`                                                                                                                                    | 通过：45 backend、5 frontend unit、1 Playwright E2E，覆盖率 87.38%                                                                                      |
| 2026-07-15 | 阶段 14 真实 Base 回算 | 用户 OAuth 全量同步 + 实库数值核对                                                                                                              | 通过：909 条在线记录；18-19 两个直播间实绩、主播、场控、ROI 和消耗均与源表一致                                                                          |
| 2026-07-15 | 阶段 14 预警恢复       | 正式库数据延迟事件重算                                                                                                                          | 通过：139 条晚到实绩预警自动恢复；截图两条事件已补全人员并关闭                                                                                          |
| 2026-07-15 | 阶段 14 同步并发回归   | 实时同步期间连续请求概览 15 次                                                                                                                  | 通过：15/15 HTTP 200，耗时 127-327ms，无 SQLite 锁错误                                                                                                  |
| 2026-07-15 | 阶段 14 完整回归       | `make check`                                                                                                                                    | 通过：47 backend、5 frontend unit、1 Playwright E2E，覆盖率 88.11%                                                                                      |
| 2026-07-15 | 阶段 14 生产验收       | `make verify-production`                                                                                                                        | 通过：7 服务、21 表、迁移、强密钥与 Docker 路径静态校验；Docker CLI 不可用                                                                              |
| 2026-07-18 | 阶段 16 后端定向验证   | `python -m pytest tests/test_anchor_trends.py tests/test_alerts.py tests/test_migrations.py tests/test_health.py tests/test_celery_tasks.py -q` | 通过：29 passed，耗时 13.71s；1 条第三方 Starlette TestClient/httpx 弃用警告。范围仅为所列测试，不代表完整 `make check`、运行库迁移、真实飞书或前端验收 |
| 2026-07-18 | 阶段 16 前端定向单测   | `npx vitest run src/api/client.test.ts src/pages/AlertsPage.test.tsx --reporter=dot`                                                            | 通过：2 test files、6 tests，耗时 7.07s；使用 Mock API，不代表实际 API/权限或浏览器验收                                                                 |
| 2026-07-18 | 阶段 16 前端质量门禁   | `npm run lint`；`npm run typecheck`；`npm run test:unit`；`npm run build`                                                                       | 部分通过：typecheck 通过；12 test files/32 tests 通过；生产 build 通过并有大 chunk 警告。lint 未通过（7 errors、1 warning），因此未标记完整门禁通过     |
| 2026-07-18 | 阶段 16 完整回归       | `make.cmd check`                                                                                                                                | 通过：Ruff/ESLint/mypy/TypeScript/Prettier、134 backend、33 frontend unit、生产 build、1 Playwright E2E；后端覆盖率 86.87%                              |
| 2026-07-18 | 阶段 16 运行库验收     | Alembic current + 实际 API + Playwright Chrome                                                                                                  | 通过：运行库 0005 head；上涨 4、下跌 2、样本不足 10；详情 Drawer 860px，规则表完整，无控制台或 HTTP 错误；桌面截图已保存                               |
| 2026-07-18 | 阶段 16 飞书测试卡     | 实际 App Bot 上涨/下跌测试推送                                                                                                                  | 通过：两次 HTTP 200、`push_status=sent`；抽查飞书 `code=0`、`msg=success` 并返回可核验 `message_id`；不创建业务事件                                    |
| 2026-07-18 | 阶段 16 严格响应契约   | OpenAPI 契约测试 + 重算/列表/详情/发送/权限 API 测试                                                                                            | 通过：5 个 JSON 路由均引用命名 Pydantic 响应模型，顶层和嵌套模型 `extra=forbid`；实际业务 API 路径测试通过                                                |
| 2026-07-18 | 阶段 16 正式业务卡     | 实际 App Bot 正式上涨/下跌汇总发送 + 事件回读 + API 进程日志                                                                                     | 通过：两事件均 `sent`、各尝试 1 次；飞书 token/message POST 和业务接口均 HTTP 200。原始 provider JSON 未持久化，去敏证据明确不包含 `message_id`          |
| 2026-07-18 | 阶段 16 状态与移动验收 | Playwright 390×844 飞书 UA、真实空态、隔离错误态、Viewer/Operator fixture                                                                        | 通过：移动 4 卡且无横向溢出，空态无错误，错误态有重试，Viewer 无管理操作，Operator 仅有重算；fixture 不冒充真实 RBAC 会话                               |
| 2026-07-18 | 阶段 16 Celery 探测    | 任务注册、`/ready`、`celery inspect ping --timeout=2`、本机运行时检查                                                                            | 阻塞：10 个任务注册通过；Redis `down`，inspect 退出 69；无 Redis/Docker/Podman 且 WSL 无发行版，不能启动真实 Worker/Beat                                 |
| 2026-07-18 | 阶段 17 完整回归       | `make.cmd check`                                                                                                                                | 通过：Ruff/ESLint/mypy/TypeScript/Prettier、136 backend、13 files/41 frontend unit、生产 build、6 Playwright；后端覆盖率 86.87%                         |
| 2026-07-18 | 阶段 17 生产构建       | `npm run build` + Chunk audit                                                                                                                    | 通过：5559 modules、22 JS chunks 全部 ≤650 KiB；无循环输出 Chunk；最大 AntD 535.55 KiB / gzip 164.03 KiB                                                |
| 2026-07-18 | 阶段 17 生产运行探针   | 严格端口 Vite Preview + 隔离 API + Playwright 页面/资源/Portal 探针                                                                              | 通过：总览、小时趋势、Select Portal、管理设置均就绪；page/resource/console/HTTP 错误为 0；表单 1120px；页面无横向溢出                                  |
| 2026-07-18 | 阶段 17 生产性能       | `npm run audit:performance`，最终 `dist` 三次采样                                                                                               | 通过：中位数业务就绪 990ms、FCP 156ms、LCP 612ms、CLS 0、阻塞 86ms、24 resources、807502 bytes                                                         |
| 2026-07-18 | 阶段 17 视觉验收       | 37 张四视口截图 + top/full 联系表 + 关键原图复核                                                                                                | 通过：清单以关键源码 SHA-256 绑定；未发现 P0/P1、深色残留、重叠、页面级横向溢出或裁切                                                                  |
| 2026-07-18 | 阶段 17 图表真实导出   | 最终生产 `dist` 点击“导出图片” + PNG 像素/视觉复核                                                                                               | 通过：2038×1360、Alpha 255..255、图例/Toolbox 分行、DataZoom 完整；SHA-256 `5692a9c1…a3aa987`                                                          |
| 2026-07-18 | 本地真实库迁移修复     | 迁移前备份 + 真实库副本演练 + Alembic 0001→0005 + 原始总览请求与浏览器复核                                                                       | 通过：SQLite integrity `ok`；1047 条小时事实、最新 2026-07-17 保持；总览直连/代理 200，页面数据正常，控制台 0 错误                                     |
| 2026-07-19 | 飞书手动同步超时修复   | 真实 OAuth/多维表格分页 + 90 秒直连回执 + 浏览器点击 + Vitest + `make.cmd check`                                                                 | 通过：四源/同步 POST 均 HTTP 200；页面越过旧 15 秒边界后成功，状态刷新；本次 1109 条全 unchanged、0 invalid；自动周期仍因无 Redis/Celery 阻塞            |
| 2026-07-22 | GitHub 发布前干净检出验收 | 临时移除私有 Excel 后执行 Playwright 6 项主流程                                                                                               | 通过：运行时生成匿名合成直播/排班数据；总览、小时筛选、图表、详情、导出、预警、权限与管理流程 6/6 通过；私有 Excel、`.env`、数据库与日志保持忽略          |
| 2026-07-22 | GitHub 发布前完整回归 | `make.cmd check`                                                                                                                                | 通过且退出 0：Ruff、ESLint、mypy、TypeScript、Prettier、174 backend、17 files/58 frontend unit、生产 build、6 Playwright；后端覆盖率 86.42%              |
| 2026-07-22 | GitHub 发布前生产验收 | `make.cmd verify-production`                                                                                                                    | 通过且退出 0：7 服务、33 表、迁移、强密钥与公网 HTTPS 策略、生产无夹具写入及 Docker 构建路径；本机无 Docker CLI，完成等价静态校验                      |

## 飞书真实数据接入

- [x] 已配置主播数据源的 Base、Table 与 View 标识（凭据仅保存在本机 `.env`）。
- [x] 已验证 App ID / App Secret 可成功换取租户访问令牌。
- [x] 已从用户提供的 `.base` 离线快照导入真实主播、场控与经营指标，并补算快照未缓存的公式字段。
- [x] 已完成两次幂等导入、小时事实重建、API 数值核对与完整回归验收。
- [x] 已实现用户 OAuth 跨租户读取、加密持久化、自动刷新和 5 分钟定时同步。
- [x] 已完成 `offline_access`、本机回调 URL、真实账号授权和目标外部 Base 在线读取验证。
- [x] 已完成 4 张真实表的管理后台连接测试、字段扫描和手动全量同步验收。
- [x] 已配置第二个排班 Base，在线同步主播/场控排班并完成幂等、排班关联和全量回归测试。
- [x] 已使用现有应用机器人向指定群发送真实测试预警卡片；该历史卡片不是主播趋势汇总卡回执。
- [x] 已发送主播趋势正式上涨/下跌卡并保留事件终态、发送时间、请求 ID 及两次飞书消息 HTTP 200 证据；Mock/历史消息未作为本功能证据。
- [ ] 应用当前不持久化 provider 原始响应正文；本次发送返回的原始 JSON 未单独归档，现有证据不声称包含正式卡 `message_id`。如业务要求原始回执长期可追溯，应先增加去敏持久化再做下一次受控发送，不为补证重复打扰业务群。
- [x] 已完成真实表名归属回算、富文本自动检查清洗和晚到实绩预警自动恢复。

## 环境限制

- 当前机器未安装 Docker CLI，Compose 运行态将在具备 Docker Desktop/Engine 的环境补充验证。
- 当前机器未安装 GNU Make；仓库已提供 `make.cmd` 作为 Windows 等价入口并用于完整门禁。
- 当前机器没有 Redis、Docker、Podman 或可运行的 WSL Linux 发行版；Redis `6379` 无监听，Celery Worker/Beat 因 broker 不可达无法启动。最小恢复路径是提供外部 Redis，或安装 Debian WSL 与 `redis-server` 后把 Worker/Beat 一并放入 Linux；Celery 官方不支持 Windows，`solo` 池只能用于本机验证。
