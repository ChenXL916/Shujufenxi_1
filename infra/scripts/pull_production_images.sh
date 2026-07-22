#!/usr/bin/env bash
set -euo pipefail

IMAGES=(
  python:3.12-slim
  node:22-alpine
  nginx:1.27-alpine
  postgres:16-alpine
  redis:7.4-alpine
)

for image in "${IMAGES[@]}"; do
  pulled=false
  for attempt in 1 2 3 4 5; do
    if docker pull "$image"; then
      pulled=true
      break
    fi
    sleep $((attempt * 3))
  done
  if [[ "$pulled" != true ]]; then
    echo "镜像拉取失败：$image" >&2
    exit 1
  fi
done

echo "BASE_IMAGE_PULL=PASS count=${#IMAGES[@]}"
