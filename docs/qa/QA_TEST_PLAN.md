# 多直播间小时数据驾驶舱独立QA测试计划

## 1. 文档信息

- 测试角色：独立高级软件测试工程师、测试架构师、数据质量审计工程师、安全测试工程师
- 执行开始：2026-07-16 17:58:17 +08:00
- 被测应用版本：0.1.0（后端与前端清单版本）
- 版本标识：当前Git仓库为未创建首个提交的 unborn `main`，无Commit ID；以锁文件SHA-256和测试时间标识本次快照
- 仓库：`C:\Users\Administrator\Documents\直播间数据\codex_live_dashboard_pack`
- APP URL：`http://127.0.0.1:5173`
- API URL：`http://127.0.0.1:8000`
- 本地测试数据库：`live_ops_test.db`（只读运行态审计）

## 2. 测试约束

1. 不修改 `apps/`、`config/`、迁移或其他生产业务代码。
2. 仅新增 `docs/qa/`、`qa/` 下的测试资产、报告和证据。
3. 不向正式数据库写入破坏性数据；需要写入的确定性测试仅使用pytest临时/内存数据库。
4. 不调用真实同步写入口，不刷新OAuth令牌，不发送真实飞书消息。
5. 飞书测试仅运行现有MockTransport、fixture或dry-run路径。
6. 不读取或输出 `.env`、App Secret、Webhook、数据库密码、Token或个人隐私；环境仅记录 `configured/empty`。
7. 已有E2E在运行前检查其副作用；含写接口或真实同步/推送的场景不直接运行。
8. 发现问题先复现、记录、保存证据，不静默修改业务代码。

## 3. 准入与发布门槛

- P0=0、P1=0。
- 核心数据、权限、ROI目标、30%规则、周期边界、预警去重必须100%通过。
- 核心E2E和回归通过率至少95%。
- Ruff、mypy、pytest、ESLint、TypeScript、Vitest、构建、Playwright和生产静态验证通过。
- 无敏感信息、未授权数据和导出泄露。
- 关键查询达到目标或有经批准的风险说明。
- 任何核心数据口径错误或权限绕过直接判定“不建议发布”。

## 4. 范围与方法

### 4.1 环境与基线

- 读取AGENTS、MASTER_PROMPT、README及全部docs。
- 记录Git、锁文件哈希、OS、Python、Node、npm、SQLite、浏览器、Alembic、数据库快照和服务健康。
- 检查Docker/Compose、Make入口、CI和部署配置。

### 4.2 现有自动化门禁

- 后端：Ruff format/check、mypy strict、全量pytest及覆盖率。
- 前端：Prettier check、ESLint、tsc、全量Vitest、Vite build。
- API/E2E：现有API测试；检查E2E副作用后执行安全场景。
- 迁移：临时SQLite空库upgrade/downgrade/re-upgrade、当前库版本与模型约束。
- 安全/依赖：pip-audit或等价、npm audit、敏感信息模式扫描、配置静态验证。

### 4.3 数据口径审计

构建独立只读数值Oracle，按 `原始记录 → 采集点 → 小时事实 → API → 页面/导出` 核对：

- ROI、净ROI、整体/净订单成本、笔单价、可重算转化率。
- 分母0、缺失、真实0、进行中、未来、异常状态。
- 累计字段LAST/LAST_PER_ROOM_DAY，禁止小时快照求和。
- 1/3/5/7/15/30天及自定义周期、跨月/年/闰年、23-24和Asia/Shanghai边界。
- 固定24小时、OHLC及average/median/total/effective_days/coverage/date字段。
- 三个直播间ROI目标、目标优先级/有效期/禁用/未配置。
- 确定性A-F状态、29.999/30.000和-29.999/-30.000边界、3.00/1.50语义。

### 4.4 API、权限与安全

- OpenAPI实际路由与产品契约差异。
- Viewer/Operator/Admin、未登录、过期会话、房间受限用户。
- 查询、详情、导出、预警、配置、同步和原始记录的服务端授权。
- SQL注入、XSS/HTML、CSV公式注入、路径遍历、开放重定向、CORS/CSRF、调试堆栈、前端Bundle密钥、日志脱敏。
- 只读探针优先；不调用生产写接口。

### 4.5 前端、交互、兼容性和可用性

- 全部路由核心流程、筛选联动、URL恢复、重置、空/错/加载/权限状态。
- 24小时ROI/消耗/附加指标、K线、目标线、Tooltip、图表/表格/抽屉联动。
- 原小时趋势继续显示自然小时+主播。
- Chrome桌面视口1920×1080、1440×900、1366×768和移动390×844。
- Edge、飞书桌面/移动内嵌若环境不可用则Blocked，不冒充Passed。
- 键盘、焦点、可访问名称、非颜色状态、中文数字/文案一致性。

### 4.6 飞书、排班和预警

- 现有Excel fixture、Mock Feishu API的分页、重试、幂等、删除/更新/异常字段。
- 排班宽转长、组合主播、跨天班次、断播/休息/未排班。
- Mock/dry-run预警规则、T+1截止、合并、去重、失败重试、终态重推保护。
- 无线上测试凭据时明确标记线上联调未执行；不向正式群发消息。

### 4.7 性能和稳定性

- 1/7/30天、单/多直播间、多指标、K线、详情分页的冷/热请求。
- 10并发；50并发仅在本机稳定且无副作用时执行。
- 平均、P50/P95/P99、错误率、吞吐、响应体大小。
- SQLite `EXPLAIN QUERY PLAN`、索引、N+1/全表扫描风险。
- 前端首屏时间和控制台/失败请求；长时稳定与真实并发同步因环境限制单列。

## 5. 证据和结果格式

- 用例：`qa/testcases/test_cases.csv`
- 机器结果：`qa/results/*.json`、`qa/results/bug_list.csv`
- 截图：`qa/evidence/screenshots/`
- 视频：`qa/evidence/videos/`
- 命令/应用日志：`qa/evidence/logs/`
- 网络请求：`qa/evidence/network/`
- 导出样本：`qa/evidence/exports/`
- 数据库审计：`qa/evidence/database/`

所有未执行项只允许标记Blocked或Skipped并说明原因；测试报告不沿用历史“已通过”声明作为本轮结果。

## 6. 退出条件

完成全量可执行门禁、核心数值Oracle、GET/API安全探针、浏览器核心回归、Mock飞书/预警测试、性能采样；每个确认缺陷至少稳定复现两次或由确定性静态/测试证据证明；生成规定的七份报告和六份机器结果文件，并给出“建议发布/有条件发布/不建议发布”唯一结论。
