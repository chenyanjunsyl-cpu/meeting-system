#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

if [ ! -f meeting.pid ]; then
  echo "未找到 meeting.pid，服务可能未运行。"
  exit 0
fi

PID="$(cat meeting.pid)"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "已停止服务，PID: $PID"
else
  echo "PID $PID 不存在，清理 pid 文件。"
fi

rm -f meeting.pid
