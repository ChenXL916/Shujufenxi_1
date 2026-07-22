# 运维手册

## 日常检查

- `/health`：Liveness，仅确认 API 进程可响应。
- `/ready`：Readiness，报告数据库、Redis、飞书/fixture 模式和机器人配置。
- 管理后台数据源：最后同步、最后成功、错误摘要。
- Celery：当前 10 个 Beat 任务（含主播趋势汇总）均使用 Redis NX/TTL 防重锁；`/ready` 的 Redis 状态必须为 `ok` 后才能启动 Worker/Beat。
- 预警中心：检查 pending/failed/skipped、重试次数和人工确认闭环。

## 同步与故障

```bash
make sync-fixture   # 幂等重放本地 fixture
make sync-feishu    # 真实凭据；无凭据自动走 fixture + Mock
docker compose logs -f --tail=200 api celery-worker celery-beat
```

429、网络超时和 5xx 会有限指数退避；401/403 说明应用权限或 Base 授权错误，不应盲目重试。原始记录保留 payload hash，重复同步计入 unchanged；无效计算行保留 raw 并排除经营聚合。

## 备份与恢复

`make backup`：PostgreSQL 使用 custom-format `pg_dump`，SQLite 开发库使用一致文件副本，默认输出到 `backups/`。

PostgreSQL 恢复示例：

```bash
pg_restore --clean --if-exists --no-owner --dbname "$DATABASE_URL" backups/live_ops_YYYYMMDDTHHMMSSZ.dump
alembic upgrade head
```

恢复后依次检查 `/ready`、21 张表、房间数、最新小时事实、预警事件，并运行 `make check`。

## 告警处置

1. 确认小时已结束且同步成功。
2. 核对最小消耗/订单/金额门槛、基准值和数据有效性。
3. 查看原始采集点与排班匹配。
4. 记录处理结果并确认事件；必要时重试飞书推送。
5. 数据源异常优先修复同步，不把缺失数据当经营异常。
