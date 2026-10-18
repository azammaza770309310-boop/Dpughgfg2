#!/usr/bin/env python3
"""CrowdCloud load generator — an ApacheBench-equivalent benchmark tool.

Why this exists
---------------
ApacheBench (`ab`) is the tool suggested by the course project brief.
The environment used to produce the official results for this report did
not include the `ab` binary and it could not be installed (no root
privileges, no network package manager access).  The brief explicitly
allows an equivalent tool, so this module reproduces ab's core metrics
using only the Python standard library:

* number of requests and concurrency level
* requests per second (throughput)
* time per request: mean, median (p50), p90, p95, p99, min, max
* failed requests (non-2xx statuses and connection errors)

Keep-alive connections are used per worker thread, exactly like ab.

The repository also ships the equivalent `ab` command lines in
benchmarks/ab_commands.txt so the same matrix can be re-run with
ApacheBench on a machine that has it.
"""

from __future__ import annotations

import argparse
import http.client
import json
import threading
import time
from urllib.parse import urlparse


def percentile(sorted_values: list, p: float) -> float:
    """Linear-interpolated percentile over a sorted list (ms)."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def run_benchmark(
    base_url: str,
    path: str,
    method: str,
    total_requests: int,
    concurrency: int,
    body: str | None,
    content_type: str,
    timeout: float,
) -> dict:
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    latencies: list = []          # milliseconds, every completed request
    status_counts: dict = {}
    errors: list = []
    lock = threading.Lock()

    base_share, remainder = divmod(total_requests, concurrency)

    def worker(worker_index: int, count: int):
        conn = None
        local_lat = []
        local_status = {}
        for _ in range(count):
            started = time.perf_counter()
            try:
                if conn is None:
                    conn = http.client.HTTPConnection(host, port, timeout=timeout)
                headers = {
                    "Host": host,
                    "Connection": "keep-alive",
                    "User-Agent": "crowdcloud-bench/1.0",
                }
                if body is not None:
                    headers["Content-Type"] = content_type
                conn.request(method, path, body=body, headers=headers)
                response = conn.getresponse()
                response.read()
                elapsed = (time.perf_counter() - started) * 1000.0
                local_lat.append(elapsed)
                local_status[response.status] = local_status.get(response.status, 0) + 1
            except Exception as exc:  # connection reset, timeout, ...
                elapsed = (time.perf_counter() - started) * 1000.0
                local_lat.append(elapsed)
                local_status["error"] = local_status.get("error", 0) + 1
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None
                if len(errors) < 20:
                    errors.append(f"{type(exc).__name__}: {exc}")
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        with lock:
            latencies.extend(local_lat)
            for key, value in local_status.items():
                status_counts[key] = status_counts.get(key, 0) + value

    threads = []
    wall_start = time.perf_counter()
    for i in range(concurrency):
        count = base_share + (1 if i < remainder else 0)
        if count == 0:
            continue
        t = threading.Thread(target=worker, args=(i, count))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    wall_seconds = time.perf_counter() - wall_start

    success = sum(v for k, v in status_counts.items() if isinstance(k, int) and 200 <= k < 300)
    failed = total_requests - success
    lat_sorted = sorted(latencies)

    return {
        "tool": "crowdcloud-bench/1.0 (Python stdlib, ab-equivalent)",
        "url": base_url + path,
        "method": method,
        "requests": total_requests,
        "concurrency": concurrency,
        "completed": len(latencies),
        "success": success,
        "failed": failed,
        "status_counts": {str(k): v for k, v in sorted(status_counts.items(), key=lambda kv: str(kv[0]))},
        "sample_errors": errors,
        "requests_per_second": round(total_requests / wall_seconds, 2) if wall_seconds else 0.0,
        "wall_time_seconds": round(wall_seconds, 3),
        "latency_ms": {
            "min": round(lat_sorted[0], 2) if lat_sorted else 0,
            "mean": round(sum(lat_sorted) / len(lat_sorted), 2) if lat_sorted else 0,
            "p50": round(percentile(lat_sorted, 50), 2),
            "p66": round(percentile(lat_sorted, 66), 2),
            "p75": round(percentile(lat_sorted, 75), 2),
            "p90": round(percentile(lat_sorted, 90), 2),
            "p95": round(percentile(lat_sorted, 95), 2),
            "p99": round(percentile(lat_sorted, 99), 2),
            "max": round(lat_sorted[-1], 2) if lat_sorted else 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    parser.add_argument("--path", default="/api/services")
    parser.add_argument("--method", default="GET")
    parser.add_argument("-n", "--num", type=int, default=100, help="total requests")
    parser.add_argument("-c", "--concurrency", type=int, default=1, help="parallel workers")
    parser.add_argument("--body", default=None, help="request body (e.g. JSON text)")
    parser.add_argument("--content-type", default="application/json")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("-o", "--output", default=None, help="write results JSON here")
    parser.add_argument("--label", default=None, help="label stored in the JSON result")
    args = parser.parse_args()

    method = args.method.upper()
    body = args.body if method in ("POST", "PUT", "PATCH") else None

    result = run_benchmark(
        args.url,
        args.path,
        method,
        max(1, args.num),
        max(1, args.concurrency),
        body,
        args.content_type,
        args.timeout,
    )
    if args.label:
        result["label"] = args.label

    lat = result["latency_ms"]
    print(f"URL:                {result['url']}")
    print(f"Method:             {method}   body={'yes' if body else 'no'}")
    print(f"Requests:           {result['requests']}  (concurrency {result['concurrency']})")
    print(f"Completed:          {result['completed']}")
    print(f"Successful (2xx):   {result['success']}")
    print(f"Failed:             {result['failed']}")
    print(f"Requests/second:    {result['requests_per_second']}")
    print(f"Wall time (s):      {result['wall_time_seconds']}")
    print(f"Latency (ms):  min={lat['min']}  mean={lat['mean']}  p50={lat['p50']}  "
          f"p90={lat['p90']}  p95={lat['p95']}  p99={lat['p99']}  max={lat['max']}")
    if result["sample_errors"]:
        print(f"Sample errors:      {result['sample_errors'][:3]}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        print(f"Saved JSON -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
