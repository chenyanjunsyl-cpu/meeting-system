#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 python3。离线安装包包含 Python 模块，但不包含 Linux Python 解释器。"
  echo "请先在目标系统安装 Python 3.10+，或使用随包提供的 Docker 镜像。"
  exit 1
fi

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --no-index --find-links wheelhouse -r requirements.txt

mkdir -p logs
chmod +x scripts/run_linux.sh scripts/stop_linux.sh scripts/docker_start.sh scripts/docker_stop.sh

echo "安装完成。运行 ./scripts/run_linux.sh 启动服务。"
