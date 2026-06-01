#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-meeting-system}"

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  docker rm -f "$CONTAINER_NAME" >/dev/null
  echo "Docker 容器已停止并删除：$CONTAINER_NAME"
else
  echo "未找到容器：$CONTAINER_NAME"
fi
