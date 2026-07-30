# 部署文档

## 拓扑

Compose 固定包含 7 个服务：PostgreSQL、Redis、API、Celery Worker、Celery Beat、Web、反向代理。只有反向代理暴露 `8080`；数据库和 Redis 不对公网开放。

## Windows 本机实时循环

当前 Windows 试运行环境没有常驻 Celery Worker/Beat 时，可用仓库中的计划任务脚本保证登录后继续执行正式飞书同步和预警评估：

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\windows\register-realtime-sync-task.ps1
Start-ScheduledTask -TaskName LiveOps-Realtime-Sync
```

任务直接托管 `scripts/realtime_sync_service.py`，由服务进程从本机忽略提交的 `.env.tunnel` 读取正式配置；异常退出后每分钟重试，并通过任务单实例设置和服务进程文件锁防止重复循环。运行日志写入忽略提交的 `logs\realtime-sync-service-*.log`。

需要撤销时：

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\windows\unregister-realtime-sync-task.ps1
```

该任务只保证当前 Windows 用户登录且电脑开机期间的后台循环，不会把 Cloudflare Quick Tunnel 变成固定入口。无人值守 24×7 公网运行仍应使用命名隧道或云服务器，并迁移到 Compose 的 Celery Worker/Beat。

## Windows 本机 API 与公网网关自启动

当前可用固定入口为 `https://chenxl916.github.io/Shujufenxi_1/`。Windows 当前用户登录后，可由计划任务同时恢复 E 盘正式 API、内置前端、Cloudflare Quick Tunnel 和 GitHub Pages 动态入口：

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\windows\register-gateway-task.ps1
Start-ScheduledTask -TaskName LiveOps-Gateway
```

`scripts/gateway_service.py` 从本机忽略提交的 `.env.tunnel` 读取生产配置，先用轻量保活进程唤醒 WSL 内 Docker/Redis，等待本机 `/ready` 后再启动隧道。FastAPI 在全部 API/认证路由之后同源提供 `apps/web/dist`，包括 React SPA 回退。Quick Tunnel 地址变化后，只把公开 origin 写入 GitHub 的 `liveops-runtime` 运行分支；GitHub Pages 固定入口读取该状态并跳转到当前 HTTPS 网关，所以密码登录、Cookie、实时数据和 API 保持同源。任务或任一子进程异常退出后每分钟重建服务周期，文件锁和计划任务设置会阻止重复实例。

注册网关任务时还会安装两个同名的“直播运营驾驶舱”固定入口：一个位于桌面，另一个位于当前用户的 Windows“启动”目录。用户重新启动电脑并登录 Windows 后，浏览器会自动打开 GitHub Pages 固定入口；该入口会等待新网关健康并跳转，不依赖上次开机生成的 `*.trycloudflare.com` 地址。浏览器被关闭后，可随时双击桌面入口重新进入。也可单独安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\windows\install-dashboard-launcher.ps1
```

运行前提：

- `cloudflared.exe` 安装在标准目录；
- GitHub CLI 已以仓库管理员账号登录；
- E 盘项目虚拟环境和 `.env.tunnel` 存在；
- 当前 Windows 用户已登录。出于不保存 Windows 密码和不复制 GitHub 凭据的安全要求，任务使用“登录时”触发，而不是在登录界面前以 SYSTEM 身份运行。

日志位于 `logs\gateway-service-*`、`logs\gateway-api-*` 和 `logs\gateway-tunnel-*`。需要撤销时：

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\windows\unregister-gateway-task.ps1
```

撤销网关任务会同时移除桌面和启动目录中的固定入口；也可单独执行 `uninstall-dashboard-launcher.ps1`。

该方案能自动恢复临时隧道并保持 GitHub Pages 用户入口不变，但电脑断电、停留在 Windows 登录界面或 GitHub/Cloudflare 公网不可达期间仍无法提供服务。当前 Netlify 站点因账户构建额度耗尽仍停留在旧代理产物，不作为可用入口。真正的无人值守 24×7 可用性仍需把后端迁到云服务器，或提供 Cloudflare 账号与自有域名配置命名隧道。

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
