# Codex 主任务：构建「多直播间小时数据驾驶舱」

你是一名资深全栈架构师、数据工程师、BI 产品工程师和测试负责人。请在当前代码仓库中直接创建一个可运行、可部署、可测试的生产级内部应用，名称为：

> 多直播间小时数据驾驶舱

不要只输出方案、伪代码、原型图或静态页面。你必须实际创建项目、数据库模型、数据同步、后端接口、前端页面、后台任务、飞书群预警、测试、Docker 部署文件和使用文档。

如果当前仓库为空，从零初始化。若仓库已有代码，先检查现有结构，优先复用，不要无故重写。

---

## 一、执行约定

1. 开始编码前先完成以下文件：
   - 根目录 `AGENTS.md`
   - `docs/EXEC_PLAN.md`
   - `docs/ARCHITECTURE.md`
   - `docs/DATA_DICTIONARY.md`
   - `docs/PROGRESS.md`
2. `docs/EXEC_PLAN.md` 必须拆分里程碑、任务、测试方式和完成标准。
3. 完成一个阶段后：
   - 运行对应测试；
   - 更新 `docs/PROGRESS.md`；
   - 修复失败后再继续下一阶段。
4. 不要把核心功能留成空壳或 TODO。
5. 若缺少飞书凭证：
   - 继续实现完整代码；
   - 使用 Mock Feishu 服务和本地 Excel fixture 完成测试；
   - 在最终报告中列出只需用户补充的环境变量；
   - 不得因没有凭证停工。
6. 不要向前端暴露飞书 App Secret、机器人签名密钥或数据库密码。
7. 不要在代码、测试快照、日志或 Git 中提交真实密钥。
8. 所有金额和比率计算使用 `Decimal`/数据库 `NUMERIC`，不要用二进制浮点直接做业务计算。
9. 所有时间以 `Asia/Shanghai` 为业务时区，数据库保存带时区时间。
10. 中文界面，桌面端优先，兼容飞书内移动端查看。
11. 如果遇到需求歧义，优先采用本任务书给定的口径；不得自行把累计数据当小时数据。
12. 每次完成任务前运行：格式化、静态检查、单元测试、集成测试和关键 E2E 测试。

---

## 二、数据源

### 1. 直播数据与实际主播、场控数据

```text
https://my.feishu.cn/base/<FEISHU_LIVE_APP_TOKEN>?table=blk9sHtuG8jrg5aD
```

配置参数：

```text
app_token = <FEISHU_LIVE_APP_TOKEN>
table_id = blk9sHtuG8jrg5aD
source_role = live_actual
```

### 2. 场控和主播排班数据

```text
https://my.feishu.cn/base/<FEISHU_SCHEDULE_APP_TOKEN>?table=<FEISHU_SCHEDULE_TABLE_ID>&view=vewT1IewEt
```

配置参数：

```text
app_token = <FEISHU_SCHEDULE_APP_TOKEN>
table_id = <FEISHU_SCHEDULE_TABLE_ID>
view_id = vewT1IewEt
source_role = schedule
```

### 3. 本地开发 fixture

如果仓库中存在以下文件，必须读取并用于开发验证：

```text
fixtures/【吉拾开张】直播间数据登记系统（AI）.xlsx
fixtures/【吉拾开张】直播部门排班系统(2).xlsx
fixtures/img_v3_0213e_9a8b845c-5c6a-46fb-8514-589e8e3f64dg.jpg
```

已知 Excel 结构：

```text
直播间数据登记系统：
- Sheet：柏瑞美-散粉，范围约 A1:AZ303
- Sheet：柏瑞美-妆前乳，范围约 A1:AZ304
- 每个直播间 Sheet 共 52 个字段

直播部门排班系统：
- Sheet：直播部门排班表，范围约 A1:AI13
- Sheet：主播直播排班表，范围约 A1:AH73
```

如果 fixture 不存在，生成结构相同的小型测试 fixture，但不要虚构生产数据。

### 4. 访问方式

禁止通过浏览器抓取或模拟登录读取飞书网页。必须使用飞书开放平台 API：

- 服务端使用自建应用 `app_id`、`app_secret` 获取租户访问令牌；
- 服务端分页读取多维表格字段与记录；
- 令牌按返回的过期时间缓存并提前刷新；
- 接口发生 429 或 5xx 时使用指数退避和有限重试；
- 所有请求设置连接和读取超时；
- 记录飞书请求 ID、错误码和同步批次，但日志中不得输出密钥。

---

## 三、业务目标

应用必须实现：

1. 支持多个直播间，不得写死当前两个直播间。
2. 同时读取直播实际数据、主播排班和人员排班。
3. 可按日期、日期范围、月份、直播间、主播、主播成员、场控、自然小时和指标筛选。
4. 核心曲线图 X 轴显示“自然小时 + 主播名字”。
5. 多日模式显示“日期 + 自然小时 + 主播名字”。
6. 全部数值指标都能通过指标选择器查看。
7. 不同单位的指标自动分图或分轴，不能全部强行压到同一 Y 轴。
8. 小时趋势优先使用“时段”字段，不能用累计整体字段冒充小时增量。
9. 支持原始采集点模式，能查看真实的“几点几分”数据。
10. 支持今日对昨日、今日对上周、日期 A 对日期 B、本月对上月等比较。
11. 支持主播分析、场控分析和主播场控搭配分析。
12. 支持主播小时排班与实际主播核对。
13. 支持场控当天班次、是否休息和是否可能在岗的判断。
14. 支持数据异常、经营异常、排班异常和数据延迟预警。
15. 预警通过飞书群机器人推送。
16. 预警有去重、冷却时间、失败重试和处理闭环。
17. 页面视觉参考用户提供的蓝色圆角汇总表截图。
18. 支持筛选结果导出 CSV/XLSX，图表导出图片。
19. 支持飞书账号登录、角色权限和按直播间授权。
20. 提供 Docker 一键部署和完整运维文档。

---

## 四、强制技术栈

除非当前仓库已有成熟等价方案，否则使用以下技术栈：

### 后端

- Python 3.12+
- FastAPI
- Pydantic 2
- SQLAlchemy 2
- Alembic
- PostgreSQL
- Redis
- Celery Worker + Celery Beat
- HTTPX
- pytest
- Ruff
- mypy

### 前端

- React
- TypeScript 严格模式
- Vite
- React Router
- TanStack Query
- Zustand 或等价轻量状态管理
- Ant Design
- Apache ECharts
- Playwright
- ESLint
- Prettier

### 基础设施

- Docker Compose
- Nginx 或 Caddy 反向代理
- GitHub Actions 或等价 CI

不得只用 Streamlit 作为正式版本。允许提供 Streamlit 快速调试工具，但正式交付必须是前后端分离的 Web 应用。

---

## 五、仓库结构

创建如下结构，可根据实现做小幅调整，但职责必须清晰：

```text
.
├── AGENTS.md
├── Makefile
├── README.md
├── .env.example
├── docker-compose.yml
├── apps
│   ├── api
│   │   ├── app
│   │   │   ├── api
│   │   │   ├── auth
│   │   │   ├── core
│   │   │   ├── db
│   │   │   ├── domain
│   │   │   ├── integrations
│   │   │   │   └── feishu
│   │   │   ├── models
│   │   │   ├── repositories
│   │   │   ├── schemas
│   │   │   ├── services
│   │   │   ├── tasks
│   │   │   └── main.py
│   │   ├── alembic
│   │   ├── tests
│   │   └── pyproject.toml
│   └── web
│       ├── src
│       │   ├── api
│       │   ├── components
│       │   ├── features
│       │   ├── hooks
│       │   ├── layouts
│       │   ├── pages
│       │   ├── routes
│       │   ├── stores
│       │   ├── styles
│       │   ├── types
│       │   └── utils
│       ├── tests
│       └── package.json
├── config
│   ├── field_aliases.yml
│   ├── metric_seed.yml
│   └── shift_seed.yml
├── docs
│   ├── EXEC_PLAN.md
│   ├── ARCHITECTURE.md
│   ├── DATA_DICTIONARY.md
│   ├── FEISHU_SETUP.md
│   ├── DEPLOYMENT.md
│   ├── OPERATIONS.md
│   ├── TEST_REPORT.md
│   └── PROGRESS.md
├── fixtures
├── infra
│   ├── nginx
│   └── scripts
└── scripts
    ├── import_excel_fixture.py
    ├── seed_demo.py
    └── verify_production.py
```

---

## 六、环境变量

创建 `.env.example`，至少包含：

```dotenv
APP_ENV=development
APP_NAME=live-ops-dashboard
APP_BASE_URL=http://localhost:8080
API_BASE_URL=http://localhost:8000
TIMEZONE=Asia/Shanghai

DATABASE_URL=postgresql+psycopg://live_ops:change_me@postgres:5432/live_ops
REDIS_URL=redis://redis:6379/0
JWT_SECRET=change_me
FIELD_ENCRYPTION_KEY=change_me

FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_REDIRECT_URI=http://localhost:8080/auth/feishu/callback

FEISHU_LIVE_APP_TOKEN=<FEISHU_LIVE_APP_TOKEN>
FEISHU_LIVE_TABLE_ID=blk9sHtuG8jrg5aD
FEISHU_LIVE_VIEW_ID=

FEISHU_SCHEDULE_APP_TOKEN=<FEISHU_SCHEDULE_APP_TOKEN>
FEISHU_SCHEDULE_TABLE_ID=<FEISHU_SCHEDULE_TABLE_ID>
FEISHU_SCHEDULE_VIEW_ID=vewT1IewEt
FEISHU_SCHEDULE_YEAR=

FEISHU_BOT_WEBHOOK_URL=
FEISHU_BOT_SECRET=

LIVE_SYNC_INTERVAL_MINUTES=5
SCHEDULE_SYNC_INTERVAL_MINUTES=30
ALERT_DELAY_MINUTES=15
ALERT_RETRY_LIMIT=3

DEV_AUTH_BYPASS=true
DEV_ADMIN_EMAIL=dev@example.com
LOG_LEVEL=INFO
```

要求：

- 生产环境强制关闭 `DEV_AUTH_BYPASS`；
- Webhook 和签名密钥在数据库中如允许配置，必须加密保存；
- API 返回系统设置时必须掩码处理密钥；
- `.env` 必须加入 `.gitignore`。

---

## 七、飞书数据源适配器

实现 `FeishuBitableClient`，至少包含：

```python
get_tenant_access_token()
list_tables(app_token)
list_fields(app_token, table_id)
list_records(app_token, table_id, view_id=None, page_token=None)
health_check_source(...)
```

要求：

1. 使用服务端 HTTP 客户端，不在浏览器中直接调用飞书并暴露 App Secret。
2. 访问令牌使用 Redis 缓存，以接口返回的 `expire` 为准提前刷新。
3. 分页读取记录，直到 `has_more=false`。
4. 单页数量使用官方允许的最大值或安全上限。
5. 保存每次请求耗时、返回记录数和错误码。
6. 对 429、超时和 5xx 做指数退避重试；4xx 权限错误直接记录并给出明确提示。
7. 保留源记录 ID、源创建时间、源更新时间和原始字段 JSON。
8. 计算 payload hash；内容未变化时避免重复清洗。
9. 支持字段扫描和字段类型扫描。
10. 管理后台提供“测试连接”“扫描字段”“立即同步”按钮。
11. 支持一个 Base 配置多个 Table，便于以后增加直播间表或排班表。
12. 如果实际直播数据没有“直播间”字段，允许数据源配置 `default_room_name`。
13. 如果排班 Base 中存在多个相关表，提供“发现数据表”功能，并根据字段特征识别：
    - 有“直播间、月份、时段、1日…31日”时识别为主播小时排班；
    - 有“姓名、岗位、状态、月份、1日…31日”时识别为人员日排班。
14. 如果当前给定 Table 只含其中一种排班，不得凭空构造另一种；管理页面显示缺失状态并允许管理员添加另一个 Table ID。

---

## 八、数据库设计

使用 UUID 主键、带时区时间和 PostgreSQL JSONB。创建 Alembic 迁移。

### 1. `source_configs`

保存数据源配置：

- id
- name
- source_type：`feishu_bitable`、`excel_fixture`
- source_role：`live_actual`、`anchor_schedule`、`staff_schedule`
- app_token
- table_id
- view_id
- default_room_name
- schedule_year
- field_mapping JSONB
- enabled
- last_sync_at
- last_success_at
- last_error
- created_at
- updated_at

唯一约束：

```text
source_type + app_token + table_id + source_role
```

### 2. `sync_runs`

- id
- source_config_id
- mode：full、incremental、manual、fixture
- status：pending、running、success、partial、failed
- started_at
- finished_at
- records_read
- records_created
- records_updated
- records_unchanged
- records_invalid
- error_summary
- triggered_by

### 3. `raw_source_records`

- id
- source_config_id
- source_record_id
- source_created_at
- source_modified_at
- raw_fields JSONB
- payload_hash
- is_deleted
- first_seen_at
- last_seen_at

唯一约束：

```text
source_config_id + source_record_id
```

### 4. `rooms`

- id
- name
- brand
- category
- active
- sort_order
- source_aliases JSONB
- created_at
- updated_at

直播间不得写死。同步时遇到新直播间可自动建立为“待确认”或按配置自动启用。

### 5. `persons`

- id
- display_name
- base_name
- prefix
- primary_role
- employment_status
- active
- notes
- created_at
- updated_at

### 6. `person_aliases`

- id
- person_id
- alias
- normalized_alias
- source

唯一约束：`normalized_alias`。

### 7. `live_points`

一条记录代表一个真实源数据采集点：

- id
- raw_source_record_id
- room_id
- observed_at
- business_date
- year
- month
- hour_slot
- hour_order
- anchor_raw
- anchor_canonical
- anchor_base_name
- anchor_members JSONB
- anchor_note
- control_raw
- control_canonical
- control_base_name
- auto_check_status
- valid
- invalid_reason
- raw_payload JSONB
- created_at
- updated_at

索引：

```text
room_id + observed_at
room_id + business_date + hour_order
anchor_base_name + business_date
control_base_name + business_date
```

### 8. `live_point_metrics`

长表保存每个采集点的全部指标：

- id
- live_point_id
- metric_key
- numeric_value NUMERIC(24, 8)
- raw_value
- parse_status

唯一约束：

```text
live_point_id + metric_key
```

### 9. `anchor_schedules`

一条记录代表一个直播间在一个日期、自然小时的主播排班：

- id
- source_config_id
- source_record_id
- room_id
- schedule_date
- year
- month
- day
- hour_slot
- hour_order
- planned_anchor_raw
- planned_anchor_canonical
- planned_anchor_base_names JSONB
- schedule_status：scheduled、combination、off_air、unassigned
- note
- created_at
- updated_at

唯一约束：

```text
room_id + schedule_date + hour_slot
```

### 10. `staff_schedules`

一条记录代表一个人员在一个日期的班次：

- id
- source_config_id
- source_record_id
- person_id
- schedule_date
- role
- employment_status
- shift_raw
- shift_name
- shift_start
- shift_end
- crosses_midnight
- is_rest
- time_configured
- created_at
- updated_at

唯一约束：

```text
person_id + schedule_date
```

### 11. `shift_rules`

- id
- name
- start_time
- end_time
- crosses_midnight
- is_rest
- enabled
- notes

初始化：

```text
00-08：00:00-08:00
08-17：08:00-17:00
12-20：12:00-20:00
20-05：20:00-次日05:00，跨天
休息：休息
```

“正常班、自由班、早班、晚班、凌晨班”不能擅自写死时间，后台标记“待配置”。

### 12. `hourly_facts`

一条记录代表：

```text
直播间 + 日期 + 自然小时
```

字段：

- id
- room_id
- business_date
- year
- month
- hour_slot
- hour_order
- hour_start_at
- hour_end_at
- latest_point_id
- latest_observed_at
- actual_anchor_canonical
- actual_anchor_base_names JSONB
- actual_control_canonical
- planned_anchor_canonical
- planned_anchor_base_names JSONB
- anchor_schedule_status
- anchor_match_status：matched、mismatched、no_schedule、off_air_but_live、scheduled_but_missing
- control_shift_name
- control_is_scheduled
- control_is_rest
- control_may_be_on_duty
- data_status：complete、partial、missing、invalid
- created_at
- updated_at

唯一约束：

```text
room_id + business_date + hour_slot
```

### 13. `hourly_metrics`

- id
- hourly_fact_id
- metric_key
- numeric_value NUMERIC(24, 8)
- value_source：latest_point、sum_points、derived_delta、computed
- quality_status

唯一约束：

```text
hourly_fact_id + metric_key
```

### 14. `metric_definitions`

- id
- metric_key
- source_field_name
- display_name
- category
- unit
- precision
- scope：period、cumulative、instant、derived
- aggregation_strategy：SUM、LAST、LAST_PER_ROOM_DAY、RATIO_OF_SUMS、WEIGHTED_RATIO、MAX、AVG、NONE
- numerator_metric_key
- denominator_metric_key
- chartable
- comparable
- alertable
- direction：higher_better、lower_better、neutral、contextual
- default_visible
- enabled
- sort_order
- description

### 15. `alert_rules`

- id
- name
- rule_type
- metric_key
- comparison_type
- operator
- threshold
- min_spend
- min_orders
- min_amount
- room_scope JSONB
- anchor_scope JSONB
- control_scope JSONB
- severity：info、warning、critical
- cooldown_minutes
- enabled
- push_enabled
- suggestion_template
- created_by
- created_at
- updated_at

### 16. `alert_events`

- id
- rule_id
- dedup_key
- triggered_at
- room_id
- business_date
- hour_slot
- anchor_name
- control_name
- metric_key
- current_value
- baseline_value
- delta_value
- ratio_percent
- growth_percent
- severity
- title
- message
- suggestion
- push_status：pending、sent、failed、skipped
- push_attempts
- pushed_at
- push_error
- acknowledged
- acknowledged_by
- acknowledged_at
- resolution_note
- created_at

唯一约束：`dedup_key`。

### 17. `users`、`roles`、`user_room_permissions`

实现：

- 飞书用户 ID
- 姓名、头像、邮箱（有权限时）
- 角色：管理员、运营、查看者
- 按直播间授权
- 用户状态
- 最近登录时间

### 18. `system_settings`

保存非敏感配置和加密后的敏感配置：

- key
- value JSONB
- encrypted
- updated_by
- updated_at

### 19. `audit_logs`

记录：

- 用户
- 动作
- 对象类型
- 对象 ID
- 变更前后摘要
- IP
- 时间

---

## 九、原始字段和指标字典

创建 `config/metric_seed.yml`。直播实际数据已知 52 个字段如下：

### 维度字段

```text
主播
场控
月份
自动检查
时间
时段
```

### 累计或快照指标

```text
直播间成交金额
成交订单数
笔单价
直播间用户支付金额
千次观看用户支付金额
实时在线人数
直播间曝光人数
直播间观看人数
商品曝光人数
商品点击人数
成交人数
曝光-观看率(人数）
观看-商品曝光率(人数）
商品曝光-点击率(人数）
商品点击-成交转化率(人数）
曝光-成交转化率（人数）
消耗
整体支付ROI
整体成交金额（元）
整体成交订单数
整体成交订单成本（元）
净支付ROI
净成交金额
净成交订单数
净成交订单成本（元）
```

### 小时/时段指标

```text
时段成交金额
时段支付金额
时段成交单数
时段笔单价
时段成交人数
时段观看人数
时段观看-成交率（人数）
时段曝光-观看率(人数）
时段观看-商品曝光率(人数）
时段商品曝光-点击率(人数）
时段商品点击-成交转化率(人数）
时段曝光-成交转化率（人数）
时段消耗
时段整体支付ROI
时段整体成交金额
时段整体成交订单数
时段整体成交订单成本
时段净支付ROI
时段净成交金额
时段净成交订单数
时段净成交订单成本
```

### 指标分类和默认聚合口径

1. 金额类：
   - 时段成交金额、时段支付金额、时段整体成交金额、时段净成交金额：跨小时 `SUM`。
2. 消耗类：
   - 时段消耗：跨小时 `SUM`。
3. 订单类：
   - 时段成交单数、时段整体成交订单数、时段净成交订单数：跨小时 `SUM`。
4. ROI 类：
   - 汇总时段整体支付 ROI = 时段整体成交金额合计 ÷ 时段消耗合计；
   - 汇总时段净支付 ROI = 时段净成交金额合计 ÷ 时段消耗合计；
   - 禁止简单平均。
5. 成本类：
   - 汇总时段整体订单成本 = 时段消耗合计 ÷ 时段整体成交订单数合计；
   - 汇总时段净订单成本 = 时段消耗合计 ÷ 时段净成交订单数合计。
6. 笔单价：
   - 汇总时段笔单价 = 时段成交金额合计 ÷ 时段成交单数合计。
7. 比率类：
   - 有明确分子、分母时用比值重新计算；
   - 无完整分子分母时，不得用简单平均冒充总转化率；
   - 可以显示“小时值”或明确标注“加权平均”。
8. 累计类：
   - 同直播间、同日期、所选时间范围内取最晚有效采集点；
   - 不得把每小时累计值求和。
9. 实时在线人数：
   - 小时图默认取小时内最后一个采集点；
   - 可选最大值或平均值，但必须标注口径。
10. 累计单调人数指标：
    - 可额外生成“小时增量（计算）”；
    - 公式为当前小时末累计值减前一小时末累计值；
    - 遇到跨日或数据重置时从头计算；
    - 结果为负时置为缺失并标记 reset，不得显示为负增长；
    - 原始累计值仍然保留。
11. 未知新数值字段：
    - 自动进入指标字典“待确认”；
    - 默认聚合策略 `LAST`；
    - 管理员确认后才可用于跨小时汇总和预警；
    - 不能默认为求和。

所有指标必须有：中文展示名、单位、小数位、趋势方向和口径说明。

---

## 十、数据清洗规则

### 1. 无效行

以下记录不进入正常分析，但必须保存在原始表和异常日志：

- 空行；
- 主播为空；
- 主播等于“用于计算”；
- 自动检查等于“错误”；
- 时段等于 `0:00-0:00`；
- 日期无法解析；
- 时段无法解析；
- 关键字段无法转换为数值。

### 2. 时间标准化

兼容：

- 飞书毫秒时间戳；
- ISO 日期时间；
- Excel 序列日期；
- 文本日期时间。

将时段统一为：

```text
00-01
01-02
...
23-24
```

兼容输入：

```text
0:00-1:00
00-01时段
9:00-10:00
09-10
23:00-24:00
```

生成：

- `business_date`
- `observed_at`
- `hour_slot`
- `hour_order` 0-23
- `hour_start_at`
- `hour_end_at`

`23-24` 归属开始日期，结束时间为次日 00:00。

### 3. 主播名称标准化

保留：

- 原始名称；
- 标准展示名称；
- 基础姓名；
- 前缀；
- 成员集合；
- 备注。

示例：

```text
Q-李昕（9.31开播）
→ 标准展示：Q-李昕
→ 基础姓名：李昕
→ 备注：9.31开播
```

```text
J-梦丽+菜菜
→ 组合展示：J-梦丽+菜菜
→ 成员基础姓名集合：[梦丽, 菜菜]
```

兼容分隔符：

```text
+
＋
/
、
&
```

组合主播比对使用排序后的成员集合，不受顺序影响。

特殊值：

- `断播`：排班状态，不作为人员；
- `用于计算`：无效；
- 空值：未排班或缺失。

创建 `config/field_aliases.yml` 支持：

- 中文括号与英文括号；
- 全角与半角符号；
- 字段标点差异；
- 人员别名；
- J-、Q- 前缀与排班基础姓名的关联。

### 4. 场控名称标准化

- 保留原始名称、标准名称和基础姓名；
- 实际场控以直播实绩表为准；
- 人员日排班仅用于判断当天是否排班、是否休息、是否可能在岗；
- 如果没有“计划场控对应直播间”的明确数据，不得推断计划场控是谁。

### 5. 数字解析

支持：

- 数字；
- 数字文本；
- 千位分隔符；
- 百分比文本；
- 空字符串；
- `-`、`—`、`N/A`。

例如：

```text
9.68% → 数据库存 0.0968，页面显示 9.68%
```

金额、ROI、成本和比率均使用 Decimal。

### 6. 去重与更新

主唯一键：

```text
source_config_id + source_record_id
```

业务冲突检查键：

```text
room_id + observed_at
```

规则：

- 同一源记录再次同步执行 update；
- payload 未变化标记 unchanged；
- 同一直播间同一时间存在多个源记录时，保存全部原始记录并标记冲突；
- 正常分析默认取源更新时间最新且有效的记录；
- 源记录删除时标记 `is_deleted=true`，不立即物理删除审计数据。

---

## 十一、排班宽表转长表

### 1. 主播小时排班

原始结构：

```text
直播间 | 月份 | 时段 | 1日 | 2日 | ... | 31日
```

转换为：

```text
直播间 | 日期 | 自然小时 | 计划主播 | 排班状态
```

规则：

1. 识别列名正则：`^(?:[1-9]|[12]\d|3[01])日$`。
2. 年份来自数据源配置或导入时管理员选择。
3. 无效日期，如 2 月 31 日，跳过并记录异常。
4. `断播` → `off_air`。
5. 空值 → `unassigned`。
6. 组合主播 → `combination`。
7. 其他非空主播 → `scheduled`。

### 2. 人员日排班

原始结构：

```text
姓名 | 岗位 | 状态 | 月份 | 1日 | 2日 | ... | 31日
```

转换为：

```text
人员 | 岗位 | 状态 | 日期 | 班次
```

显式班次自动解析：

```text
00-08
08-17
12-20
20-05
休息
```

文字班次：

```text
正常班
自由班
早班
晚班
凌晨班
```

如果班次规则未配置：

- 仍保存排班；
- `time_configured=false`；
- 只能判断“有排班/休息”，不能判断该小时是否在岗；
- 后台提示管理员配置。

---

## 十二、小时事实构建

### 1. 采集点模式

保留每条真实 `observed_at`。页面提供：

```text
粒度：小时 / 采集点
```

采集点模式：

- X 轴显示 `HH:mm + 主播`；
- 展示原始采集点；
- 不虚构不存在的分钟值；
- 适合查看“几点几分的数据”。

### 2. 小时模式

一条小时事实按：

```text
直播间 + business_date + hour_slot
```

生成。

如果该小时只有一条有效采集点：直接使用。

如果该小时有多条采集点：

- `latest_point_id` 取最晚有效点；
- 快照和累计指标取最晚点；
- 只有被明确标记为“子小时增量”的指标才允许求和；
- 未确认的指标不求和；
- 所有采集点仍可在详情抽屉查看。

### 3. 主播排班比对

按以下键关联：

```text
room_id + business_date + hour_slot
```

匹配结果：

- `matched`：实际主播与计划主播相同；
- `mismatched`：不同；
- `no_schedule`：无排班；
- `off_air_but_live`：排班断播但存在实绩；
- `scheduled_but_missing`：计划开播但无实绩。

组合主播使用成员集合比较。

### 4. 场控班次比对

按：

```text
control_base_name + business_date
```

关联人员日排班。

输出：

- 是否有排班；
- 是否休息；
- 班次名称；
- 班次时间是否配置；
- 当前小时是否可能在岗。

不得输出不存在来源的“计划场控”。

---

## 十三、汇总计算口径

### 1. 时段整体支付 ROI

```text
汇总时段整体支付ROI
= SUM(时段整体成交金额) / SUM(时段消耗)
```

### 2. 时段净支付 ROI

```text
汇总时段净支付ROI
= SUM(时段净成交金额) / SUM(时段消耗)
```

### 3. 时段整体订单成本

```text
汇总时段整体成交订单成本
= SUM(时段消耗) / SUM(时段整体成交订单数)
```

### 4. 时段净订单成本

```text
汇总时段净成交订单成本
= SUM(时段消耗) / SUM(时段净成交订单数)
```

### 5. 时段笔单价

```text
汇总时段笔单价
= SUM(时段成交金额) / SUM(时段成交单数)
```

### 6. 累计指标

同一个直播间、同一天、所选时间范围：

- 取最晚有效点；
- 不求和；
- 界面显示“截至所选时段”。

跨多日汇总累计指标：

- 每个直播间每天先取最后有效点；
- 再根据指标业务含义汇总；
- 不允许直接把一天内每个小时的累计值相加。

### 7. 除零规则

分母为 0 或空：

- 返回 `null`；
- 前端显示 `—`；
- 不显示 Infinity；
- 不触发百分比类预警。

---

## 十四、比较引擎

实现统一 `ComparisonService`，支持：

1. 当前日 vs 昨日同小时；
2. 当前日 vs 上周同星期同小时；
3. 指定日期 A vs 指定日期 B；
4. 本月 vs 上月；
5. 当前主播 vs 同直播间同小时历史平均；
6. 当前场控搭配 vs 同主播其他场控平均；
7. 当前直播间 vs 多直播间平均。

默认对齐键：

```text
room_id + hour_slot
```

可选附加：

```text
same_anchor=true
same_control=true
```

输出字段：

- current_value
- baseline_value
- delta_value
- ratio
- ratio_percent
- growth_percent
- direction_status
- explanation

公式：

```text
delta = current - baseline
ratio = current / baseline
ratio_percent = ratio * 100%
growth_percent = (current - baseline) / baseline * 100%
```

示例：

```text
8日 ROI = 3.00
7日 ROI = 1.50
```

必须输出：

```text
8日ROI为3.00，是7日同小时ROI 1.50的200%，较7日提升100%。
```

不得只写：

```text
高200%
```

基准为空或 0：

```text
无有效可比基准
```

本月对上月同时提供：

- 月度总量；
- 日均值；
- 有效直播小时均值；
- 完整月份与未完整月份状态提示。

---

## 十五、后端 API

所有接口前缀：

```text
/api/v1
```

使用 OpenAPI 自动文档并提供严格响应模型。

### 1. 健康与身份

```text
GET  /health
GET  /ready
GET  /auth/feishu/login
GET  /auth/feishu/callback
POST /auth/logout
GET  /me
```

### 2. 筛选选项

```text
GET /filters/options
```

返回：

- 日期范围；
- 月份；
- 直播间；
- 主播；
- 主播成员；
- 场控；
- 自然小时；
- 指标分类与指标；
- 比较方式。

按用户直播间权限过滤。

### 3. 总览

```text
GET /dashboard/overview
```

参数：

- start_date
- end_date
- month
- room_ids
- anchor_names
- anchor_members
- control_names
- hour_slots
- comparison_type

返回：

- KPI；
- 排名；
- 最近预警；
- 数据完整率；
- 同步状态。

### 4. 小时与采集点曲线

```text
GET /charts/timeline
```

参数：

- grain=`hour|point`
- metric_keys
- group_by=`room|anchor|control|date|comparison`
- compare_type
- 全局筛选参数

返回建议结构：

```json
{
  "grain": "hour",
  "groups": [
    {
      "group_key": "room-id",
      "group_label": "柏瑞美-散粉",
      "x_items": [
        {
          "key": "2026-07-08|08-09|Q-李昕",
          "label": "08-09\nQ-李昕",
          "date": "2026-07-08",
          "hour_slot": "08-09",
          "anchor": "Q-李昕",
          "control": "郑荣贵",
          "observed_at": "2026-07-08T09:00:00+08:00"
        }
      ],
      "series": [
        {
          "metric_key": "period_overall_roi",
          "name": "时段整体支付ROI",
          "unit": "ratio",
          "axis_group": "roi",
          "data": [3.0]
        }
      ],
      "annotations": []
    }
  ]
}
```

### 5. 数据点详情

```text
GET /live-points/{id}
GET /hourly-facts/{id}
GET /hourly-facts/{id}/points
GET /hourly-facts/{id}/alerts
```

### 6. 主播分析

```text
GET /analytics/anchors/summary
GET /analytics/anchors/timeline
GET /analytics/anchors/rooms
GET /analytics/anchors/controls
GET /analytics/anchors/hours
```

### 7. 场控分析

```text
GET /analytics/controls/summary
GET /analytics/controls/timeline
GET /analytics/controls/anchors
GET /analytics/controls/rooms
GET /analytics/pairings
```

### 8. 数据对比

```text
GET /comparisons
```

### 9. 主播场控透视

```text
GET /pivot/anchor-control
```

支持参数：

- row_levels
- metric_keys
- sort
- pagination
- export

### 10. 明细与导出

```text
GET  /data/hourly
GET  /data/points
POST /exports
GET  /exports/{id}
```

### 11. 预警

```text
GET    /alerts/events
GET    /alerts/events/{id}
POST   /alerts/events/{id}/acknowledge
POST   /alerts/events/{id}/retry-push
GET    /alerts/rules
POST   /alerts/rules
PATCH  /alerts/rules/{id}
DELETE /alerts/rules/{id}
POST   /alerts/test-push
POST   /alerts/evaluate
```

### 12. 管理

```text
GET  /admin/sources
POST /admin/sources
PATCH /admin/sources/{id}
POST /admin/sources/{id}/test
POST /admin/sources/{id}/discover
POST /admin/sources/{id}/sync
GET  /admin/sync-runs
GET  /admin/metrics
PATCH /admin/metrics/{id}
GET  /admin/shifts
PATCH /admin/shifts/{id}
GET  /admin/settings
PATCH /admin/settings
GET  /admin/audit-logs
```

---

## 十六、前端页面

路由：

```text
/overview
/timeline
/comparison
/anchors
/controls
/pivot
/details
/alerts
/admin/sources
/admin/metrics
/admin/shifts
/admin/settings
/admin/audit
```

### 1. 全局布局

- 左侧固定导航；
- 顶部显示应用名、数据更新时间、同步状态、当前用户；
- 顶部提供“立即同步”按钮，只有管理员可见；
- 主内容区适配 1440px 宽屏；
- 筛选条件同步到 URL query，支持复制链接；
- 飞书预警卡片中的深链可直接打开对应直播间、日期和时段。

### 2. 全局筛选区

包含：

- 单日/日期范围；
- 月份；
- 直播间，多选；
- 主播，多选搜索；
- 主播成员，多选搜索；
- 场控，多选搜索；
- 自然小时，多选；
- 指标，多选并按类别分组；
- 对比方式；
- 粒度：小时/采集点；
- 重置；
- 保存常用视图。

要求：

- 筛选区吸顶；
- 筛选变化后所有卡片、图表和表格联动；
- 请求防抖；
- 取消过期请求；
- 默认使用最新有数据日期；
- 权限范围外选项不出现。

### 3. 经营总览 `/overview`

KPI 卡片：

- 时段成交金额；
- 时段支付金额；
- 时段消耗；
- 汇总时段整体支付 ROI；
- 汇总时段净支付 ROI；
- 时段成交订单数；
- 汇总时段整体订单成本；
- 时段观看人数；
- 时段成交人数；
- 主播排班一致率；
- 数据完整率；
- 当前预警数。

每张卡片显示：

- 当前值；
- 基准值；
- 差值；
- 增幅；
- 趋势方向；
- 小型趋势；
- 口径提示。

注意：

- ROI、成交金额上涨可显示正向；
- 成本上涨通常显示负向；
- 消耗上涨属于 contextual，不机械显示绿色。

下方：

- 小时趋势概览；
- 直播间排名；
- 主播排名；
- 场控搭配排名；
- 最近预警；
- 数据缺失和同步状态。

### 4. 小时趋势 `/timeline`

这是核心页面。

#### X 轴

单日小时模式：

```text
00-01
J-兰婷

01-02
J-兰婷

08-09
Q-李昕
```

多日小时模式：

```text
07-07 08-09
Q-李昕

07-08 08-09
Q-李昕
```

采集点模式：

```text
09:31
Q-李昕
```

排序必须按：

```text
日期 → hour_order → observed_at
```

不得按标签文字排序。

#### 多直播间

选择多个直播间时：

- 默认按直播间拆成 Small Multiples 多张图；
- 每张图 X 轴仍显示自然小时 + 主播；
- 提供“合并系列”切换；
- 合并时图例必须清楚标注直播间。

#### Y 轴

全部数值指标可选，但按单位自动分组：

- ROI；
- 金额；
- 消耗；
- 订单；
- 成本/笔单价；
- 人数；
- 百分比；
- 累计快照。

规则：

- 默认最多 4 条系列；
- 超过 4 个指标时按单位拆图；
- 同单位共轴；
- ROI 与金额可双轴；
- ROI、金额、人数不能强行放在一个轴；
- 图例可点击隐藏；
- 支持 Data Zoom、框选、全屏、导出图片；
- 异常点显示警告图标；
- 优秀点显示正向图标；
- 对比基准线使用虚线。

#### Tooltip

分组显示：

基础：

- 日期；
- 完整采集时间；
- 直播间；
- 自然小时；
- 主播；
- 主播备注；
- 场控；
- 计划主播；
- 排班匹配状态；
- 场控班次。

指标：

- 当前选中的全部指标；
- 每个指标的单位和口径。

对比：

- 基准日期；
- 基准值；
- 差值；
- 是基准的百分比；
- 增幅百分比。

#### 点击数据点

右侧详情抽屉显示：

- 该小时的所有采集点；
- 全部原始字段；
- 全部标准化指标；
- 时段指标；
- 累计指标；
- 排班信息；
- 数据质量状态；
- 对比结果；
- 相关预警；
- 来源 Base、Table、Record ID；
- 源更新时间；
- 同步时间。

### 5. 数据对比 `/comparison`

组件：

- 当前与基准 KPI；
- 双折线；
- 差值柱状图；
- 最大增长时段；
- 最大下降时段；
- 对比明细表；
- 解释文案。

表格字段：

- 日期；
- 直播间；
- 时段；
- 主播；
- 场控；
- 当前值；
- 基准值；
- 差值；
- 是基准的百分比；
- 增幅；
- 状态。

### 6. 主播分析 `/anchors`

展示：

- 有效直播小时数；
- 成交金额；
- 消耗；
- ROI；
- 净 ROI；
- 订单数；
- 订单成本；
- 观看人数；
- 成交人数；
- 排班一致率；
- 不同直播间表现；
- 不同自然小时表现；
- 不同场控搭配表现；
- 日期趋势。

排名设置最小样本门槛：

- 至少 3 个有效小时，或
- 达到管理员配置的最低消耗。

### 7. 场控分析 `/controls`

展示：

- 有效直播小时数；
- 成交金额；
- 消耗；
- ROI；
- 订单数；
- 订单成本；
- 搭配主播数量；
- 当日排班匹配率；
- 休息日出现实绩次数；
- 不同主播搭配表现；
- 不同直播间表现；
- 不同自然小时表现。

文案使用“搭配表现”，不得把相关关系直接写成因果关系。

### 8. 主播场控时间汇总 `/pivot`

视觉参考截图：

- 白色大卡片；
- 2px 蓝色圆角边框；
- 浅蓝色表头；
- 主播、场控列固定；
- 指标列横向滚动；
- 轻分隔线；
- 树形展开折叠。

行层级：

```text
主播
  └─ 场控
       └─ 日期
            └─ 自然小时
```

默认指标：

- 时段成交金额；
- 时段支付金额；
- 时段成交单数；
- 时段消耗；
- 汇总时段整体支付 ROI；
- 时段整体成交金额；
- 时段整体成交订单数；
- 汇总时段整体订单成本；
- 汇总时段净支付 ROI；
- 时段净成交金额；
- 时段净成交订单数；
- 汇总时段净订单成本。

功能：

- 展开/折叠；
- 字段显示隐藏；
- 排序；
- 搜索；
- 固定列；
- 虚拟滚动；
- 导出；
- 点击主播跳转主播分析；
- 点击场控跳转场控分析；
- 点击小时打开详情。

### 9. 数据明细 `/details`

固定列：

- 日期；
- 采集时间；
- 直播间；
- 自然小时；
- 主播；
- 场控。

其他指标横向滚动。

支持：

- 字段管理；
- 排序；
- 筛选；
- 保存个人视图；
- 服务端分页；
- CSV/XLSX 导出；
- 异常行浅红底；
- 排班不一致浅黄底；
- 数据延迟浅橙底；
- 状态标签和图标，不能只靠颜色。

### 10. 预警中心 `/alerts`

顶部：

- 今日预警数；
- 严重数；
- 重要数；
- 提醒数；
- 已推送数；
- 推送失败数；
- 未处理数。

列表：

- 触发时间；
- 直播间；
- 日期；
- 自然小时；
- 主播；
- 场控；
- 类型；
- 指标；
- 当前值；
- 基准值；
- 增幅；
- 级别；
- 推送状态；
- 处理状态。

支持：

- 查看详情；
- 查看曲线；
- 标记处理；
- 填写结果；
- 重新推送；
- 导出。

### 11. 管理后台

数据源：

- 测试连接；
- 扫描 Table；
- 扫描字段；
- 字段映射；
- 默认直播间；
- 排班年份；
- 同步状态；
- 立即同步。

指标字典：

- 字段名；
- 分类；
- 单位；
- 聚合方式；
- 趋势方向；
- 是否可图表；
- 是否可预警；
- 待确认新字段。

班次：

- 配置文字班次时间；
- 跨天；
- 休息；
- 启用状态。

系统设置：

- 同步频率；
- 预警延迟；
- 机器人 Webhook；
- 签名密钥；
- 阈值默认值；
- 每日汇总时间。

---

## 十七、UI 设计规范

整体风格：企业级数据驾驶舱，清晰、高信息密度、不过度装饰。

色值：

```text
页面背景：#F5F7FA
卡片背景：#FFFFFF
主色：#3370FF
浅蓝表头：#EAF4FF
边框：#DCE6F5
主文字：#1F2329
次文字：#646A73
辅助文字：#8F959E
正向：#00B42A
负向：#F53F3F
警告：#FF7D00
排班异常：#722ED1
```

布局：

- 12 列网格；
- 卡片间距 16-20px；
- 卡片圆角 12-16px；
- 汇总透视卡片使用蓝色边框；
- 阴影轻；
- 不使用大面积渐变；
- 不使用无意义动画。

KPI：

- 指标名在上；
- 当前值最大；
- 基准、差值和增幅在下；
- 点击后联动图表；
- 指标方向决定颜色。

表格：

- 表头吸顶；
- 数值右对齐；
- 金额 2 位小数；
- ROI 2 位小数；
- 百分比格式；
- 人数和订单默认整数；
- 左侧关键列固定；
- 支持横向滚动。

空状态：

```text
当前筛选条件下暂无实际数据，请调整日期、直播间或检查数据是否已同步。
```

只有排班无实绩：

```text
当前直播间已有排班数据，但暂无实绩数据。
```

加载使用骨架屏；错误状态显示可执行的解决建议和重试按钮。

移动端：

- 核心 KPI；
- 简化趋势；
- 预警列表；
- 明细折叠卡片；
- 深链可打开预警详情。

---

## 十八、预警规则

所有阈值可配置，规则默认在自然小时结束后 15 分钟执行。

### 1. ROI 优秀上涨

默认条件：

```text
当前时段整体支付ROI / 昨日同小时ROI >= 1.5
当前时段消耗 >= 最小消耗门槛
```

### 2. ROI 暴跌

```text
增长率 <= -30%
当前时段消耗 >= 最小消耗门槛
```

### 3. ROI 低于底线

```text
当前时段整体支付ROI < 1.2
当前时段消耗 >= 最小消耗门槛
```

### 4. 消耗异常上涨

```text
消耗较昨日同小时上涨 >= 50%
且时段整体成交金额涨幅 < 10%
```

### 5. 订单成本异常

```text
订单成本较昨日同小时上涨 >= 40%
且订单数 >= 最小订单门槛
```

### 6. 成交金额断崖

```text
时段整体成交金额较昨日下降 >= 50%
且昨日基准成交金额 >= 最小金额门槛
```

### 7. 数据延迟

```text
小时结束 + ALERT_DELAY_MINUTES 后仍无有效实绩
且该直播间该时段存在正常主播排班
且排班状态不是断播
```

### 8. 主播排班不一致

```text
实际主播成员集合 != 计划主播成员集合
```

### 9. 断播异常

- 排班为断播但存在实绩；
- 或排班为正常但无实绩。

### 10. 场控排班异常

- 实际场控当天为休息；
- 或没有人员排班记录；
- 如果班次时间已配置，可判断当前小时不在班次内。

### 11. 数据质量异常

- 自动检查错误；
- 日期/时段解析失败；
- 数字解析失败；
- 重复冲突；
- 负金额/负订单；
- 转化率小于 0 或大于 100%；
- ROI 与金额、消耗明显不一致。

### 12. 优秀时段

```text
ROI 高于目标
成交金额高于历史同小时均值
订单成本不高于目标
且达到最小样本门槛
```

### 防误报

百分比波动规则必须满足：

- 当前小时结束；
- 同步成功；
- 当前值和基准值有效；
- 基准值不为 0；
- 当前消耗/订单/金额达到门槛；
- 不是异常数据行。

### 去重

```text
room_id + business_date + hour_slot + anchor + control + metric_key + rule_type
```

同一 `dedup_key` 只创建一个预警事件。

同一小时多个相关规则可合并成一张飞书卡片，但数据库仍保存每个规则事件。

---

## 十九、飞书群推送

实现 `FeishuBotClient`：

- 支持文本和消息卡片；
- 支持签名校验；
- 请求超时；
- 重试；
- 返回码校验；
- 失败原因保存；
- 管理后台提供测试消息；
- 单元测试中使用 mock，不发送真实消息。

消息模板：

```text
【直播间小时预警｜{预警类型}】

直播间：{直播间}
日期时段：{日期} {自然小时}
主播：{主播}
场控：{场控}
预警级别：{级别}

当前{指标名称}：{当前值}
对比基准：{基准日期} {自然小时}
基准值：{基准值}

结果：
当前值是基准值的{ratio_percent}，较基准{提升或下降}{growth_percent}。

关联数据：
- 时段整体成交金额：{值}
- 时段支付金额：{值}
- 时段消耗：{值}
- 时段整体支付ROI：{值}
- 时段整体成交订单数：{值}
- 时段整体成交订单成本：{值}

建议：
{建议动作}
```

按钮：

- 查看预警详情；
- 查看小时趋势；
- 查看主播分析。

示例：

```text
当前ROI是昨日同小时的200%，较昨日提升100%。
```

不要写成：

```text
较昨日高200%
```

推送策略：

- critical：立即推送；
- warning：立即或按配置推送；
- info：可进入阶段汇总；
- 推送失败自动重试，最多 `ALERT_RETRY_LIMIT`；
- 记录每次尝试；
- 提供手动重试。

---

## 二十、后台任务

Celery Beat 创建：

1. `sync_live_actual`：每 5 分钟；
2. `sync_schedules`：每 30 分钟；
3. `build_hourly_facts`：每次同步后；
4. `evaluate_hourly_alerts`：每小时结束后延迟 15 分钟；
5. `check_data_delay`：每 10 分钟；
6. `retry_failed_pushes`：每 5 分钟；
7. `daily_summary`：默认 10:00、16:00、次日 00:15；
8. `cleanup_expired_exports`：每日；
9. `source_health_check`：每 30 分钟。

任务必须：

- 幂等；
- 有分布式锁；
- 可手动触发；
- 有日志和运行状态；
- 失败不会导致重复数据；
- 超时后可重试；
- 任务重叠时避免并发重复执行同一数据源。

---

## 二十一、登录和权限

### 1. 飞书网页应用登录

实现服务端 OAuth 登录：

- 获取授权码；
- 服务端换取用户访问令牌；
- 获取用户身份；
- 建立本地会话；
- 校验 `state`；
- Cookie 使用 HttpOnly、Secure、SameSite；
- 生产环境使用 HTTPS。

本地开发允许 `DEV_AUTH_BYPASS=true` 创建开发管理员，生产禁止。

### 2. 角色

管理员：

- 全部直播间；
- 数据源；
- 同步；
- 指标；
- 班次；
- 预警；
- Webhook；
- 权限；
- 导出；
- 审计日志。

运营：

- 授权直播间；
- 看板与分析；
- 预警处理；
- 授权范围导出；
- 不可查看密钥。

查看者：

- 授权看板；
- 基础筛选；
- 默认不可导出；
- 不可修改。

所有查询、导出、预警详情和 API 都必须在服务端执行按直播间权限过滤，不能只靠前端隐藏。

---

## 二十二、安全与可靠性

1. App Secret、JWT、Webhook Secret 仅从环境变量或加密配置读取。
2. 日志自动脱敏：token、secret、webhook URL、手机号、邮箱。
3. SQL 全部使用 ORM/参数化查询。
4. 导出任务验证权限。
5. 对管理接口进行 CSRF/会话保护和角色校验。
6. API 设置合理限流。
7. CORS 仅允许配置的前端域名。
8. 文件上传限制类型和大小。
9. Excel fixture 解析防止公式注入；导出文本以 `=、+、-、@` 开头时进行安全处理。
10. 提供数据库备份脚本。
11. 提供恢复说明。
12. 健康检查区分 liveness 和 readiness。
13. 结构化 JSON 日志包含 request_id、user_id、sync_run_id。
14. 可选接入 Sentry，但不得作为必需条件。

---

## 二十三、性能要求

目标规模至少支持：

```text
20 个直播间
365 天
24 小时/天
每小时最多 12 个采集点
60 个指标
```

要求：

- 常用总览接口 P95 小于 1.5 秒；
- 单直播间 31 天小时曲线 P95 小于 1 秒；
- 明细服务端分页；
- 透视表使用分页或虚拟滚动；
- 为日期、直播间、主播、场控、小时和指标建立索引；
- 可使用 Redis 缓存筛选选项和常用总览，缓存键包含权限与筛选条件；
- 同步完成后使相关缓存失效；
- 大型导出使用后台任务。

---

## 二十四、测试要求

### 1. 单元测试

至少覆盖：

- Excel 日期和飞书时间戳解析；
- 时段标准化；
- 23-24 跨日；
- 主播备注清洗；
- 组合主播成员集合；
- `断播`、`用于计算`；
- 百分比和金额解析；
- 排班宽表转长表；
- 班次跨天；
- ROI 聚合；
- 订单成本聚合；
- 累计指标取最后值；
- 比较公式；
- 基准为 0；
- 预警阈值；
- 去重 key；
- 飞书机器人签名与请求体生成。

### 2. 集成测试

使用 mock Feishu API：

- Token；
- 字段列表；
- 多页记录；
- 429 重试；
- 5xx 重试；
- 权限错误；
- 同步重复执行；
- 源记录更新；
- 源记录缺失；
- Webhook 成功和失败。

使用临时 PostgreSQL/测试容器测试迁移和查询。

### 3. Fixture 测试

使用用户的 Excel fixture 验证：

1. 识别两个直播间 Sheet；
2. 每个直播间识别 52 个字段；
3. 过滤“用于计算”；
4. 过滤“自动检查=错误”；
5. `0:00-1:00` → `00-01`；
6. `00-01时段` → `00-01`；
7. `Q-李昕（9.31开播）` → `Q-李昕` + 备注；
8. `J-梦丽+菜菜` 可按组合和成员匹配；
9. `断播` 不进入人员表；
10. 实际带前缀姓名可关联排班基础姓名。

### 4. E2E

Playwright 至少覆盖：

- 登录或开发登录；
- 全局筛选；
- 日筛选；
- 月筛选；
- 直播间多选；
- 主播多选；
- 场控多选；
- 小时曲线 X 轴；
- 指标切换；
- 数据点详情；
- 比较页面；
- 透视表；
- 预警处理；
- 管理员测试同步；
- 权限隔离。

### 5. 关键业务断言

必须存在自动测试：

```text
current ROI = 3.00
baseline ROI = 1.50
ratio_percent = 200%
growth_percent = 100%
```

文案断言：

```text
当前ROI是基准同小时的200%，较基准提升100%。
```

### 6. 质量门槛

- 领域服务单元测试覆盖率 >= 85%；
- 全部 lint、type check 和测试通过；
- 不允许忽略失败测试交付；
- 测试不得调用真实飞书群机器人。

---

## 二十五、开发命令

创建 Makefile：

```text
make dev
make stop
make logs
make migrate
make seed
make sync-fixture
make sync-feishu
make test
make test-unit
make test-integration
make test-e2e
make lint
make typecheck
make format
make check
make build
make backup
make verify-production
```

`make check` 必须运行：

- 后端格式检查；
- Ruff；
- mypy；
- pytest；
- 前端 ESLint；
- TypeScript 检查；
- 前端单测；
- 关键 E2E 或 smoke test。

---

## 二十六、Docker 部署

`docker-compose.yml` 至少包含：

```text
postgres
redis
api
celery-worker
celery-beat
web
reverse-proxy
```

要求：

- 数据卷持久化；
- 健康检查；
- 启动依赖；
- 数据库迁移单独执行；
- 非 root 用户运行应用；
- 前端生产构建；
- Nginx/Caddy 代理 `/api`；
- 支持 HTTPS 部署说明；
- 提供 Windows Docker Desktop 和 Linux 服务器启动说明。

生产启动流程：

```text
复制 .env.example 为 .env
填写凭证
启动数据库和 Redis
执行迁移
初始化指标和班次
创建管理员
执行首次同步
启动全部服务
执行 verify-production
```

---

## 二十七、实施阶段

### 阶段 0：项目初始化

- 创建目录；
- AGENTS.md；
- ExecPlan；
- Docker；
- CI；
- 基础健康接口；
- 前端壳。

完成标准：`make dev` 可启动，`/health` 正常。

### 阶段 1：数据源与 fixture

- Feishu Client；
- Mock Feishu；
- Excel fixture 导入；
- 字段扫描；
- 同步日志。

完成标准：可以读取 fixture 和 mock 多页记录，并幂等同步。

### 阶段 2：数据模型与清洗

- 迁移；
- 指标字典；
- 时间、人员、数值清洗；
- 排班宽转长；
- 异常记录。

完成标准：已知 Excel 用例全部通过。

### 阶段 3：小时事实与聚合

- 采集点；
- 小时事实；
- 排班关联；
- ROI/成本聚合；
- 缓存。

完成标准：业务口径测试通过。

### 阶段 4：总览和小时趋势

- 全局筛选；
- KPI；
- ECharts；
- 小时/采集点切换；
- Tooltip；
- 详情抽屉。

完成标准：X 轴和全部指标选择验收通过。

### 阶段 5：主播、场控、透视和对比

- 主播页；
- 场控页；
- 搭配页；
- 透视表；
- 比较引擎。

完成标准：3 vs 1.5 比较文案正确。

### 阶段 6：预警与飞书推送

- 规则；
- 事件；
- Celery；
- 去重；
- 飞书卡片；
- 重试；
- 处理闭环。

完成标准：Mock 推送和一条手动测试推送流程通过。

### 阶段 7：登录、权限和管理后台

- 飞书登录；
- 角色；
- 按直播间权限；
- 数据源管理；
- 指标和班次配置；
- 审计。

完成标准：未授权用户无法通过 API 获取直播间数据。

### 阶段 8：生产化

- E2E；
- 性能测试；
- 安全检查；
- 备份恢复；
- 部署文档；
- 测试报告。

完成标准：`make check` 和 `make verify-production` 全部通过。

---

## 二十八、验收清单

最终必须逐项验证并写入 `docs/TEST_REPORT.md`：

1. 能连接两个飞书 Base。
2. 能分页读取所有记录。
3. 能自动扫描字段。
4. 能识别多个直播间。
5. 没有直播间字段时能用数据源默认直播间配置。
6. 新增直播间无需改代码。
7. 能读取主播小时排班。
8. 能读取人员日排班。
9. 宽表成功转成长表。
10. 排班年份可配置。
11. “用于计算”不进入图表。
12. “自动检查=错误”进入异常记录。
13. `0:00-0:00` 不进入小时趋势。
14. 时段格式统一。
15. Excel 日期正确。
16. 百分比正确。
17. 主播备注正确拆分。
18. 组合主播可筛选和匹配。
19. `断播` 不作为人员。
20. 可选日期和日期范围。
21. 可选月份。
22. 可多选直播间。
23. 可多选主播。
24. 可多选场控。
25. X 轴显示自然小时 + 主播。
26. 多日显示日期 + 时段 + 主播。
27. 采集点模式显示真实分钟。
28. 全部数值指标可选。
29. 不同单位自动分图或分轴。
30. 多直播间默认拆图。
31. 点击点位可看全部字段。
32. 小时曲线默认使用时段字段。
33. 累计字段不被错误求和。
34. 汇总 ROI 不做简单平均。
35. 订单成本公式正确。
36. 分母为 0 不报错。
37. 今日与昨日可对比。
38. 今日与上周可对比。
39. 月度对比可用。
40. ROI 3 vs 1.5 显示 200% 和提升 100%。
41. 主播分析可用。
42. 场控分析可用。
43. 主播场控搭配可用。
44. 透视表与参考截图风格一致。
45. 数据延迟规则正确。
46. 断播不误报数据延迟。
47. 排班不一致可预警。
48. 基准为 0 不触发百分比预警。
49. 小样本不触发剧烈波动预警。
50. 同一预警不重复推送。
51. 飞书推送成功/失败有记录。
52. 推送失败可重试。
53. 预警可标记处理。
54. 飞书登录可用。
55. 按直播间权限在服务端生效。
56. Webhook 密钥不暴露。
57. Docker 一键启动。
58. 数据库迁移可重复执行。
59. 全部测试通过。
60. README 和部署文档完整。

---

## 二十九、禁止事项

1. 不得只输出计划而不创建代码。
2. 不得只做静态页面。
3. 不得用多维表格现有仪表盘代替应用。
4. 不得硬编码两个直播间。
5. 不得硬编码主播和场控名单。
6. 不得把累计字段当小时增量。
7. 不得简单平均 ROI。
8. 不得把累计值按小时求和。
9. 不得在无分钟数据时虚构分钟值。
10. 不得只写“高200%”而不区分倍率与增幅。
11. 不得在基准为 0 时输出 Infinity。
12. 不得在没有来源时推断计划场控。
13. 不得删除异常原始记录。
14. 不得重复发送同一预警。
15. 不得在前端保存 App Secret。
16. 不得把真实 Webhook 写入仓库。
17. 不得用前端权限隐藏代替服务端鉴权。
18. 不得因平台凭证未提供而停止开发。
19. 不得跳过测试。
20. 不得交付无法通过 Docker 启动的代码。

---

## 三十、最终交付

完成后必须提供：

1. 可运行代码；
2. 完整 Git diff；
3. `README.md`；
4. `.env.example`；
5. `AGENTS.md`；
6. 架构文档；
7. 数据字典；
8. 飞书应用配置清单；
9. 数据同步说明；
10. 指标口径说明；
11. 预警规则说明；
12. 权限说明；
13. Docker 部署说明；
14. 备份和恢复说明；
15. 测试报告；
16. 已完成与因真实凭证缺失待验证的项目清单；
17. 运行命令；
18. 至少一张 Playwright 页面截图；
19. 一条小时趋势验证；
20. 一条 3.00 vs 1.50 的比较验证；
21. 一条模拟预警推送验证。

最终回复格式：

```text
已完成
- ...

验证结果
- ...

运行方式
- ...

需要用户补充的凭证
- ...

已知限制
- ...
```

现在开始执行。先检查仓库和 fixture，然后创建 `AGENTS.md` 与 `docs/EXEC_PLAN.md`，接着按阶段完成实际代码，不要停在方案阶段。
