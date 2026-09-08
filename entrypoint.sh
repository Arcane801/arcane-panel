#!/bin/bash
set -e
export NGINX_PORT="${PORT:-8080}"
export APP_PORT="${APP_PORT:-10000}"
export XRAY_API_PORT="${XRAY_API_PORT:-10001}"
envsubst '${NGINX_PORT} ${APP_PORT}' < /etc/nginx/nginx.conf > /tmp/nginx.conf
mv /tmp/nginx.conf /etc/nginx/nginx.conf
mkdir -p /app/data
chmod 700 /app/data
cleanup() {
    echo "[entrypoint] Shutting down..."
    [ -n "$NGINX_PID" ] && kill -TERM "$NGINX_PID" 2>/dev/null || true
    [ -n "$APP_PID" ] && kill -TERM "$APP_PID" 2>/dev/null || true
    wait
    exit 0
}
trap cleanup SIGTERM SIGINT
nginx -g 'daemon off;' &
NGINX_PID=$!
python -m uvicorn app.main:app --host 127.0.0.1 --port "$APP_PORT" --proxy-headers --forwarded-allow-ips '*' --log-level info &
APP_PID=$!
echo "[entrypoint] Services started: nginx=$NGINX_PID app=$APP_PID"
wait -n
echo "[entrypoint] A service exited."
cleanup
