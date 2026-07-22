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

## Netlify 前端部署

仓库根目录的 `netlify.toml` 已固定从 `apps/web` 安装依赖和执行 Vite 构建，并发布 `apps/web/dist`。构建过程会生成 `_redirects`，保证 `/overview`、`/alerts` 等 React Router 地址刷新后仍返回 `index.html`，不再出现 Netlify 默认 404。

Netlify 只承载前端。实时飞书同步、数据库、权限和预警任务仍由 FastAPI、PostgreSQL、Redis、Celery Worker/Beat 组成的后端服务承载。后端部署完成后，在 Netlify 的环境变量中设置：

```dotenv
NETLIFY_BACKEND_ORIGIN=https://api.example.com
```

该值必须是公开 HTTPS 源站，不能包含路径、账号密码、查询参数或锚点。重新部署后，构建脚本会按顺序生成 `/api/*`、`/auth/*`、`/health`、`/ready` 的同源代理规则，再写入 SPA 回退规则。这样飞书 OAuth 会话 Cookie 和 CSRF 校验仍通过 Netlify 域名工作。

后端生产环境同时需要把 `APP_BASE_URL`、`API_BASE_URL` 和 `FEISHU_REDIRECT_URI` 配置为用户访问的 Netlify HTTPS 域名，把 `CORS_ORIGINS` 限定为该域名。飞书 `App Secret`、机器人密钥和数据库密码只能配置在后端，禁止写入 Netlify 的 `VITE_*` 构建变量。

若尚未配置 `NETLIFY_BACKEND_ORIGIN`，前端会把非 JSON 的 SPA 回退响应识别为“API 未连接”，页面显示可重试错误态，不再因把 HTML 当作接口数据而白屏。该保护只改善故障呈现，不代表实时后端已经上线。
