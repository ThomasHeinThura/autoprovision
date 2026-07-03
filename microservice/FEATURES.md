# TaskDesk — Feature List & MVP

> Companion to [PLAN.md](./PLAN.md). This is the master checklist of features. Each item is tagged:
> **[MVP]** = Phase 1 · **[P2]** = Phase 2 · **[P3]** = Phase 3+ (incl. **multi-channel**, §15) ·
> **[NS]** = North Star / platform seed (the Plane-alternative vision, §16–20).
> Interactive UX for the **[MVP]** set is prototyped in [Frontend/ui/index.html](./Frontend/ui/index.html).
>
> Many capabilities are **modules** (§12) that can be **enabled/disabled** per tenant or globally, and
> **god mode** (§13) is the operator surface that controls them. A feature is available only when its
> **role allows it AND its module is enabled**.

TaskDesk is a multi-tenant, Jira-style **project & task management** tool with a **customer support
portal**, built for a **System Integrator (SI)** servicing many client companies. Hierarchy:

```
SI (operator)
 └─ Customer (client company)        e.g. Acme Corp, Globex Ltd
     └─ Project (engagement)         e.g. Support Retainer (AMC), Cloud Migration (Delivery)
         └─ Work Item (ticket/task)  e.g. ACME-SUP-42
```

---

## 1. Authentication & accounts

- **[MVP]** Login for **customers** and **team members** (single sign-in; role from token).
- **[MVP]** SSO via **Keycloak** (OIDC Authorization Code + PKCE).
- **[MVP]** **Access-code + unique-ID login** (passwordless) — a contact enters their unique ID (e.g.
  `ACME-4821`) + a secret code → scoped guest session. Codes are hashed, revocable, optionally
  expiring, rate-limited. For customers who won't create a password / ad-hoc access. (PLAN §8.1)
- **[MVP]** Session management + sign out.
- **[MVP]** User profile mirrored from Keycloak (name, email, position, access role).
- **[P2]** Self-service signup / invite flow for customer contacts.
- **[P2]** Social login, MFA, password reset (delegated to Keycloak).
- **[P2]** Step-up auth (re-auth/MFA) to enter **god mode** (§13).

## 2. RBAC — roles & permissions

**Access tiers (RBAC):** `Admin` · `Member` · `Guest`.
**Positions (level label, internal only):** Junior · Senior · Manager · PM · Director.

| Position | Access tier | Capability |
|---|---|---|
| Customer contact | **Guest** | Portal only |
| Junior / Senior | **Member** | Work tasks |
| Manager / PM | **Admin** | Manage + report |
| Director | **Member (reports-only)** | Read-only reports |
| Operator (us) | **Platform admin** | **God mode** (§13) — cross-tenant, module control, impersonation |

> Capabilities are **role × enabled module** (§12). A role can only use a capability when the owning
> module is on for that tenant. `Platform admin` bypasses tenant scoping only inside god mode (§13).

Capability matrix (**[MVP]**):

| Capability | Guest | Member | Member·Director | Admin |
|---|:--:|:--:|:--:|:--:|
| Raise & track own tickets (portal) | ✅ | — | — | ✅ |
| View own company projects | ✅ | — | — | ✅ |
| View team boards / work items | — | ✅ | ✅ (read) | ✅ |
| Update status, comment, log time | — | ✅ | — | ✅ |
| Self-assign from triage | — | ✅ | — | ✅ |
| Assign work to others | — | — | — | ✅ |
| Add internal notes | — | ✅ | — | ✅ |
| View dashboards / reports | — | — | ✅ | ✅ |
| Create/edit projects & contracts | — | — | — | ✅ |
| Manage customers, teams, members | — | — | — | ✅ |
| Configure SLA / working hours | — | — | — | ✅ |

- **[P2]** Per-project role overrides (a Member who is Admin on one project).
- **[P3]** Custom roles / fine-grained permission editor.

## 3. Customer portal (Guest)

- **[MVP]** Overview: open tickets, active projects, SLA-at-risk, resolved counts.
- **[MVP]** Submit a ticket (choose project, type, priority, description, attachments).
- **[MVP]** My tickets — list, filter, status + live SLA.
- **[MVP]** Ticket detail — reply thread, status, SLA countdown.
- **[MVP]** Projects — the customer's engagements, each with tickets + timeline + contract summary (hours left, AMC period, SLA).
- **[MVP]** Notification on agent reply / status change.
- **[P2]** Knowledge base / self-service articles.
- **[P2]** CSAT survey after resolution.
- **[P3]** Customer-side reports (their own SLA compliance, hours consumed trend).

## 4. Team workspace

- **[MVP]** Dashboard — open items, unassigned, SLA breaching, compliance, workload by member, open-by-project (Admin/Director).
- **[MVP]** My work — items assigned to me across all customers (Member/Admin).
- **[MVP]** Triage queue — unassigned incoming tickets (with customer badge); self-assign or route.
- **[MVP]** Global search & filter across work items (project/status/assignee/label/text).
- **[P2]** Saved filters / custom queues.
- **[P2]** Bulk actions (reassign, relabel, close).

## 5. Projects

- **[MVP]** Projects list — all engagements across customers (Admin/all-internal read).
- **[MVP]** Project detail with tabs:
  - **[MVP]** **Board** — Kanban columns = workflow statuses; drag work items (Member/Admin).
  - **[MVP]** **List** — sortable table of work items.
  - **[MVP]** **Timeline** — kick-off status + milestone timeline (done/active/upcoming).
  - **[MVP]** **Managed service** — contract/AMC details (see §7).
  - **[MVP]** **Members** — delivery team + customer contacts; project lead.
  - **[MVP]** **Overview** — status breakdown + contract snapshot.
- **[MVP]** Create project (Admin): key, name, customer, team, type, lead.
- **[P2]** Workflow editor — custom statuses & transitions per project.
- **[P2]** Sprints / backlog / story points / burndown (agile).
- **[P2]** Project templates (spin up a standard AMC or delivery project).

## 6. Work items (unified ticket / task)

- **[MVP]** Types: **Ticket** (customer), **Task**, **Bug** (internal) — one entity, one board.
- **[MVP]** Fields: title, description, status, priority, type, project, requester, assignee, labels, due date.
- **[MVP]** Auto key per project (e.g. `ACME-SUP-42`).
- **[MVP]** Status transitions (workflow-validated).
- **[MVP]** Assign / self-assign.
- **[MVP]** Comments — **public reply** vs **internal note** (hidden from customer).
- **[MVP]** Activity / audit trail per item.
- **[MVP]** Time logging — deducts from the project hour bank.
- **[MVP]** Attachment metadata (upload UI; blob storage in P2).
- **[P2]** Linked items / sub-tasks / dependencies.
- **[P2]** Watchers & @mentions.
- **[P2]** Attachment storage backend (MinIO/S3).

## 7. Managed service / AMC (SI-specific)

- **[MVP]** Service type per project: **Managed Service (AMC)** vs **Project Delivery**.
- **[MVP]** Contract period (start → end) with days-remaining.
- **[MVP]** Kick-off status: Pending / Scheduled / Completed (+ date).
- **[MVP]** **Hour bank**: contracted hours, hours used, **hours left**, burn-down bar (color-coded).
- **[MVP]** **Hour deduction** via time logging; recent-deductions log.
- **[MVP]** **SLA policy**: first-response + resolution targets per priority.
- **[MVP]** **Working hours & coverage** (e.g. 9×5 business hours vs 24×7 on-call).
- **[MVP]** Contract status: Active / In delivery / Kickoff pending / Expiring.
- **[P2]** SLA timers with pause on "Waiting on Customer"; automatic **breach flagging**.
- **[P2]** Expiring-AMC reminders; renewal workflow.
- **[P2]** Hours-per-month burn chart; low-balance alerts.
- **[P2]** Timesheet approval flow (Manager approves logged time).
- **[P3]** Contract billing / invoicing export.

## 8. SLA & reporting

- **[MVP]** Live SLA countdown on cards, lists, and detail.
- **[MVP]** SLA-at-risk / breaching indicators on dashboard.
- **[MVP]** Dashboard reports: workload, status breakdown, open-by-project, SLA compliance %.
- **[P2]** SLA breach report + trend.
- **[P2]** Report exports (CSV / PDF).
- **[P2]** Scheduled report emails to Directors.
- **[P3]** Custom report builder.

## 9. Realtime & notifications

- **[MVP]** Realtime board updates (card moves) and new comments (Node + Valkey pub/sub).
- **[MVP]** Presence indicator ("realtime connected").
- **[MVP]** In-app notification on reply / assignment / status change.
- **[P2]** Email notifications.
- **[P2]** Webhooks for integrations.
- **[P3]** Slack / Teams notification channel.

## 10. Administration

- **[MVP]** Customers directory — client companies, plan, projects, open tickets, contacts.
- **[MVP]** Customer detail — projects + contacts.
- **[MVP]** Teams directory — squads, members, load.
- **[P2]** Member management (invite, deactivate, change role/position).
- **[P2]** Org/customer settings (branding, default SLA, working calendar/holidays).
- **[P3]** Audit log console (cross-project).

## 11. Platform / non-functional (see PLAN.md §5, §8–13)

- **[MVP]** Multi-tenant isolation (every query scoped by customer).
- **[MVP]** All backend APIs behind **WSO2 APIM** (rate-limit, subscriptions, analytics).
- **[MVP]** Deployed via **ArgoCD** app-of-apps on RKE2 + Istio ambient mesh.
- **[MVP]** DB (MSSQL per repo, or Postgres — PLAN §19 Q7) + Valkey (cache/realtime/sessions).
- **[MVP]** **Right-sized architecture** (PLAN ADR-001): .NET core API (read+write), Go workers, Node
  realtime/gateway — *no* premature read/write split.
- **[MVP]** Health probes, resource limits, non-root containers, DB migrations.
- **[P2]** OpenTelemetry tracing + Prometheus metrics dashboards.
- **[P2]** Valkey HA (Sentinel/cluster); read replica **only if** scale ever justifies it.

## 12. Module system & feature toggles (PLAN §14)

- **[MVP]** Module registry — every non-core capability is a **module** (`managed_service`, `channels`,
  `ai_assist`, `kb`, `automations`, `reports_advanced`, …) with a global default.
- **[MVP]** **Enable/disable** modules — global default + **per-tenant override**; effective state
  resolved with fallback, cached in Valkey, live-invalidated on toggle.
- **[MVP]** Enforcement everywhere — core API returns `403 module_disabled`; SPA hides nav/screens;
  Go workers skip jobs for off modules.
- **[P2]** Per-module config (`config_json`) — e.g. AI default model, channel tokens, SLA defaults.
- **[P2]** Licensing tiers — the licensed module set per customer (sell "AMC on, AI off").

## 13. God mode (`/godmode`) (PLAN §15)

- **[P2]** Operator console at **`/godmode`** — `platform_admin` only, **step-up auth**, distinct
  visually-marked shell, off the tenant path.
- **[P2]** **Module control** — enable/disable any module globally or per tenant; edit config.
- **[P2]** **Tenant control** — list/create/suspend customers; read-only view into any tenant.
- **[P2]** **Impersonation** — "view as" a tenant user (time-boxed, fully audited).
- **[P2]** **Access-code** issue/revoke (§1); **AI model registry** management (§14).
- **[P2]** **Platform audit** — immutable trail of every god-mode action + module toggle; audit viewer.
- **[MVP]** (prototype) `/godmode` surfaces as a console view behind the operator persona.

## 14. AI assist — multi-model (PLAN §16)

> Module `ai_assist` — opt-in, disableable. "Multi-model" = provider-agnostic layer switchable across
> LLM models/providers.

- **[P2]** **Model registry** — register multiple providers/models (Anthropic/Claude default,
  OpenAI/Azure, local); mark enabled + one default; per-tenant/per-feature selection.
- **[P2]** **AiGateway** abstraction — swapping models is config, not code; calls run in the Go worker.
- **[P2]** Auto-**triage/classification** of new tickets (type, priority, project suggestion).
- **[P2]** **Suggested replies** / draft responses for agents (human confirms — never unattended).
- **[P2]** **Thread summarization**; **KB-article draft** from a resolved ticket; **SLA-risk hints**.
- **[P2]** Guardrails — per-tenant token/rate budgets, secret redaction, `AiRun` usage/cost audit,
  global kill-switch.
- **[P3]** Deeper automation (auto-route, auto-reply) once trust is established.

## 15. Multi-channel communication — **Phase 3** (PLAN §17)

> Module `channels` — **Phase 3**, not MVP. Architecture already leaves the seam (Node channel
> gateway) + identity model (`ChannelIdentity`). Funnels scattered chat/DMs into one tracked queue.

- **[P3]** **Viber** intake (bot API webhook in / send-message out) → creates/updates a Work Item in triage.
- **[P3]** **Email** intake (mailbox → ticket) as the second channel.
- **[P3]** **Telegram / WhatsApp** intake (later, same pattern).
- **[P3]** **Cross-channel identity** — same person across Viber + email + portal → one Customer/User.
- **[P3]** **Two-way** — agent replies + notifications fan back out to the originating channel.
- **[P3]** Raw message log (`InboundMessage`) tied to each Work Item; shared omni-channel inbox.

## 16. Extensibility & plugin framework (PLAN §20)

> **Plug-and-play by design.** Thin kernel; everything else (modules, products, project apps, addons)
> uses the same public contract — first-party features and third-party plugins are identical machinery.

- **[MVP]** Build every module to the **plugin contract** now (registry + toggle + enforcement), so
  the platform is plug-and-play later without a rewrite.
- **[P2]** **Plugin manifest** (`plugin.yaml`): provides/contributes/permissions/config/delivery.
- **[P2]** **Out-of-process backend plugin** — own container; installing = add a Deployment + ArgoCD
  Application (GitOps *is* the installer). No core redeploy.
- **[P2]** **Extension hierarchy** — Plugin ▸ Product (licensable bundle) ▸ Module ▸ Project App ▸ Addon.
- **[P2]** **Contribution points** — work-item types & custom fields, custom views, workflow states,
  automations, intake channels, AI providers, report widgets, slash actions, webhooks, MCP tools, UI
  slots, auth providers.
- **[P3]** Frontend plugins (micro-frontend / sandboxed UI slots); plugin lifecycle & install UI in god mode.
- **[P3]** `create-taskdesk-plugin` scaffolding CLI + typed SDK + example plugin.
- **[NS]** **Marketplace** — catalog, versioning, ratings, one-click install.

## 17. Public API & developer platform (PLAN §21)

- **[MVP]** **API-first** — everything the UI does is a public API call (no private endpoints).
- **[P2]** **REST v1 + OpenAPI 3** spec (source of truth); versioned resources.
- **[P2]** **Auth** — OAuth2 apps + **Personal Access Tokens** + service tokens, all via WSO2 APIM.
- **[P2]** **Webhooks** — event subscriptions, signed payloads, retries, delivery log.
- **[P2]** **Developer portal** (WSO2 APIM) — self-serve keys, subscriptions, docs, try-it, rate tiers, analytics.
- **[P3]** **SDKs** generated from OpenAPI (TS / .NET / Go / Python).
- **[NS]** GraphQL / event firehose for high-volume integrators.

## 18. MCP integration (PLAN §22)

- **[P2]** **TaskDesk MCP server** — tools (`create_ticket`, `search_work_items`, `transition`,
  `add_comment`, `log_time`, `get_project`, `list_sla_breaches`) + resources; tenant-scoped, audited.
- **[P3]** **MCP as a contribution point** — plugins register their own MCP tools via manifest.
- **[P3]** **MCP client** — AI module consumes external MCP servers for triage/enrichment.

## 19. North Star — Plane / Jira alternative (PLAN §23)

- **[NS]** Self-hostable, extensible **PM + service-desk** platform; parity map in PLAN §23.
- **[NS]** Differentiators: built-in **service desk + SLA + AMC hour bank**, **omni-channel**,
  **multi-model AI**, **MCP-native**, **plugin marketplace**, Keycloak + APIM governance.
- **[P2]** Rename Plane-style issue-grouping to **Epic / Work-Item Group** (avoids clash with feature "Module").
- **[NS]** Pages/Wiki (docs), saved Views, Cycles/Sprints, cross-project analytics.

## 20. Developer experience & setup (PLAN §24)

- **[MVP]** **One-command bootstrap** — `docker compose up` brings up all services + DB + Valkey +
  Keycloak, **pre-seeded** with the prototype's demo data.
- **[MVP]** Task runner (Taskfile/Makefile), `.env` templates, health checks.
- **[P2]** OpenAPI-first codegen; drift fails CI; SonarQube + image scan; ArgoCD auto-deploy.
- **[P2]** Docs: architecture, ADRs, contribution guide, **plugin author guide**, API reference.

---

## MVP definition (first deployable cut)

The MVP is everything tagged **[MVP]** above. In one line: **customers and team members log in
(Keycloak), customers raise/track tickets per project, team members (RBAC-gated) work them on
project boards with SLA + hour-bank tracking, admins manage projects/customers/contracts and see
reports — all behind WSO2 APIM, deployed by ArgoCD.**

Suggested build order (from PLAN.md §18):
1. **[done]** UI/UX prototype (this repo).
2. .NET core-API vertical slice: Projects + Work Items + one board + **module registry skeleton**, behind ArgoCD & APIM.
3. Node realtime/BFF + Go **workers** (SLA scan, notifications) + Valkey.
4. React SPA against the API + Keycloak login **+ access-code login** + RBAC + module-aware nav.
5. Managed-service + SI: SLA timers/breaches, hour bank, contracts, reports.
6. **God mode + module toggles** + platform audit.
7. **AI assist** module (multi-model): triage / suggested replies / summarize (opt-in).
8. **Phase 3 — multi-channel** (Viber → email → …) + cross-channel identity.
9. Phase 2 backlog (sprints, workflow editor, automations, storage, public API).
