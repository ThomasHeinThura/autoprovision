# Spec C+D — Console

**Date:** 2026-08-08
**Status:** Awaiting approval
**Covers:** React rewrite · run sheet · dependency awareness · in-UI requirements, guide and theory
**Depends on:** [Spec A+B](2026-08-08-foundation-design.md) §5.1 — the workload registry

Approved visual design: the clickable mockup reviewed on 2026-08-08.

---

## 1 · Goals

1. Show where the rollout is, at a glance, during a multi-hour change window.
2. Stop a workload being run before its prerequisites exist.
3. Make destructive actions impossible to trigger by accident.
4. Put the requirements, the operator guide, and the design reasoning in front of the operator
   at the moment they are needed, instead of in a README they will not open mid-run.

**Non-goals:** authentication (tracked in `techstack.md` known gaps), multi-user collaboration,
and run history beyond the last run per workload.

---

## 2 · What is wrong with the current UI

| Problem | Consequence |
| ------- | ----------- |
| A flat list of 31 tracks in one sidebar | No sense of overall progress, or of what to do next |
| No dependency model | The Istio card looks runnable before a cluster exists; clicking it fails confusingly |
| Destructive cards sit beside normal ones | Run All can tear down an availability group (spec A+B §5.2) |
| Logs are an undifferentiated `<pre>` | No search, no filter, no way to find the failing task in 200 KB of output |
| Preview writes into the log pane | Overwrites the previous run's output you were reading |
| Hand-rolled `while (true)` polling | No backoff, no cancellation, leaks a loop per run |
| Workload list hardcoded in HTML | Drifts from the backend (spec A+B §5.1) |
| No requirements shown anywhere | Operators discover the VM count when the playbook fails |

---

## 3 · Information architecture

### Run sheet — one environment at a time

Not a tile dashboard. A **run sheet**: the document you follow top-to-bottom through a change
window. Workloads are rows, and ordinals hang in a left margin against a continuous rule, the way
a printed runbook sets them.

**Each section in the rail is its own screen, not an anchor into a long scroll.** Shared services,
UAT and Production are separate views, as are Certificates, Secrets, Backups & DR and the Danger
zone. During a rollout an operator works inside one environment for an hour at a time; showing
three at once costs focus and buys nothing. The rail carries each section's progress ribbon and
count, so the whole picture is still available at a glance without leaving the screen you are
working in.

Every view is deep-linkable — `/env/uat`, `/env/uat/db` — so a link to a failing workload can be
pasted into a chat.

```text
┌ UAT — 5 VMs · cluster uat-cluster        5 of 12 complete · 1 running  ▰▰▰▱▱ ┐
│  1 │ Docker + Traefik          ● Complete   ▰▰        3m 48s              │
│  3 │ RKE2 cluster              ◐ Running    ▰         6m 41s              │
│  4 │ MetalLB + Istio ambient   ○ Waiting    ▱▱            —               │
│    │   Waiting on 3 · RKE2 cluster — needs a kubeconfig on the jump host   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### The step ribbon — one device, three densities

A track is an ordered list of Ansible plays, and a re-run skips completed ones. So progress is
drawn as **discrete segments, never a percentage**: filled for complete, faded for
skipped-because-already-installed, pulsing for running, red for failed, hollow for pending. The
same device appears at 3 px in the rail, 6 px in a row, and full size in the detail panel.

### Workload detail — four tabs

| Tab | Contains |
| --- | -------- |
| **Configure** | Inputs, the resolved plan, the inventory, what this unblocks, and the log console |
| **Requirements** | VM count and sizing, the pre-run checklist, ports opened, and what this explicitly does not do |
| **Guide** | The operator walkthrough, numbered, ending by naming the next workload |
| **Theory** | Why the design is what it is — the reasoning that would otherwise be lost |

The Requirements tab carries a badge showing the VM count, which changes with the configuration
(spec E+F).

---

## 4 · Dependency model

### Declaration

Each entry in `workloads.py` declares what it needs:

```python
Workload(
    id="uat_istio",
    requires=[Requires.workload("uat_rke2"),
              Requires.artifact("data/k8s/{cluster_name}/kubeconfig")],
    unblocks_hint="MetalLB must own an address before the shared gateway gets an external IP",
)
```

Two kinds of prerequisite:

- **`workload`** — another workload must have reached `completed`. Cheap; read from the existing
  `install_status` table.
- **`artifact`** — a path must exist on the jump host. Authoritative, because it survives a
  database reset and catches the case where the cluster was built outside the console.

### Resolution

`GET /workloads/state` returns per-workload readiness:

| Readiness | Meaning |
| --------- | ------- |
| `ready` | Prerequisites met, not yet run |
| `blocked` | One or more prerequisites unmet; the response names them |
| `running`, `completed`, `partial`, `failed` | As today |

The graph is **advisory in the API and enforced only for bulk run**. A single workload can still
be run while blocked — with a confirmation — because an operator debugging a half-built cluster
legitimately needs to. **Run ready workloads** only starts `ready` entries, and never destructive
ones.

A cycle in the graph is a startup error, not a runtime surprise.

---

## 5 · Backend changes

`main.py` is 916 lines and mixes routing, planning, persistence, and process execution. It is
split along its existing seams — no behaviour change beyond the new endpoints:

```text
app/
├── main.py           FastAPI app, route registration, static mount
├── workloads.py      the registry (spec A+B §5.1)
├── planner.py        _track_plan — action → inventory + steps
├── runner.py         subprocess execution, per-job inventory, log writing
├── state.py          SQLite: targets, install_status
├── deps.py           dependency resolution
└── content.py        serves markdown from app/content/
```

### Endpoints

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/workloads` | The registry: groups, fields, steps, dependencies, destructive flags |
| `GET` | `/workloads/state` | Per-workload status, steps, readiness, blocking reasons |
| `GET` | `/content/{id}/{tab}` | Markdown for `requirements`, `guide`, or `theory` |
| `POST` | `/tracks/start` | Unchanged, plus a required `confirm` for destructive workloads |
| `GET` | `/tracks/stream/{job_id}` | **New** — Server-Sent Events for live log lines |
| Existing | `/tracks/preview`, `/tracks/job/{id}`, `/tracks/log/{track}`, `/tracks/reset`, `/state/targets` | Retained |

### Log streaming

Polling `/tracks/job/{id}` re-sends the entire log every 1.5 s. On a 200 KB Ansible run with six
workloads in parallel that is roughly 1 MB every 1.5 s over the jump host's network.

`/tracks/stream/{job_id}` is an SSE endpoint emitting appended lines only. Polling is kept as the
fallback path when the stream drops, so a proxy that buffers SSE degrades rather than breaks.

---

## 6 · Frontend

### Stack

Per `techstack.md` B2 — React 19, TypeScript, Vite 7, TanStack Query, React Router 7, CSS Modules.
No component library: the visual language is specific and a library would be fought more than used.

### Structure

```text
ui/
├── src/
│   ├── app/          router, layout shell, theme
│   ├── views/        RunSheet · WorkloadDetail · DangerZone · Handbook
│   ├── components/   Ribbon · StateChip · Row · Console · DocPane · ConfirmDialog
│   ├── api/          typed client + TanStack Query hooks
│   ├── types/        generated from GET /workloads
│   └── styles/       tokens.css + module files
└── vite.config.ts    dev server proxies /api, /tracks, /workloads, /content → :3000
```

### Design tokens

The full token set from the approved mockup, as CSS custom properties. Light is the committed
default; dark is a complete second set, not an inversion. Both are defined at `:root`, in
`@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])`, and in
`:root[data-theme="dark"]` — so the un-stamped system default resolves correctly.

Accent `#1B4F8F`. Semantic colours are deliberately desaturated —`#14804A`, `#A85C0B`, `#B42318` —
so a screen of green does not glow. No drop shadows anywhere; structure comes from hairline rules
and background tints.

### The bilingual type rule

Prose is sans. **Every machine fact is monospace on a tinted chip** — IP addresses, version pins,
namespaces, secret names, playbook paths, workload ids. The rule is semantic, not decorative: if
an operator must type it exactly right, it is set in mono, and they can scan for it.

### Data fetching

TanStack Query throughout. `/workloads` is fetched once and cached; `/workloads/state` polls at
3 s while any run is active and 30 s when idle; log lines arrive over SSE and are appended to a
query cache entry. This replaces every hand-rolled poll loop.

---

## 7 · In-UI documentation

### Storage

Markdown under `app/content/<workload-id>/`:

```text
app/content/
├── _shared/
│   ├── ubuntu-2404.md          included by every workload targeting Ubuntu
│   └── autoprovision-user.md   the bootstrap prerequisite
├── uat_db/
│   ├── requirements.md
│   ├── guide.md
│   └── theory.md
└── uat_rke2/…
```

Markdown, not TSX, so the content is editable without touching React and reviewable as a normal
diff. Rendered with `react-markdown` + `remark-gfm`.

### Conditional content

Requirements change with configuration — one VM for a single instance, three plus a virtual IP for
a cluster. Front matter declares variants:

```markdown
---
when: { topology: single }
vms: 1
---
You need **one Ubuntu 24.04 VM** before you run this.
```

The UI selects the matching variant from the current form state. The VM-count badge on the tab
comes from the same front matter, so it cannot disagree with the prose beneath it.

### The checklist

Requirements renders a checklist with three states — met, unknown, and **not met**. Unmet items
are the valuable ones, and they come from real lab experience: the Corosync `127.0.1.1` split
brain, the missing vault meaning passwords travel in `--extra-vars`. Findings recorded in
`docs/status/service-status.md` are carried into this content so a lab discovery reaches the
operator who needs it, instead of ageing in a status file.

Where `preflight` (spec A+B §4) has run, its results populate the met/unmet states automatically
rather than leaving the operator to self-assess.

### Handbook

A top-level view aggregating every Theory page into one readable manual — for reading end to end,
or sharing with the customer. Same markdown, different assembly.

---

## 8 · Build and delivery

The jump host has no Node and may have no internet. So:

1. `ui/` is built on a workstation or in GitLab CI with `npm ci && npm run build`.
2. Output goes to `app/dist/` and is **committed**.
3. FastAPI mounts `app/dist/` as static files and serves `index.html` at `/`.
4. `bootstrap-jumphost.sh` is unchanged — no Node, no npm, no registry access.

**Bundle budget: under 400 KB gzipped.** `dist/` lives in git permanently, so every dependency
has a lasting cost. A CI check fails the build if the budget is exceeded.

A pre-commit hook warns when `ui/src/` changes without a corresponding `app/dist/` change — the
predictable failure mode of this approach is shipping source without the rebuilt bundle.

---

## 9 · Migration

The rewrite lands in one change, not incrementally — the two UIs would otherwise share a backend
whose contract is changing underneath both.

| Phase | Content |
| ----- | ------- |
| 1 | `workloads.py` registry; `main.py` split; new endpoints. Old HTML UI still served, still working. |
| 2 | `ui/` built against the new endpoints. Reachable at `/next` for side-by-side comparison. |
| 3 | Content authored for all workloads. |
| 4 | `/` serves the React app. `ui_parallel.html` is deleted, not left to rot. |

Phase 1 ships the two data-loss fixes (spec A+B §5.1, §5.2) independently of the UI work.

---

## 10 · Verification

| Claim | Evidence |
| ----- | -------- |
| No workload drift | Test: every `/workloads` id is routable and every action resolves in the planner |
| Destructive workloads are protected | Test: bulk run rejects them; `POST /tracks/start` returns 400 without a matching `confirm` token |
| Dependencies resolve | Test: a known-blocked workload reports `blocked` and names its blocker; the graph is acyclic at startup |
| Both themes are legible | Every token defined at bare `:root`; no colour declared only inside a media or `[data-theme]` block |
| Keyboard reachable | Every control has a visible focus state; the danger dialog traps focus and restores it on close |
| Bundle within budget | CI fails over 400 KB gzipped |
| Content matches configuration | Test: the VM-count badge equals the front matter of the variant being rendered |

---

## 11 · Risks

| Risk | Mitigation |
| ---- | ---------- |
| Committed `dist/` drifts from `ui/src/` | Pre-commit warning, plus CI rebuilds and fails on a diff |
| SSE is buffered by an intermediate proxy | Polling retained as an automatic fallback |
| Content becomes stale as playbooks change | Content lives beside the code; the same pre-commit checks lint both |
| The rewrite loses a behaviour someone relied on | Phase 2 serves both UIs at once for direct comparison before `/` switches |
| Dependency graph is wrong and blocks legitimate work | Blocking is advisory for single runs — an operator can always override with a confirmation |

---

## 12 · Decisions needed from you

1. **Handbook in phase one, or later?** It is the largest content-authoring item and the least
   urgent during an actual run.
2. **How much Theory content do you want written now** versus stubbed with headings for you to
   fill in? I can draft it all from the existing planning documents, but it is your reasoning and
   you may prefer to write it.
