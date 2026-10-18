#!/usr/bin/env bash
# =============================================================================
# Benchmark through the FULL DEPLOYMENT PATH (Caddy:81 -> Next.js:3000 -> Gunicorn:5000)
# This measures the real user experience, not just the backend.
# Results saved to /home/z/my-project/download/deploy_bench_results/
# =============================================================================
set -euo pipefail
BASE="${1:-http://127.0.0.1:81}"
OUT="/home/z/my-project/download/deploy_bench_results"
mkdir -p "$OUT"
HERE="$(cd "$(dirname "$0")" && pwd)"
BENCH="/home/z/my-project/github_clone_test/benchmarks/bench.py"

echo "============================================================"
echo " Deployed-path benchmark: $BASE"
echo " (Caddy -> Next.js proxy -> CrowdCloud Gunicorn 4x2)"
echo "============================================================"

run() {
  local name="$1"; shift
  echo ""
  echo "--- $name ---"
  python3 "$BENCH" --url "$BASE" -o "$OUT/$name.json" "$@"
  python3 - "$OUT/$name.json" << 'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
lat = d['latency_ms']
print(f"  requests={d['requests']} success={d['success']} failed={d['failed']} "
      f"RPS={d['requests_per_second']:.2f} mean={lat['mean']:.1f}ms p95={lat['p95']}ms")
PYEOF
}

# Read endpoints (what the UI polls every 3s)
run deploy_api_services_c10 --path /api/services -n 500 -c 10
run deploy_api_services_c50 --path /api/services -n 1000 -c 50

# Home page (full HTML render through proxy)
run deploy_home_c10 --path / -n 300 -c 10

# Write endpoint (ticket creation through the full chain)
run deploy_ticket_create_c10 --path /api/tickets --method POST -n 500 -c 10 \
    --body '{"service_code": "it_support", "customer_name": "deploy-bench"}'
run deploy_ticket_create_c50 --path /api/tickets --method POST -n 1000 -c 50 \
    --body '{"service_code": "registration_support", "customer_name": "deploy-bench"}'

# Control: healthz (no DB) through the full chain
run deploy_healthz_c10 --path /healthz -n 500 -c 10

echo ""
echo "============================================================"
echo " All results saved to $OUT"
echo "============================================================"
ls -la "$OUT"
