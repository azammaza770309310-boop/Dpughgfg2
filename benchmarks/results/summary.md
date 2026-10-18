# CrowdCloud benchmark summary

| label | method | endpoint | n | c | RPS | mean (ms) | p50 | p95 | p99 | failed |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| api_services_L1 | GET | `5000/api/services` | 200 | 1 | 676.94 | 1.47 | 1.37 | 1.83 | 2.12 | 0 |
| api_services_L2 | GET | `5000/api/services` | 500 | 10 | 976.33 | 7.24 | 5.03 | 29.01 | 36.83 | 0 |
| api_services_L3 | GET | `5000/api/services` | 1000 | 50 | 1027.82 | 20.82 | 14.75 | 57.81 | 67.7 | 0 |
| api_ticket_create_L1 | POST | `5000/api/tickets` | 200 | 1 | 651.41 | 1.53 | 1.48 | 1.68 | 3.3 | 0 |
| api_ticket_create_L2 | POST | `5000/api/tickets` | 500 | 10 | 812.19 | 8.97 | 6.29 | 29.48 | 37.39 | 0 |
| api_ticket_create_L3 | POST | `5000/api/tickets` | 1000 | 50 | 805.8 | 32.13 | 25.62 | 91.43 | 118.33 | 0 |
| api_ticket_create_L4 | POST | `5000/api/tickets` | 2000 | 100 | 767.84 | 72.05 | 72.91 | 144.26 | 168.82 | 0 |
| control_healthz_L2 | GET | `5000/healthz` | 500 | 10 | 2083.76 | 2.85 | 1.97 | 7.08 | 24.54 | 0 |
| control_healthz_L3 | GET | `5000/healthz` | 1000 | 50 | 2405.17 | 3.36 | 1.4 | 10.89 | 30.35 | 0 |
| home_page_L1 | GET | `5000/` | 200 | 1 | 638.22 | 1.56 | 1.5 | 1.7 | 1.84 | 0 |
| home_page_L2 | GET | `5000/` | 500 | 10 | 981.21 | 8.07 | 5.43 | 31.74 | 40.3 | 0 |
| home_page_L3 | GET | `5000/` | 1000 | 50 | 905.65 | 28.38 | 23.81 | 63.92 | 78.98 | 0 |
