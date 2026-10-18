#!/usr/bin/env python3
"""Gradual stress (ramp) test for CrowdCloud.

Purpose
-------
The benchmark matrix in ``run_benchmarks.sh`` measures fixed load levels
(L1-L4).  This script goes further: it *ramps* the concurrency upward
step by step while the server keeps running, until throughput stops
growing or latency clearly degrades.  The output answers:

* At which concurrency does the system reach peak throughput (RPS)?
* At which concurrency does performance start to *decline* (the knee)?
* When do the first failed requests appear?

Levels are run against the SAME running server, so queue state grows
exactly like it would under a real, sustained traffic surge.  A read
phase (GET /api/services) and a write phase (POST /api/tickets) are both
ramped, because writes exercise SQLite's write lock and are the
bottleneck under contention.

Usage
-----
    # server must already be running, e.g.:
    #   CROWDCLOUD_DB=/tmp/ramp.db gunicorn --workers 4 --threads 2 \
    #        --bind 127.0.0.1:5000 run:app
    python3 benchmarks/ramp_test.py --url http://127.0.0.1:5000 \
        -o benchmarks/results/ramp_test.json

No third-party packages are used (Python stdlib only), consistent with
benchmarks/bench.py.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Reuse the ab-equivalent load generator from bench.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench import run_benchmark  # noqa: E402

DEFAULT_LEVELS = [10, 25, 50, 100, 200, 400, 800]
WRITE_BODY = '{"service_code": "it_support", "customer_name": "ramp-test"}'


def http_post_json(url: str, payload: dict | None = None, timeout: float = 30.0):
    """Small helper for control calls (demo reset / stats)."""
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def ramp_phase(base_url: str, method: str, path: str, body: str | None,
               levels: list[int], requests_factor: int, min_requests: int,
               reset_between: bool, label: str) -> list[dict]:
    """Run one ramp phase; return list of per-level result dicts."""
    results = []
    for c in levels:
        n = max(min_requests, c * requests_factor)
        if reset_between:
            try:
                http_post_json(f"{base_url}/api/demo/reset")
                time.sleep(0.3)
            except Exception as exc:  # reset is best-effort
                print(f"  (demo reset skipped: {exc})")
        print(f"  [{label}] c={c:>4}  n={n:>5} ...", end=" ", flush=True)
        r = run_benchmark(
            base_url, path, method, n, c, body, "application/json", 60.0
        )
        r["label"] = f"{label}_c{c}"
        r["level_concurrency"] = c
        results.append(r)
        lat = r["latency_ms"]
        print(
            f"RPS={r['requests_per_second']:>8.1f}  "
            f"mean={lat['mean']:>7.1f}ms  p95={lat['p95']:>7.1f}ms  "
            f"p99={lat['p99']:>7.1f}ms  failed={r['failed']}"
        )
        time.sleep(1.0)  # cool-down between levels
    return results


def analyze(results: list[dict]) -> dict:
    """Locate peak throughput, the degradation knee, and first failures."""
    if not results:
        return {}
    peak = max(results, key=lambda r: r["requests_per_second"])
    peak_idx = results.index(peak)

    baseline_p95 = results[0]["latency_ms"]["p95"] or 1.0
    knee_idx = None
    first_fail_idx = None
    for i, r in enumerate(results):
        if first_fail_idx is None and r["failed"] > 0:
            first_fail_idx = i
        if knee_idx is None and i > peak_idx:
            rps_drop = (peak["requests_per_second"] - r["requests_per_second"]) / peak["requests_per_second"]
            p95_ratio = r["latency_ms"]["p95"] / baseline_p95
            # knee = throughput fell >10% below peak OR p95 tripled vs baseline
            if rps_drop > 0.10 or p95_ratio >= 3.0:
                knee_idx = i
    return {
        "peak_rps": peak["requests_per_second"],
        "peak_concurrency": peak["level_concurrency"],
        "peak_is_last_level": peak_idx == len(results) - 1,
        "knee_concurrency": results[knee_idx]["level_concurrency"] if knee_idx is not None else None,
        "knee_reason": (
            "throughput fell >10% below peak and/or p95 latency reached 3x the c=10 baseline"
            if knee_idx is not None else
            "no degradation observed within the tested concurrency range"
        ),
        "first_failed_requests_concurrency": (
            results[first_fail_idx]["level_concurrency"] if first_fail_idx is not None else None
        ),
        "peak_rps_relative_decline_at_max_level": round(
            1 - results[-1]["requests_per_second"] / peak["requests_per_second"], 3
        ) if peak["requests_per_second"] else 0.0,
    }


def to_markdown(read_results, write_results, read_a, write_a, meta) -> str:
    """Render the ramp results as a Markdown report fragment."""

    def table(rows, analysis, phase):
        lines = [
            f"### {phase} — GET vs POST ramp",
            "",
            "| concurrency | requests | success | failed | RPS | mean (ms) | p50 | p95 | p99 | max |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for r in rows:
            lat = r["latency_ms"]
            lines.append(
                f"| {r['level_concurrency']} | {r['requests']} | {r['success']} | "
                f"{r['failed']} | {r['requests_per_second']} | {lat['mean']} | "
                f"{lat['p50']} | {lat['p95']} | {lat['p99']} | {lat['max']} |"
            )
        return "\n".join(lines)

    parts = [
        "# Gradual Stress Test (Ramp) — Real Results",
        "",
        f"- Date (UTC): {meta['date']}",
        f"- Server: {meta['server']}",
        f"- Workers: {meta['workers']}",
        f"- Levels (concurrency): {meta['levels']}",
        f"- Reset between write levels: {meta['reset_between']}",
        "",
        table(read_results, read_a, "Read phase"),
        "",
        f"- Peak throughput: **{read_a.get('peak_rps')} RPS** at c={read_a.get('peak_concurrency')}",
        f"- Degradation knee: **c={read_a.get('knee_concurrency')}** — {read_a.get('knee_reason')}",
        f"- First failed requests at: **{read_a.get('first_failed_requests_concurrency') or 'none within tested range'}**",
        "",
        table(write_results, write_a, "Write phase"),
        "",
        f"- Peak throughput: **{write_a.get('peak_rps')} RPS** at c={write_a.get('peak_concurrency')}",
        f"- Degradation knee: **c={write_a.get('knee_concurrency')}** — {write_a.get('knee_reason')}",
        f"- First failed requests at: **{write_a.get('first_failed_requests_concurrency') or 'none within tested range'}**",
        "",
        "## Interpretation",
        "",
        "Read the knee column as the *practical concurrency ceiling* of this single",
        "container/instance. Below it, adding more simultaneous users still raises",
        "throughput; beyond it, latency grows without benefit. Horizontal scaling",
        "(docker-compose.scale.yml: nginx + replicated containers) is the cloud",
        "answer to push this ceiling upward, as analysed in the project report.",
        "",
    ]
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    parser.add_argument("-o", "--output", default="benchmarks/results/ramp_test.json")
    parser.add_argument("--levels", type=int, nargs="+", default=DEFAULT_LEVELS,
                        help="concurrency levels, increasing (default: 10 25 50 100 200 400 800)")
    parser.add_argument("--requests-factor", type=int, default=10,
                        help="requests per level = max(min_requests, c * factor)")
    parser.add_argument("--min-requests", type=int, default=3000,
                        help="minimum requests per level")
    parser.add_argument("--skip-write", action="store_true",
                        help="only ramp the read endpoint")
    parser.add_argument("--skip-read", action="store_true",
                        help="only ramp the write endpoint")
    parser.add_argument("--no-reset", action="store_true",
                        help="do NOT reset the demo state between write levels "
                             "(queue keeps growing — a sustained-surge simulation)")
    args = parser.parse_args()

    levels = sorted(set(args.levels))
    meta = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "server": args.url,
        "levels": levels,
        "requests_factor": args.requests_factor,
        "min_requests": args.min_requests,
        "reset_between": not args.no_reset,
    }

    # sanity: server reachable?
    try:
        with urllib.request.urlopen(f"{args.url}/healthz", timeout=10) as resp:
            assert resp.status == 200
    except Exception as exc:
        print(f"ERROR: server at {args.url} is not reachable ({exc}). Start it first.")
        return 2

    # capture effective worker count from /api/stats (context info)
    try:
        stats = json.loads(urllib.request.urlopen(f"{args.url}/api/stats", timeout=10).read())
        meta["queue_state_before"] = {
            "waiting": stats.get("waiting"),
            "serving": stats.get("serving"),
            "done": stats.get("done"),
        }
    except Exception:
        meta["queue_state_before"] = None
    meta["workers"] = "see run command in VERIFICATION.md (Gunicorn 4 workers x 2 threads unless noted)"

    print(f"=== READ RAMP: GET /api/services at levels {levels} ===")
    read_results = [] if args.skip_read else ramp_phase(
        args.url, "GET", "/api/services", None, levels,
        max(2, args.requests_factor // 2), max(1500, args.min_requests // 2),
        reset_between=False, label="read",
    )

    print(f"=== WRITE RAMP: POST /api/tickets at levels {levels} ===")
    write_results = [] if args.skip_write else ramp_phase(
        args.url, "POST", "/api/tickets", WRITE_BODY, levels,
        args.requests_factor, args.min_requests,
        reset_between=not args.no_reset, label="write",
    )

    read_a = analyze(read_results)
    write_a = analyze(write_results)

    payload = {
        "test": "gradual_stress_ramp",
        "meta": meta,
        "read_phase": read_results,
        "write_phase": write_results,
        "read_analysis": read_a,
        "write_analysis": write_a,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRaw JSON results saved to {out}")

    md = to_markdown(read_results, write_results, read_a, write_a, meta)
    md_path = out.with_suffix(".md")
    md_path.write_text(md, encoding="utf-8")
    print(f"Markdown summary saved to {md_path}")

    print("\n=== RAMP SUMMARY ===")
    if read_a:
        print(f"READ : peak {read_a['peak_rps']} RPS @ c={read_a['peak_concurrency']} | "
              f"knee c={read_a['knee_concurrency']} | first failure c={read_a['first_failed_requests_concurrency']}")
    if write_a:
        print(f"WRITE: peak {write_a['peak_rps']} RPS @ c={write_a['peak_concurrency']} | "
              f"knee c={write_a['knee_concurrency']} | first failure c={write_a['first_failed_requests_concurrency']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
