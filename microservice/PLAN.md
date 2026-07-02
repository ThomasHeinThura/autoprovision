# TaskDesk — Plan & Architecture

> Working name: **TaskDesk** (change anytime). A multi-tenant, Jira-style **project & task
> management** tool with a built-in **customer support portal**. External clients raise tickets;
> internal teams triage and resolve them as work items on boards, organized into projects.

Status: **PLANNING** — no application code yet. This document is the source of truth for features,
service boundaries, data model, auth, networking, and GitOps. Next step after sign-off: design the
UI/UX as static HTML (workflow-first), then implement service by service.

---

## 1. Vision & scope

TaskDesk unifies two experiences over one domain:

- **Customer Portal** — customers of a tenant submit support requests ("tickets"), track status,
  reply to agents, and see SLAs. Minimal, focused, self-service.
- **Team Workspace** — internal agents/teams manage all incoming tickets *and* their own internal
  work (tasks, bugs) as **work items** on Kanban/agile **boards**, grouped into **projects**, with
  assignments, comments, labels, SLAs, and dashboards.

A **ticket** and an internal **task** are the same underlying entity — a **Work Item** with a
`type` — so one board and one workflow engine serve both. This is what keeps the domain small while
covering "Jira + Service Management."

**Reusable by design:** any org running client support + internal delivery (agencies, MSPs,
software teams, internal IT/ops desks) can adopt it.

---

## 2. Platform context (already in this repo)

This app deploys onto the existing platform — reuse, don't reinvent:

- **RKE2** Kubernetes cluster.
- **Istio ambient mesh** with a cluster-wide **`shared-gateway`** (istio-system) + Gateway API
  **`HTTPRoute`** for host/path routing and TLS. Pattern reference: [../echo.yaml](../echo.yaml).
- **WSO2 API Manager** — mandatory API gateway in front of **every** backend (subscriptions,
  rate-limiting, OAuth2 token validation, analytics). *WSO2 IS is NOT used.*
- **Keycloak** *(to be added)* — identity provider (users, login, OAuth2/OIDC, roles), wired into
  WSO2 APIM as a **third-party Key Manager**.
- **MSSQL** — relational store (see [../microservice/credential](./credential)).
- **ArgoCD** — GitOps from `github.com/ThomasHeinThura/autoprovision.git`. Pattern reference:
  [../echo-argocd-app.yaml](../echo-argocd-app.yaml).
- **Valkey** *(to be added)* — cache, sessions, realtime pub/sub, SLA timers.

---

## 3. Roles & personas

Roles live in **Keycloak** and are carried in the OAuth2 token; backends authorize on them.

| Role | Who | Can do |
|---|---|---|
| `customer` | External client of a tenant | Create/track own tickets, reply, view own SLA. Portal only. |
| `agent` | Internal support/team member | Work all items on projects they're a member of; comment (public+internal); assign; transition status. |
| `project_admin` | Team lead | Agent + manage project settings, boards, workflow, SLA policies, members. |
| `org_admin` | Tenant owner | Everything in the tenant: projects, users, billing/plan, org settings. |
| `platform_admin` | Us (operator) | Cross-tenant admin (guarded, separate Keycloak realm/role). |

Every user belongs to exactly one **Organization (tenant)**. Multi-tenancy is enforced on every
query by `organization_id` (row-level scoping).

---

## 4. Features

### 4.1 MVP (Phase 1 — the "full-blown deployable" first cut)

**Customer Portal**
- Sign up / log in (Keycloak); join an org via invite.
- Create a ticket: title, description, type (Incident / Service Request / Question), priority, attachments.
- List & filter my tickets; view detail with full comment thread.
- Reply to a ticket; see status + SLA countdown.
- Email/realtime notification on status change or agent reply.

**Team Workspace**
- Projects: create, key (e.g. `SUP`, `WEB`), members, description.
- Boards: Kanban columns mapped to workflow statuses; drag work items between columns.
- Work Items (unified ticket/task): type (Ticket / Task / Bug), status, priority, assignee,
  reporter, labels, due date, description, comments (public vs **internal note**), activity log.
- Queue/triage view of incoming customer tickets; assign to agent; convert into board work.
- Search & filter (by project, status, assignee, label, text) — served by **Go**.
- SLA policies (response time, resolution time) per priority; live countdown; breach flagging.
- Realtime: board updates, new comments, presence — served by **Node**.
- Dashboards: open vs resolved, SLA compliance, workload by assignee — served by **Go**.
- Audit/activity trail on every work item.

### 4.2 Phase 2 (later)

- Agile: sprints, backlog, story points, burndown.
- Workflow editor (custom statuses/transitions per project).
- Automations/rules ("when priority = high → assign to on-call").
- Canned responses / knowledge base articles.
- File storage backend (S3/MinIO) — MVP stores attachment **metadata** only.
- CSAT surveys after resolution.
- Webhooks / public REST API product in WSO2 APIM for integrations.
- Reporting exports (CSV/PDF).

### 4.3 Explicit non-goals (for now)

- No WSO2 Identity Server. No eID/credential issuance. No billing gateway integration in Phase 1.

---

## 5. Service responsibilities (bounded contexts)

Folders under [./](.) — one deployable per folder, each behind WSO2 APIM.

### 5.1 `app1.backend` — **.NET** (flagship / system of record)
- **Owns MSSQL.** All writes to the core domain go here.
- Domain: Organizations, Users (mirror of Keycloak), Projects, Boards/Columns, Work Items, Comments,
  Labels, Attachments (metadata), SLA policies + timers, Workflow statuses/transitions, Audit log.
- Business rules: workflow transitions, SLA start/pause/stop, permission checks, tenant scoping.
- Emits **domain events** to Valkey pub/sub on every mutation (for Node realtime + Go read models).
- EF Core migrations own the schema.
- Stack: ASP.NET Core (.NET 8/9) Web API, EF Core + SQL Server provider, StackExchange.Redis
  (Valkey-compatible) for cache/pub-sub.

### 5.2 `app2.backend` — **Go** (read/compute plane)
- **Stateless, high-throughput reads.** No writes to the domain.
- Search & filtering across work items (project/status/assignee/label/full-text).
- Reporting & dashboard aggregations (counts, SLA compliance %, workload).
- SLA-breach scanner: reads SLA timer set from Valkey (sorted set by due time), flags/reports breaches.
- Reads from MSSQL (read-optimized queries / read replica later) and Valkey caches.
- Stack: Go (net/http or chi/echo), `database/sql` + `go-mssqldb`, `redis/go-redis`.

### 5.3 `app3.backend` — **Node.js** (BFF + realtime)
- **Backend-for-frontend** for the React app: aggregates .NET + Go calls into view-shaped responses.
- **Realtime**: WebSocket/SSE for board updates, new comments, presence — subscribes to Valkey
  pub/sub (events published by .NET) and fans out to connected clients.
- Session/presence state in Valkey.
- Stack: Node (TypeScript) + Fastify/Express, `ws`/socket.io, `ioredis`.

### 5.4 `Frontend` — **React** (SPA)
- Two routed experiences behind one app: **Customer Portal** + **Team Workspace**.
- Talks to **Node BFF** for reads/realtime and to .NET/Go **via APIM** for actions where appropriate.
- Auth via Keycloak (OIDC Authorization Code + PKCE).
- Served by nginx; exposed through the Istio `shared-gateway`.
- Stack: React + Vite + TypeScript, React Router, TanStack Query, WebSocket client.

### 5.5 `cache` — **Valkey**
- Roles: hot-read cache (project/board/permission lookups), **sessions**, **realtime pub/sub**,
  **SLA timer** sorted sets, rate-limit counters (secondary to APIM).
- Deployed as a StatefulSet + PVC (single node MVP; Sentinel/cluster later).

### 5.6 Communication summary

```
                       ┌────────────── Keycloak (OIDC) ──────────────┐
                       │  login / tokens (customers + agents)         │
  Browser (React) ──►  Istio shared-gateway ──► Node BFF ──► .NET (writes) ──► MSSQL
       │                                          │   └────► Go   (search/report)
       │                                          └────────► Valkey (sessions, pub/sub)
       └── public/API traffic ──► WSO2 APIM ──► (.NET | Go | Node) backends
                                   (token validation via Keycloak Key Manager,
                                    rate-limit, subscriptions, analytics)

  .NET  ──publishes domain events──►  Valkey pub/sub  ──►  Node  ──WebSocket──►  Browser
```

---

## 6. Data model (MSSQL, owned by .NET)

Core tables (Phase 1). All tenant-scoped tables carry `organization_id`.

- **Organization** — `id, name, slug, plan, created_at`.
- **User** — `id (=Keycloak sub), organization_id, email, display_name, role, is_active`.
- **Project** — `id, organization_id, key, name, description, lead_user_id, created_at`.
- **ProjectMember** — `project_id, user_id, role_in_project`.
- **Board** — `id, project_id, name`; **BoardColumn** — `id, board_id, name, status_id, order`.
- **WorkflowStatus** — `id, project_id, name, category (todo|in_progress|done)`.
- **WorkItem** — `id, organization_id, project_id, key (e.g. SUP-42), type (ticket|task|bug),
  title, description, status_id, priority, reporter_user_id, assignee_user_id, requester_user_id
  (customer, nullable), due_at, created_at, updated_at`.
- **Comment** — `id, work_item_id, author_user_id, body, is_internal (bool), created_at`.
- **Label** — `id, organization_id, name, color`; **WorkItemLabel** — `work_item_id, label_id`.
- **Attachment** — `id, work_item_id, filename, content_type, size, storage_key, created_at`
  (metadata only in Phase 1).
- **SlaPolicy** — `id, project_id, priority, response_minutes, resolution_minutes`.
- **SlaTimer** — `id, work_item_id, type (response|resolution), started_at, due_at, paused_at,
  breached (bool), completed_at`.
- **ActivityLog** — `id, work_item_id, actor_user_id, verb, from_value, to_value, created_at`.

Relationships: Organization 1─* Project 1─* WorkItem 1─* Comment / Attachment / SlaTimer /
ActivityLog. WorkItem *─* Label. Board 1─* BoardColumn ↔ WorkflowStatus.

---

## 7. API surface (representative)

Convention: `/api/v1/...`. **Public** = published in WSO2 APIM (subscription + token required).
**Internal** = mesh-only, called by Node BFF.

### .NET (`app1.backend`) — writes & system of record
- `POST /api/v1/tickets` *(public, customer)* — create ticket.
- `GET  /api/v1/workitems/{key}` *(public/internal)* — detail.
- `POST /api/v1/workitems` `PATCH /api/v1/workitems/{key}` — create/update work item.
- `POST /api/v1/workitems/{key}/transition` — move status (workflow-validated).
- `POST /api/v1/workitems/{key}/comments` — add comment (public/internal note).
- `POST /api/v1/workitems/{key}/assign` — assign.
- `CRUD /api/v1/projects`, `/api/v1/projects/{key}/board`, `/api/v1/sla-policies`.
- `POST /api/v1/webhooks/keycloak` — user sync from Keycloak events.

### Go (`app2.backend`) — reads/compute
- `GET /api/v1/search?project=&status=&assignee=&label=&q=&page=` — filtered search.
- `GET /api/v1/reports/overview?project=` — open/resolved/SLA counts.
- `GET /api/v1/reports/workload?project=` — items per assignee.
- `GET /api/v1/sla/breaches?project=` — current + upcoming breaches.

### Node (`app3.backend`) — BFF + realtime
- `GET /bff/portal/home`, `GET /bff/workspace/board/{projectKey}` — view-shaped aggregations.
- `WS  /realtime` — subscribe to project/work-item channels (board updates, comments, presence).

---

## 8. Auth & security

- **Keycloak** realm `taskdesk` (plus separate `platform` realm for operators).
  - Clients: `taskdesk-spa` (public, Auth Code + PKCE for React), `taskdesk-apim` (for APIM Key
    Manager integration), optional `taskdesk-bff` (confidential, Node).
  - Roles: `customer`, `agent`, `project_admin`, `org_admin` → mapped into token claims.
  - `organization_id` carried as a token claim / user attribute for tenant scoping.
- **WSO2 APIM** validates Keycloak-issued JWTs (Keycloak configured as **third-party Key Manager**);
  enforces subscriptions, rate limits, and captures analytics. **All backend traffic** transits APIM.
- Backends re-validate the JWT (signature + audience + roles) and enforce **tenant scoping** on
  every query — defense in depth; never trust the gateway alone.
- Secrets (MSSQL creds, Keycloak client secrets) via Kubernetes Secrets / sealed-secrets; never in git.
  Current plaintext [./credential](./credential) is a dev placeholder to be replaced.

---

## 9. Caching & realtime strategy (Valkey)

| Use | Structure | Owner |
|---|---|---|
| Session / presence | `sess:{sid}` hash, `presence:{projectId}` set | Node |
| Hot reads (project/board/permission) | `proj:{id}` / `board:{id}` JSON, TTL | .NET writes, all read |
| Realtime events | pub/sub channels `events:project:{id}` | .NET pub → Node sub |
| SLA timers | sorted set `sla:due` (score = due epoch) | .NET writes, Go scans |
| Report cache | `report:{project}:{name}` JSON, short TTL | Go |
| Rate-limit (secondary) | counters | any (APIM is primary) |

Realtime flow: .NET mutates → publishes `events:project:{id}` → Node fans out over WebSocket to
subscribed browsers. Cache invalidation is event-driven off the same publish.

---

## 10. Networking & ingress

- **Frontend + BFF + internal service-to-service** → Istio **`shared-gateway`** via `HTTPRoute`
  (host-based, e.g. `taskdesk.example.com`), namespace enrolled in the ambient mesh (mirror
  [../echo.yaml](../echo.yaml)).
- **Public/partner APIs** → **WSO2 APIM** gateway (auth, rate-limit, analytics), which forwards to
  the in-cluster Services.
- Suggested hosts: `taskdesk.example.com` (SPA), `api.taskdesk.example.com` (APIM-fronted APIs).
- One namespace: `taskdesk` (ambient-enrolled). Keycloak + Valkey either in-namespace or shared
  infra namespace — TBD (see open questions).

---

## 11. Repo & folder structure

```
microservice/
├── PLAN.md                     # this file
├── credential                  # dev secrets placeholder (to be replaced by k8s Secrets)
├── app1.backend/               # .NET flagship
│   ├── src/                    # ASP.NET Core solution
│   ├── Dockerfile
│   └── k8s/                    # Deployment, Service, HTTPRoute, config, (APIM API def)
├── app2.backend/               # Go read/compute
│   ├── cmd/ internal/
│   ├── Dockerfile
│   └── k8s/
├── app3.backend/               # Node BFF + realtime
│   ├── src/
│   ├── Dockerfile
│   └── k8s/
├── Frontend/                   # React SPA
│   ├── src/  (+ /ui prototype HTML during design phase)
│   ├── Dockerfile              # multi-stage → nginx
│   └── k8s/
├── cache/                      # Valkey
│   └── k8s/                    # StatefulSet, Service, PVC
└── argocd/                     # app-of-apps + child Applications (see §12)
```

---

## 12. GitOps / ArgoCD

**App-of-apps.** One root `Application` points at `microservice/argocd/`, which contains a child
`Application` per deployable, each pointing at its `k8s/` dir. Mirror the conventions in
[../echo-argocd-app.yaml](../echo-argocd-app.yaml): `finalizers`, `project: default`,
`syncPolicy.automated { prune, selfHeal }`, repo `autoprovision.git`, `targetRevision: main`.

```
argocd/
├── root-app.yaml               # app-of-apps → microservice/argocd/apps
└── apps/
    ├── taskdesk-namespace.yaml
    ├── valkey.yaml
    ├── keycloak.yaml
    ├── app1-dotnet.yaml
    ├── app2-go.yaml
    ├── app3-node.yaml
    └── frontend.yaml
```

Sync order via sync-waves: namespace → Valkey/Keycloak → .NET (migrations) → Go/Node → Frontend.

---

## 13. Cross-cutting concerns

- **Config**: env via ConfigMaps; secrets via Secrets. 12-factor.
- **DB migrations**: EF Core migrations run as an init job/ArgoCD PreSync hook before .NET rollout.
- **Health**: `/healthz` (live) + `/readyz` (ready incl. DB/Valkey) on every backend; k8s probes.
- **Observability**: structured logs; OpenTelemetry traces (Istio gives L7 metrics free); expose
  Prometheus metrics.
- **Resource hygiene**: requests/limits + `securityContext { runAsNonRoot, allowPrivilegeEscalation:false }`
  on every pod (match [../echo.yaml](../echo.yaml)).
- **Images**: multi-stage Dockerfiles, non-root, pinned base tags.

---

## 14. Delivery phases

1. **Design (now)** — sign off this plan → build static **HTML UI/UX prototype** (workflow-first)
   under `Frontend/ui/` for both Portal and Workspace. *No backend yet.*
2. **Vertical slice** — .NET + MSSQL for Work Items + Projects; one board end-to-end; Dockerized;
   deployed via ArgoCD behind APIM. Proves the pipeline.
3. **Read/compute + realtime** — Go search/reports + Node BFF/WebSocket + Valkey.
4. **React SPA** — implement the signed-off UI against the BFF; Keycloak login.
5. **Support features** — SLA timers/breaches, notifications, customer portal polish.
6. **Phase 2 backlog** — sprints, workflow editor, automations, storage, webhooks.

---

## 15. Open questions

1. **Hosts/domains** — confirm `*.example.com` vs your real domain for the `HTTPRoute`s + APIM.
2. **Keycloak deploy** — Operator vs Helm chart? Own namespace vs `taskdesk`?
3. **Valkey topology** — single node (MVP) vs Sentinel/HA now?
4. **APIM Key Manager wiring** — confirm APIM version supports Keycloak as third-party KM in your install.
5. **Attachments** — metadata-only for Phase 1, or stand up MinIO now?
6. **Tenant model** — one org per customer company (B2B) confirmed? Any need for a user to span orgs?
```
