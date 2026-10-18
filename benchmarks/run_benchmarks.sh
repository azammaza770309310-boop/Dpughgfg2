#!/usr/bin/env bash
# =============================================================================
# CrowdCloud benchmark matrix (W5 — Performance & Benchmarking)
#
# Runs the load generator against a RUNNING server at three load levels
# for three endpoints, plus one extra high-concurrency level for the
# write endpoint. Results (JSON) are stored in benchmarks/results/.
#
# Usage:
#     ./benchmarks/run_benchmarks.sh [BASE_URL]
#
# Note on the tool: the environment used for the official results has no
# ApacheBench binary; benchmarks/bench.py reproduces ab's metrics with
# the Python standard library. See benchmarks/ab_commands.txt for the
# equivalent ab commands.
# =============================================================================
set -euo pipefail

BASE="${1:-http://127.0.0.1:5000}"
HERE="$(cd "$(dirname "$0")" && pwd)"
RESULTS="$HERE/results"
mkdir -p "$RESULTS"

if ! curl -sfL "$BASE/healthz" > /dev/null; then
  echo "Server not reachable at $BASE — start it first." >&2
  exit 1
fi

run() {  # run <label> <path> <method> <num> <concurrency> [body]
  local label="$1" path="$2" method="$3" num="$4" conc="$5" body="${6:-}"
  local file="$RESULTS/${label}.json"
  echo ""
  echo ">>> [$label] $method $path  (n=$num, c=$conc)"
  if [ -n "$body" ]; then
    python3 "$HERE/bench.py" --url "$BASE" --path "$path" --method "$method" \
      -n "$num" -c "$conc" --body "$body" -o "$file" --label "$label"
  else
    python3 "$HERE/bench.py" --url "$BASE" --path "$path" --method "$method" \
      -n "$num" -c "$conc" -o "$file" --label "$label"
  fi
}

echo "CrowdCloud benchmark matrix — target: $BASE"
python3 -c 'import sys; print("Python:", sys.version.split()[0])'

# ---- control endpoint (client/tool sanity check) -----------------------
# /healthz is a trivial response: if it reaches far higher RPS than the
# dynamic endpoints, the load generator itself is not the bottleneck.
run "control_healthz_L2" "/healthz" "GET" 500 10
run "control_healthz_L3" "/healthz" "GET" 1000 50

# ---- level 1/2/3 per endpoint ------------------------------------------
# (n, c): L1 = (200, 1), L2 = (500, 10), L3 = (1000, 50)

for level in "L1 200 1" "L2 500 10" "L3 1000 50"; do
  set -- $level
  run "home_page_$1"    "/"              "GET"  "$2" "$3"
  run "api_services_$1" "/api/services"  "GET"  "$2" "$3"
done

# ---- write endpoint (ticket creation) ----------------------------------
# a fresh database state before each level keeps runs comparable
for level in "L1 200 1" "L2 500 10" "L3 1000 50" "L4 2000 100"; do
  set -- $level
  curl -sfL -X POST "$BASE/api/demo/reset" > /dev/null
  run "api_ticket_create_$1" "/api/tickets" "POST" "$2" "$3" \
    '{"service_code": "it_support", "customer_name": "load-test"}'
  curl -sfL "$BASE/api/stats" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("    (DB now holds", d["total"], "tickets after this level)")'
done

echo ""
echo "All raw results saved under: $RESULTS"
echo "Summarise them with:  python3 benchmarks/summarize.py"
