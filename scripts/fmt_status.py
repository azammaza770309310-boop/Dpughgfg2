#!/usr/bin/env python3
"""Pretty-print /api/services output for the demo scenario script."""
import json
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)

for s in data["services"]:
    print(
        f"  {s['name']:<24} waiting={s['waiting']:>3}"
        f"   in-service={s['serving']:>2}   load={s['load']}"
    )
stats = data.get("stats", {})
print(
    f"  OVERALL: waiting={stats.get('waiting')}  "
    f"overall load = {stats.get('overall_load')}"
)
