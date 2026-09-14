#!/usr/bin/env bash
# 강사용: 로컬(네이티브) 서버 기동/중지. 사용: scripts/servers.sh local|platform|stop [SPEED]
cd "$(dirname "$0")/.."
pkill -f "uvicorn hydops.b9_dashboard.app" 2>/dev/null
pkill -f "uvicorn labplatform.main" 2>/dev/null
sleep 1
[ "$1" = "stop" ] && exit 0
MODE=${1:-local}; SPEED=${2:-4}
mkdir -p out
( ORCHESTRATION=$MODE SPEED=$SPEED PYTHONPATH=. nohup .venv/bin/uvicorn hydops.b9_dashboard.app:app --host 0.0.0.0 --port 8800 > out/hydops-api.log 2>&1 & )
( PYTHONPATH=. nohup .venv/bin/uvicorn labplatform.main:app --host 0.0.0.0 --port 8910 > out/labplatform.log 2>&1 & )
for i in $(seq 1 40); do curl -sf localhost:8800/api/state >/dev/null && curl -sf localhost:8910/health >/dev/null && echo "up: hydops($MODE, x$SPEED) :8800, lab-platform :8910" && exit 0; sleep 1; done
echo "servers failed to start"; tail -20 out/hydops-api.log; exit 1
