#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

IMAGE_NAME="${IMAGE_NAME:-meeting-system:offline}"
CONTAINER_NAME="${CONTAINER_NAME:-meeting-system}"
PORT="${PORT:-5000}"
DATA_DIR="${DATA_DIR:-$APP_DIR/docker-data}"
IMAGE_TAR="${IMAGE_TAR:-$APP_DIR/meeting-system-docker.tar}"

mkdir -p "$DATA_DIR"

if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
  if [ -f "$IMAGE_TAR" ]; then
    docker load -i "$IMAGE_TAR"
  else
    echo "未找到 Docker 镜像 $IMAGE_NAME，也未找到镜像文件 $IMAGE_TAR"
    exit 1
  fi
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

docker run -d \
  --name "$CONTAINER_NAME" \
  -p "$PORT:5000" \
  -v "$DATA_DIR:/data" \
  -e SECRET_KEY="${SECRET_KEY:-change-this-secret-key}" \
  "$IMAGE_NAME"

echo "Docker 服务已启动：http://127.0.0.1:${PORT}"
echo "数据目录：$DATA_DIR"
