# 部署文档

## 拓扑

Compose 固定包含 7 个服务：PostgreSQL、Redis、API、Celery Worker、Celery Beat、Web、反向代理。只有反向代理暴露 `8080`；数据库和 Redis 不对公网开放。

## 生产准备

1. 复制 `.env.example` 为 `.env`，设置强随机数据库密码、JWT 密钥和字段加密密钥。
2. 设置 `APP_ENV=production`、`DEV_AUTH_BYPASS=false`、HTTPS 域名、严格 CORS 和飞书 OAuth 回调。
3. App Secret、机器人 Webhook/Secret 和群 `chat_id` 注入环境变量或加密设置，禁止提交仓库。
4. 执行 `make check` 与 `make verify-production`。
5. 启动：`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`。
6. 检查 `/health`（进程存活）和 `/ready`（数据库/Redis 就绪）。

API 启动顺序为 Alembic 迁移 → 指标/班次/角色 seed → fixture 幂等导入 → Uvicorn。Worker/Beat 等待 API 健康后启动。首次接入真实飞书后执行 `make sync-feishu`。

## 安全基线

- 生产配置会拒绝开发登录旁路、空密钥和 `change_me`。
- OAuth 校验签名 state；会话 Cookie 为 HttpOnly、Secure、SameSite=Lax；写接口校验 CSRF。
- 查询、详情、导出、预警与管理 API 在服务端执行角色/直播间权限。
- 系统设置密钥使用 Fernet 加密，返回值只显示掩码。
- SQL 使用 ORM/参数化语句；导出拦截公式注入；CORS 仅允许配置来源。

## 回滚

部署前运行 `make backup`。应用回滚使用上一个镜像标签；数据库迁移默认只前滚。若必须恢复，停止写入服务，按运维手册恢复备份并重新执行 `/ready`、fixture 幂等同步和冒烟测试。

当前开发机没有 Docker CLI，因此最终报告会区分“Compose 静态验证通过”和“容器运行态尚需在 Docker Engine 环境复验”。
