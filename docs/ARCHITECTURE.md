# 架构说明

## 系统边界

系统是前后端分离的内部应用：React/Vite/Ant Design/ECharts 提供中文驾驶舱；FastAPI 提供 `/api/v1` 与健康接口；PostgreSQL 保存源记录、事实、指标、权限、预警和审计；Redis 用于令牌/查询缓存和分布式锁；Celery Worker/Beat 执行同步、聚合、预警和重试；Nginx 统一代理。

## 数据流

```text
Excel fixture / Feishu Bitable
  -> SourceConfig + SyncRun
  -> RawSourceRecord (payload hash, 原文保留)
  -> 清洗与异常判定
  -> LivePoint / AnchorSchedule / StaffSchedule
  -> HourlyFact + HourlyMetric
  -> 查询、比较、透视、导出、预警
  -> Web UI / Mock 或真实 Feishu Bot
```

## 关键边界

- 路由只处理鉴权、参数和响应；清洗、聚合、比较、预警在 domain/service 层。
- 飞书密钥只在服务端环境变量或加密设置中出现；前端只接收掩码状态。
- 仓储查询必须传入用户可访问房间集合，导出和预警详情复用同一权限约束。
- 原始记录不物理删除；无效记录保留并标记，正常分析过滤。
- 测试默认 SQLite 做快速领域/接口验证；生产和迁移目标是 PostgreSQL JSONB/NUMERIC/TIMESTAMPTZ，PostgreSQL 集成测试由 Compose 运行。

## 聚合不变量

- 小时趋势使用源“时段”字段；多采集点时累计/快照取最后有效点。
- 跨小时金额、消耗和订单使用明确的 period 指标求和。
- ROI、成本、笔单价使用合计分子除以合计分母；分母为 0 返回空。
- 跨多日累计指标先按直播间/日取最后有效点，再按指标定义处理。
- 不推断无明确来源的计划场控，不制造分钟级时间戳。
