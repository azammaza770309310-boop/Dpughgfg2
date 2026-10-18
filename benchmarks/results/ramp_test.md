# Gradual Stress Test (Ramp) — Real Results

- Date (UTC): 2026-10-06 23:34:47 UTC
- Server: http://127.0.0.1:5000
- Workers: see run command in VERIFICATION.md (Gunicorn 4 workers x 2 threads unless noted)
- Levels (concurrency): [10, 25, 50, 100, 200, 400, 800]
- Reset between write levels: True

### Read phase — GET vs POST ramp

| concurrency | requests | success | failed | RPS | mean (ms) | p50 | p95 | p99 | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 1500 | 1500 | 0 | 905.25 | 8.4 | 5.43 | 30.53 | 41.52 | 50.74 |
| 25 | 1500 | 1500 | 0 | 1012.91 | 19.54 | 15.01 | 46.87 | 62.1 | 78.64 |
| 50 | 1500 | 1500 | 0 | 985.48 | 32.19 | 26.46 | 76.78 | 83.76 | 90.33 |
| 100 | 1500 | 1500 | 0 | 995.38 | 37.81 | 30.5 | 90.14 | 100.77 | 140.14 |
| 200 | 1500 | 1500 | 0 | 1009.75 | 30.02 | 23.16 | 82.34 | 113.68 | 142.21 |
| 400 | 2000 | 2000 | 0 | 968.35 | 85.49 | 65.86 | 243.62 | 284.63 | 298.42 |
| 800 | 4000 | 4000 | 0 | 975.29 | 70.21 | 49.51 | 200.62 | 282.15 | 305.79 |

- Peak throughput: **1012.91 RPS** at c=25
- Degradation knee: **c=400** — throughput fell >10% below peak and/or p95 latency reached 3x the c=10 baseline
- First failed requests at: **none within tested range**

### Write phase — GET vs POST ramp

| concurrency | requests | success | failed | RPS | mean (ms) | p50 | p95 | p99 | max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 3000 | 3000 | 0 | 716.44 | 12.11 | 8.7 | 36.6 | 45.5 | 81.08 |
| 25 | 3000 | 3000 | 0 | 676.86 | 29.33 | 25.13 | 60.04 | 68.92 | 84.43 |
| 50 | 3000 | 3000 | 0 | 708.32 | 55.95 | 58.66 | 97.49 | 108.62 | 150.79 |
| 100 | 3000 | 3000 | 0 | 651.86 | 97.96 | 90.78 | 237.43 | 277.2 | 295.48 |
| 200 | 3000 | 3000 | 0 | 649.97 | 134.91 | 124.39 | 282.35 | 406.97 | 461.91 |
| 400 | 4000 | 4000 | 0 | 582.44 | 241.67 | 153.59 | 804.43 | 883.05 | 910.68 |
| 800 | 8000 | 8000 | 0 | 464.84 | 730.01 | 592.81 | 1822.06 | 2195.05 | 2296.27 |

- Peak throughput: **716.44 RPS** at c=10
- Degradation knee: **c=100** — throughput fell >10% below peak and/or p95 latency reached 3x the c=10 baseline
- First failed requests at: **none within tested range**

## Interpretation

Read the knee column as the *practical concurrency ceiling* of this single
container/instance. Below it, adding more simultaneous users still raises
throughput; beyond it, latency grows without benefit. Horizontal scaling
(docker-compose.scale.yml: nginx + replicated containers) is the cloud
answer to push this ceiling upward, as analysed in the project report.
