# app1.backend — TaskDesk core API (.NET)

The **core API / system of record** (PLAN [ADR-001, §5.1](../PLAN.md)). Serves reads **and** writes
(no premature read/write split), API-first, with the **module registry** (plugin contract, §14/§20)
built in. This is the Phase-2 vertical slice: Customers · Projects · Work Items · Comments · Activity
· Modules.

## Run locally (no dependencies)

Uses **SQLite** by default — nothing else to install. Schema is created and demo data seeded on boot.

```bash
cd src
ASPNETCORE_URLS=http://localhost:5199 dotnet run
# → http://localhost:5199/api/v1/projects
# → http://localhost:5199/openapi/v1.json
```

Or containerised (one command):

```bash
docker compose up --build      # → http://localhost:8080/api/v1/projects
```

## Endpoints (`/api/v1`)

| Method | Path | Notes |
|---|---|---|
| GET  | `/healthz`, `/readyz` | liveness / readiness (DB check) |
| GET  | `/customers` | client companies |
| GET  | `/projects` `?customer=ACME` | list (optionally by customer) |
| GET  | `/projects/{key}` | one project |
| POST | `/projects` | create |
| GET  | `/projects/{key}/workitems` | items in a project |
| GET  | `/workitems/{key}` | detail + comments + activity |
| POST | `/workitems` | create (validates type/priority) |
| POST | `/workitems/{key}/transition` | change status (validated) |
| POST | `/workitems/{key}/comments` | public reply or internal note |
| GET  | `/reports/overview` `?customer=` | **gated by `managed_service` module** |
| GET  | `/modules` `?customer=` | effective on/off per module |
| POST | `/modules/{key}/toggle` | enable/disable global or per customer |

Module gating demo: `POST /modules/managed_service/toggle {"enabled":false}` → `/reports/overview`
returns **403 `module_disabled`**. Toggle back on → 200. This is the §14 plugin contract in code.

## Database

SQLite for dev. To move to **Postgres/MSSQL** (PLAN §19 Q7): add the EF provider package and swap
the single `UseSqlite(...)` line in [`src/Program.cs`](src/Program.cs) for `UseNpgsql(...)` /
`UseSqlServer(...)` reading a connection-string Secret. Entities/queries are provider-agnostic.

## Deploy (GitOps)

- Build & push the image from [`Dockerfile`](Dockerfile).
- Manifests in [`k8s/`](k8s/) (Namespace, Deployment, Service, HTTPRoute on the `shared-gateway`).
- ArgoCD picks it up via [`../argocd/apps/app1-dotnet.yaml`](../argocd/apps/app1-dotnet.yaml)
  (app-of-apps root: [`../argocd/root-app.yaml`](../argocd/root-app.yaml)).
- Public/partner traffic is fronted by **WSO2 APIM** (PLAN §10); the HTTPRoute is the in-mesh path.
