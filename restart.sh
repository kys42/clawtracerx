#!/bin/bash
set -euo pipefail

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8901}"
LOG_FILE="${LOG_FILE:-$HOME/.openclaw/tools/ocmon/web.log}"

pkill -f "ctrace web --host ${HOST} --port ${PORT}" 2>/dev/null || true
pkill -f "ctrace\.py web --host ${HOST} --port ${PORT}" 2>/dev/null || true

# Fallback: kill anything holding the target port.
if command -v lsof >/dev/null 2>&1; then
  pids="$(lsof -ti tcp:${PORT} 2>/dev/null || true)"
  if [ -n "${pids}" ]; then
    kill ${pids} 2>/dev/null || true
  fi
fi

sleep 0.5
nohup ctrace web --host "${HOST}" --port "${PORT}" >> "${LOG_FILE}" 2>&1 &
PID=$!

sleep 0.3
LOCAL_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
if [ -z "${LOCAL_IP}" ]; then
  LOCAL_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
fi
if [ -z "${LOCAL_IP}" ]; then
  LOCAL_IP="$(ipconfig getifaddr en1 2>/dev/null || true)"
fi

echo "ctrace restarted (pid ${PID})"
echo "log: ${LOG_FILE}"
echo "local:   http://127.0.0.1:${PORT}"
if [ -n "${LOCAL_IP}" ]; then
  echo "network: http://${LOCAL_IP}:${PORT}"
fi
echo "tunnel: forward port ${PORT} to access from code tunnel"
