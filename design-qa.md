# 阶段 42 设计 QA：预警卡片、指标配置与主播时段明细

## 对照范围

- 指标配置参考：
  `C:\Users\Administrator\AppData\Roaming\LarkShell\sdk_storage\5b30d524477872f0871d7beaa47606a7\resources\images\img_v3_02140_0e412da2-ac36-41b5-ba88-e8065aa2428g.jpg`
- 主播时段明细参考：
  `C:\Users\Administrator\AppData\Roaming\LarkShell\sdk_storage\5b30d524477872f0871d7beaa47606a7\resources\images\img_v3_02140_ff1b2bea-92f0-4544-9978-a9049448b5ag.jpg`
- 当前指标配置：
  `artifacts/stage42/anchor-metric-configurator.png`
- 当前全屏明细：
  `artifacts/stage42/anchor-hour-detail-fullscreen.png`
- 同屏对照：
  `artifacts/stage42/metric-reference-vs-implementation.png`
  与 `artifacts/stage42/detail-reference-vs-implementation.png`

## 视觉检查

- 字体与层级：沿用全站暖白驾驶舱字体、标题字重和中文标签；弹窗以“配置指标—已选摘要—业务分组—操作区”形成稳定层级。
- 间距与布局：桌面端指标按业务组分为双栏卡片，底部操作固定；全屏明细保留标题、数据量、下载与退出入口，表格使用剩余空间并允许横向滚动。
- 颜色与状态：选中指标使用现有信息蓝和极浅蓝背景；主操作继续使用全站黑色按钮，未引入参考图的深色主题，避免破坏现有品牌一致性。
- 图标与资产：设置、搜索、恢复、下载、进入全屏和退出全屏均使用 Ant Design 图标，并补齐中文无障碍名称。
- 文案与数据：指标名称、口径、筛选条件、表格值和分页来自现有接口；下载接口复用当前日期、直播间、主播、场控、小时与已选指标，不改写业务数据。

## 动画与交互检查

- 指标触发器展示已选数量和前两个指标，点击后打开分组弹窗；支持搜索、勾选、恢复默认、取消与应用。
- 指标至少保留一项；应用后主播汇总和时段明细同时刷新，URL 指标参数保持可恢复。
- 下载按钮仅在存在数据时可用，成功后给出反馈，实际下载文件为 XLSX。
- 全屏状态提供明确的“退出全屏”按钮、关闭按钮和 Escape 关闭路径；表格排序、分页和横向滚动保持可用。
- 1440×900 Chromium 端到端测试确认弹窗、下载和全屏交互均可完成。

## 飞书预警卡片检查

- 推送内容从单段长 Markdown 改为字段区、主播分组、判断与建议、分隔线、时间注释和操作按钮。
- 每位主播固定四个核心字段：当前/基准 ROI、当前/基准消耗、ROI 目标、目标状态；下跌时段和建议另起区块。
- 本轮未向真实群发送额外验收消息，避免测试噪音；卡片结构由单元测试校验，下一次真实触发或人工发送将使用新排版。

## 测试证据

- `make.cmd check`：Ruff、mypy、ESLint、TypeScript、Prettier、201 个后端测试、82 个前端测试、23 个生产 JS Chunk 和 8 个 Chromium E2E 全部通过。
- 后端覆盖率 85.85%，满足 85% 门槛。
- 新增 E2E 真实请求 `/api/v1/analytics/anchors/hours/export` 并验证 `.xlsx` 文件名。

## 最终结果

final result: passed
