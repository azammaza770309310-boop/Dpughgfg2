#!/usr/bin/env bash
# =============================================================================
# CrowdCloud live-demo scenario
# Shows the required load transition on a RUNNING server:
#
#     NORMAL  ->  BUSY  ->  HIGH LOAD   (and back down after serving)
#
# Usage:
#     ./scripts/demo_scenario.sh [BASE_URL]
#     ./scripts/demo_scenario.sh http://127.0.0.1:5000
#
# Requirements: curl, python3. The server must already be running
# (python run.py, docker compose up, or gunicorn).
# =============================================================================
set -euo pipefail

BASE="${1:-http://127.0.0.1:5000}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SERVICE="it_support"          # the demo focuses on one service
OTHERS=(academic_advising registration_support student_services)

line() { printf '%s\n' "--------------------------------------------------------------------------------"; }
head() { printf '\n== %s\n' "$1"; }

status() {
  curl -sfL "$BASE/api/services" | python3 "$HERE/fmt_status.py"
}

issue() {  # issue N tickets on the demo service
  local n="$1" i
  for i in $(seq 1 "$n"); do
    curl -sfL -X POST "$BASE/api/tickets" \
      -H "Content-Type: application/json" \
      -d "{\"service_code\": \"$SERVICE\", \"customer_name\": \"demo-$((RANDOM % 90 + 10))\"}" \
      > /dev/null
  done
}

serve_one() {  # call the next ticket and complete it
  local number
  number=$(curl -sfL -X POST "$BASE/api/services/$SERVICE/next" \
            | python3 -c 'import json,sys; t=json.load(sys.stdin).get("ticket"); print(t["ticket_number"] if t else "")')
  [ -n "$number" ] && curl -sfL -X POST "$BASE/api/tickets/$number/status" \
        -H "Content-Type: application/json" -d '{"status": "DONE"}' > /dev/null
}

# ------------------------------------------------------------------ script

if ! curl -sfL "$BASE/healthz" > /dev/null; then
  echo "Server is not reachable at $BASE — start it first (python run.py)." >&2
  exit 1
fi

line
echo "CrowdCloud demo scenario — service: IT Support"
echo "Thresholds: BUSY at 8 waiting tickets, HIGH LOAD at 16 (defaults)."
line

head "STEP 0 — clean state"
curl -sfL -X POST "$BASE/api/demo/reset" > /dev/null
status

head "STEP 1 — low load: issue 3 tickets (NORMAL expected)"
issue 3
status

head "STEP 2 — load grows: +5 tickets = 8 waiting (BUSY expected)"
issue 5
status

head "STEP 3 — peak: +8 tickets = 16 waiting (HIGH LOAD expected)"
issue 8
status

head "STEP 4 — staff serves customers: 3 completed (de-escalation)"
serve_one; serve_one; serve_one
status

head "STEP 5 — other services stay independent (issue 1 ticket each)"
for svc in "${OTHERS[@]}"; do
  curl -sfL -X POST "$BASE/api/tickets" -H "Content-Type: application/json" \
    -d "{\"service_code\": \"$svc\", \"customer_name\": \"visitor-1\"}" > /dev/null
done
status

head "DONE — leave the queue draining or reset with:"
echo "  curl -X POST $BASE/api/demo/reset"
line
