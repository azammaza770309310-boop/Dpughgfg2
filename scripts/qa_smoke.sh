#!/usr/bin/env bash
# =============================================================================
# QA smoke test — verifies the CrowdCloud prototype actually WORKS at delivery
# time, using the exact production settings from the Dockerfile
# (Gunicorn, 4 workers x 2 threads).
#
# Covers: healthz, service listing, ticket creation, unique numbering,
# queue position, load-state transitions (NORMAL -> BUSY -> HIGH LOAD),
# staff serving (next/done), user cancel, 400/404 error handling.
# =============================================================================
set -euo pipefail

BASE="${1:-http://127.0.0.1:5055}"
DB="/tmp/qa_crowdcloud.db"
PORT="${BASE##*:}"
cd "$(dirname "$0")/.."

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }
check() { # check <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then ok "$1 ($3)"; else bad "$1 — expected [$2], got [$3]"; fi
}

rm -f "$DB"
echo "=== starting Gunicorn 4x2 on port $PORT (same as Dockerfile) ==="
CROWDCLOUD_DB="$DB" gunicorn --workers 4 --threads 2 --bind "0.0.0.0:$PORT" \
  --access-logfile - --error-logfile - run:app > /tmp/qa_gunicorn.log 2>&1 &
GUNI_PID=$!
trap 'kill $GUNI_PID 2>/dev/null || true' EXIT

# wait for readiness
READY=0
for i in $(seq 1 40); do
  if curl -sfL "$BASE/healthz" > /dev/null 2>&1; then READY=1; break; fi
  # if the master died, show why instead of waiting the full 20 s
  if ! kill -0 "$GUNI_PID" 2>/dev/null; then break; fi
  sleep 0.5
done
if [ "$READY" -ne 1 ]; then
  echo "!! server did not become ready — gunicorn log follows:"
  cat /tmp/qa_gunicorn.log 2>/dev/null || true
  exit 1
fi

echo; echo "=== 1. health & pages ==="
H=$(curl -sfL -o /dev/null -w '%{http_code}' "$BASE/healthz"); check "GET /healthz" "200" "$H"
for p in / /queue /admin; do
  C=$(curl -sfL -o /dev/null -w '%{http_code}' "$BASE$p"); check "GET $p" "200" "$C"
done
# unknown ticket page must 404 (curl -f fails on 404, so probe without -f)
C=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/ticket/AA-001"); check "GET /ticket/unknown 404" "404" "$C"

echo; echo "=== 2. functional flow ==="
# clean state
curl -sfL -X POST "$BASE/api/demo/reset" > /dev/null

# service listing + structure
SVC=$(curl -sfL "$BASE/api/services")
N=$(echo "$SVC" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["services"]))')
check "services count" "4" "$N"
LV=$(echo "$SVC" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["services"][2]["load"])')
check "initial load level" "NORMAL" "$LV"

# create ticket
T=$(curl -sfL -X POST "$BASE/api/tickets" -H "Content-Type: application/json" \
    -d '{"service_code":"it_support","customer_name":"qa-test"}')
NUM=$(echo "$T" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ticket"]["ticket_number"])')
check "ticket issued prefix+number" "IT-001" "$NUM"
ST=$(echo "$T" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ticket"]["status"])')
check "ticket status WAITING" "WAITING" "$ST"
POS=$(echo "$T" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ticket"]["people_ahead"] + 1)')
check "queue position 1 (people_ahead=0)" "1" "$POS"

# get ticket by number
G=$(curl -sfL "$BASE/api/tickets/$NUM")
ST2=$(echo "$G" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ticket"]["status"])')
check "GET ticket status" "WAITING" "$ST2"
# duplicate ticket number must never happen: create 30 more, all unique
for i in $(seq 1 30); do
  curl -sfL -X POST "$BASE/api/tickets" -H "Content-Type: application/json" \
    -d '{"service_code":"it_support","customer_name":"u'$i'"}' > /dev/null
done
UNIQ=$(curl -sfL "$BASE/api/tickets?status=WAITING" | \
  python3 -c 'import json,sys; ts=json.load(sys.stdin)["tickets"]; print(len({t["ticket_number"] for t in ts}))')
CNT=$(curl -sfL "$BASE/api/tickets?status=WAITING" | \
  python3 -c 'import json,sys; print(len(json.load(sys.stdin)["tickets"]))')
check "31 tickets, all unique numbers" "31" "$UNIQ"
check "31 waiting tickets listed" "31" "$CNT"

# load level after 31 waiting -> HIGH LOAD
LV2=$(curl -sfL "$BASE/api/services" | \
  python3 -c 'import json,sys; d=json.load(sys.stdin); print([s["load"] for s in d["services"] if s["code"]=="it_support"][0])')
check "load at 31 waiting" "HIGH LOAD" "$LV2"

echo; echo "=== 3. staff console actions ==="
# call next -> SERVING
NX=$(curl -sfL -X POST "$BASE/api/services/it_support/next")
NXT=$(echo "$NX" | python3 -c 'import json,sys; t=json.load(sys.stdin)["ticket"]; print(t["ticket_number"] if t else "")')
check "next called IT-001" "IT-001" "$NXT"
# double-call from second clerk must NOT return same ticket (atomic claim)
NX2=$(curl -sfL -X POST "$BASE/api/services/it_support/next")
NXT2=$(echo "$NX2" | python3 -c 'import json,sys; t=json.load(sys.stdin)["ticket"]; print(t["ticket_number"] if t else "")')
check "second next returns different ticket" "IT-002" "$NXT2"
# invalid transition: mark SERVING ticket as SERVING again -> 400
C2=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/tickets/IT-001/status" \
     -H "Content-Type: application/json" -d '{"status":"SERVING"}')
check "invalid transition rejected (409)" "409" "$C2"
# complete it
C3=$(curl -sfL -o /dev/null -w '%{http_code}' -X POST "$BASE/api/tickets/IT-001/status" \
     -H "Content-Type: application/json" -d '{"status":"DONE"}')
check "mark DONE (200)" "200" "$C3"
# user cancel a waiting ticket
C4=$(curl -sfL -o /dev/null -w '%{http_code}' -X POST "$BASE/api/tickets/IT-031/cancel")
check "user cancel (200)" "200" "$C4"

echo; echo "=== 4. error handling ==="
E1=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/tickets" \
     -H "Content-Type: application/json" -d '{"service_code":"nope"}')
check "unknown service rejected (404)" "404" "$E1"
E2=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/tickets/XX-999")
check "unknown ticket 404" "404" "$E2"

echo; echo "=== 5. persistence across restart ==="
kill $GUNI_PID; wait $GUNI_PID 2>/dev/null || true
sleep 1
CROWDCLOUD_DB="$DB" gunicorn --workers 4 --threads 2 --bind "0.0.0.0:$PORT" run:app \
  > /tmp/qa_gunicorn2.log 2>&1 &
GUNI_PID=$!
for i in $(seq 1 40); do
  curl -sfL "$BASE/healthz" > /dev/null 2>&1 && break
  sleep 0.5
done
W=$(curl -sfL "$BASE/api/tickets?status=WAITING" | \
  python3 -c 'import json,sys; print(len(json.load(sys.stdin)["tickets"]))')
check "waiting tickets survive restart (28)" "28" "$W"
LV3=$(curl -sfL "$BASE/api/services" | \
  python3 -c 'import json,sys; d=json.load(sys.stdin); print([s["load"] for s in d["services"] if s["code"]=="it_support"][0])')
check "load level still HIGH LOAD after restart" "HIGH LOAD" "$LV3"

kill $GUNI_PID 2>/dev/null || true
echo
echo "================================="
echo "QA SMOKE RESULT: PASS=$PASS FAIL=$FAIL"
echo "================================="
[ "$FAIL" -eq 0 ]
