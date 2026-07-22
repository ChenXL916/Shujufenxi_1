# 多直播间小时数据驾驶舱

面向直播运营的小时级经营、排班、对比和预警应用。后端为 FastAPI + SQLAlchemy + Celery，前端为 React + Ant Design + ECharts，生产拓扑使用 PostgreSQL、Redis 和 Nginx。

当前仓库无需飞书凭据即可通过两份 Excel fixture 与 Mock Feishu API 完整运行。配置飞书凭据后，`make sync-feishu` 会切换到开放平台 API；不会抓取飞书网页或模拟登录。

## 快速开始

### 本机开发

```powershell
Copy-Item .env.example .env
python -m pip install -e ".\apps\api[dev]"
Push-Location apps\web; npm.cmd ci; Pop-Location
python scripts\seed_demo.py
python scripts\import_excel_fixture.py
```

分别启动 API 和 Web：

```powershell
python -m uvicorn app.main:app --app-dir apps/api --reload --port 8000
npm.cmd --prefix apps/web run dev
```

浏览器打开 `http://localhost:5173`。认证旁路默认关闭；仅在明确隔离的本地开发环境中设置 `DEV_AUTH_BYPASS=true` 才会以开发管理员身份运行，生产环境始终拒绝该配置。

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

访问 `http://localhost:8080`。API 容器启动时执行迁移、参考数据 seed 和幂等 fixture 导入。

生产环境使用：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

必须设置强 `POSTGRES_PASSWORD`、`JWT_SECRET`、`FIELD_ENCRYPTION_KEY`，并配置 HTTPS。详见 [部署文档](docs/DEPLOYMENT.md)、[飞书配置](docs/FEISHU_SETUP.md) 和 [运维手册](docs/OPERATIONS.md)。

## 常用命令

```bash
make sync-fixture
make sync-feishu
make check
make verify-production
make backup
```

Windows 未安装 GNU Make 时可直接运行 `make.cmd check`；仓库也提供同名 `make.cmd` 以满足 PowerShell 调用。

指标口径与数据字段见 [数据字典](docs/DATA_DICTIONARY.md)，预警和主播趋势推送边界见 [告警说明](docs/ALERT_RULES.md)，阶段证据和最终测试结果分别见 [开发进度](docs/PROGRESS.md) 与 [测试报告](docs/TEST_REPORT.md)。
