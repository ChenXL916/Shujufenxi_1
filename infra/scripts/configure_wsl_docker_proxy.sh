#!/usr/bin/env bash
set -euo pipefail

GATEWAY="${1:-}"
if [[ ! "$GATEWAY" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  echo "用法：$0 <WSL 默认网关 IPv4>" >&2
  exit 2
fi

install -m 0755 -d /etc/systemd/system/docker.service.d
printf '[Service]\nEnvironment="HTTP_PROXY=http://%s:7898"\nEnvironment="HTTPS_PROXY=http://%s:7898"\nEnvironment="NO_PROXY=localhost,127.0.0.1,::1,postgres,redis,api,web,reverse-proxy"\n' \
  "$GATEWAY" "$GATEWAY" > /etc/systemd/system/docker.service.d/http-proxy.conf

systemctl daemon-reload
systemctl restart docker
systemctl is-active --quiet docker

echo "Docker 代理已配置到 WSL 网关 ${GATEWAY}:7898"
