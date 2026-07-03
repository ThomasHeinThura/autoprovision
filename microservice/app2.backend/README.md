# app2.backend — TaskDesk workers (Go)

The **background / async plane** (PLAN [§5.2](../PLAN.md)) — *not* a read plane (ADR-001). On a
ticker it scans the core API (`app1`), computes an overview / SLA-risk snapshot, **caches it in
Valkey**, and **publishes an event** (`taskdesk:events`). Small HTTP surface for health + inspection.

## Run locally

```bash
API_BASE=http://localhost:5199 REDIS_ADDR=localhost:6379 SCAN_INTERVAL=20s go run .
# REDIS_ADDR is optional — omit it to run without Valkey (in-memory only)
```

## Endpoints

| Path | Notes |
|---|---|
| `/healthz` | liveness |
| `/readyz` | ready (pings Valkey if configured) |
| `/workers/status` | api target, redis on/off, scan count, last snapshot |
| `/reports/overview` | last computed overview (projects/open/resolved/unassigned/urgentOpen) |

## Config (env)

| Var | Default | Meaning |
|---|---|---|
| `PORT` | `8081` | HTTP port |
| `API_BASE` | `http://localhost:5199` | core API (app1) base URL |
| `REDIS_ADDR` | *(empty)* | Valkey/Redis `host:port`; empty = disabled |
| `SCAN_INTERVAL` | `30s` | worker tick (Go duration) |

In the compose stack: `API_BASE=http://app1:8080`, `REDIS_ADDR=valkey:6379`.
Deploy manifests in [`k8s/`](k8s/); ArgoCD app at [`../argocd/apps/app2-go.yaml`](../argocd/apps/app2-go.yaml).
