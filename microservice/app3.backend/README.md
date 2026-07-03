# app3.backend — TaskDesk BFF + realtime (Node)

The **backend-for-frontend + realtime gateway** (PLAN [§5.3](../PLAN.md)). Aggregates the core API
(app1) and the workers' cached report (Valkey) into view-shaped responses, and pushes live updates to
browsers over WebSocket. (Phase 3: this is where channel webhooks — Viber/email — will land.)

## Run locally

```bash
npm install
API_BASE=http://localhost:5199 REDIS_ADDR=localhost:6379 npm start
# REDIS_ADDR optional — omit to run without realtime/cache
```

## Endpoints

| Path | Notes |
|---|---|
| `GET /healthz`, `/readyz` | health (readyz also pings app1 + Valkey) |
| `GET /bff/overview` | projects + workers report + totals |
| `GET /bff/projects` `?customer=` | project list |
| `GET /bff/projects/:key/board` | work items grouped into columns |
| `GET /bff/workitems/:key` | detail + comments + activity |
| `GET /bff/modules` | effective module states |
| `POST /bff/workitems` · `/:key/transition` · `/:key/comments` | proxied to app1, then broadcast |
| `WS /realtime` | `hello` on connect; `event` (Valkey pub/sub) + `change` (on writes) |

## Config (env)

`PORT` (8082) · `API_BASE` (app1 base URL) · `REDIS_ADDR` (`host:port`, empty = disabled).
In compose: `API_BASE=http://app1:8080`, `REDIS_ADDR=valkey:6379`. k8s: [`k8s/`](k8s/), ArgoCD:
[`../argocd/apps/app3-node.yaml`](../argocd/apps/app3-node.yaml).
