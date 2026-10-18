#!/usr/bin/env bash
# =============================================================================
# Worker-scaling benchmark (used in the scalability analysis, W6)
#
# Starts Gunicorn locally with 1, 2 and 4 worker processes and runs the
# same load against each configuration, so the effect of adding
# application workers can be compared with real numbers.
#
# Usage (from the project root):
#     ./benchmarks/run_scaling.sh
#
# Requirements: gunicorn (pip install gunicorn), curl, python3.
# A dedicated port (5001) and a throwaway database are used so the demo
# server on port 5000 keeps running untouched.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(cd "$HERE/.." && pwd)"
BASE="http://127.0.0.1:5001"
RESULTS="$HERE/results"
PORT=5001
PID_FILE="/tmp/crowdcloud-bench-gunicorn.pid"
DB="/tmp/crowdcloud-scaling.db"

mkdir -p "$RESULTS"

start_server() {
  local workers="$1"
  rm -f "$DB"
  (cd "$PROJECT" && \
   CROWDCLOUD_DB="$DB" AUTO_SERVE=0 \
   nohup gunicorn --workers "$workers" --bind "127.0.0.1:$PORT" \
     --access-logfile /dev/null --error-logfile /tmp/crowdcloud-bench.log \
     run:app > /dev/null 2>&1 & echo $! > "$PID_FILE")
  # wait for readiness
  for _ in $(seq 1 40); do
    if curl -sfL "$BASE/healthz" > /dev/null 2>&1; then return 0; fi
    sleep 0.5
  done
  echo "Gunicorn (workers=$workers) did not become ready" >&2
  exit 1
}

stop_server() {
  if [ -f "$PID_FILE" ]; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    rm -f "$PID_FILE"
  fi
  pkill -f "gunicorn.*:$PORT" 2>/dev/null || true
  sleep 1
}

trap stop_server EXIT

echo "CrowdCloud worker-scaling benchmark (gunicorn on port $PORT)"

for workers in 1 2 4; do
  stop_server
  start_server "$workers"
  echo ""
  echo ">>> Gunicorn workers = $workers"

  curl -sfL -X POST "$BASE/api/demo/reset" > /dev/null
  python3 "$HERE/bench.py" --url "$BASE" --path "/api/services" \
    -n 1000 -c 50 -o "$RESULTS/scaling_read_w${workers}.json" \
    --label "read_w${workers}"

  curl -sfL -X POST "$BASE/api/demo/reset" > /dev/null
  python3 "$HERE/bench.py" --url "$BASE" --path "/api/tickets" \
    --method POST --body '{"service_code": "it_support", "customer_name": "scale-test"}' \
    -n 500 -c 25 -o "$RESULTS/scaling_write_w${workers}.json" \
    --label "write_w${workers}"
done

stop_server
echo ""
echo "Scaling results saved under: $RESULTS (scaling_read_w*.json / scaling_write_w*.json)"
