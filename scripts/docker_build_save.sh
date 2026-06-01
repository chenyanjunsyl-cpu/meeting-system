#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

IMAGE_NAME="${IMAGE_NAME:-meeting-system:offline}"
IMAGE_TAR="${IMAGE_TAR:-meeting-system-docker.tar}"

docker build -t "$IMAGE_NAME" .
docker save -o "$IMAGE_TAR" "$IMAGE_NAME"

echo "Docker 镜像已构建并保存：$APP_DIR/$IMAGE_TAR"
