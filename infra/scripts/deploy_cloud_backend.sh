#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:-$ROOT/.env.cloud}"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.cloud.yml")

if [[ ! -f "$ENV_FILE" ]]; then
  echo "缺少云端环境文件：$ENV_FILE" >&2
  exit 2
fi

for command in docker curl; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "缺少命令：$command" >&2
    exit 2
  }
done

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

required=(
  CLOUD_API_DOMAIN
  SITES_GATEWAY_TOKEN
  POSTGRES_DB
  POSTGRES_USER
  POSTGRES_PASSWORD
  DATABASE_URL
  JWT_SECRET
  FIELD_ENCRYPTION_KEY
  FEISHU_APP_ID
  FEISHU_APP_SECRET
)
for key in "${required[@]}"; do
  if [[ -z "${!key:-}" ]]; then
    echo "云端环境变量未配置：$key" >&2
    exit 2
  fi
done

"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" build api
"${COMPOSE[@]}" up -d postgres redis
"${COMPOSE[@]}" run --rm api alembic upgrade head

if [[ -f "${MIGRATION_DIR:-}/source.sqlite3" ]]; then
  if [[ -f "${MIGRATION_DIR}/manifest.json" ]]; then
    echo "迁移清单已存在，拒绝自动覆盖：${MIGRATION_DIR}/manifest.json" >&2
    exit 3
  fi
  "${COMPOSE[@]}" --profile migration run --rm migrate-data
else
  echo "未发现 SQLite 快照；仅创建空 PostgreSQL 结构，不导入业务数据。"
fi

"${COMPOSE[@]}" up -d api celery-worker celery-beat api-gateway

for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error \
    "https://${CLOUD_API_DOMAIN}/ready" >/dev/null; then
    echo "云端后端已就绪：https://${CLOUD_API_DOMAIN}/ready"
    exit 0
  fi
  sleep 2
done

echo "云端后端在 60 秒内未通过 /ready；保留容器和日志供排查。" >&2
"${COMPOSE[@]}" ps >&2
exit 1
