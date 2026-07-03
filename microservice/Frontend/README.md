# Frontend — TaskDesk React SPA

Vite + React + TypeScript SPA (charco theme, dark/light). Talks to the **BFF (app3)** over
same-origin `/bff/*` + `/realtime` (proxied by Vite in dev, by nginx in prod). This is the initial
SPA slice — Login, Dashboard, Projects, Board, and the Work-item drawer — wired to **live data** with
**realtime** updates. The richer, fully-featured design reference remains the static prototype in
[`ui/`](ui/) (served at `/ui`).

## Run locally (dev)

```bash
npm install
npm run dev        # http://localhost:5173  (proxies /bff + /realtime → app3 on :8082)
```
Needs app1 + app3 running (or the whole `docker compose` stack). Build: `npm run build` → `dist/`.

## What's wired

- **Login** — pick Customer / Team (no real auth yet; Keycloak is Phase 4).
- **Dashboard** (team) — totals + project cards from `/bff/overview`; live "Realtime connected" dot.
- **Projects** — cards from `/bff/projects`.
- **Board** — columns from `/bff/projects/:key/board`; click a card → drawer.
- **Drawer** — detail from `/bff/workitems/:key`; team can change **status** and post replies /
  **internal notes**; customers see the public conversation only. Writes go through app3 and
  **broadcast** so other clients refresh live.

## Deploy

Multi-stage [`Dockerfile`](Dockerfile) builds the SPA and serves it via nginx ([`nginx.conf`](nginx.conf)
proxies `/bff` + `/realtime` → the `app3` Service). Manifests in [`k8s/`](k8s/); ArgoCD app at
[`../argocd/apps/frontend.yaml`](../argocd/apps/frontend.yaml).
