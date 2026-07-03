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
| `platform_admin` | Us (operator) | Cross-tenant super-admin — the **god mode** operator (§15). Separate Keycloak realm/role, step-up auth. |

Every user belongs to exactly one **Organization (tenant)**. Multi-tenancy is enforced on every
query by `organization_id` (row-level scoping). Capabilities are the product of **role × enabled
modules** (§14): a role can only exercise a capability if the owning module is on for that tenant.
The `platform_admin` bypasses tenant scoping only inside the guarded god-mode surface (§15).

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

> **Architecture decision (ADR-001) — right-sized, not read/write-split.** An earlier draft split
> the backend into a Go "read plane" + .NET "write plane" behind a Node BFF (a CQRS-ish pattern).
> That was **premature optimization** for our scale (an internal SI tool), buying complexity with no
> throughput evidence to justify it. **We've dropped the read/write split.** The three backends now
> divide by **genuine bounded responsibility**: .NET is the full core API (reads *and* writes), Go
> runs **background/async work**, Node is the **realtime + channel gateway**. A read replica / read
> plane can be re-introduced later *if* scale ever demands it — not an MVP concern. Polyglot is
> retained deliberately as a learning/showcase goal; a single modular monolith would be an equally
> valid, simpler choice, and nothing here forbids collapsing later.

### 5.1 `app1.backend` — **.NET** (core API / system of record)
- **Owns the database.** Full domain: Organizations, **Customers**, Users, Projects, Boards, Work
  Items, Comments, Labels, Attachments (metadata), SLA policies + timers, Workflow, **Contracts/AMC +
  hour bank**, ActivityLog — plus the **module registry** (§14), **god-mode/platform config** (§15),
  and **access-code** records (§8).
- Serves **both reads and writes** (list/search/reports included) — no separate read plane.
- Business rules: workflow transitions, SLA start/pause/stop, hour-bank deduction, permission +
  **module-gate** checks, tenant scoping.
- Emits **domain events** to Valkey pub/sub on every mutation (consumed by Node realtime + Go workers).
- Stack: ASP.NET Core (.NET 8/9), EF Core, StackExchange.Redis (Valkey). EF migrations own the schema.

### 5.2 `app2.backend` — **Go** (workers & async jobs)
- **Background/async work**, not a read plane — a genuinely separate concern from the request path.
- Jobs: SLA-timer scanning + **breach detection** (Valkey sorted set by due time), **notification
  dispatch**, scheduled **report generation**, search-index maintenance, **AMC-expiry / low-hour
  reminders**, and — later — **channel-message processing** (§17) + **AI model-call orchestration** (§16).
- Triggered by Valkey pub/sub events and cron-style tickers; writes back via the .NET API or Valkey.
  Stateless, horizontally scalable.
- Stack: Go (chi/echo), `redis/go-redis`, read-only DB driver.

### 5.3 `app3.backend` — **Node.js** (realtime + BFF + channel gateway)
- **Realtime**: WebSocket/SSE for board updates, comments, presence — subscribes to Valkey pub/sub.
- **BFF**: aggregates core-API calls into view-shaped responses for the SPA where useful.
- **Channel gateway seam (Phase 3)**: inbound webhooks from Viber/email/etc. land here, are
  normalized into a Work Item via the .NET API; outbound replies fan back to the originating channel (§17).
- Session/presence in Valkey. Stack: Node (TypeScript) + Fastify, `ws`/socket.io, `ioredis`.

### 5.4 `Frontend` — **React** (SPA)
- Routed experiences behind one app: **Customer Portal**, **Team Workspace**, and the **God-mode
  console** (§15). UI is **module-aware** — screens/nav render only for enabled modules (§14).
- Auth via Keycloak (OIDC Auth Code + PKCE) **or** the **access-code + ID** flow (§8).
- Talks to Node (realtime/BFF) and to the core API **via APIM**. Served by nginx via the Istio gateway.
- Stack: React + Vite + TypeScript, React Router, TanStack Query, WebSocket client.

### 5.5 `cache` — **Valkey**
- Roles: hot-read cache, **sessions**, **realtime pub/sub**, **SLA timer** sorted sets, **module-flag
  cache**, **AI usage/rate counters**, **channel session map** (P3), rate-limit counters.
- StatefulSet + PVC (single node MVP; Sentinel/cluster later).

### 5.6 Communication summary

```
                       ┌────────────── Keycloak (OIDC)  |  Access-code+ID ─────────────┐
                       │  login / tokens (customers + agents + operators)               │
  Browser (React) ──►  Istio shared-gateway ──► Node (realtime/BFF) ─┐
       │                                          │                   ├─► .NET core API ──► DB
       │                                          └► Valkey pub/sub ◄─┘        │
       │                                                    ▲                  │ emits events
       └── public/API traffic ──► WSO2 APIM ──► (.NET | Go | Node)             ▼
                                   (token validation, rate-limit, analytics)  Go workers
                                                                    (SLA scan, notify, reports, AI, channels)

  Phase 3:  Viber / Email / … ──webhook──► Node channel gateway ──► .NET (create/update Work Item)
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

Platform / capability tables (see §14–17):

- **Module** — `key (e.g. managed_service, ai_assist, channels, kb), name, description, scope
  (global|tenant), default_enabled`. The catalog of toggleable features.
- **ModuleState** — `module_key, organization_id (null = global), enabled, config_json, updated_by,
  updated_at`. The effective on/off (+ config) per tenant, resolved with global fallback.
- **AccessCode** — `id, organization_id, subject_id (=unique login ID), code_hash, role, expires_at,
  revoked, created_by, last_used_at`.
- **PlatformAudit** — `id, actor_user_id, action, target, before, after, created_at` — every god-mode
  action + module toggle (immutable trail, §15).
- **AiProvider / AiModel** — `id, provider (anthropic|openai|azure|local|…), model_id, display_name,
  enabled, is_default, config_json`. The multi-model registry (§16).
- **AiRun** — `id, feature (triage|reply|summarize|kb), model_id, work_item_id, tokens_in, tokens_out,
  latency_ms, status, created_at` — usage/audit for AI calls.
- **Channel** *(Phase 3)* — `id, organization_id, type (viber|email|telegram|whatsapp), name,
  config_json (bot token / mailbox), enabled`.
- **ChannelIdentity** *(Phase 3)* — `id, channel_id, external_id, customer_id (nullable),
  display_name, linked_user_id` — maps a person on a channel to a Customer/User (cross-channel identity).
- **InboundMessage** *(Phase 3)* — `id, channel_id, channel_identity_id, work_item_id, direction
  (in|out), body, raw_json, created_at` — the raw channel log tied to a Work Item.

Relationships: Organization 1─* Project 1─* WorkItem 1─* Comment / Attachment / SlaTimer /
ActivityLog. WorkItem *─* Label. Board 1─* BoardColumn ↔ WorkflowStatus. Module 1─* ModuleState.
Channel 1─* ChannelIdentity 1─* InboundMessage ─* WorkItem.

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
- Secrets (DB creds, Keycloak client secrets) via Kubernetes Secrets / sealed-secrets; never in git.
  Current plaintext [./credential](./credential) is a dev placeholder to be replaced.

### 8.1 Access-code + ID login (lightweight, passwordless)

A second login path beside full Keycloak accounts — for customer contacts who won't create a
password, one-off external stakeholders, or quick guest access.

- Each customer contact (or an ad-hoc invite) gets a **unique ID** (e.g. `ACME-4821`) plus a
  **secret access code**. Entering both on the login screen mints a **scoped guest session** —
  restricted to that customer's tenant + `guest` role, no admin surface.
- Codes are **single-owner, revocable, optionally expiring**, rate-limited on the login endpoint,
  and stored **hashed** (never plaintext). One code can be regenerated by an `org_admin`/operator.
- Implementation: a Keycloak custom authenticator (or a direct-grant flow in the core API that issues
  a short-lived scoped JWT) validating `id + code` against the `AccessCode` table (§6). Still transits
  APIM and still yields a JWT so all downstream authz is unchanged.
- This is how a Phase-3 channel user (Viber/email, §17) with no portal account gets a durable identity.

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

## 14. Module system & feature toggles

Every non-core capability is a **module** that can be **enabled/disabled** — globally (platform
default) or **per tenant**. This keeps the core small and lets us ship/roll-back features safely and
sell tiers ("Managed Service module on, AI module off").

> **Modules are the built-in case of the plugin contract (§20).** First-party features (Managed
> Service, Channels, AI, KB) and third-party plugins use the **same** registration + toggle +
> enforcement machinery — we dogfood our own extension API. Design every module to the plugin
> contract from day one so the platform is **plug-and-play** later without a rewrite.

- **Registry** — the `Module` catalog (§6): `managed_service`, `channels` (P3), `ai_assist`, `kb`,
  `automations`, `reports_advanced`, … Each has a `scope` and `default_enabled`.
- **Effective state** — `ModuleState` resolves per request as *tenant override → global default*.
  Cached in Valkey (`mod:{tenant}` hash), invalidated on toggle via pub/sub.
- **Enforcement everywhere** — the core API guards each module-owned endpoint (`403 module_disabled`);
  the SPA hides nav/screens for disabled modules; Go workers skip jobs for off modules. A capability
  exists only when **role allows it AND its module is enabled** (§3).
- **Who toggles** — `org_admin` may toggle tenant-scoped modules they're licensed for; **god mode**
  (§15) toggles anything, global or per-tenant, and sets the licensed set. Every toggle → `PlatformAudit`.
- **Config per module** — `config_json` holds module settings (e.g. AI default model, channel tokens).

---

## 15. God mode (`/godmode`)

A guarded **platform-operator console** for us (the SI running TaskDesk) — cross-tenant control that
never appears in the normal UI.

- **Entry** — a user with the `platform_admin` role (separate Keycloak realm) navigates to
  **`/godmode`** (also reachable via the command palette). Entry requires **step-up auth** (re-auth /
  MFA) and opens a distinct console shell, visually marked (banner) so it's never confused with a
  tenant view.
- **Powers** — (1) **modules**: enable/disable any module globally or per tenant, edit module config;
  (2) **tenants**: list/create/suspend customers, view any tenant's projects/tickets read-only;
  (3) **impersonation**: "view as" a tenant user for support (time-boxed, fully audited);
  (4) **AI**: manage the model registry, set defaults, view usage (§16); (5) **access codes**:
  issue/revoke (§8); (6) **system**: feature flags, health, job/queue status, audit log viewer.
- **Guardrails** — everything god mode does is written to **`PlatformAudit`** (immutable). Destructive
  actions require confirmation. Impersonation and cross-tenant reads are labelled and time-limited.
  God mode is **off the tenant path** — enforced at the API by realm+role, not just UI hiding.
- In the **prototype**, `/godmode` will surface as a console view gated behind the operator persona.

---

## 16. Multi-model AI assist

> Interpretation: "multi-model" = a **provider-agnostic AI layer** that can be pointed at multiple
> LLM models/providers and switched per feature/tenant. (If you meant multi-tenant data models or
> something else, say so and I'll re-scope.)

An optional **module** (`ai_assist`) — no AI ships in the core; it's added and can be disabled.

- **Model registry** — `AiProvider`/`AiModel` (§6): register Anthropic (Claude family), OpenAI/Azure,
  or a local model; mark `enabled` + one `is_default`. Per-tenant or per-feature model selection via
  module `config_json`. Newest capable Claude models are the sensible default.
- **Abstraction** — a single internal `AiGateway` interface (prompt, model, context) so features are
  provider-agnostic; swapping models is config, not code. Calls are orchestrated by the **Go worker**
  (async) and logged to `AiRun` (tokens, latency, cost) for usage caps + billing.
- **Features (all module-gated, opt-in):** auto-**triage/classification** of new tickets (type,
  priority, project suggestion), **suggested replies** / draft responses for agents, **thread
  summarization**, **KB-article draft** from a resolved ticket, **SLA-risk hints**. Every AI output is
  a *suggestion a human confirms* — never an unattended action in MVP.
- **Guardrails** — per-tenant token/rate budgets (Valkey counters), redaction of secrets before send,
  full `AiRun` audit, and a global kill-switch (disable the module).

---

## 17. Multi-channel communication — **Phase 3**

> **Scope: Phase 3, not now.** Captured here so the architecture leaves a clean seam (the Node
> channel gateway, §5.3) and identity model (`ChannelIdentity`, §6) for it — but MVP intake stays the
> **portal + access-code login**. This directly addresses "meet customers where they already are"
> (Viber/chat) rather than forcing everyone into a portal.

The `channels` module turns scattered inbound (Viber, email, Telegram, WhatsApp) into **one tracked
queue**, so requests stop landing in personal DMs.

- **Inbound** — each channel registers a webhook (`Channel` config). Messages hit the **Node channel
  gateway**, which resolves/creates a **`ChannelIdentity`** (cross-channel identity: same person across
  Viber + email + portal → one Customer/User), then **creates or updates a Work Item** via the core
  API and drops it in the shared **triage** queue. Raw messages logged as `InboundMessage`.
- **Outbound** — agent replies (and status/SLA notifications) fan back out to the originating channel
  via the Go worker (send-message APIs), so the whole conversation stays two-way inside TaskDesk.
- **Order of channels** — **Viber first** (bot API: webhook in / send-message out), **email second**,
  then Telegram/WhatsApp. Cross-channel identity + threading are first-class from the start of Phase 3.
- **Why Phase 3** — MVP proves the core (tracker + help desk + SI managed-service). Channels are the
  highest-value *next* layer and are pre-wired for, but not built until the core is solid.

---

## 18. Delivery phases

1. **Design (now)** — sign off this plan → build static **HTML UI/UX prototype** (workflow-first)
   under `Frontend/ui/` for both Portal and Workspace. *No backend yet.*
2. **Vertical slice** — .NET core API + DB for Work Items + Projects; one board end-to-end; Dockerized;
   deployed via ArgoCD behind APIM. Proves the pipeline. Includes the **module registry** skeleton.
3. **Realtime + workers** — Node realtime/BFF + Go workers (SLA scan, notifications) + Valkey.
4. **React SPA** — implement the signed-off UI against the API; Keycloak login **+ access-code login**;
   module-aware nav.
5. **Support + SI features** — SLA timers/breaches, contracts/AMC + hour bank, reports, portal polish.
6. **God mode + modules** — `/godmode` console, per-tenant module toggles, platform audit.
7. **AI assist module** — multi-model registry + triage/suggested-reply/summarize (opt-in).
8. **Phase 3 — Multi-channel** — Node channel gateway, Viber first → email → others; cross-channel identity.
9. **Phase 2 backlog** — sprints, workflow editor, automations, attachment storage, public API/webhooks.

---

## 19. Open questions

1. **Hosts/domains** — confirm `*.example.com` vs your real domain for the `HTTPRoute`s + APIM.
2. **Keycloak deploy** — Operator vs Helm chart? Own namespace vs `taskdesk`?
3. **Valkey topology** — single node (MVP) vs Sentinel/HA now?
4. **APIM Key Manager wiring** — confirm APIM version supports Keycloak as third-party KM in your install.
5. **Attachments** — metadata-only for Phase 1, or stand up MinIO now?
6. **Tenant model** — one org per customer company (B2B) confirmed? Any need for a user to span orgs?
7. **DB engine** — MSSQL (per the repo `credential` cluster) vs Postgres (if your ecosystem is
   Postgres-first). Core API is EF Core so either works; decide before the vertical slice.
8. **"Multi-model"** — confirm this means multi-LLM AI (§16) and not another notion of model.
9. **Monolith vs polyglot** — keep 3 services (learning/showcase) or collapse to one modular backend
   now that the read/write split is dropped (ADR-001)?

---

# Part II — Platform seeds (North Star / future)

> Forward-looking design so today's decisions don't box us in. Not MVP. The goal: TaskDesk becomes a
> **self-hostable, extensible, open PM + service-desk platform** — a genuine **Plane / Jira
> alternative** — with a plug-and-play extension model, a first-class API, and MCP-native AI.

## 20. Extensibility & plugin framework (plug-and-play)

**Principle — thin kernel, everything else is an extension.** The **kernel** is small and stable:
identity/tenancy, the work-item store, the event bus, the API gateway, and the module/plugin
registry. *Everything else* — Managed Service, Channels, AI, KB, Reports — is an extension using the
**same public contract** third parties use. This is the plug-and-play guarantee.

**The extension hierarchy (all plug-and-play):**

| Unit | What it is | Example |
|---|---|---|
| **Plugin** | The installable package (manifest + optional backend service + optional UI). Unit of distribution. | `taskdesk-viber`, `acme-custom-fields` |
| **Product** | A curated **bundle of modules** licensed/enabled together. | "Help Desk", "Project Management", "Managed Services", "AI" |
| **Module** | A toggleable feature flag a plugin registers (§14). A plugin ships ≥1 module. | `managed_service`, `channels` |
| **Project App** | A plugin **scoped to a project** — adds views/fields/automations to that project (Jira/Plane project-app analog). | "Sprint board app", "SLA app" |
| **Addon** | A small extension (one field type, widget, integration). A lightweight plugin. | "Priority-matrix field", "Grafana card" |

**Manifest (`plugin.yaml`)** declares: `id`, `version`, `provides` (modules/products), `contributes`
(extension points), `permissions` (capability scopes), `configSchema`, `dependencies`, and delivery
(`backend`: image/endpoint · `frontend`: remote entry · `mcp`: tools). Registration is manifest-driven —
no core code change to add a plugin.

**Contribution points (extend without forking):** work-item **types** & **custom fields** · board /
list / timeline / **custom views** · **workflow states** & **automations/rules** · **intake channels**
(a channel is a plugin, §17) · **AI providers & features** (a model is a plugin, §16) · **report
widgets / dashboard cards** · **command-palette / slash actions** · **event subscribers / webhooks**
(§21) · **MCP tools & resources** (§22) · **UI slots** (project tab, work-item panel, settings page) ·
**auth providers** (Keycloak, access-code) · **notification channels**.

**Runtime models — chosen to fit this stack:**
- **Out-of-process backend plugin** *(preferred, most plug-and-play)* — its own container/service; it
  registers via manifest, calls the **public API** (§21), subscribes to the **event bus** (Valkey
  streams), and is exposed through **APIM**. **Installing a plugin = drop in a Deployment + one ArgoCD
  Application** — the existing GitOps flow *is* the plugin installer. No redeploy of the core.
- **In-process module** — a compiled first-party feature guarded by a module flag (fastest path for
  core features).
- **Frontend plugin** — manifest-driven UI (remote module / micro-frontend / sandboxed iframe)
  rendering into declared **UI slots**; the SPA's module-aware nav already shows/hides on toggle.

**Lifecycle & governance:** register → install (platform) → **enable per tenant** → configure →
disable → uninstall. Backed by `Plugin` / `PluginContribution` / `PluginInstall` tables (extends §6,
reuses `ModuleState`). **God mode (§15)** installs/enables and sets licensed **Products**; every action
audited. **Security:** capability scopes in the manifest, tenant-scoped tokens, signed plugins,
resource limits, per-plugin kill-switch.

**DX:** a `create-taskdesk-plugin` scaffolding CLI, typed **SDK** per language (§21), an example
plugin, and a local dev harness. **Marketplace** (catalog, versioning, ratings, one-click install)
is the North-Star endpoint of this framework.

## 21. Public API & developer platform

**API-first:** everything the UI does is a public, documented API call — no private endpoints — so
integrations and plugins are first-class, not bolted on.

- **REST v1 + OpenAPI 3** — versioned, consistent resources (projects, work items, comments,
  contracts, SLAs, reports). Spec is the source of truth.
- **AuthN** — OAuth2 **apps** (Keycloak), **Personal Access Tokens**, and per-plugin **service tokens**
  — all issued/validated through **WSO2 APIM** (which we already mandate as the gateway).
- **Webhooks** — subscribe to events (`work_item.created|transitioned`, `comment.added`,
  `sla.breached`, `hour_bank.low`, …); signed payloads, retries, delivery log.
- **Developer portal** — WSO2 APIM's built-in portal: self-serve keys, subscriptions, interactive
  docs, try-it, per-app **rate-limit tiers** and analytics.
- **SDKs** — generated from OpenAPI (TypeScript, .NET, Go, Python).
- **Event stream / GraphQL** — optional later (firehose for high-volume integrators).

## 22. MCP integration (AI-native)

Model Context Protocol makes TaskDesk **operable by AI agents** and lets plugins expose AI-callable tools.

- **TaskDesk MCP server** — exposes **tools** (`create_ticket`, `search_work_items`, `transition`,
  `add_comment`, `log_time`, `get_project`, `list_sla_breaches`, …) and **resources** (work items,
  projects, contracts) so Claude / other agents can *operate* TaskDesk. Auth via PAT/OAuth through
  APIM; strictly **tenant-scoped**; every call in `AiRun`/audit.
- **MCP as a contribution point** — plugins register their own MCP tools via the manifest (§20); the
  AI module and external agents discover them automatically.
- **MCP client** — the AI module (§16) can *consume* external MCP servers as tools (pull data from a
  customer's systems for triage/enrichment).
- Runs as a small dedicated service (Node/Go) behind APIM; ties §16 (multi-model) + §20 (plugins).

## 23. North Star — open-source Plane / Jira alternative (seed)

Position: a **self-hostable, extensible** project-management **+** service-desk platform. Parity map:

| Plane / Jira concept | TaskDesk |
|---|---|
| Workspace | **Tenant / Customer** (SI hierarchy) |
| Project | **Project** |
| Issue | **Work Item** (unified ticket/task/bug) |
| Cycle / Sprint | **Sprint/Cycle** (agile, P2) |
| Module (Plane's issue-grouping) | **Epic / Work-Item Group** *(renamed to avoid clash with our feature "Module")* |
| Views (saved filters) | **Saved views** |
| Pages / Wiki | **Knowledge base / Docs** |
| States | **Workflow statuses** |
| Estimates | **Story points** |
| Inbox / Intake | **Triage + omni-channel** (§17) |
| Analytics | **Reports & dashboards** |
| Integrations / API / Webhooks | **§21** |
| Self-host | **RKE2 + ArgoCD** (already ours) |
| Marketplace | **Plugin framework** (§20) |

**Differentiators vs Plane:** built-in **service desk + SLA + managed-service/AMC hour bank**,
**omni-channel intake**, **multi-model AI**, **MCP-native**, a **plugin marketplace**, and
enterprise auth (**Keycloak**) + API governance (**WSO2 APIM**). Sequenced strictly after the core MVP.

## 24. Developer setup & DX ("very good setup")

- **One-command local bootstrap** — `docker compose up` (or Tilt/Skaffold for the k8s path) brings up
  all services + DB + Valkey + Keycloak, **pre-seeded** with the prototype's demo tenants/projects/
  tickets. Zero-to-running in minutes.
- **Task runner** — Taskfile/Makefile targets (`up`, `seed`, `test`, `lint`, `gen-sdk`, `new-plugin`).
- **OpenAPI-first** — contracts generate SDKs + typed clients; drift fails CI.
- **Plugin scaffolding** — `create-taskdesk-plugin` + a working example plugin.
- **Quality gates** — pre-commit, conventional commits, SonarQube (already in your stack), image scan,
  ArgoCD auto-deploy on merge.
- **Docs** — architecture overview, ADRs, contribution guide, **plugin author guide**, API reference.
```
