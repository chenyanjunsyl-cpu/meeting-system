#!/bin/sh
set -eu

mkdir -p /data

if [ ! -f "${MEETING_DB_PATH}" ]; then
  cp /app/meeting.db "${MEETING_DB_PATH}"
fi

if [ ! -f "${ROOMS_CONFIG_PATH}" ]; then
  cp /app/rooms.json "${ROOMS_CONFIG_PATH}"
fi

exec "$@"
