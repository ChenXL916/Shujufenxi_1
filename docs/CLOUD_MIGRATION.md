# Sites 与云端后端/数据库迁移手册

## 最终拓扑

```text
浏览器
  └─ HTTPS → OpenAI Sites（现有 React/Vite 前端）
               ├─ /、/overview、/anchors… → Sites 静态资源 + SPA 回退
               └─ /api、/auth、/health、/ready → Sites 同源 Worker
                                                    └─ HTTPS + 网关密钥
                                                       → Caddy
                                                          → FastAPI
                                                             ├─ PostgreSQL
                                                             └─ Redis
                                                                ├─ Celery Worker
                                                                └─ Celery Beat
```

网页仍然只访问一个 Sites HTTPS 地址。网页登录 Cookie、飞书 OAuth state、CSRF、权限、导出和详情跳转保持同源；数据库、Redis 和飞书密钥不进入前端或 Sites 构建产物。

当前所有者私有 Sites 并行入口为 `https://jishi-live-ops-dashboard.chenclya.chatgpt.site`。它暂时代理现有正式后端用于并行验证；目标云 API、PostgreSQL 和 Redis 验收通过前，不替换现有共享入口。

## 云服务器最低准备

- Linux x86_64 云服务器，建议至少 2 vCPU、4 GB 内存、80 GB SSD；安装 Docker Engine 与 Compose Plugin。
- 一个指向服务器公网 IP 的 API 子域名，开放 TCP 80/443；PostgreSQL 5432 和 Redis 6379 不开放公网。
- 可使用 SSH 和 `sudo` 的部署账号。项目放在 `/opt/live-ops/current`，快照放在 `/opt/live-ops/migration`，备份放在 `/opt/live-ops/backups`。
- 云厂商、服务器 IP/域名和 SSH 授权属于外部资源；缺少这些信息时可以完成代码、Sites 私有版本和迁移快照，但不能声称云后端已经上线。

## 1. 保持旧系统运行并生成一致性快照

在 E 盘仓库执行，不停止当前 API、网关或实时同步：

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
& .\apps\api\.venv\Scripts\python.exe `
  .\infra\scripts\prepare_cloud_migration.py `
  --env-file .\.env.tunnel `
  --output-dir ".\backups\cloud-migration-$stamp"
```

脚本通过 SQLite Online Backup API 读取 WAL 中已提交记录，生成 `source.sqlite3` 和 `source.manifest.json`，并验证 `PRAGMA integrity_check=ok` 与 SHA-256。它不读取或输出飞书 Secret、用户密码明文或机器人凭证。

## 2. 准备云端环境

1. 把仓库发布包、`source.sqlite3` 和本地创建的 `.env.cloud` 上传到服务器；不要上传 `.env.tunnel`。
2. 从 `.env.cloud.example` 创建 `.env.cloud`，生成不同的强随机 `POSTGRES_PASSWORD`、`JWT_SECRET`、`FIELD_ENCRYPTION_KEY` 和 `SITES_GATEWAY_TOKEN`。
3. `APP_BASE_URL`、`API_BASE_URL`、`FEISHU_REDIRECT_URI` 和 `CORS_ORIGINS` 使用最终 Sites HTTPS 地址；`CLOUD_API_DOMAIN` 使用 API 子域名。
4. 把飞书 App ID/Secret、两份 Base Token/Table/View、机器人和群配置仅写入服务器 `.env.cloud`。
5. 在飞书开放平台增加最终 Sites 回调：`https://<Sites 域名>/auth/feishu/callback`。旧回调保留到切换完成。

## 3. 启动并迁移

```bash
cd /opt/live-ops/current
install -m 0600 /secure/upload/.env.cloud .env.cloud
install -m 0400 /secure/upload/source.sqlite3 /opt/live-ops/migration/source.sqlite3
./infra/scripts/deploy_cloud_backend.sh ./.env.cloud
```

部署脚本会依次完成：

1. 校验必填环境变量和 Compose；
2. 构建 API 镜像；
3. 启动 PostgreSQL/Redis 并执行 Alembic；
4. 在空目标库中导入 SQLite；
5. 生成 `/opt/live-ops/migration/manifest.json`，核对每表行数和主键摘要；
6. 启动 API、Worker、Beat 和 Caddy；
7. 等待公网 `/ready`。

迁移清单已存在时脚本拒绝自动覆盖；目标库非空时迁移器默认拒绝写入。生产启动命令不执行 demo seed 或 fixture 导入。

## 4. 连接 Sites

Sites 运行时仅配置两个变量：

- `BACKEND_ORIGIN=https://<API 子域名>`
- `BACKEND_GATEWAY_TOKEN=<与服务器 SITES_GATEWAY_TOKEN 相同的强随机值>`（标记为 secret）

变量更新后必须保存并部署一个新的 Sites 版本。Caddy 对 `/health`、`/ready` 以外的直连请求返回 403；正常 API 请求必须从 Sites Worker 携带密钥进入。

## 5. 切换前验收

```bash
python infra/scripts/verify_cloud_backend.py \
  --site-origin "https://<Sites 域名>" \
  --backend-origin "https://<API 子域名>" \
  --manifest "/opt/live-ops/migration/manifest.json"
```

然后按角色验证：

- 开发者、管理员、运营负责人、直播主管、项目 PM 的直播间范围；
- 网页账号登录、长期会话、退出、改密、创建/删除用户；
- 飞书登录与回调；
- 总览、小时趋势、数据对比、主播/场控分析、排班透视、详情、全屏和 CSV/XLSX/图片下载；
- 手动飞书同步、自动同步、Celery Worker/Beat、预警生成、去重、重试和群卡片链接；
- `/health=200`、`/ready=200`、未登录 `/auth/me=401`、直连云 API 业务路径 `403`；
- 迁移清单源/目标逐表行数一致，主键摘要一致。

生产验收不额外发送测试群消息；使用已有预警记录核对卡片，或在独立 Mock 群完成推送测试。

## 6. 切换与回滚

1. 选择低峰期，暂停旧机实时同步，记录最后成功同步时间。
2. 再生成一次最终在线快照；清空尚未承载正式流量的云目标库后重新迁移并核对清单。
3. 在云端执行一次真实同步，确认最后成功时间不早于旧机。
4. 把共享入口切换到 Sites，并观察至少一个完整同步/预警周期。
5. 验收通过后再停用旧机 Gateway/Realtime-Sync；旧 SQLite 和最终快照只读保留。

若 Sites、云 API、数据核对或后台任务任一失败：立即恢复原共享入口并重启旧机任务。数据库迁移默认只前滚；不得为回滚网页而自动删除或反向迁移 PostgreSQL。
