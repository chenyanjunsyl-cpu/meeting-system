#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

PORT="${PORT:-5000}"
HOST="${HOST:-0.0.0.0}"
SECRET_KEY="${SECRET_KEY:-change-this-secret-key}"
MEETING_DB_PATH="${MEETING_DB_PATH:-$APP_DIR/meeting.db}"
ROOMS_CONFIG_PATH="${ROOMS_CONFIG_PATH:-$APP_DIR/rooms.json}"

if [ ! -x ".venv/bin/waitress-serve" ]; then
  echo "未检测到 .venv，请先运行 ./scripts/install_linux.sh"
  exit 1
fi

if [ -f meeting.pid ] && kill -0 "$(cat meeting.pid)" 2>/dev/null; then
  echo "服务已经在运行，PID: $(cat meeting.pid)"
  exit 0
fi

mkdir -p logs
export SECRET_KEY MEETING_DB_PATH ROOMS_CONFIG_PATH
nohup .venv/bin/waitress-serve --host="$HOST" --port="$PORT" app:app > logs/meeting.log 2>&1 &
echo $! > meeting.pid

echo "服务已启动：http://127.0.0.1:${PORT}"
echo "日志：$APP_DIR/logs/meeting.log"
