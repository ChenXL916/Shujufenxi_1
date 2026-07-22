# Better Stack 视觉语言启发的驾驶舱重构

更新日期：2026-07-18（Asia/Shanghai）

## 目标与边界

本任务是在现有“多直播间小时数据驾驶舱”上做增量视觉重构。应用仍是高信息密度的企业数据产品，不改为营销落地页，不创建第二套应用，不改现有路由、数据口径、API 业务逻辑、数据库、权限、飞书同步或预警计算。

只借鉴参考页面的视觉语言：午夜色主画布、精细表面层级、克制的紫蓝强调、低对比边框、清晰的数据排版、紧凑控制条和轻量交互。以下资产明确不复制：Better Stack Logo、品牌名称、营销标题与宣传文案、插画、产品截图、导航文案、客户 Logo、参考站 CSS 与任何下载的品牌素材。

## 审计证据

- 参考地址：`https://getdesign.md/design-md/betterstack?page=9`
- 参考页内部审计截图：`artifacts/redesign/reference-betterstack-page9.png`
- 参考页计算色板与可见文本：`artifacts/redesign/reference-betterstack-page9-audit.json`
- 改造前 fixture 总览：`artifacts/redesign/before/overview-fixture.png`
- 改造前 fixture 主播趋势：`artifacts/redesign/before/anchor-trends-fixture.png`
- 改造前前端基线：ESLint 通过、TypeScript 通过、12 个文件 / 34 个单测通过。

参考页实际表现为深黑主画布、近白正文、多个中性灰阶、低对比 1px 分隔线、紧凑顶部导航与大尺寸高对比标题；产品截图使用深色嵌套表面、紫蓝主操作和克制的边缘光。转译到驾驶舱时只保留这些抽象规律，删除营销首屏、CTA、客户 Logo 墙和大面积留白。

## 设计原则

1. **Midnight observability**：根背景、侧栏、卡片形成至少三层深色表面，禁止大面积纯黑卡片。
2. **数据优先**：页面内边距 24–32px，表格与图表保持高密度；标题下不留无业务价值的空白。
3. **强调克制**：紫色只用于主操作、活跃导航、焦点和关键曲线；绿/红/橙仅表达带文字或图标的业务状态。
4. **可读数字**：KPI 和表格启用 `tabular-nums`，金额、ROI 和时间保持对齐。
5. **局部滚动**：高密度表格的横向滚动限定在卡片内部，页面自身不得横向溢出。
6. **可访问交互**：键盘 Focus Ring 清晰；状态不只靠颜色；图标按钮有可访问名称；尊重 `prefers-reduced-motion`。
7. **性能克制**：不引入第二套 UI 框架、外部大字体、视频、粒子、3D 或全局高成本滤镜。

## Design Token

令牌的唯一运行时来源为 `apps/web/src/styles/global.css`，Ant Design 映射位于 `apps/web/src/theme/dashboardTheme.ts`，ECharts 映射位于 `apps/web/src/theme/chartTheme.ts`。

### 颜色

| Token | Value | Usage |
| --- | --- | --- |
| `--color-bg-root` | `#07070A` | 根画布 |
| `--color-bg-sidebar` | `#090A0F` | 侧栏 |
| `--color-bg-header` | `rgba(9, 10, 15, 0.88)` | 吸顶顶部栏 |
| `--color-surface-1` | `#0D0F14` | 主卡片 |
| `--color-surface-2` | `#12141B` | 表头与嵌套表面 |
| `--color-surface-3` | `#171A22` | 浮层与高层表面 |
| `--color-surface-hover` | `#1B1E28` | Hover/选中行 |
| `--color-border-subtle` | `#20232D` | 低对比分隔线 |
| `--color-border-default` | `#292D39` | 控件与卡片边框 |
| `--color-border-strong` | `#393E4E` | 强调边框 |
| `--color-text-primary` | `#F5F7FA` | 主文本 |
| `--color-text-secondary` | `#B2B7C5` | 次文本 |
| `--color-text-muted` | `#757B8C` | 标签/坐标轴 |
| `--color-text-disabled` | `#535866` | 禁用状态 |
| `--color-accent-primary` | `#6C5CE7` | 主操作/选中 |
| `--color-accent-hover` | `#7C6CF2` | 主操作 Hover |
| `--color-accent-light` | `#9A8BFF` | 焦点/关键曲线 |
| `--color-accent-soft` | `rgba(108, 92, 231, 0.14)` | 选中背景 |
| `--color-accent-cyan` | `#5DD9FF` | 辅助关键曲线 |
| `--color-positive` | `#38D996` | 上涨/达标 |
| `--color-negative` | `#FF6577` | 下跌/严重 |
| `--color-warning` | `#F7B955` | 目标/延迟 |
| `--color-info` | `#6EA8FE` | 信息状态 |

### 圆角、间距与阴影

- 圆角：`6 / 8 / 12 / 16 / 20px`
- 间距：`4 / 8 / 12 / 16 / 20 / 24 / 32 / 40px`
- 卡片阴影：`0 0 0 1px rgba(255,255,255,.035), 0 16px 48px rgba(0,0,0,.22)`
- 浮层阴影：`0 24px 72px rgba(0,0,0,.42)`
- 交互时长：`150–220ms`；减少动画模式下降为近零。

### 字体

- 中文正文：`Inter, "SF Pro Display", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif`
- 数据/时间：`"JetBrains Mono", "SFMono-Regular", Consolas, monospace`
- 页面标题：28–34px / 650–700
- KPI：30–42px / 650–750 / tabular nums
- 正文：13–14px；表格表头：11–12px。
- 不下载大型字体资源，使用现有系统字体回退。

## 实现架构

### 共享设计系统

- `theme/dashboardTheme.ts`：Ant Design 暗色算法与组件 Token。
- `theme/chartTheme.ts`：统一 ECharts 颜色、轴线、网格、Tooltip、Legend、DataZoom、K 线主题。
- `components/PageHeader.tsx`：统一页面标题、说明和操作区。
- `components/StatusBadge.tsx`：状态圆点 + 文本，避免只靠颜色。
- `components/DashboardCard.tsx`：统一图表/数据卡语义与 class。
- `styles/global.css`：CSS 变量、应用外壳、卡片、表格、表单、响应式与 Reduce Motion。

### 应用外壳

- 224px 展开侧栏、72px 折叠侧栏；移动端使用 Drawer。
- 导航分为分析、人员、监控、管理，保持所有现有 URL。
- 顶部栏吸顶，显示页面上下文、同步状态、最近更新时间、同步操作和当前角色。
- 主内容宽屏充分使用，1366 及以下降低内边距。

### 页面覆盖

现有页面全部保留，通过共享主题统一经营总览、小时趋势、数据对比、主播/场控/搭配分析、透视、预警中心和管理后台。主播上涨/下跌/样本不足保留原计算与权限，只改变状态卡、表格和移动卡视觉。

## 风险控制

- E2E 固定使用隔离 API `18000`、Web `4173` 和 `e2e.db`；请求只使用相对 `/api`，不得触碰真实 `8000` 服务或真实群。
- 图表只改呈现配置，不改数据序列与口径。
- 不更改 URL 筛选参数。
- 不在截图和报告中输出密钥；最终截图使用 fixture 数据。
- 运行服务加载最终代码时，先在候选端口验证模式和依赖，再替换现有进程。

## 验收矩阵

| Proof | Command / artifact | Status |
| --- | --- | --- |
| Frontend baseline | `npm run lint && npm run typecheck && npm run test:unit` | 通过：12 files / 34 tests |
| Unit | `npm run test:unit` | 待最终改动后 |
| TypeScript | `npm run typecheck` | 待最终改动后 |
| ESLint | `npm run lint` | 待最终改动后 |
| Prettier | `npm run format:check` | 待最终改动后 |
| Production build | `npm run build` | 待最终改动后 |
| Chunk gate | 构建产物单 JS chunk `< 1,000,000 bytes` | 待验证 |
| Playwright | `npm run test:e2e`（隔离服务） | 待最终改动后 |
| Full gate | `make.cmd check` | 待最终改动后 |
| Responsive | 390×844 / 1366×768 / 1440×900 / 1920×1080 | 待截图与 DOM 检查 |
| Accessibility | 键盘、名称、焦点、状态文本、axe/等价检查 | 待验证 |
| Runtime | 最终前端/API 就绪与浏览器回归 | 待验证 |

## 阶段状态

- [x] 阶段 1：参考页、现有应用、结构与测试基线审计
- [ ] 阶段 2：Design Token、Ant Design 和 ECharts 暗色主题
- [ ] 阶段 3：应用外壳、侧栏、顶部栏、移动导航、筛选栏
- [ ] 阶段 4：经营总览、KPI、24 小时图表、K 线、质量区域
- [ ] 阶段 5：分析、对比、透视和明细
- [ ] 阶段 6：预警中心、上涨/下跌榜和管理表单
- [ ] 阶段 7：响应式、无障碍与性能
- [ ] 阶段 8：全门禁、运行态、截图与最终交付
