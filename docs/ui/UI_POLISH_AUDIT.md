# UI 排版与交互专项审计

> 项目：多直播间小时数据驾驶舱<br>
> 审计基线：当前运行中的 Vite `http://127.0.0.1:5173` + 开发 API `http://127.0.0.1:8000`<br>
> 采集时间：2026-07-21（Asia/Shanghai）<br>
> 任务边界：只修前端排版、响应式、图标、文本、Tooltip、动画与可访问性；不改业务计算、权限、飞书同步、数据库、API口径或路由语义。<br>
> 最终状态：专项完成；30项审计问题均已修复并由最终源码的静态、构建、浏览器和证据门禁验证。

## 方法与证据

- 读取了 `AGENTS.md`、`README.md`、`MASTER_PROMPT.md`、`docs/EXEC_PLAN.md`、`docs/PROGRESS.md`、阶段17暖白视觉设计文档、Ant Design主题、ECharts主题、全局CSS、应用外壳、公共组件、页面、前端单测和Playwright测试。
- 对16个现有主要路由在6个视口执行只读浏览器审计：`390×844`、`768×1024`、`1024×768`、`1366×768`、`1440×900`、`1920×1080`。
- 共生成96张修改前全页截图；导航错误0、控制台错误0、失败请求0、页面级横向溢出0。
- DOM候选扫描最初报告194个“裁切”候选，其中标题/KPI大量只是字体行盒比`clientHeight`多2px，并没有视觉裁切，已排除，未虚增Bug数量。
- 134个无名称图标按钮候选均定位为第三方Ant Pagination上一页/下一页（124次）及Tabs更多按钮（10次），属于真实可访问名称缺口。
- before总清单：[`evidence/before/metrics.json`](evidence/before/metrics.json)
- before截图目录：[`evidence/before/`](evidence/before/)
- after总清单：[`evidence/after/metrics.json`](evidence/after/metrics.json)
- after截图目录：[`evidence/after/`](evidence/after/)
- 只读交互验收：[`evidence/after/interactions.json`](evidence/after/interactions.json)
- 移动Drawer录屏：[`mobile-drawers.webm`](evidence/after/motion/mobile-drawers.webm)
- 侧栏与图表Resize录屏：[`sidebar-collapse.webm`](evidence/after/motion/sidebar-collapse.webm)

## 最终结果

最终证据绑定 Chrome `150.0.7871.125`、Node `v24.14.0`，并在 `metrics.json` 中保存关键源码及 `package-lock.json` 的 SHA-256。

| 门禁 | 结果 |
|---|---:|
| 视口 | 6 |
| 页面/状态 | 16 |
| after全页截图 | 96 |
| 导航错误 | 0 |
| 页面级横向溢出 | 0 |
| 真实文字裁切 | 0 |
| 图标错位 | 0 |
| 无名称图标按钮 | 0 |
| 移动端小于44px触控目标 | 0 |
| Console错误 | 0 |
| 失败请求 | 0 |
| 被安全策略阻断的危险请求 | 0 |

文字检测使用 DOM Range 测量真实文字行宽，排除了 Ant 固定列 `::after` 阴影造成的恒定30px `scrollWidth`伪差；最后4个真实多选标签裁切通过桌面指标选择器跨两列解决，最终重新采集为0。

只读交互验收全部通过，覆盖移动导航、筛选Drawer、Timeline键盘详情入口、Escape关闭、焦点恢复、44px命中区、KPI完整值、图表视口边界、Comparison局部横滚、侧栏折叠、ECharts Resize和Reduce Motion。所有非GET、外网请求及扫描/导出/重算/发送类端点均由脚本硬阻断。

### 最终源码门禁

| 门禁 | 结果 |
|---|---:|
| Vitest | 17个文件，56/56通过，无未处理错误 |
| TypeScript | `tsc -b --pretty false`通过 |
| ESLint | `eslint . --max-warnings=0`通过 |
| Prettier | 全部文件通过 |
| Vite生产构建 | 5,564个模块，构建通过 |
| Chunk审计 | 22个JavaScript Chunk全部≤650KiB |
| 最大Chunk | Ant Design 535.55KiB |

### 代表性前后对照

| 场景 | Before | After |
|---|---|---|
| 390×844 经营总览 | [`before`](evidence/before/390x844/overview.png) | [`after`](evidence/after/390x844/overview.png) |
| 390×844 小时趋势 | [`before`](evidence/before/390x844/timeline.png) | [`after`](evidence/after/390x844/timeline.png) |
| 1024×768 预警中心 | [`before`](evidence/before/1024x768/alerts-rise.png) | [`after`](evidence/after/1024x768/alerts-rise.png) |
| 1440×900 数据对比 | [`before`](evidence/before/1440x900/comparison.png) | [`after`](evidence/after/1440x900/comparison.png) |
| 1920×1080 用户与权限 | [`before`](evidence/before/1920x1080/admin-users.png) | [`after`](evidence/after/1920x1080/admin-users.png) |

## 审计表

| 编号 | 页面 | 组件 | 问题类型 | 分辨率 | 严重程度 | 截图 | 修复状态 |
|---|---|---|---|---|---|---|---|
| UI-001 | 预警中心、小时趋势、数据对比 | PageHeader | text-clipping / mobile-layout | 1024×768 | P1 | [`alerts-rise`](evidence/before/1024x768/alerts-rise.png) | 已修复 |
| UI-002 | 经营总览 | KPI Grid | mobile-layout / text-clipping | 390×844 | P1 | [`overview`](evidence/before/390x844/overview.png) | 已修复 |
| UI-003 | 经营总览 | KPI Card | missing-tooltip | 全部 | P2 | [`overview`](evidence/before/390x844/overview.png) | 已修复 |
| UI-004 | 小时趋势、经营总览 | ECharts legend/toolbox | chart-toolbar-overflow | 390×844 | P1 | [`timeline`](evidence/before/390x844/timeline.png) | 已修复 |
| UI-005 | 全部分析页 | FilterBar | mobile-layout | 390×844、768×1024 | P1 | [`overview`](evidence/before/390x844/overview.png) | 已修复 |
| UI-006 | 经营总览 | 小时模块多选 | inconsistent-height / overflow | 1920×1080 | P1 | [`overview`](evidence/before/1920x1080/overview.png) | 已修复 |
| UI-007 | 分析/管理/预警页 | Pagination | accessibility | 全部 | P1 | [`admin-users`](evidence/before/390x844/admin-users.png) | 已修复 |
| UI-008 | 分析/管理/预警页 | Pagination | accessibility / mobile-layout | 390×844、768×1024 | P2 | [`admin-users`](evidence/before/390x844/admin-users.png) | 已修复 |
| UI-009 | 全部页面 | 顶部预警图标按钮 | accessibility / inconsistent-height | 768×1024 | P2 | [`anchors`](evidence/before/768x1024/anchors.png) | 已修复 |
| UI-010 | 含日期筛选页面 | DatePicker清除按钮 | accessibility | 390×844、768×1024 | P2 | [`overview`](evidence/before/390x844/overview.png) | 已修复 |
| UI-011 | 管理后台、预警中心 | Tabs更多按钮 | accessibility / missing-tooltip | 390×844 | P1 | [`admin-users`](evidence/before/390x844/admin-users.png) | 已修复 |
| UI-012 | 全部页面 | Card Header | text-clipping / inconsistent-height | 全部 | P1 | [`timeline`](evidence/before/390x844/timeline.png) | 已修复 |
| UI-013 | 分析、透视、预警、管理 | Table Header | text-clipping / missing-tooltip | 全部 | P1 | [`pivot`](evidence/before/390x844/pivot.png) | 已修复 |
| UI-014 | 分析、预警、管理 | Table Cell | text-clipping / missing-tooltip | 中小屏 | P2 | [`alerts-rise`](evidence/before/1024x768/alerts-rise.png) | 已修复 |
| UI-015 | 全部页面 | Icon system | icon-misalignment / inconsistent-height | 全部 | P2 | [`contact`](evidence/before/contact-top-1440x900.jpg) | 已修复 |
| UI-016 | 全部页面 | Motion tokens | stiff-animation | 全部 | P1 | 源码审计 | 已修复 |
| UI-017 | Dropdown/Tooltip/Popover | Overlay motion/layout | stiff-animation / overflow | 全部 | P2 | 源码审计 | 已修复 |
| UI-018 | 所有图表页 | ECharts wrapper | layout-shift | 全部 | P1 | 源码审计 | 已修复 |
| UI-019 | 所有图表页 | Reduced motion | accessibility | 全部 | P2 | 源码审计 | 已修复 |
| UI-020 | 经营总览 | KPI定位滚动 | accessibility / stiff-animation | 全部 | P2 | 源码审计 | 已修复 |
| UI-021 | 小时趋势/预警/详情 | Drawer | mobile-layout / overflow | 390×844、768×1024 | P1 | 源码审计 | 已修复 |
| UI-022 | 小时模块/管理/预警 | Modal | overflow / mobile-layout | 中小屏 | P1 | 源码审计 | 已修复 |
| UI-023 | 图表和长文本 | Tooltip | overflow / mobile-layout | 中小屏 | P1 | [`timeline`](evidence/before/390x844/timeline.png) | 已修复 |
| UI-024 | 经营总览、小时趋势 | Loading/Empty/Error | layout-shift / inconsistent-height | 全部 | P1 | 源码审计 | 已修复 |
| UI-025 | 桌面/移动导航 | 导航图标 | inconsistent-height | 全部 | P2 | [`contact`](evidence/before/contact-top-1024x768.jpg) | 已修复 |
| UI-026 | 全部页面 | Filter controls | inconsistent-spacing / overflow | 1024×768、1366×768 | P1 | [`alerts-rise`](evidence/before/1024x768/alerts-rise.png) | 已修复 |
| UI-027 | 全部页面 | Multi Select tags | overflow / inconsistent-height | 全部 | P1 | [`overview`](evidence/before/1920x1080/overview.png) | 已修复 |
| UI-028 | 超宽屏页面 | App content | inconsistent-spacing | 1920×1080 | P2 | [`overview`](evidence/before/1920x1080/overview.png) | 已修复 |
| UI-029 | 经营总览/分析/对比/透视 | 数据刷新 | layout-shift / stiff-animation | 全部 | P2 | 源码审计 | 已修复 |
| UI-030 | 管理后台 | 两级Tabs | mobile-layout / missing-tooltip | 390×844 | P1 | [`admin-users`](evidence/before/390x844/admin-users.png) | 已修复 |

## 已确认的正向基线

- 所有6个视口均没有页面级横向滚动；宽表由Ant Table内部横向滚动承载。
- 390px页面标题目前视觉上完整，未使用省略号。
- 390px预警榜使用移动卡片而不是把2300px桌面表格硬塞入视口。
- 图标相对父按钮的几何中心偏差没有超过1.5px；本轮主要是统一尺寸、容器和触控区，而不是用负margin逐个校正。
- 当前暖白画布、白卡、橙蓝数据语义和侧栏固定行为保留。

## 修复原则

1. 优先修共享组件与Token，再处理页面例外。
2. 不使用`transition: all`、大量负margin或普通布局绝对定位。
3. 页面标题完整显示；长表头允许两行并提供完整提示；姓名/直播间受控省略并可查看完整值；数字不换行且右对齐。
4. 移动端使用稳定单列/抽屉策略；宽表仅在自身容器滚动。
5. 所有交互动效使用统一Motion Token并支持`prefers-reduced-motion`。
6. 每项修复必须由单测、Playwright或after DOM指标验证；不通过降低原有业务断言换取绿灯。
