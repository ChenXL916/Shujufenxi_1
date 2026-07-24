# 测试报告

测试日期：2026-07-15（Asia/Shanghai）

## 结论

应用已使用两份 Excel fixture、Mock Feishu API 和用户提供的真实飞书 `.base` 离线快照完成前后端、21 表数据库、幂等同步、小时事实、图表、对比、预警、OAuth/RBAC、管理后台、测试和 Docker 交付。真实快照包含 4 个数据表、857 条记录；811 条有效业务记录进入分析，44 条“用于计算”辅助行与 2 条空行按既有规则排除。阶段 9 新增并完成飞书用户 OAuth 在线读取：令牌加密持久化、到期前刷新、refresh token 轮换、实绩独立同步、手动同步和 5 分钟定时同步均已通过真实账号验收。

阶段 10 对当前正式数据库和真实 Base 又执行了 37 项完整功能冒烟检查，结果 37/37 通过。检查过程中发现管理后台“连接测试/扫描字段”仍使用租户令牌，已修复为复用加密保存的用户令牌及刷新流程；修复后 4 张在线表的连接、字段扫描和手动同步全部成功，手动同步结果为 4 个数据源、2827 条指标事实。

阶段 11 已接入第二个真实排班 Base。程序从页面块链接自动发现主播排班与人员排班两张 API 表，在线读取 72 + 19 条记录；重复同步 91 条全部 unchanged。排班展开后共有 2232 条主播小时排班和 689 条人员日排班，并已关联到小时事实。现有应用机器人也已按指定群 `chat_id` 完成真实卡片发送，飞书返回 `code=0` 且创建消息。

阶段 12 增加明确的日/月筛选和自动群预警闭环。月份选择会展开为完整自然月并保存在 URL；曲线继续使用“自然小时 + 主播”作为 X 轴，46 个数值指标均可作为 Y 轴。预警评估后会立即推送新事件，失败或中断的事件由 5 分钟轮询恢复重试，并使用事件 UUID 防止飞书重复投递。隔离测试数据库模拟 7 日 ROI=1.5、8 日 ROI=3.0，真实应用机器人自动创建并成功发送 1 条群预警，未污染正式业务数据库。首次常驻评估暴露了历史数据延迟事件补发问题，现已限制为只评估 Asia/Shanghai 时区最近结束的自然小时，并有旧小时 created=0 的回归测试。

阶段 13 修复小时趋势多选筛选不生效：Axios 原先将数组编码为带 `[]` 的参数名，FastAPI 无法匹配。现在直播间、主播、场控、自然小时和指标均使用重复同名参数。浏览器回归已验证选择 `08-09` 后 URL、请求参数和响应数据同时变化，响应中的全部 X 轴点均为 `08-09`。

阶段 14 修复真实群数据延迟卡片错误。根因包括在线表名变更后未回算未变化记录、飞书“自动检查”富文本未被展开、卡片使用房间 UUID 且未引用计划人员、晚到实绩未关闭旧事件。修复后重新同步 909 条在线记录，通用“直播实绩”房间归零并停用，富文本 `错误` 行按规则排除，初次回算与随后实时同步共将 139 条已有晚到实绩的延迟事件自动恢复。截图中的两条事件已补全真实主播和场控并关闭；对应 18-19 小时数值已与飞书源表核对一致。本机预览数据库同时启用 SQLite WAL 和 30 秒锁等待，实时同步期间连续 15 次概览请求全部为 HTTP 200。

`make check` 通过：Ruff、ESLint、Python/TypeScript 严格类型、47 个后端测试、5 个前端单元测试、1 个覆盖完整主流程的 Playwright E2E 均通过；领域与服务分支覆盖率 88.11%（门槛 85%）。

`make verify-production` 通过：7 服务 Compose、21 表、Alembic 临时库迁移、生产强密钥/关闭开发旁路、Docker 构建上下文和必需文档静态验证通过。当前机器没有 Docker CLI，容器实际构建/启动需在 Docker Desktop/Engine 环境复验。

## 自动化结果

| 类别                  | 命令                                 | 结果                                                                                           |
| --------------------- | ------------------------------------ | ---------------------------------------------------------------------------------------------- |
| 后端格式/静态         | Ruff format/check                    | 通过，70 个 Python 文件                                                                        |
| 后端类型              | `mypy app` strict                    | 通过，48 个源文件                                                                              |
| 后端测试              | Pytest + coverage                    | 47 passed；88.11%                                                                              |
| 前端格式/静态         | Prettier + ESLint                    | 通过                                                                                           |
| 前端类型              | `tsc -b`                             | 通过                                                                                           |
| 前端单元              | Vitest                               | 5 passed                                                                                       |
| 浏览器 E2E            | Playwright / Chrome                  | 1 passed；总览、小时/采集点、分析、对比、透视、预警、管理后台                                  |
| 生产构建              | Vite                                 | 通过；路由和 vendor 分包输出                                                                   |
| 生产验证              | `make verify-production`             | exit 0                                                                                         |
| Mock 同步幂等         | `make sync-feishu` 连续两次          | 第二次 84 + 605 均 unchanged；事实数稳定                                                       |
| 真实 `.base` 同步幂等 | `import_feishu_base.py` 连续两次     | 第二次 857 条全部 unchanged；2424 小时事实稳定                                                 |
| 用户 OAuth 实时同步   | OAuth/客户端/同步服务测试            | 12 项针对性测试通过；令牌加密与轮换、Base 多表自动发现、在线源原地升级、幂等和错误记录均覆盖   |
| 真实 Base 在线读取    | 用户 OAuth + HTTP API                | 表列表/记录接口 HTTP 200；4 表共 857 条在线记录读取成功，无重复数据                            |
| 实库完整功能冒烟      | 37 项 API/权限/导出/管理检查         | 37/37 通过；总览、趋势、详情、三类分析、三类对比、透视、CSV/XLSX、预警、权限和后台均有真实响应 |
| 真实表连接与扫描      | 管理后台 source test/scan            | 4/4 连接成功，4/4 字段扫描成功；字段数分别为 52、52、52、53                                    |
| 真实 Base 手动同步    | 用户令牌全量同步                     | 4 个在线数据源、2827 条指标事实同步成功；数据模式为 `feishu`                                   |
| 真实排班 Base         | 用户令牌 + 自动表识别                | 主播表 72、人员表 19；第二次同步 91 条全部 unchanged                                           |
| 排班事实关联          | 小时事实重建                         | 490 个小时主播匹配、10 个不一致、807 个小时场控在班                                            |
| 真实群预警            | 应用机器人 + `chat_id`               | 非 Mock；飞书 `code=0`，消息创建成功                                                           |
| 自动预警闭环          | 隔离数据库 1.5→3.0 + 真实应用机器人  | created 1、queued 1、sent 1、failed 0；文案为基准的 200%、提升 100%                            |
| 历史补发保护          | 最近自然小时范围 + 业务时区回归      | 旧小时 created 0、queued 0；重启不回填历史事件                                                 |
| 小时趋势筛选          | Axios 重复参数 + Playwright 响应验证 | 直播间/主播/场控/小时/指标参数可识别；选择 08-09 后响应点全部为 08-09                          |
| 真实预警纠正          | 在线全量同步 + 正式库回算            | 909 条在线记录同步；139 条晚到实绩事件自动恢复；错误通用房间 0 采集点、0 事实并停用            |
| 18-19 数值核对        | 飞书源记录 vs 小时事实               | 散粉 ROI 1.92143331/消耗 7720.32；妆前乳 ROI 1.80785087/消耗 2828.22；主播与场控一致           |
| 本机同步并发          | SQLite WAL + 实时同步期间概览轮询    | 15/15 HTTP 200，127-327ms；无 `database is locked`                                             |

## 完整功能实库验收

- 基础运行：`/health`、`/ready`、飞书 OAuth 状态、实时同步状态均正常。
- 数据看板：4 个直播间、46 个指标；总览 8 个 KPI，小时和采集点趋势及两类详情均返回真实数据。
- 业务分析：11 个主播汇总、4 个场控汇总、23 个主播场控搭配以及昨日、上周、月度对比均正常。
- 数据工具：四层透视、CSV 导出（5327 bytes）和 XLSX 导出（7904 bytes）均成功。
- 预警与权限：189 个预警事件、5 条规则、卡片生成、数据源/指标/班次/用户管理和密钥脱敏均通过；App ID 与 App Secret 未在设置接口明文暴露。
- 飞书在线能力：4 张表连接和字段扫描成功，随后真实手动同步成功。

## 真实 `.base` 快照验收

- 支持读取飞书导出的 `gzipSnapshot`，限制压缩包与解压后大小，拒绝无效结构。
- 自动解析数据表、字段、视图、记录、单选项名称、富文本和毫秒时间戳。
- 真实主播表覆盖 2026-06-22 至 2026-07-13；两张主要直播表分别为 426、429 条记录。
- 根据同日相邻累计点补算快照未缓存的时段成交金额、支付金额、订单、人数和转化率，并补算累计金额、ROI 与订单成本。
- 2026-07-08 API 核对：时段成交金额 743742.80、时段消耗 498013.26、时段订单数 14414、时段观看人数 160200，两个有数据直播间均进入排名。
- 当前真实 Base 属于外部租户，企业自建应用无法跨租户加入；程序已改为按登录用户权限读取，并已使用 `bitable:app:readonly + offline_access` 自动发现和同步 4 张直播间表。

已知非阻断提示：FastAPI TestClient 依赖发出 Starlette/httpx2 迁移提醒；少量测试引擎在 Python 3.13 退出阶段发出 SQLite ResourceWarning，不影响断言和生产 PostgreSQL 连接生命周期。

真实群预警已使用应用机器人完成测试卡片及一次自动评估投递。自动化回归通过 MockTransport 验证首次失败、后台重试成功和重复评估不新增事件；真实自动链路只执行一次，避免测试套件重复打扰群聊。

## 关键样例

- 小时趋势：`08-09\nQ-李昕` 作为自然小时 + 主播 X 轴，采集点模式使用原始 `observed_at` 的真实分钟。
- 汇总 ROI：先汇总成交金额与消耗，再相除；不平均小时 ROI。
- 比较：3.00 vs 1.50 → 当前是基准的 200%，较基准提升 100%；基准 0 返回不可比。
- 自动预警：ROI 上涨通过最小消耗门槛后生成并立即推送；首次失败进入 failed，后台重试后转 sent，重复评估不新增；1.5→3.0 的真实群投递通过。
- 数据延迟：卡片展示直播间名称、计划主播、排班场控、中文等级和最近有效实绩；晚到实绩会补全事件上下文并自动标记恢复。
- 权限：Viewer API 只返回授权直播间，导出为 403，管理接口为 403。
- 导出安全：CSV/XLSX 对 `= + - @` 开头文本进行公式注入转义。

## 60 项验收清单

状态说明：通过 = 当前环境已自动化或人工验证；待真实凭据 = 代码/Mock 已通过但无法对真实企业飞书资源断言；待 Docker = 静态校验通过但当前机器无容器运行时。

| #   | 验收项                   | 状态/证据                                                                |
| --- | ------------------------ | ------------------------------------------------------------------------ |
| 1   | 连接两个飞书 Base        | 通过：实绩 Base 自动发现 4 张直播间表；排班 Base 自动发现主播/人员两张表 |
| 2   | 分页读取所有记录         | 通过 Mock 多页及真实用户令牌测试；当前 4 表在线读取共 857 条             |
| 3   | 自动扫描字段             | 通过 fixture/Mock 与真实 Base 表/记录接口                                |
| 4   | 识别多个直播间           | 通过，两间 fixture 动态入库                                              |
| 5   | 无直播间字段用默认直播间 | 通过                                                                     |
| 6   | 新增直播间无需改代码     | 通过，Room 动态 upsert                                                   |
| 7   | 读取主播小时排班         | 通过真实 Base；72 条源记录展开为 2232 条小时排班                         |
| 8   | 读取人员日排班           | 通过真实 Base；19 条源记录展开为 689 条人员日排班                        |
| 9   | 宽表转长表               | 通过                                                                     |
| 10  | 排班年份可配置           | 通过                                                                     |
| 11  | “用于计算”不进入图表     | 通过指标 seed/选择规则                                                   |
| 12  | 自动检查错误进入异常     | 通过，raw 保留且聚合排除                                                 |
| 13  | 0:00-0:00 不进入趋势     | 通过                                                                     |
| 14  | 时段格式统一             | 通过，24 个 `HH-HH` 时段                                                 |
| 15  | Excel 日期正确           | 通过                                                                     |
| 16  | 百分比正确               | 通过 Decimal/百分比测试                                                  |
| 17  | 主播备注拆分             | 通过                                                                     |
| 18  | 组合主播筛选匹配         | 通过成员数组与集合匹配                                                   |
| 19  | 断播不作为人员           | 通过                                                                     |
| 20  | 日期/范围筛选            | 通过 API/E2E                                                             |
| 21  | 月份筛选                 | 通过筛选选项                                                             |
| 22  | 多选直播间               | 通过                                                                     |
| 23  | 多选主播                 | 通过                                                                     |
| 24  | 多选场控                 | 通过                                                                     |
| 25  | X 轴自然小时 + 主播      | 通过 API/E2E                                                             |
| 26  | 多日日期 + 时段 + 主播   | 通过服务测试                                                             |
| 27  | 采集点真实分钟           | 通过 API/E2E                                                             |
| 28  | 全部数值指标可选         | 通过 46 指标/52 fixture 字段覆盖测试                                     |
| 29  | 不同单位分图/分轴        | 通过                                                                     |
| 30  | 多直播间默认拆图         | 通过                                                                     |
| 31  | 点位全部字段详情         | 通过                                                                     |
| 32  | 小时曲线用时段字段       | 通过                                                                     |
| 33  | 累计字段不错误求和       | 通过 LAST-per-room-day 测试                                              |
| 34  | 汇总 ROI 非简单平均      | 通过 ratio-of-sums 测试                                                  |
| 35  | 订单成本公式             | 通过                                                                     |
| 36  | 分母 0 不报错            | 通过                                                                     |
| 37  | 今日/昨日比较            | 通过                                                                     |
| 38  | 今日/上周比较            | 通过                                                                     |
| 39  | 月度比较                 | 通过                                                                     |
| 40  | 3 vs 1.5 文案            | 通过，200% 与提升 100%                                                   |
| 41  | 主播分析                 | 通过 E2E                                                                 |
| 42  | 场控分析                 | 通过 API/页面                                                            |
| 43  | 主播场控搭配             | 通过 API/页面                                                            |
| 44  | 透视表参考截图风格       | 通过人工截图检查/E2E                                                     |
| 45  | 数据延迟规则             | 通过                                                                     |
| 46  | 断播不误报延迟           | 通过规则条件                                                             |
| 47  | 排班不一致预警           | 通过                                                                     |
| 48  | 基准 0 不触发百分比      | 通过                                                                     |
| 49  | 小样本不触发波动         | 通过最小门槛测试                                                         |
| 50  | 同一预警不重复推送       | 通过 dedup/cooldown 测试                                                 |
| 51  | 推送成功/失败记录        | 通过状态模型、MockTransport 与真实应用机器人成功响应                     |
| 52  | 推送失败可重试           | 通过 Mock 重试、事件 UUID 去重与 UI                                      |
| 53  | 预警可标记处理           | 通过 API/E2E                                                             |
| 54  | 飞书登录                 | OAuth、state、加密保存、刷新轮换及真实账号授权均通过                     |
| 55  | 服务端直播间权限         | 通过 403/筛选隔离测试                                                    |
| 56  | Webhook 密钥不暴露       | 通过加密存储与掩码 API；群 chat_id 同样掩码返回                          |
| 57  | Docker 一键启动          | 待 Docker；Compose/路径静态验证通过                                      |
| 58  | 数据库迁移可重复         | 通过 Alembic 重复/临时库验证                                             |
| 59  | 全部测试通过             | 通过 `make check`                                                        |
| 60  | README/部署文档完整      | 通过                                                                     |

## 待外部环境验证

1. 在安装 Docker Engine 的主机执行生产 Compose，等待 7 服务健康并复跑 E2E/备份恢复演练。

## 2026-07-22 GitHub 发布验收

- `make.cmd check` 退出 0：174 个后端测试、17 个前端测试文件/58 个单测、生产构建与 6 个 Playwright E2E 全部通过；领域与服务覆盖率 86.42%，高于 85% 门槛。
- 私有 Excel 临时移出后的干净检出模拟通过 6/6 浏览器流程；测试会在运行时生成匿名合成直播、排班、小时事实和采集点，不把真实主播数据写入 Git。
- `make.cmd verify-production` 退出 0：验证 7 个 Compose 服务、33 张迁移表、生产强密钥/公网 HTTPS/飞书凭据策略、生产启动不导入 fixture 以及 Docker 构建路径。
- 当前主机没有 Docker CLI，因此本次生产验收为 YAML、路径、安全策略和数据库迁移静态验收；容器实际启动仍属于外部环境验证项。
- 发布边界检查确认 `.env`、数据库、日志、运行产物和 `fixtures/*.xlsx` 被忽略；仓库只包含 `.env.example` 与匿名测试生成逻辑。

## 2026-07-22 Netlify 404 修复验收

- 根因确认：Netlify 跟随的 GitHub 默认分支 `main` 只有初始 README，因此既没有可发布的前端产物，也没有单页应用路由回退规则。
- 部署配置回归测试 6/6 通过；根目录 `netlify.toml` 明确使用 `apps/web` 构建并发布 `dist`。
- 两种生产构建均通过：未配置后端时生成 SPA 回退；配置 `NETLIFY_BACKEND_ORIGIN=https://api.example.com` 时先生成 `/api/*`、`/auth/*`、`/health`、`/ready` 的 HTTPS 代理，再生成 SPA 回退。
- `make.cmd check` 退出 0：176 个后端测试、17 个前端测试文件/58 个单测、生产构建与 6 个 Playwright E2E 全部通过；后端覆盖率 86.42%，高于 85% 门槛。
- `make.cmd verify-production` 退出 0：7 个 Compose 服务、33 张迁移表、强密钥策略、生产无夹具写入与 Docker 构建路径验证通过。
- 当前主机没有 Docker CLI，因此容器运行态仍未在本机验证；Netlify 只托管前端，要在线读取飞书实时数据还必须部署 API、数据库、Redis、Worker/Beat，并配置 `NETLIFY_BACKEND_ORIGIN`。
- PR #1 合并后已在 Netlify 创建 `jskzsjfx` 项目并连接 `ChenXL916/Shujufenxi_1` 的 `main`；首个生产构建读取根目录 `netlify.toml`，确认当前目录为 `apps/web`、命令为 `npm run build`。
- 线上冒烟通过：`https://jskzsjfx.netlify.app/` 与 `/overview` 均返回 HTTP 200，React Router 自动进入经营总览，默认 404 已消失。
- 未配置公网后端时，线上 `/api` 会命中 SPA 回退。新增响应格式保护与总览错误态后，前端不再把 `text/html` 当作接口 JSON；定向 ESLint、TypeScript、10 个单测与生产构建均通过。
- 响应保护修复后的最终 `make.cmd check` 退出 0：176 个后端测试、17 个前端测试文件/61 个单测、生产构建和 6 个 Playwright E2E 全部通过；覆盖率 86.42%。
- 最终 `make.cmd verify-production` 退出 0：7 服务、33 表、迁移、强密钥策略、生产无夹具写入与 Docker 构建路径均通过；Docker 运行态限制不变。
- GitHub Linux CI 首轮仅有一条原有预警页重交互测试在 5.35 秒触发默认 5 秒超时；定向放宽该测试至 15 秒后连续复跑 3/3 通过（4.55–5.23 秒），未跳过测试或删除断言。
- CI 稳定性修复后的最终复验：`make.cmd check` 退出 0（176 个后端、17 个前端文件/61 个单测、生产构建、6 个 Playwright E2E，覆盖率 86.42%）；`make.cmd verify-production` 退出 0。

## 2026-07-22 Netlify 真实数据恢复验收

- 根因：Netlify 已能加载前端，但此前配置的 Cloudflare 临时后端返回 HTTP 502，导致 `/api` 无法取得数据；不是飞书表格为空。
- 飞书正式同步：使用已有用户授权令牌读取 4 个实绩源与 2 个排班源，共 1,469 条源记录；生成 2,384 条小时事实。首轮同步的源校验异常共 18 条，随后幂等复查仍保留 `Mistine 水散粉` 9 条异常，异常未混入聚合结果。
- 运行态：FastAPI `/health` 返回 HTTP 200；`/ready` 返回 `ready`，模式为 `feishu`，数据库与 Redis 均为 `ok`；实时同步循环首轮完成且未产生重复预警推送。
- Netlify 同源代理：`/health`、`/ready`、`/auth/me`、`/api/v1/filters/options`、总览和小时趋势均返回 HTTP 200 JSON；筛选接口识别 3 个直播间、25 位主播、5 位场控和 46 个指标，数据范围为 2026-06-23 至 2026-07-21。
- 浏览器验收：`/overview?start=2026-07-21&end=2026-07-21` 显示 8 项 KPI、3 个直播间排名和 24 个小时段；成交金额 ¥551,448.49、消耗 ¥359,637.02、整体 ROI 1.75、订单 10,248、观看人数 118,722。浏览器控制台错误/警告为 0。
- 部署证据：Netlify 生产部署 ID `6a605c0cda8a26deaa18eea1` 构建成功，构建日志确认后端代理规则已生成。
- 完整门禁：首轮发现 4 个前端文件存在 Prettier 格式漂移；按项目规则格式化后从头复跑，最终 `make.cmd check` 退出 0。Ruff、ESLint、mypy、TypeScript、Prettier、176 个后端测试、17 个前端测试文件/61 个单测、生产构建及 6 个 Playwright E2E 全部通过，后端覆盖率 86.42%。
- 生产验收：`make.cmd verify-production` 退出 0，验证 7 服务、33 表、迁移、强密钥、生产无夹具写入和 Docker 构建路径；由于本机无 Docker CLI，容器部分为等价 YAML/路径/安全静态校验。
- 边界：当前公网后端通过 Cloudflare Quick Tunnel 暂时恢复，入口没有持久 SLA，依赖本机 API、同步与隧道进程；正式长期部署仍需固定隧道或云主机。

## 2026-07-22 飞书 OAuth 与隧道二次恢复验收

- 飞书回调登记：新授权请求使用 `https://jskzsjfx.netlify.app/auth/feishu/callback`，飞书授权入口已接受该地址，不再出现错误码 `20029`。
- OAuth state：登录入口设置 10 分钟有效的安全 cookie；保持 cookie 的伪造 code 回调进入令牌交换阶段而非 `OAuth state 校验失败`，证明 state 绑定链路正确。
- 故障边界：旧 Quick Tunnel 在回调阶段返回 Cloudflare Host 502；本地 `/ready` 同时返回 HTTP 200、`mode=feishu`、数据库和 Redis 均为 `ok`，因此根因不是飞书权限或数据为空。
- 新隧道探针：新的 HTTPS 源站 `/ready` 返回 HTTP 200；Netlify 生产构建生成 API、OAuth、健康和就绪四组同源代理规则。
- 定向回归：`test_deployment_safety.py` 6/6 通过；`HourlyRoiSpendSection.test.tsx` 7/7 通过且无测试环境销毁后的未处理 React 错误。
- 完整门禁：`make.cmd check` 退出 0；176 个后端测试、17 个前端测试文件/61 个单测、生产构建、6 个 Playwright E2E 全部通过，后端覆盖率 86.42%。
- 生产验收：`make.cmd verify-production` 退出 0；验证 7 服务、33 表、迁移、强密钥、生产无夹具写入与 Docker 构建路径。本机无 Docker CLI，容器运行态仍未实测。
- 运行边界：Cloudflare Quick Tunnel 无持续可用性保证；正式 24×7 运行必须迁移到固定域名的命名隧道或云服务器。

## 2026-07-22 飞书登录后数据范围验收

- OAuth 与同步均正常；真实账号完成登录，长期授权可刷新，最新四个实绩源同步全部为 `success`。
- 无数据显示的根因不是飞书授权或表格为空，而是登录用户为 `viewer` 且有效直播间范围为 0。
- 修复前已使用 SQLite 在线备份；随后将当前登录账号恢复为 `developer`，会话签名与用户 ID 不变，浏览器只需刷新页面。
- 生产域名会话复验：`/auth/me` 返回 `feishu_oauth`/`developer`/全部直播间；筛选返回 3 个直播间、25 位主播和 46 个指标；2026-07-21 总览返回 8 项 KPI、3 条直播间排名与真实经营数值。
- 数据库存量复验：2,384 条小时事实，日期覆盖 2026-06-23 至 2026-07-31；水散粉最新同步的 9 条异常记录保持隔离。

## 2026-07-22 共享登录与分级权限验收

- 结论：共享访问、飞书首次登录、账号独立开户、菜单权限和服务端 RBAC 均通过；同事首次登录后不再看到空白页，也不会获得开发者权限。
- 后端定向测试：22 passed；覆盖邀请账号绑定、历史 `pending:` 兼容、未邀请身份自动开户、默认角色限制和审计日志。
- 前端定向测试：8 passed；覆盖未登录飞书入口、受限用户导航隔离和管理员自动开户设置。
- 完整质量门禁：`make.cmd check` 退出码 0；Ruff、ESLint、mypy、TypeScript、Prettier、178 个后端测试、63 个前端单元测试、生产构建及 6 个 Playwright E2E 全部通过；后端覆盖率 86.32%，高于 85% 门槛。
- 运行时 RBAC 冒烟：`live_manager` 会话返回 HTTP 200，角色范围包含 3 个直播间；筛选接口返回 3 个直播间；权限管理总览返回 HTTP 403。
- 公网就绪探针：`https://jskzsjfx.netlify.app/ready` 返回 HTTP 200，后端处于 `feishu` 就绪模式。
- 数据安全：修改运行库前已备份到 `backups/live_ops_20260722T091642Z.sqlite3`；测试未向真实飞书群发送消息，也未修改真实业务记录。
- 部署边界：公网 API 仍经 Cloudflare Quick Tunnel 连接本机，适合当前验收和共享试用，但不具备 24×7 SLA；长期运行应迁移到固定隧道或云主机。
- 最终生产验收：`make.cmd verify-production` 退出码 0；7 个服务、33 张表、迁移、强密钥、生产无夹具写入和 Docker 构建路径均有效。本机无 Docker CLI，容器部分为等价 YAML、路径和安全静态校验。
- Netlify 发布后浏览器验收：根链接 HTTP 200；无 Cookie 会话显示飞书登录提示和按钮，页面无 JavaScript 异常。控制台仅记录未登录探测 `/auth/me` 的预期 HTTP 401。
- 公网权限验收：通过 Netlify 同源代理模拟 `live_manager` 会话，`/auth/me` 与筛选接口 HTTP 200，角色范围和筛选均包含 3 个直播间；`can_manage_permissions=false`，权限总览 HTTP 403。

## 2026-07-22 阶段 24：网页账号密码登录与分级访问

- 认证实现：新增网页账号密码登录，使用随机 16-byte 盐的 scrypt 单向哈希；密码和哈希不进入 API 响应或审计内容。错误账号、错误密码和停用账号统一返回 HTTP 401“账号或密码错误”。
- 会话安全：登录成功签发原有 8 小时签名 `HttpOnly` 会话 Cookie 和独立 CSRF Cookie；生产环境继续启用 `Secure`、`SameSite=Lax`。`/auth/me` 明确返回 `auth_mode=password`。
- 暴力破解防护：相同来源和登录名 5 次失败后返回 HTTP 429 与 `Retry-After: 300`；生产 Redis 提供共享计数，依赖不可用时退化为进程内计数。
- 权限管理：开发者可创建包含登录名、初始密码、角色及直播间范围的网页账号，并可对已有账号重置密码；列表只返回 `password_login_enabled` 布尔状态。普通账号仍无法调用权限管理接口。
- 定向后端：`test_auth_permissions.py` 与 `test_rbac_data_scope.py` 共 13 项通过，覆盖随机盐哈希、正确/错误/停用登录、限流、密码会话、创建/重置、审计与秘密不回显。
- 定向前端：`App.test.tsx` 与 `AdminPage.test.tsx` 共 8 项通过，覆盖共享链接登录表单、账号提交、飞书备用入口、初始密码字段和网页登录状态。
- 完整门禁：`make.cmd check` 退出 0；182 个后端测试全通过，领域与服务覆盖率 86.36%；17 个前端测试文件/63 个单测全通过；Vite 生产构建 22 个 JS Chunk 均不超过 650 KiB；6 个 Chromium E2E 全通过。
- 生产静态验收：`make.cmd verify-production` 退出 0，验证 7 个服务、33 张迁移表、生产强密钥、关闭开发旁路、无 fixture 写入及 Docker 构建路径。本机没有 Docker CLI，容器运行态仍为等价静态验收。
- 数据安全：部署前已在线备份生产 SQLite 到 `backups/live_ops_20260722T101626Z.sqlite3`；自动测试没有调用真实飞书消息发送接口，也未修改直播经营事实。
- 生产发布：提交 `f13e026` 已推送至 `ChenXL916/Shujufenxi_1/main`；Netlify 生产站点 `/`、`/overview` 与 `/ready` 均为 HTTP 200，线上主入口包与本地生产构建一致并包含网页账号登录界面。
- 公网账号链路：对隔离的 `live_manager_test` 临时设置随机密码后，`POST /auth/password/login` HTTP 200，`/auth/me` 返回 `auth_mode=password`、`role=live_manager` 和 3 个直播间；筛选接口返回 3 个直播间，权限管理接口 HTTP 403；退出 HTTP 204，退出后会话 HTTP 401。
- 公网测试清理：临时密码只存在于测试进程内，测试结束后已把 `password_hash`、最近登录时间和临时登录审计恢复/清理；复查为 `PASSWORD_CLEARED=True`、`SMOKE_AUDIT_ROWS=0`。没有在代码、文档、Git 或日志中记录该随机密码。

## 2026-07-22 阶段 25：长期免密进入与滚动会话

- 功能口径：首次登录后签发默认 30 天的持久化签名 Cookie；应用启动调用 `/auth/me` 时在账号仍有效的前提下滚动续期。同一浏览器关闭后重新打开链接可直接进入，浏览器不保存密码。
- 安全口径：会话 Cookie 保持 `HttpOnly`，生产保持 `Secure`、`SameSite=Lax`、`Path=/`；CSRF Cookie 同期滚动。账号停用、角色与直播间范围变化仍由服务端逐请求校验，主动退出删除两枚 Cookie。
- 配置验证：`SESSION_MAX_AGE_DAYS` 默认 30，Pydantic 强制范围 1–365；`.env.example` 与生产 Compose 均已声明。定向测试覆盖默认 Max-Age、45 天自定义值、上下界拒绝、滚动续期和退出后 HTTP 401。
- 定向测试：`test_auth_permissions.py` 与 `test_rbac_data_scope.py` 共 14 项通过；前端 `App.test.tsx` 5 项通过；Ruff 格式与检查通过。
- 完整门禁：`make.cmd check` 通过。183 个后端测试全部通过，领域与服务覆盖率 86.36%；17 个前端测试文件/63 个单元测试通过；Vite 生产构建生成 22 个 JS Chunk，全部不超过 650 KiB；6 个 Chromium E2E 通过。
- 生产验证：`make.cmd verify-production` 通过，验证 7 个服务、33 张表、迁移、生产强密钥、关闭开发旁路、无 fixture 写入和 Docker 构建路径。本机无 Docker CLI，因此容器运行态继续采用 YAML、路径与安全静态等价验收。
- 数据保护：部署前生成 `backups/live_ops_20260722T103410Z.sqlite3`；测试未调用真实飞书群推送，也未修改直播经营事实。
- 运行验证：生产 API 重启后，本地 `/health`、`/ready` 与公网 `/ready` 均为 HTTP 200，`ready.mode=feishu`。
- 公网会话冒烟：隔离账号临时随机密码登录 HTTP 200；登录与 `/auth/me` 响应均返回 `Max-Age=2592000`，Cookie 安全属性完整；复制 Cookie 到新客户端模拟浏览器重开后 `/auth/me` HTTP 200，角色为 `live_manager`、范围为 3 个直播间；退出 HTTP 204，退出后 `/auth/me` HTTP 401。
- 清理复核：冒烟结束后恢复隔离账号原密码哈希、最近登录时间与更新时间，并清理本次新增登录审计；复查 `PASSWORD_RESTORED=True`、`SMOKE_AUDIT_RESTORED=True`，没有记录临时密码或 Cookie 内容。
- 发布复核：功能提交 `f814d7a` 已推送至 `ChenXL916/Shujufenxi_1/main`；Netlify 生产入口从旧资源切换到 `/assets/index-BcTUAAJW.js`，线上脚本确认包含“本设备将保持登录”，公网 `/ready` 返回 `ready / feishu`。

## 2026-07-23 阶段 26：所有者网页登录恢复

- 生产数据核对：飞书身份“陈佳琪”已存在且启用，角色为 `developer`；不能进入的原因是该身份原先没有网页登录名和密码，并非数据或飞书授权失效。
- 处理方式：直接在既有身份上启用网页登录，未创建重复用户，原飞书绑定、角色和数据范围保持不变；凭据未写入仓库或测试报告。
- 数据保护：修改前完成 SQLite 在线备份 `backups/live_ops_account_20260723T012406Z.sqlite3`，并写入不含密码的权限审计记录。
- 公网冒烟：`POST /auth/password/login` HTTP 200，`GET /auth/me` HTTP 200 且角色为 `developer`；退出 HTTP 204，退出后会话查询 HTTP 401。
- 变更边界：本阶段仅修改生产账号凭据与审计数据，没有代码、数据库结构或部署配置变更，因此沿用阶段 25 已通过的完整 `make.cmd check` 和 `make.cmd verify-production` 门禁结果。
- 登录名调整：所有者账号登录名从 `chenjiaqi` 改为 `1058177562`；修改前生成 `backups/live_ops_username_20260723T012722Z.sqlite3`，数据库确认新登录名唯一、旧登录名记录数为 0，身份、飞书绑定和 `developer` 权限未改变。
- 密码恢复与最终验证：发现原密码哈希已不再匹配后，在不记录明文密码的前提下重新生成哈希并写入脱敏审计。正式 HTTPS 入口登录 HTTP 200、`/auth/me` HTTP 200 且返回“陈佳琪 / developer”，退出 HTTP 204，退出后 `/auth/me` HTTP 401。

## 2026-07-23 阶段 27：立即同步网关超时修复

- 故障复现：正式飞书状态接口显示应用凭据、用户授权、刷新令牌和实时数据源全部就绪，`last_error=null`；旧版 `POST /auth/feishu/sync` 从公网约 30 秒后返回 HTTP 504，而后端日志显示同步约 37 秒完成。结论为同步请求超过代理等待时间，页面的“请检查飞书授权状态”属于错误归因。
- 后端修复：同步 POST 现在以 HTTP 202 创建或复用后台任务，并新增任务状态查询接口；后台仍调用正式 `live_actual` 同步服务，成功结果只暴露授权模式、来源数和小时事实数，失败结果经过安全归一化。
- 前端修复：按钮在后台任务结束前保持同步状态，每 2 秒轮询并在完成后刷新页面数据；飞书重新授权、业务同步失败和状态查询中断分别显示真实原因。连续 4 次短暂轮询故障可自动恢复，第 5 次才结束等待并说明任务可能仍在后台执行。
- 定向测试：后端 `test_auth_permissions.py` 13 passed；前端 `client.test.ts` 9 passed。覆盖 HTTP 202、排队/运行/完成、重新授权失败、错误信息透传和瞬时断线恢复。
- 公网真实链路：密码会话登录成功；同步受理耗时 0.630 秒并返回 HTTP 202；任务 `6f436b51-1134-46ba-bfa4-f22bd22b9b08` 最终为 `completed`，`auth_mode=user_access_token`、`sources_synced=4`、`hourly_facts=2384`。同步后状态的 `last_error` 为空。
- 完整质量门禁：`make.cmd check` 退出 0。185 个后端测试通过，领域与服务覆盖率 85.85%；17 个前端测试文件的 65 个单元测试通过；生产构建生成 22 个 JS Chunk，均不超过 650 KiB；6 个 Chromium E2E 通过。
- 生产验证：`make.cmd verify-production` 退出 0，验证 7 个服务、33 张表、迁移、生产强密钥、无 fixture 写入和 Docker 构建路径。本机没有 Docker CLI，容器运行态仍为 YAML、路径和安全静态等价验收。
- 数据与消息边界：部署前备份 `backups/live_ops_background_sync_20260723T014831Z.sqlite3`；真实联调执行了表格读取、清洗和幂等业务同步，但没有触发飞书群预警推送，也没有记录凭据或会话秘密。
- 发布复核：功能提交 `4705202` 已推送到 `ChenXL916/Shujufenxi_1/main`；Netlify 已从旧入口包切换至 `/assets/index-Bqvtlmk_.js`。线上脚本确认包含后台同步轮询提示且不含旧的统一授权失败提示，公网 `/ready` 返回 `status=ready`、`mode=feishu`，数据库和 Redis 均为 `ok`。

## 2026-07-23 阶段 28：后台账号与密码自助维护

- 功能结果：用户管理的操作列新增统一“账号密码”入口，覆盖已有网页账号和仅绑定飞书的用户。管理员可修改网页登录名；新密码留空时原密码不变，填写并确认后旧密码失效。
- 数据边界：凭据修改不更新角色、账号启停状态、个人/角色直播间范围或飞书身份绑定；当前会话按用户 ID 保持有效，后续网页登录使用保存后的登录名和密码。
- 后端安全：新增凭据更新接口执行 `permission.manage` 和 CSRF，登录名规范化并唯一，密码只写入随机盐单向哈希。审计动作 `user_credentials_updated` 仅记录脱敏元数据，不包含密码或哈希。
- 定向验证：后端认证/RBAC 16 passed；前端管理页与 API client 13 passed。覆盖密码轮换、只改登录名时哈希不变、同名 HTTP 409、无登录名飞书用户启用网页登录、二次密码确认和提交路径。
- 安全回归：首次 `make.cmd check` 的 184/185 后端测试通过，唯一失败是 CSRF 写路由固定计数仍为 35；扫描结果已确认新增接口包含保护依赖。将清单计数更新为 36 后从头复跑全部通过。
- 完整门禁：最终 `make.cmd check` 退出 0。185 个后端测试通过，领域与服务覆盖率 85.85%；17 个前端测试文件/66 个单元测试通过；生产构建 22 个 JS Chunk 均不超过 650 KiB；6 个 Chromium E2E 通过。
- 生产验证：`make.cmd verify-production` 退出 0，验证 7 个服务、33 张表、迁移、强密钥、无 fixture 写入及 Docker 构建路径。本机没有 Docker CLI，容器运行态采用 YAML、路径和安全静态等价验收。
- 数据保护：部署前在线备份 `live_ops_test.db` 到 `backups/live_ops_account_admin_20260723T021420Z.sqlite3`，备份完整性检查为 `ok`；自动测试未修改正式账号、密码或直播经营数据，也未触发真实飞书群推送。
- 发布复核：提交 `9a53a40` 已推送至 `ChenXL916/Shujufenxi_1/main`；生产 API 无迁移重启后，本地与公网 `/ready` 均返回 `ready / feishu`。Netlify 入口为 `/assets/index-CpY53Vl1.js`，管理页分包 `/assets/AdminPage-Rl8bmTIo.js` 包含“账号密码”“网页登录名”及权限范围保护说明。
- 公网权限复核：对新凭据接口发送结构合法但无会话的请求返回 HTTP 401，而非 2xx；说明路由已生效并继续由登录、`permission.manage` 与 CSRF 链路保护。该探针使用不存在的全零用户 ID，没有修改生产账号。

## 2026-07-23 阶段 30：五级角色层级与防越级授权

- 角色种子：8 个正式/兼容角色幂等创建；管理员和运营负责人均覆盖 3 个正式直播间，管理员不含 `database.manage`，运营负责人权限集合与 L3 设计完全一致。
- 防越级：管理员创建开发者、修改开发者凭据、修改自身角色、把运营负责人提升为管理员均返回 HTTP 403/409；管理员修改运营负责人凭据和创建项目 PM 成功。
- 权限上限：向运营负责人角色加入 `user.manage` 返回 HTTP 403；使用 L3 允许的同步、数据源、目标、规则和审计权限可保存。
- 分区入口：运营负责人请求数据源与审计 API 返回 HTTP 200，请求系统设置与用户权限总览返回 HTTP 403；前端只显示数据源、预警与 ROI 目标、审计入口。
- 兼容安全：旧 `role_name=admin` 且历史带有 developer 关联的用户再次执行权限种子后只保留 `admin`，不再越级。
- 自动开户：飞书首次登录只能授予直播主管、各项目 PM 或受限查看者，不能选择运营负责人、管理员或开发者。
- 定向测试：后端权限、安全、认证、CSRF 与数据范围 25 项通过；前端 App 与管理页 9 项通过。
- 完整门禁：`make.cmd check` 退出 0。189 个后端测试通过，领域与服务覆盖率 85.89%；17 个前端测试文件/68 个单测通过；生产构建 22 个 JS Chunk 全部不超过 650 KiB；6 个 Chromium E2E 通过。
- 生产验证：`make.cmd verify-production` 退出 0，验证 7 个服务、33 张表、迁移、生产强密钥、无 fixture 写入和 Docker 构建路径。本机没有 Docker CLI，容器运行态采用 YAML、路径和安全静态等价验收。
- 数据与消息边界：测试使用内存库和隔离 E2E 数据库，没有改动正式用户角色、密码或直播经营事实，也没有调用真实飞书群机器人。
- 发布备份：`backups/live_ops_20260723T042946Z.sqlite3` 完整性为 `ok`，包含发布前的 7 个用户和 6 个角色。
- 正式种子：发布后角色数为 8；新增管理员和运营负责人角色，未自动给现有用户分配新角色。
- 公网只读验收：`/ready` 为 `ready / feishu`；所有者会话 `/auth/me` 和权限总览 HTTP 200，五级返回顺序为 500/400/300/200/100。
- 前端发布：线上主包 `/assets/index-DPPYGmmj.js`、管理包 `/assets/AdminPage-BSalkNlE.js` 已包含本阶段角色和防越级界面。

## 2026-07-23 阶段 31：经营总览指标与可筛选主播分析

- 总览口径：默认 KPI 固定为时段整体成交金额、消耗、整体支付 ROI、净支付 ROI、成交单数、整体成交订单成本、观看人数和成交人数；不再返回时段支付金额，成交人数位于最后。
- 主播分析：日期/月份、1/3/5/7/15/30 天、直播间、主播、主播成员、场控、自然小时和指标均可筛选；指标写入 URL 并作为重复 `metric_keys` 传给汇总 API，表格按所选指标动态生成列。
- 定向验证：后端 2 passed；前端 3 个测试文件共 15 passed；修正筛选 URL 的 Playwright 场景后定向 E2E 1 passed。
- 完整门禁：`make.cmd check` 退出 0。189 个后端测试通过，领域与服务覆盖率 85.89%；18 个前端测试文件/70 个单元测试通过；生产构建生成 22 个 JS Chunk，全部不超过 650 KiB；6 个 Chromium E2E 通过。
- 生产验证：`make.cmd verify-production` 退出 0，验证 7 个服务、33 张表、迁移、强密钥、生产无 fixture 写入和 Docker 构建路径；本机没有 Docker CLI，容器运行态完成 YAML、路径和安全静态等价验收。
- 安全边界：发布前在线备份正式 SQLite 到 `backups/live_ops_20260723T062447Z.sqlite3`，大小 70,701,056 字节且 `PRAGMA integrity_check=ok`；后端测试显式使用测试配置，E2E 使用隔离数据库与 Mock 飞书机器人；没有修改正式经营数据，也没有向真实飞书群发送消息。
- 发布复核：提交 `8ad1eb6` 已推送到 `ChenXL916/Shujufenxi_1/main`；本地与公网 `/ready` 均返回 `ready / feishu`。新主播分析接口在无会话时本地和公网均返回 HTTP 401，证明路由已加载且继续受登录保护。
- 前端发布：线上入口为 `/assets/index-CgkB2sMz.js`，总览分包为 `/assets/OverviewPage-CPeIo3fy.js`，主播分析分包为 `/assets/AnalysisPage-BDA7J2KT.js`；线上分析分包包含 `period_buyers` 和动态指标筛选实现。

## 2026-07-23 阶段 32：主播逐时段数据明细

- 功能结果：主播分析新增分页“主播时段明细”，展示日期、自然小时、直播间、主播、场控和当前选择的全部指标；支持日/月及 1/3/5/7/15/30 天、直播间、主播、主播成员、场控、自然小时和指标联动筛选。
- 数据口径：明细只读取已完成的标准小时事实；同一页指标一次批量查询，并复用指标字典的 `sum`、`ratio`、`cost` 聚合规则，避免把 ROI 或成本直接相加。
- 权限结果：新接口复用服务端直播间范围校验；越权显式请求直播间返回 HTTP 403，空权限范围不会返回其他直播间数据。
- 交互结果：主播汇总名称可直接点击并写入 URL 的 `anchors` 参数，明细页码同步回到第一页；每页可选 20/50/100/200 条，动态指标列与上方汇总保持一致。
- 定向验证：后端主播明细与 RBAC 共 6 passed；前端 API client 与主播页共 14 passed；Ruff、ESLint、Prettier、mypy 和 TypeScript 全部通过。
- 完整门禁：`make.cmd check` 退出 0。189 个后端测试通过，领域与服务覆盖率 85.87%；18 个前端测试文件/71 个单元测试通过；生产构建生成 22 个 JS Chunk，全部不超过 650 KiB；6 个 Chromium E2E 通过。
- 生产验证：`make.cmd verify-production` 退出 0，验证 7 个服务、33 张表、迁移、强密钥、生产无 fixture 写入和 Docker 构建路径；本机没有 Docker CLI，容器运行态完成 YAML、路径和安全静态等价验收。
- 安全边界：自动测试使用内存数据库、隔离 E2E 数据库和 Mock 飞书机器人；发布前在线备份正式 SQLite 到 `backups/live_ops_20260723T064058Z.sqlite3`，大小 70,701,056 字节且 `PRAGMA integrity_check=ok`，未向真实飞书群发送消息。
- 发布复核：功能提交 `81ffe7d` 已推送至 `ChenXL916/Shujufenxi_1/main`；生产 API 重启后本地和公网 `/ready` 均为 HTTP 200、`ready / feishu`，新主播时段接口在未登录时均返回 HTTP 401。
- 前端发布：Netlify 入口已切换为 `/assets/index-VYX36Qtp.js`，主播分析分包为 `/assets/AnalysisPage-BYfaX15w.js`；线上资源包含新接口路径和“主播时段明细”界面。

## 2026-07-23 阶段 33：分析页面默认指标精简

- 默认集合：分析页未带 `metrics` 参数时，按配置默认选择截图中的 20 项，顺序从 `period_gmv` 到 `period_net_order_cost`；`period_spend`“时段消耗”及其他未勾选指标不进入默认集合。
- 配置隔离：新增独立 `analysis_default` 元数据并随筛选选项 API 返回，不修改经营总览和小时趋势使用的 `default_visible`；前端不再维护重复硬编码列表。
- 请求一致性：指标选择器、主播/场控/搭配汇总和主播逐时段明细均发送同一默认集合；URL 显式包含 `metrics` 时只显示并请求用户选择项。
- 转化率口径：带完整分子分母的观看成交率继续按合计分子/分母重算；其余无完整分母的时段转化率不做简单平均，汇总显示最近有效时段并明确标注，逐时段表显示该小时原值。
- 定向验证：后端默认指标、逐时段值和 RBAC 6 passed；前端主播页与 API client 15 passed；mypy 和 TypeScript 通过。
- 完整门禁：`make.cmd check` 退出 0。189 个后端测试通过，领域与服务覆盖率 85.90%；18 个前端测试文件/72 个单元测试通过；生产构建生成 22 个 JS Chunk，全部不超过 650 KiB；6 个 Chromium E2E 通过。
- 生产验证：`make.cmd verify-production` 退出 0，验证 7 个服务、33 张表、迁移、强密钥、生产无 fixture 写入和 Docker 构建路径；本机没有 Docker CLI，容器运行态完成 YAML、路径和安全静态等价验收。
- 安全边界：自动测试使用内存数据库、隔离 E2E 数据库和 Mock 飞书机器人；发布前在线备份正式 SQLite 到 `backups/live_ops_20260723T072935Z.sqlite3`，大小 70,701,056 字节且 `PRAGMA integrity_check=ok`，未修改正式经营数据或发送真实群消息。
- 发布复核：功能提交 `778a16e` 已推送至 `ChenXL916/Shujufenxi_1/main`；生产 API 重启后本地和公网 `/ready` 均为 HTTP 200、`ready / feishu`，筛选选项接口未登录探针返回 HTTP 401。
- 前端发布：Netlify 入口已切换为 `/assets/index-BpSoq5-r.js`，主播分析分包为 `/assets/AnalysisPage-BSODBGsA.js`；线上分包包含 `analysis_default` 和“最近时段”，运行配置确认默认 20 项且排除 `period_spend`。

## 2026-07-23 阶段 34：数据点详情暖白视觉与信息排版

- 实现范围：小时趋势的数据点详情抽屉改为全站暖白卡片体系；基础字段中文化，状态转为“数据完整/待补录/缺失”和“排班一致/不一致/待实绩”等业务文案；指标按本时段、直播累计、实时快照和其他口径分组。
- 完整数据：小时事实详情展示服务端返回的全部真实采集点、采集时间和有效/异常说明；采集点 `raw_payload` 仍可完整展开，没有删除或改写原始数据。

- 单元测试：`DataPointDetailDrawer.test.tsx` 2/2 通过，覆盖中文字段、状态、指标分组、金额/ROI/人数格式、采集记录、英文键隐藏和原始字段默认折叠/展开。
- 视觉证据：源截图与实现均归一化为 600 × 1200、`deviceScaleFactor=1`，同屏证据为 `docs/ui/evidence/after/data-point-detail-comparison.png`；390 × 844 手机截图验证单列布局。`design-qa.md` 检查字体、间距、颜色、图标资产和文案，最终 `passed`，无 P0/P1/P2/P3 遗留。
- 浏览器交互：本地真实运行库只读验收 24/24 断言通过；600px 三组指标均为双列，390px 三组均为单列；46 个指标值无截断，页面与抽屉无横向溢出，关闭焦点恢复，控制台错误、失败请求和被阻断请求均为 0。
- 完整门禁：`make.cmd check` 退出 0。Ruff、ESLint、mypy、TypeScript 和 Prettier 通过；189 个后端测试通过，领域与服务覆盖率 85.90%；19 个前端测试文件/74 个单元测试通过；生产构建的 22 个 JS Chunk 全部不超过 650 KiB；6 个 Chromium E2E 通过。
- 生产验证：`make.cmd verify-production` 退出 0，验证 7 个服务、33 张表、迁移、生产强密钥、关闭开发旁路、无 fixture 写入和 Docker 构建路径。本机没有 Docker CLI，因此容器运行态完成 YAML、路径与安全静态等价验收。
- 数据保护：发布前 SQLite 在线备份为 `backups/live_ops_detail_ui_20260723T081103Z.sqlite3`，`PRAGMA integrity_check=ok`；自动测试使用隔离数据库和 Mock 飞书运输，手工视觉验收只允许本机只读 HTTP 请求，没有修改正式经营数据、账号、权限或发送真实飞书群消息。
- 发布复核：功能提交 `21f7c48` 已推送至 `ChenXL916/Shujufenxi_1/main`；Netlify 入口为 `/assets/index-QE3-1PVU.js`，Timeline 分包为 `/assets/TimelinePage-CvIaT2DL.js`，样式为 `/assets/index-BcjKepA4.css`。
- 线上资产：Timeline 分包返回 HTTP 200 并包含“本时段表现”“直播累计”“采集记录”“自然小时汇总”和 `timeline-detail-drawer`；CSS 返回 HTTP 200 并包含 `.detail-overview-card` 与 `.detail-metric-grid`。公网 `/ready` 返回 HTTP 200、`status=ready`、`mode=feishu`，数据库和 Redis 均为 `ok`。

## 2026-07-23 阶段 35：全站业务详情界面统一

- 实现范围：数据点详情、自然小时分时详情和主播趋势事实详情共用同一套暖白首卡、状态、上下文、章节和指标卡结构；设置、权限和账号编辑继续保持为操作表单。
- 业务保持：原详情 API、房间权限、指标字典、逐日/小时/原始事实、时间线跳转、预警跳转和 CSV 导出均未改变；没有新增、推导或覆盖经营数据。
- 定向组件测试：`DataPointDetailDrawer.test.tsx`、`HourlyRoiSpendSection.test.tsx`、`AlertsPage.test.tsx` 共 14/14 通过。
- 详情 E2E：新增 `detail-drawers.spec.ts`，在 600×1200 隔离视口依次打开三类详情，验证标题、状态、八项核心指标、事实章节、抽屉边界和内部横向溢出，1/1 通过。
- 视觉证据：三张同尺寸截图和 `docs/ui/evidence/after/all-detail-pages-comparison.png` 已复核；`design-qa.md` 未发现 P0/P1/P2/P3 问题，`final result: passed`。
- React 专项审查：共享组件使用命名导出、稳定 key、语义化 `section/nav/article` 和图标+文字状态；发现并修正无障碍中文标签编码问题。
- 首轮全量验收：后端、单测和构建通过；旧 E2E 仍按不带数量的“逐日汇总/24小时明细”精确文本查找而失败。已将测试契约改为匹配新数量标签，主流程单独复跑 1/1 通过。
- 最终 `make.cmd check`：退出码 0；Ruff、mypy、ESLint、TypeScript、Prettier 全部通过；后端 189/189、前端 74/74、Playwright 7/7；覆盖率 85.90%；生产构建转换 5567 个模块，23 个 JS Chunk 全部 ≤650 KiB。
- `make.cmd verify-production`：退出码 0；7 个服务、33 张表、迁移、强密钥策略、生产无夹具写入和 Docker 构建路径验证通过。Docker CLI 不可用，容器运行态未实启，完成的是等价 YAML/路径/安全静态校验。
- 安全边界：浏览器测试使用 `e2e.db`、开发认证旁路和空飞书凭据；趋势重算只写隔离数据库，未访问正式经营库，未执行真实同步或飞书群推送。
- 发布复核：功能提交 `588ee99` 已推送至 `ChenXL916/Shujufenxi_1/main`；Netlify 入口 `/assets/index-D4ioi0n9.js`、共享详情分包 `/assets/DetailScaffold-BLraFtfH.js`、三个页面分包和 `/assets/index-DY3U0702.css` 均返回 HTTP 200。
- 线上内容：共享分包含“详情状态/详情数值”，总览分包含“核心表现/明细数据”，趋势分包含 `LIVE DATA POINT`，预警分包含“经营对比/事实明细”，样式包含详情操作条、洞察网格和宽指标网格；公网 `/ready` 返回 HTTP 200、`status=ready`、`mode=feishu`，数据库与 Redis 均为 `ok`。

## 2026-07-23 阶段 36：运行目录迁移至 E 盘

- 迁移结果：正式运行目录已由 C 盘迁移到 `E:\直播间数据\codex_live_dashboard_pack`；38,426 个文件、2.670GB 的文件数量、相对路径、总大小和关键 SHA-256 全部匹配，目标 Git 对象库完整。
- 数据保护：迁移前在线备份和停服备份均保存于 `E:\直播间数据\migration_backups\20260723T093201Z`；`PRAGMA integrity_check=ok`，备份包含 2,384 条小时事实、2,029 条采集点和 8 个用户，配置副本哈希一致。
- 路径恢复：`.env.tunnel` 的 SQLite 绝对路径已改为 E 盘；Python 3.12.11 虚拟环境按锁文件重建，生产配置为 `APP_ENV=production`、`DEV_AUTH_BYPASS=false`，Redis `PING` 成功。
- 公网恢复：E 盘 API、本机 8000、原 Cloudflare 源站和 Netlify `/ready` 均为 HTTP 200、`ready / feishu`，数据库与 Redis 为 `ok`；保留原隧道地址，因此没有修改飞书 OAuth 回调或要求重新授权。
- 完整门禁：`make.cmd check` 退出 0；189/189 后端测试、74/74 前端单测、7/7 Playwright E2E 通过，覆盖率 85.90%，生产构建转换 5,567 个模块，23 个 JS Chunk 全部 ≤650 KiB。
- 生产验收：`make.cmd verify-production` 退出 0；验证 7 个服务、33 张表、迁移、生产强密钥、关闭开发旁路、无 fixture 写入和 Docker 构建路径。本机没有 Docker CLI，容器运行态为 YAML、路径和安全静态等价验收。
- 实时同步：E 盘实时循环首轮使用 `user_access_token` 同步四个实绩源 653、655、0、116 条和两个排班源 72、41 条，全部完成；小时事实稳定为 2,384 条。预警重试、旧预警、小时预警和趋势汇总均未产生推送，没有向飞书群发送测试消息。
- 在线业务：迁移后已有真实线上会话通过 Netlify 成功调用 `/auth/me`、飞书状态、筛选、主播汇总和主播时段明细，全部 HTTP 200；生产库完整性保持 `ok`，账号、角色和权限未变。
- 磁盘结果：C 盘可用空间由约 11.9GB 增至约 14.5GB；旧目录内容已全部迁出，仅留下被当前 Codex 会话占用的零文件、零字节空目录，关闭本任务后可删除。
- 已知边界：公网 API 仍通过本机 Cloudflare Quick Tunnel 提供服务；本次迁移保持现有地址和当前正常运行，但电脑关机或隧道退出后的自动恢复需要后续配置固定命名隧道或云服务器。

## 2026-07-24 阶段 37：曲线易点选、主播时均成交与快捷排序

### 功能与口径测试

- 曲线命中层：经营总览、小时时间线、当前/基线 ROI、消耗和附加指标的折线点均生成 `24×24px` 透明命中层；点击事件会还原为原始业务序列索引，详情数据未被辅助序列污染。
- 时均成交：验证 `时段整体成交金额（千川）÷ 有效小时` 使用 `Decimal` 精确计算；即使请求仅选择其他动态指标，响应仍固定返回 `hourly_average_amount`；无金额或零有效小时返回空值。
- 主播排序：验证“有效小时”“直播间数”“时均成交”及全部动态指标列均有升/降序按钮；数值升序、降序、空值末尾、当前方向高亮和稳定排序行为均通过。
- 定向结果：后端 `4 passed`；前端 3 个测试文件共 `10 passed`；TypeScript 通过。

### 全量质量门禁

- 命令：`make.cmd check`
- 结果：退出码 `0`。
- 静态检查：Ruff format/check、ESLint、mypy（64 个源文件）、TypeScript、Prettier 全部通过。
- 后端：`191/191 passed`，覆盖率 `85.93%`；仅保留 10 条 Starlette/Alembic 兼容性弃用警告。
- 前端：20 个测试文件、`76/76 passed`；存在 1 条 Ant Design StickyScrollBar 测试环境 `act(...)` 提示，不影响断言、构建或运行。
- 构建：Vite 转换 5,568 个模块，生成 23 个 JS Chunk，全部不超过 650 KiB。
- E2E：Chromium `7/7 passed`；主播分析场景同时验证固定“时均成交”列和升序快捷按钮。

### 视觉、生产与安全验收

- 视觉对照：1440×900 同视口完整页和聚焦区域前后对照均通过；新增排序控件与表头对齐，曲线视觉样式未改变；`design-qa.md` 为 `final result: passed`。
- 命令：`make.cmd verify-production`
- 结果：退出码 `0`；7 个服务、33 张表、迁移、强密钥策略、关闭开发旁路、生产无 fixture 写入和 Docker 构建路径均有效。
- Docker 边界：当前机器无 Docker CLI，容器运行态未实启；完成的是 Compose YAML、构建路径和安全策略的等价静态验证。
- 数据安全：测试使用 `e2e.db`、开发认证旁路和 Mock 飞书机器人；没有访问或改写正式经营数据，没有向真实飞书群发送测试预警。
- 上线备份：`backups/live_ops_stage37_20260724T032307Z.sqlite3`，73,572,352 字节，`PRAGMA integrity_check=ok`。
- 正式库只读口径核对：27/27 个主播汇总行满足 `hourly_average_amount == period_overall_amount / Decimal(valid_hours)`；未执行数据库写入、飞书同步或群推送。
- 发布提交：`d8158a1` 已推送至 `ChenXL916/Shujufenxi_1/main`；生产 API 重启后本机与 Netlify `/ready` 均为 HTTP 200、`ready / feishu`。
- 线上资产：入口 `/assets/index-NC4OXPFV.js`、主播分析 `/assets/AnalysisPage-Cpn6aB56.js`、时间线 `/assets/TimelinePage-Ct-gFM9I.js`、命中层 `/assets/chartHitTarget-BfBUoLGD.js` 均返回 HTTP 200；内容探针确认“时均成交”、`hourly_average_amount`、升序交互、24px 命中尺寸和 `pointer` 光标已上线。
