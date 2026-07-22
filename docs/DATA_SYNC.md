# 数据同步说明

## 路径

- 真实飞书：`FeishuBitableClient` 获取 tenant token，以 500 条分页读取 Table/Field/Record；`scripts/sync_feishu.py` 将 API record 转为统一 `FixtureRecord` 后进入同一清洗管道。
- 无凭据：`make sync-feishu` 自动调用两份 Excel fixture，并将外部接口标记为 `fixture_mock`。
- Celery Beat：直播实绩 5 分钟、排班 30 分钟；另有构建小时事实、预警评估、主播趋势汇总、失败推送重试、健康检查、清理、日报汇总和排班重算，当前共 10 个任务，均使用 Redis NX/TTL 锁。

## 幂等与审计

`source_config_id + source_record_id` 唯一，规范化 JSON 计算 SHA-256。首次为 created，内容改变为 updated，相同为 unchanged。每次同步写入 `sync_runs` 读取/新增/更新/未变化/无效数量；raw payload 永久保留，源删除只标记 `is_deleted`。

无效行（计算错误、`0:00-0:00`、缺失时间）保留 raw 并排除聚合。主播小时排班和人员日排班在导入时宽转长，排班年份由配置决定。同步完成后重建 `hourly_facts/hourly_metrics`，实绩优先使用小时内最后有效真实采集点；不会虚构分钟点。

## 手动命令

```bash
make sync-fixture
make sync-feishu
```

重复执行的验收结果：689 条记录全部计为 unchanged，小时事实数量保持稳定。
