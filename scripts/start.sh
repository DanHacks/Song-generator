#!/usr/bin/env bash
# Build the frontend, start the SautiGen backend (which serves both the API
# and the built React app) and expose it through a public Cloudflare quick
# tunnel (great for M-Pesa callbacks and sharing).
#
# Usage:  ./scripts/start.sh          (starts everything)
#         ./scripts/start.sh --stop   (stops everything)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLOUDFLARED="${CLOUDFLARED:-cloudflared}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
LOG_DIR="${LOG_DIR:-/tmp/opencode}"
PID_DIR="${LOG_DIR}/pids"

stop_all() {
  for f in "$PID_DIR"/backend.pid "$PID_DIR"/tunnel.pid; do
    if [ -f "$f" ]; then
      kill "$(cat "$f")" 2>/dev/null || true
      rm -f "$f"
    fi
  done
  echo "Stopped."
}

if [ "${1:-}" = "--stop" ]; then
  stop_all
  exit 0
fi

mkdir -p "$PID_DIR"
stop_all
sleep 1

echo "Building frontend..."
(cd "$ROOT/frontend" && npm run build >/dev/null 2>&1)

echo "Starting backend on :$BACKEND_PORT (serves app + API) ..."
(cd "$ROOT/backend" && setsid nohup uvicorn main:app --port "$BACKEND_PORT" \
  </dev/null >"$LOG_DIR/server.log" 2>&1 & echo $! >"$PID_DIR/backend.pid")

echo "Opening public tunnel -> http://localhost:$BACKEND_PORT ..."
setsid nohup "$CLOUDFLARED" tunnel --url "http://localhost:$BACKEND_PORT" --no-autoupdate \
  </dev/null >"$LOG_DIR/tunnel.log" 2>&1 &
echo $! >"$PID_DIR/tunnel.pid"

echo "Waiting for services..."
for i in $(seq 1 30); do
  if curl -sf "http://localhost:$BACKEND_PORT/api/health" >/dev/null; then
    break
  fi
  sleep 1
done

PUBLIC_URL=""
for i in $(seq 1 30); do
  PUBLIC_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_DIR/tunnel.log" | tail -1 || true)"
  [ -n "$PUBLIC_URL" ] && break
  sleep 1
done

echo ""
echo "  Local app+API:  http://localhost:$BACKEND_PORT"
echo "  Public URL:     ${PUBLIC_URL:-not ready yet - see $LOG_DIR/tunnel.log}"
echo ""
echo "Set MPESA_CALLBACK_BASE to the Public URL above in backend/.env"
echo "to receive M-Pesa STK push callbacks."
echo ""
echo "For live-editing development, run 'cd frontend && npm run dev' and"
echo "open http://localhost:5173 (Vite proxies /api and /data to :$BACKEND_PORT)."
