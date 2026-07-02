# TaskDesk — Feature List & MVP

> Companion to [PLAN.md](./PLAN.md). This is the master checklist of features. Each item is tagged:
> **[MVP]** = first deployable release · **[P2]** = Phase 2 (later) · **[P3]** = nice-to-have.
> Interactive UX for the **[MVP]** set is prototyped in [Frontend/ui/index.html](./Frontend/ui/index.html).

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
- **[MVP]** Session management + sign out.
- **[MVP]** User profile mirrored from Keycloak (name, email, position, access role).
- **[P2]** Self-service signup / invite flow for customer contacts.
- **[P2]** Social login, MFA, password reset (delegated to Keycloak).

## 2. RBAC — roles & permissions

**Access tiers (RBAC):** `Admin` · `Member` · `Guest`.
**Positions (level label, internal only):** Junior · Senior · Manager · PM · Director.

| Position | Access tier | Capability |
|---|---|---|
| Customer contact | **Guest** | Portal only |
| Junior / Senior | **Member** | Work tasks |
| Manager / PM | **Admin** | Manage + report |
| Director | **Member (reports-only)** | Read-only reports |

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
- **[MVP]** MSSQL (system of record) + Valkey (cache/realtime/sessions).
- **[MVP]** Health probes, resource limits, non-root containers, DB migrations.
- **[P2]** OpenTelemetry tracing + Prometheus metrics dashboards.
- **[P2]** Valkey HA (Sentinel/cluster); MSSQL read replica for the Go read plane.

---

## MVP definition (first deployable cut)

The MVP is everything tagged **[MVP]** above. In one line: **customers and team members log in
(Keycloak), customers raise/track tickets per project, team members (RBAC-gated) work them on
project boards with SLA + hour-bank tracking, admins manage projects/customers/contracts and see
reports — all behind WSO2 APIM, deployed by ArgoCD.**

Suggested build order (from PLAN.md §14):
1. **[done]** UI/UX prototype (this repo).
2. .NET + MSSQL vertical slice: Projects + Work Items + one board, behind ArgoCD & APIM.
3. Go (search/reports) + Node (BFF/realtime) + Valkey.
4. React SPA against the BFF + Keycloak login + RBAC.
5. Managed-service: SLA timers/breaches, hour bank, contract screens.
6. Phase 2 backlog.
