#!/usr/bin/env python3
"""Summarise benchmark JSON results into CSV + Markdown tables.

Usage:  python3 benchmarks/summarize.py [results_dir]
"""

from __future__ import annotations

import csv
import glob
import json
import os
import sys

RESULTS_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "results"
)


def load_results():
    rows = []
    for path in sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        lat = data["latency_ms"]
        rows.append(
            {
                "label": data.get("label", os.path.basename(path)),
                "endpoint": data["url"],
                "method": data["method"],
                "requests": data["requests"],
                "concurrency": data["concurrency"],
                "success": data["success"],
                "failed": data["failed"],
                "rps": data["requests_per_second"],
                "mean_ms": lat["mean"],
                "p50_ms": lat["p50"],
                "p90_ms": lat["p90"],
                "p95_ms": lat["p95"],
                "p99_ms": lat["p99"],
                "max_ms": lat["max"],
            }
        )
    return rows


def main() -> int:
    rows = load_results()
    if not rows:
        print(f"No JSON results found in {RESULTS_DIR}")
        return 1

    csv_path = os.path.join(RESULTS_DIR, "summary.csv")
    fieldnames = list(rows[0].keys())
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    md_path = os.path.join(RESULTS_DIR, "summary.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("# CrowdCloud benchmark summary\n\n")
        header = (
            "| label | method | endpoint | n | c | RPS | mean (ms) | "
            "p50 | p95 | p99 | failed |\n"
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|\n"
        )
        fh.write(header)
        for r in rows:
            endpoint = r["endpoint"].split(":", 2)[-1]  # strip scheme+host
            fh.write(
                f"| {r['label']} | {r['method']} | `{endpoint}` | "
                f"{r['requests']} | {r['concurrency']} | {r['rps']} | "
                f"{r['mean_ms']} | {r['p50_ms']} | {r['p95_ms']} | "
                f"{r['p99_ms']} | {r['failed']} |\n"
            )

    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")
    print()
    print(open(md_path, encoding="utf-8").read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
