#!/usr/bin/env python3
"""Consistency checker for CrowdCloud benchmark result files.

Validates the RAW JSON files produced by benchmarks/bench.py,
benchmarks/ramp_test.py and the worker-scaling runs — without any
hardcoded expected values, so it works on any fresh run:

1. every result file parses as JSON and has the required fields
2. completed == success + failed
3. requests/second is consistent with completed / wall_time
   (tolerance for the 3-decimal rounding of wall_time)
4. latency percentile ordering: p50 <= p95 <= p99 <= max
5. status codes sum to completed
6. reports aggregate totals (requests, failures, measurements)

Usage:
    python3 scripts/verify_consistency.py [results_dir]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_FIELDS = ("requests", "concurrency", "completed", "success", "failed",
                   "requests_per_second", "wall_time_seconds", "latency_ms")

passed = failed = 0


def chk(desc, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  [PASS] {desc}")
    else:
        failed += 1
        print(f"  [FAIL] {desc} — {detail}")


def load_measurement(p: Path):
    d = json.loads(p.read_text())
    if "phases" in d or "read_phase" in d:  # ramp test file structure
        return None
    if "requests" not in d:  # not a measurement file
        return None
    return d


def main() -> int:
    results_dir = Path(sys.argv[1] if len(sys.argv) > 1 else
                       Path(__file__).resolve().parent.parent / "benchmarks" / "results")
    if not results_dir.is_dir():
        print(f"results directory not found: {results_dir}")
        return 2

    files = sorted(results_dir.glob("*.json"))
    print(f"Scanning {results_dir} — {len(files)} JSON file(s)\n")

    measurements = []
    for f in files:
        try:
            d = load_measurement(f)
        except Exception as exc:
            chk(f"{f.name}: valid JSON", False, str(exc))
            continue
        if d is None:
            continue
        measurements.append((f, d))
        label = f.stem

        missing = [k for k in REQUIRED_FIELDS if k not in d]
        chk(f"{label}: required fields", not missing, f"missing {missing}")
        chk(f"{label}: completed == success + failed",
            d["completed"] == d["success"] + d["failed"],
            f"{d['completed']} != {d['success']}+{d['failed']}")
        implied = d["completed"] / d["wall_time_seconds"] if d["wall_time_seconds"] else 0
        tol = max(3.0, d["requests_per_second"] * 0.005)
        chk(f"{label}: RPS matches completed/wall_time",
            abs(implied - d["requests_per_second"]) < tol,
            f"implied={implied:.2f} stated={d['requests_per_second']:.2f}")
        lm = d["latency_ms"]
        chk(f"{label}: p50 <= p95 <= p99 <= max",
            lm["p50"] <= lm["p95"] <= lm["p99"] <= lm["max"])
        chk(f"{label}: status codes sum to completed",
            sum(d["status_counts"].values()) == d["completed"])
        non2xx = [k for k in d["status_counts"] if not str(k).startswith("2")]
        if d["failed"] == 0:
            chk(f"{label}: all responses 2xx", not non2xx, f"non-2xx codes: {non2xx}")

    # ramp test file (separate structure)
    ramp = results_dir / "ramp_test.json"
    if ramp.exists():
        data = json.loads(ramp.read_text())
        levels = []
        for phase in ("read_phase", "write_phase"):
            for r in data.get(phase, []):
                levels.append(r)
                lm = r["latency_ms"]
                chk(f"ramp {r['label']}: completed == success + failed",
                    r["completed"] == r["success"] + r["failed"])
                chk(f"ramp {r['label']}: percentile order",
                    lm["p50"] <= lm["p95"] <= lm["p99"] <= lm["max"])
        total_ramp = sum(r["requests"] for r in levels)
        fails_ramp = sum(r["failed"] for r in levels)
        print(f"\n  ramp levels checked: {len(levels)} "
              f"({total_ramp} requests, {fails_ramp} failures)")

    total = sum(d["completed"] for _, d in measurements)
    fails = sum(d["failed"] for _, d in measurements)
    print(f"\n=== AGGREGATES over {len(measurements)} measurement files ===")
    print(f"  total completed requests : {total}")
    print(f"  failed requests          : {fails}")
    print(f"  success rate             : {100.0 * (total - fails) / total:.3f}%" if total else "")

    print(f"\n{'=' * 50}\nCONSISTENCY VERIFICATION: PASS={passed} FAIL={failed}\n{'=' * 50}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
