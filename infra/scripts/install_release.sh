#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 7 ]]; then
  echo "用法：$0 <archive> <sha256> <release-id> <env> <server-key> <server-cert> <sqlite-snapshot>" >&2
  exit 2
fi

ARCHIVE=$1
EXPECTED=$2
RELEASE_ID=$3
ENV_FILE=$4
SERVER_KEY=$5
SERVER_CERT=$6
SQLITE_SNAPSHOT=$7
RELEASE="/opt/live-ops/releases/${RELEASE_ID}"

read -r ACTUAL _ < <(sha256sum "$ARCHIVE")
if [[ "$ACTUAL" != "$EXPECTED" ]]; then
  echo "发布包 SHA-256 不匹配" >&2
  exit 1
fi

install -d -m 0755 "$RELEASE" /opt/live-ops/secrets/tls /opt/live-ops/migration /opt/live-ops/backups
tar -xf "$ARCHIVE" -C "$RELEASE"
install -m 0600 "$ENV_FILE" "$RELEASE/.env"
install -m 0600 "$SERVER_KEY" /opt/live-ops/secrets/tls/server.key
install -m 0644 "$SERVER_CERT" /opt/live-ops/secrets/tls/server.crt
install -m 0400 "$SQLITE_SNAPSHOT" /opt/live-ops/migration/source.sqlite3
ln -sfn "$RELEASE" /opt/live-ops/current

printf 'RELEASE=%s\nARCHIVE_SHA256=%s\nCURRENT=%s\n' \
  "$RELEASE" "$ACTUAL" "$(readlink -f /opt/live-ops/current)"
