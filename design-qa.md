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

# 阶段 44 设计 QA：全站统一配置指标

## 对照范围

- 交互参考：`artifacts/stage42/anchor-metric-configurator.png`
- 小时趋势桌面实现：`artifacts/stage44/timeline-metric-configurator-desktop.png`
- 经营总览桌面实现：`artifacts/stage44/overview-hourly-metric-configurator-desktop.png`
- 小时趋势移动实现：`artifacts/stage44/timeline-metric-configurator-mobile.png`
- 同屏对照：`artifacts/stage44/metric-config-reference-vs-implementation.png`
- 视口：桌面 1440 × 900、设备像素比 1；移动 390 × 844、设备像素比 1。

## 视觉与版式复核

- 字体、标题字重、暖白背景、浅灰分隔、信息蓝选中态和黑色主按钮均复用现有驾驶舱设计系统；没有引入新的色板或近似图标。
- 桌面弹窗使用稳定的标题、说明、已选摘要、搜索、双栏业务分组和固定操作区；相较旧下拉，指标名称、口径和选择状态不再挤压在窄浮层中。
- 经营总览复用相同布局，同时在已选说明中明确“固定显示、最多 4 个”；锁定指标仍有选中态但不可取消。
- 移动端切换单栏，弹窗保留安全边距、完整标题、搜索、已选摘要和固定底部操作；未出现横向溢出或控件出屏。
- 同屏对照确认实现保持阶段 42 的分组语言，并消除参考截图中动画中间帧的透明和缩放状态；最终证据均在弹窗稳定后截取。

## 动画、交互与可访问性

- 指标入口在元数据就绪前禁用，避免空状态闪烁；弹窗完成过渡后再允许截图和操作，并遵守 Ant Design 既有动画。
- 搜索、复选框、恢复默认、取消、应用、Escape 关闭和移动端更多筛选路径均可操作；应用后 URL 与 API 查询同步更新。
- 最大数量会禁用剩余未选项；固定核心指标带“固定”说明且不可取消，不依赖颜色单独表达约束。
- Chromium E2E 覆盖五个页面、经营总览和移动端，页面错误与控制台错误均为 0。

## 比较记录

- 首轮截图捕获到弹窗动画中间帧，且指标元数据尚未返回时摘要短暂显示 0；归类为 P2。
- 修复方式：入口在指标就绪前禁用、摘要使用页面默认指标回退，并在动画完成后采集证据。
- 复验结果：桌面与移动端布局稳定，默认数量正确，无 P0、P1 或 P2 遗留问题。

## 最终结果

final result: passed
