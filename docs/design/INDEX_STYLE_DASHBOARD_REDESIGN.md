# Index 视觉语言启发的暖白 BI 驾驶舱重构

更新日期：2026-07-18（Asia/Shanghai）

## 1. 目标与边界

本任务在现有“多直播间小时数据驾驶舱”中进行增量 UI 重构，不创建第二套应用，不删除路由或功能，不改变 ROI、消耗、订单成本、转化率、业务 K 线、周期比较、T+1 完整率、预警、权限、同步、数据库或 API 业务口径。

最终方向为暖白色高密度企业 BI：暖白画布、白色卡片、黑色强标题、橙色当前周期、蓝色对比周期、细边框、轻阴影、大圆角和克制留白。上一版 Better Stack 深色视觉不再作为最终方案。

只转译抽象视觉语言，不复制 Index/Mora/getdesign.md 的 Logo、品牌名称、营销文案、客户 Logo、产品截图、插画、示例数据、导航文案、CTA、HTML 或 CSS。

## 2. 参考页面实际访问证据

- 目录 URL：`https://getdesign.md/design-md/index-app?page=10`
- 页面标题：`Index-style design system — getdesign.md`
- 目录说明将其归类为数据探索和 Dashboard 工具，适用于 BI SaaS。
- 目标截图直接资产：`https://cdn.getdesign.md/catalog/index-app/home.jpg`
- 目标截图尺寸：`3840 × 19021`
- 本地审计截图：`artifacts/index-redesign/reference-index-home.jpg`
- 像素量化与对比度：`artifacts/index-redesign/reference-index-audit.json`

> 主色来自缩小后的 JPEG 像素量化，不冒充源站 CSS Token。量化主色中 `#FFFFFF` 占 39.23%、`#FBFAF8` 占 26.29%、`#1F1E1C` 占 11.12%、`#F3F2F1` 占 5.14%，支持“暖白画布 + 白表面 + 近黑标题”的观察。

### 2.1 目标层与目录外壳区分

getdesign.md 自身是黑色目录外壳；本次目标是其中 3840px 宽的 Index 页面截图。目录站的黑色顶栏、粉色提示、橙色请求按钮和发布工具卡片不属于目标设计，不能转译到驾驶舱。

### 2.2 可直接转译

- 暖白/近白画布与白色数据表面。
- 近黑标题、灰阶正文、紧凑的数据排版。
- 橙色与浅蓝/蓝色图表系列，辅以紫、黄作为少量多系列色。
- 1px 低对比边框、14–22px 圆角、非常轻的环境阴影。
- 图表、表格和单值卡组合成高密度数据模块。
- 大区域留白转译为 16–32px 的模块节奏，不照搬营销页的大段空白。

### 2.3 必须适配或拒绝

- 巨型居中营销标题改为左对齐 28–34px 页面标题。
- CTA、客户 Logo 墙、营销分镜、产品截图、线路插画、深色宣传区和页脚全部拒绝复制。
- Index/Mora Logo、名称、口号、示例人员标签、客户名称和图表样本不得使用。
- 参考页偶发的深色营销卡不能成为应用主主题；业务状态仍使用带文字/图标的语义色。

## 3. 当前应用审计

### 3.1 当前结构

- React 19 + TypeScript strict + React Router。
- Ant Design 6，集中主题：`apps/web/src/theme/dashboardTheme.ts`。
- ECharts 6 按需注册，集中主题：`apps/web/src/theme/chartTheme.ts`。
- 共享外壳：`apps/web/src/App.tsx`。
- 共享筛选：`apps/web/src/components/FilterBar.tsx`。
- 共享标题、状态和 KPI：`PageHeader.tsx`、`StatusBadge.tsx`、`KpiCard.tsx`。
- URL 筛选状态：`apps/web/src/hooks/useDashboardFilters.ts`。
- 核心周期图：`features/hourly-comparison/*`。
- 响应式、卡片、表格和表单集中在 `apps/web/src/styles/global.css`。
- 页面按路由懒加载，构建使用 Vite manual chunks。

### 3.2 修改前问题与解决状态

1. [x] `dashboardTheme.ts` 已从 `darkAlgorithm` 切换为浅色算法，背景、容器、Drawer、Modal、Table、Menu 使用统一暖白语义。
2. [x] `global.css` 已移除 Midnight 深色覆盖效果；组件区视觉色值统一通过 Design Token 表达。
3. [x] `chartTheme.ts` 已切换为高对比橙蓝主色、白色 Tooltip、浅色 DataZoom 和可读轴标签。
4. [x] 固定表格列深色硬编码和深色图片导出背景已移除；导出画布为白色。
5. [x] 经营总览主图与摘要形成约 8/4 主区域，24 行明细和直播间表现继续全宽。
6. [x] 移动 Drawer、筛选折叠、表格局部滚动、键盘 KPI 和 Reduced Motion 均已纳入 Playwright 回归。

## 4. 修改前真实基线

基线时间：2026-07-18；命令在新任务开始前、当前深色代码上实际运行。

| Proof | Result |
| --- | --- |
| `make.cmd check` | 通过，退出码 0 |
| Ruff format/check | 92 files formatted；通过 |
| mypy | 56 source files；0 issue |
| Backend pytest | 136 passed；覆盖率 86.87% |
| ESLint | 通过，0 warning |
| TypeScript | 通过 |
| Prettier | 通过 |
| Frontend unit | 13 files / 39 tests 通过 |
| Production build | 5559 modules；7.68s |
| Playwright | 5/5 通过，隔离 API 18000、Web 4173、`e2e.db` |
| 最大 JS Chunk | `index-B0fNs6H9.js` 687.83kB / gzip 228.49kB |
| ECharts Chunk | 671.61kB / gzip 228.47kB |

修改前深色截图已复制至：`artifacts/index-redesign/before/`。其中包含 390×844、1366×768、1440×900、1920×1080 总览和主要分析/预警/管理页面。

## 5. 统一 Design Token

运行时唯一视觉来源为 `global.css` CSS 变量；Ant Design 与 ECharts 只映射这些语义角色。组件内不得新增主题色硬编码。

### 5.1 颜色

| Token | Value | Role |
| --- | --- | --- |
| `--color-bg-root` | `#F7F6F2` | 应用主画布 |
| `--color-bg-secondary` | `#F2F0EB` | 页面分区/侧栏辅助背景 |
| `--color-bg-soft` | `#FAF9F6` | 轻量嵌套区域 |
| `--color-bg-sidebar` | `#FBFAF7` | 左侧导航 |
| `--color-bg-header` | `rgb(255 255 255 / 90%)` | 吸顶顶部栏 |
| `--color-surface-primary` / `--color-surface-1` | `#FFFFFF` | 主卡片/表格 |
| `--color-surface-secondary` / `--color-surface-2` | `#F8F7F3` | 表头/工具栏 |
| `--color-surface-tertiary` / `--color-surface-3` | `#F3F1EC` | Hover/嵌套层 |
| `--color-surface-hover` | `#FAF8F4` | 行 Hover |
| `--color-border-subtle` | `#ECE8E1` | 卡片分隔线 |
| `--color-border-default` | `#E2DED6` | 卡片与内容默认分隔线 |
| `--color-border-strong` | `#D4CFC5` | 强调边框 |
| `--color-border-control` | `#8D8981` | 可交互控件边界；白底 3.48:1 |
| `--color-text-primary` | `#171716` | 标题/KPI |
| `--color-text-secondary` | `#5F5C56` | 正文，白底对比度 6.66:1 |
| `--color-text-muted` | `#706D67` | 元数据/坐标轴；白底 5.16:1 |
| `--color-text-disabled` | `#706D67` | 禁用/占位文字基础色；组件状态另提供非颜色提示 |
| `--color-accent-orange` | `#C44720` | 当前周期/选中/小号眉题；白底 4.92:1 |
| `--color-accent-orange-hover` | `#B83F1B` | 橙色 Hover/强调 |
| `--color-accent-orange-soft` | `color-mix(... 10%, transparent)` | 选中背景；浏览器契约禁止变量自引用 |
| `--color-accent-blue` | `#4565D4` | 对比周期/链接/信息；白底 5.17:1 |
| `--color-accent-blue-hover` | `#3652B8` | 蓝色 Hover/Focus |
| `--color-accent-blue-soft` | `rgb(69 101 212 / 10%)` | 信息背景 |
| `--color-accent-purple` | `#6656CE` | 多系列辅助色 |
| `--color-accent-yellow` | `#9B5F0E` | 多系列辅助/目标 |
| `--color-positive` | `#1E7A54` | 上涨/达标 |
| `--color-positive-soft` | `#EAF7F1` | 上涨背景 |
| `--color-negative` | `#B83C3C` | 下跌/严重 |
| `--color-negative-soft` | `#FCEEEE` | 下跌背景 |
| `--color-warning` | `#9B5F0E` | 延迟/不足 |
| `--color-warning-soft` | `#FFF5E6` | 警告背景 |
| `--color-info` | `#4565D4` | 信息状态 |
| `--color-info-soft` | `#EEF2FF` | 信息背景 |

### 5.2 圆角、阴影和间距

- `--radius-xs/sm/md/lg/xl`: `6 / 8 / 12 / 16 / 22px`。
- `--shadow-card`: `0 1px 2px rgb(35 31 24 / 3%), 0 8px 24px rgb(35 31 24 / 5%)`。
- `--shadow-card-hover`: `0 2px 4px rgb(35 31 24 / 4%), 0 12px 32px rgb(35 31 24 / 8%)`。
- `--shadow-elevated`: `0 20px 60px rgb(35 31 24 / 14%)`。
- 间距：`4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48px`。
- 交互：150–200ms；Reduce Motion 降为近零。

### 5.3 字体

- UI：`Inter, "SF Pro Display", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif`。
- 数据：现有系统等宽栈，不下载字体包。
- 页面标题 28–34px/700；模块标题 17–20px/650；正文 13–14px；表头 12px；KPI 30–42px/700。
- 金额、ROI、时间和表格数字统一 `tabular-nums`。

## 6. 布局改造

### 6.1 应用外壳

- 导航 224px，折叠 72px；暖白/白表面，右侧 1px 细边框。
- 选中菜单为淡橙背景 + 2px 橙色指示条；普通/hover 为中性灰阶。
- 顶部栏 64px、白色 90% + 单处 14px blur，保留同步、授权、通知与身份权限。
- 主区不限制为营销窄列；1920/1440/1366/移动分别使用 32/24/20/12–16px 内边距。

### 6.2 页面顺序

统一为：PageHeader → 全局筛选 → KPI/摘要 → 主图/主表 → 补充分析 → 明细/操作。避免标题与数据之间的无业务空白。

### 6.3 经营总览

- KPI：1440/1920/1366 四列，1024 两列，390 单列；两行 8 卡。
- 主区：24 小时 ROI/消耗卡 8 列，趋势/预警与质量摘要 4 列。
- 24 行小时明细保持全宽，不被 8/4 列压缩。
- 直播间表现保持全宽高密度表格。
- 主图桌面目标高度约 620–700px，避免旧 900px 的过度纵向占用。

## 7. 组件改造

- `App.tsx`：Menu 切换 light，暖白导航和顶部工具栏。
- `PageHeader`：黑色强标题、紧凑说明和右侧操作。
- `FilterBar`：白色紧凑控制条，桌面换行、移动折叠；保持 URL 寻址。
- `KpiCard`：白卡、统一高度、黑色数据、状态胶囊、橙色选中和键盘联动。
- `StatusBadge`：淡色语义背景 + 状态文字，不依赖颜色。
- `HourlyRoiSpendSection`：允许插入总览 4 列摘要；主图与摘要 8/4，明细全宽。
- `StatePanel`：暖灰 Skeleton，空态和局部错误重试。
- Drawer/Modal：白色浮层、细边框、轻阴影；移动详情全屏。

## 8. 图表主题

- 当前周期：橙 `#C44720` 实线。
- 对比周期：蓝 `#4565D4` 虚线。
- 多系列扩展：橙、蓝、紫、黄、绿、红，禁止回到紫色单主调。
- 坐标轴 `#DCD8D0`；标签 `#706D67`；网格 `#EEEAE3`。
- Tooltip 白底、黑字、1px 边框、12px 圆角和 elevated shadow。
- ROI 目标使用可区分的黄褐/深灰虚线，不与当前/对比同色。
- K 线正向绿、负向红；消耗 K 线使用蓝/橙，不把“消耗上涨”自动编码为绿色。
- 图片导出背景改为白色。
- 保留 null、不连接缺失、双 Y 轴、数据缩放、十字准星、图例、全屏、导出和 ARIA 描述。

## 9. 表格与表单

- 表头 `surface-secondary`，12px muted；行高 48–52px；细分隔线；Hover 暖灰。
- 固定列背景白色；数字右对齐；null 使用“—”。
- 宽表格只允许容器横向滚动；页面必须满足 `scrollWidth === clientWidth`。
- 表单输入白色/暖灰背景，Focus 使用蓝色高对比 Ring。
- 主操作优先近黑按钮，橙色只作选择/数据强调；危险操作红色分离。

## 10. 响应式策略

| Viewport | Strategy |
| --- | --- |
| 1920×1080 | 32px 内边距；KPI 四列；主图 8/4；榜单双列；高密度表格 |
| 1440×900 | 24px 内边距；KPI 四列；主图 8/4；表格局部滚动 |
| 1366×768 | 20px 内边距；KPI 四列或安全两列；筛选换行；无页面溢出 |
| 390×844 | 12px；导航 Drawer；KPI/图表/摘要单列；筛选折叠；详情 Drawer 全屏；周期横向滚动 |

所有尺寸断言 `document.documentElement.scrollWidth === clientWidth`。Drawer 关闭后隐藏导航不在 Tab 序列；打开截图等待动画几何稳定。

## 11. 无障碍

- 正文、muted、轴标签和数据色板在暖白/白色表面均 ≥ 4.5:1；可交互控件边界 ≥ 3:1。
- 状态同时有文字、箭头/图标和颜色。
- KPI Enter/Space 激活并显示 `aria-pressed`。
- 图标按钮有 `aria-label`；移动按钮至少 44×44px。
- Focus Ring 可见；Drawer/Modal 保持 Ant Design 焦点锁和 Esc 关闭。
- 图表有 ARIA 描述，表格/明细是 Tooltip 之外的数据入口。
- `prefers-reduced-motion` 关闭非必要动画。

## 12. 性能策略

- 不新增 UI 框架、图片背景、视频、3D、外部字体或高成本全局滤镜。
- 继续路由懒加载、ECharts 按需注册和 manual chunks。
- `npm run build` 内置硬门禁：全部 JS Chunk `<= 650 KiB`，超过即退出非零。
- 最终记录最大 Chunk 原始/gzip、构建时间、生产 Preview 三次性能中位数、资源数与传输量。

## 13. 测试与视觉验收

### 自动门禁

- `npm run lint`
- `npm run typecheck`
- `npm run format:check`
- `npm run test:unit`
- `npm run build`
- `npm run test:e2e`
- `npm run audit:performance`（生产 Preview）
- `make.cmd check`

### 重点浏览器链路

暖白主题、左侧导航、7 天周期、直播间筛选、ROI KPI 联动、折线/柱状/K线、ROI 目标线、小时详情、上涨/下跌榜、预警中心、主播分析、透视、管理页、导出、移动导航、键盘和页面级无横向溢出。

### 截图矩阵

- 总览：390×844、1366×768、1440×900、1920×1080。
- 1440×900 与 1920×1080：小时趋势、主播分析、预警中心、上涨/下跌、透视、系统设置及实际存在的主要管理页面。
- 输出根目录：`artifacts/index-redesign/after/`。
- 截图生成后必须用联系表和关键原图进行像素审查，不能只证明文件存在。

## 14. 实施进度

- [x] 阶段 1：访问参考页、保存直接资产、量化色板、审计当前结构、记录全量基线和 before 截图
- [x] 阶段 1：创建本实施文档
- [x] 阶段 2：暖白 CSS/Ant Design/ECharts Token
- [x] 阶段 3：外壳、导航、顶部栏、筛选、移动 Drawer
- [x] 阶段 4：总览 KPI、8/4 主区、质量/预警摘要、直播间表格
- [x] 阶段 5：分析、对比、主播/场控、搭配、透视
- [x] 阶段 6：预警、榜单、管理表单、Drawer/Modal
- [x] 阶段 7：响应式、键盘、Reduced Motion、横向溢出
- [x] 阶段 8：全门禁、生产构建、Chunk、性能、截图与人工视觉验收

## 15. 最终验收结果

- `make.cmd check`：退出 0；136 个后端测试、13 个前端文件/41 个单测、6 项 Playwright 全部通过；后端覆盖率 86.87%。
- 生产构建：5559 modules；22 个 JS Chunk 全部不超过 650 KiB，无循环输出 Chunk 警告。最大 Chunk 为 AntD 535.55 KiB / gzip 164.03 KiB；ECharts 为 464.61 KiB / gzip 162.88 KiB。
- 最终 `dist` 运行探针：经营总览、小时趋势、AntD Select Portal 和 1920px 管理表单均业务就绪；page error、失败资源、console error、HTTP 4xx/5xx 均为 0；系统设置凭据表单实测 1120px，页面无横向溢出。
- 生产性能三次中位数：业务就绪 990ms、FCP 156ms、LCP 612ms、CLS 0、阻塞时间 86ms、24 个资源、807502 bytes；全部阈值通过。证据：`artifacts/index-redesign/after/performance-production.json`。
- 最新截图：37 张，覆盖 390×844、1366×768、1440×900、1920×1080；清单使用关键源码 SHA-256 绑定，见 `artifacts/index-redesign/after/screenshot-manifest.json`。
- 已重新生成并检查 `contact-sheet-top.png`、`contact-sheet-full.png` 及移动首屏、1440 总览长页、1920 管理设置原图；未发现 P0/P1 阻断、深色残留、页面级横向溢出、重叠或裁切。空数据页留白来自 fixture 空态。
- 已通过最终生产 `dist` 的真实“导出图片”动作生成 `chart-export-final.png`（2038×1360、全像素不透明、SHA-256 `5692a9c1…a3aa987`）；图例与 Toolbox 分行，DataZoom 完整位于画布内，未发现 P0/P1/P2。
