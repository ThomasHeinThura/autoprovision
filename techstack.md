# Tech Stack

The full stack for the Autoprovision on-premise IaC control plane, in two parts:

- **[Part A — Platform stack](#part-a--platform-stack)** — what Autoprovision installs onto customer VMs.
- **[Part B — Control plane and development stack](#part-b--control-plane-and-development-stack)** — what runs on the jump host, and what you install locally to build the tool.

Every table carries a **Status** column, because most layers have a chosen tool *and* a
credible alternative that a customer may mandate:

| Status | Meaning |
| ------ | ------- |
| **Selected** | The default. Automated, tested, and what the console installs unless told otherwise. |
| **Optional** | Automated and supported, but off by default — enabled per deployment. |
| **Alternative** | Deliberately evaluated and not chosen. Documented so the decision is reversible and the reasoning survives. |
| **Written, untested** | The playbook exists, the console plans it correctly, and its decision logic has unit tests — but it has not run against a real machine. Trial it in UAT before Production. |
| **Planned** | Agreed for a future phase. Not yet automated. |

> **Verify version pins before an install.** The pins below reflect the current lab build.
> Upstream releases move; confirm against the vendor release notes on execution day rather
> than trusting this table blind. Where a pin matters for compatibility, the reason is stated.

---

## Part A — Platform stack

What gets deployed onto the 19 customer VMs.

### A1 · Kubernetes layer

| Component | Choice | Version | Status | Notes |
| --------- | ------ | ------- | ------ | ----- |
| Distribution | **RKE2** | `v1.36.1+rke2r2` | Selected | Kubernetes v1.36.1. Installed by `ansible/k8s/rke2_cluster.yml`. FIPS-capable, CIS-hardened defaults, and it installs onto ordinary Ubuntu VMs — no custom node OS. |
| Node OS | **Ubuntu Server 24.04 LTS** | 24.04 | Selected | Required by SQL Server 2025. Ubuntu 26.04 is not yet supported by the MSSQL packages. |
| CNI | **Canal** (Flannel + Calico policy) | bundled with RKE2 | **Selected** | RKE2's default. Zero extra moving parts, `kube-proxy` retained, and network policy available through the Calico half. |
| CNI | **Cilium** | 1.17.x | **Alternative** | Second choice. eBPF dataplane, Hubble observability, and its `kube-proxy` replacement plus L2 announcements could retire MetalLB entirely. Not chosen: it is a substantially larger operational surface, its L2 announcement path would have to be re-validated against Istio ambient's ztunnel, and Canal already meets the requirement. Revisit if the customer asks for eBPF-level network observability. |
| LoadBalancer | **MetalLB** (FRR-K8s mode) | 0.15.x | Selected | Bare metal has no cloud LB. Hands one external IP to the shared Istio gateway. See [`rke2-cluster/metallb-install.md`](./docs/runbooks/metallb-install.md). |
| Service mesh / ingress | **Istio ambient** | 1.30 | Selected | `profile=ambient` — ztunnel and istio-cni, **no sidecars**, no `istio-ingressgateway`. Ingress is the Kubernetes Gateway API. |
| Ingress API | **Gateway API** (standard channel) | v1.2+ | Selected | One shared `Gateway` (`shared-gateway` in `istio-system`) serving every host from a single MetalLB IP; apps attach with `HTTPRoute`. |
| Certificates | **cert-manager** + self-signed root CA | 1.17.x | Selected | `ca-issuer` ClusterIssuer for internal auto-renewal. Customer-supplied PEMs are also accepted. |
| GitOps | **ArgoCD** | 3.x | Selected | Exposed via `HTTPRoute` on the shared gateway. |
| Cluster UI | **Headlamp** | latest chart | Optional | Skips itself without failing when the chart repo is unreachable. |

> **Why the RKE2 bundled ingress is disabled.** RKE2 v1.36 ships Traefik as its in-cluster
> ingress (ingress-nginx was retired upstream). Istio owns Kubernetes ingress here, so
> `rke2_cluster.yml` sets `disable: [rke2-ingress-nginx, rke2-traefik]`. This is unrelated to
> the Docker-platform Traefik in [A4](#a4--docker-platform-layer).

### A2 · Data layer

Three engines, each in a single-node and a multi-node topology. Engine and topology are
chosen per workload in the console — this is general-purpose database provisioning, not
a WSO2-only path.

| Engine | Version | Single node | Multi node | Status |
| ------ | ------- | ----------- | ---------- | ------ |
| **Microsoft SQL Server** | 2025 (2022 selectable) | Native install, Enterprise PID | **Always On availability group** — Pacemaker + Corosync, `CLUSTER_TYPE=EXTERNAL`, synchronous commit, VIP | Selected |
| **PostgreSQL** | 17 | Native install, `scram-sha-256` auth | **Patroni** + etcd — automatic failover through the consensus store. Also two-node streaming replication. | **Written, untested** |
| **MySQL** | 8.4 LTS | Native install | **InnoDB Cluster** — Group Replication with MySQL Router. Also semi-synchronous replication and multi-primary. | **Written, untested** |

**HA alternatives considered and not chosen:**

| Instead of | We rejected | Why |
| ---------- | ----------- | --- |
| MySQL InnoDB Cluster | Percona XtraDB Cluster (Galera) | Synchronous multi-primary changes write semantics in ways applications assuming a single writer handle badly. |
| PostgreSQL Patroni | repmgr, pgpool-II | repmgr failover is semi-manual; Patroni's DCS-driven leader election matches the automatic-failover behaviour MSSQL AG already provides. |
| Patroni's etcd | Reusing the RKE2 cluster's etcd | Never share the Kubernetes control plane's etcd with an application. A database failover storm must not be able to take down the cluster. |

#### Database users — two-tier, least privilege

Applications never connect as `sa`, `root`, or `postgres`. Those accounts are host-compromise
vectors, not merely privileged ones: MSSQL `sa` reaches `xp_cmdshell`, MySQL `root` with `FILE`
reads and writes arbitrary files, and a PostgreSQL superuser reaches `COPY … FROM PROGRAM`.
Each is a shell on the VM.

| Tier | Purpose | Lifetime | Privileges |
| ---- | ------- | -------- | ---------- |
| **Provisioning admin** | Used only by Ansible to create databases, load schemas, and grant rights | Disabled or rotated once provisioning completes | Server-level admin |
| **Runtime login** | One per consuming component — WSO2 APIM, WSO2 IS, SonarQube, GitLab | Life of the deployment | DML on its own schemas only. No DDL, no server-level rights. |

Engine-specific correctness requirements:

- **MSSQL** — every runtime login is created on **every AG replica with an identical SID**.
  Without this, a failover orphans the user and the application loses its connection. Already
  implemented in [`ansible/db/mssql_wso2_db.yml`](./ansible/db/mssql_wso2_db.yml).
- **MySQL** — users are created on every node **before** it joins the cluster, and are scoped
  to a host or subnet (`'wso2'@'10.20.30.%'`), never `'%'`. Anonymous users and the `test`
  database are removed.
- **PostgreSQL** — roles are cluster-global and reach streaming replicas automatically, but
  must exist before Patroni bootstraps a replica. Roles are `LOGIN NOSUPERUSER NOCREATEDB
  NOCREATEROLE` and own only their own schema. `pg_hba.conf` uses `scram-sha-256` — never
  `trust` or `md5`.

Built-in accounts are disabled or renamed after provisioning, per engine.

#### Backup and recovery

| Engine | Tool | Status | Notes |
| ------ | ---- | ------ | ----- |
| MSSQL | Native `BACKUP DATABASE` + cron | Selected | FULL daily, LOG every 15 min, retention pruning. Primary-aware, so backups follow failover. [`ansible/db/mssql_backup.yml`](./ansible/db/mssql_backup.yml). |
| PostgreSQL | **pgBackRest** | Written, untested | Incremental, parallel, with PITR and repository verification. Preferred over `pg_dump` for anything holding real data. |
| MySQL | **Percona XtraBackup** | Written, untested | Physical hot backup plus binlog for PITR. `mysqldump` is a fallback for small datasets only. |
| Kubernetes | RKE2 etcd snapshots | Selected | Daily scheduled plus on-demand. [`ansible/k8s/etcd_backup.yml`](./ansible/k8s/etcd_backup.yml). |
| Kubernetes | **Velero** | Alternative | Namespace-scoped backup with PV snapshots. Worth adding once stateful workloads live in-cluster; today the stateful tier is all on VMs, where etcd snapshots plus database backups already cover recovery. |

> **Point every backup target at NFS or NAS.** A backup on the same disk as the database does
> not survive the VM.

### A3 · Application layer

| Component | Version | Status | Notes |
| --------- | ------- | ------ | ----- |
| **WSO2 API Manager** | 4.7.0 | Selected | Control plane plus internal and external gateways. Namespaces enrolled in Istio ambient. |
| **WSO2 Identity Server** | 7.3.0 | Selected | |
| WSO2 database backend | MSSQL | Selected | The tested path. MySQL and PostgreSQL schema scripts are [Planned](#a2--data-layer) — the engines will be provisionable well before WSO2 is certified against them. |

Authoritative deployment source: [`WSO2_APIM_KUBE_ISTIO/`](WSO2_APIM_KUBE_ISTIO/README.md).

### A4 · Docker platform layer

Runs on the three Docker VMs (GitLab, Prod ELK, UAT ELK). Every Docker VM runs Traefik, which
owns the shared `platform` network; services attach to it and are reachable over HTTPS at their
domain, never on a raw port.

| Component | Version | Status | Notes |
| --------- | ------- | ------ | ----- |
| Container runtime | Docker CE | 27.x | Selected | |
| Edge proxy | **Traefik** | v3.7.1 | Selected | Per-VM ingress. Unrelated to Istio. |
| Source control | See [A4a](#a4a--source-control-and-ci) | — | Selected | Customer's choice — GitLab, GitHub or Azure DevOps |
| Code quality | **SonarQube** | Community | Selected | Integrates with all three SCM options |
| Platform database | PostgreSQL | 17.10 | Selected | Backs GitLab and SonarQube. Separate from the provisioned database tier in A2. |
| Container management | Dockhand | latest | Selected | |
| Alerting | ElastAlert2 | latest | Selected | Paired with the Elastic or OpenSearch path |

### A4a · Source control and CI

The repository platform is the customer's decision, and it changes four things: where manifests
live, what runs CI, where container images are stored, and what ArgoCD points at. All three
options are supported; **the console installs only GitLab**, because the other two are either
customer-hosted already or SaaS.

| Platform | Version | Status | Installed by us | Registry | CI runner | Notes |
| -------- | ------- | ------ | --------------- | -------- | --------- | ----- |
| **GitLab CE** | 19.0.1 | **Selected** | **Yes** — `ansible/platform/gitlab_stack.yml`, self-hosted on the shared VM | GitLab Container Registry | GitLab Runner, Docker executor | The default. Fully air-gappable, one product for source, CI, registry and packages. |
| **GitHub** | Enterprise Server 3.x, or github.com | Optional | No | GHCR, or the customer's | Actions runner — **self-hosted** on the shared VM | Choose when the customer already standardises on GitHub. A self-hosted runner is required: cloud runners cannot reach on-premise VMs. |
| **Azure DevOps** | Server 2022, or dev.azure.com | Optional | No | Azure Container Registry, or the customer's | Azure Pipelines **self-hosted agent** on the shared VM | Choose when the customer is Microsoft-aligned. Same constraint: the agent must run inside the network. |

What changes per choice:

| Concern | GitLab | GitHub | Azure DevOps |
| ------- | ------ | ------ | ------------ |
| CI configuration | `.gitlab-ci.yml` | `.github/workflows/` | `azure-pipelines.yml` |
| Runner install | `gitlab_stack.yml` registers it | `ansible/ci/github_runner.yml` | `ansible/ci/azdo_agent.yml` |
| ArgoCD source | GitLab repo + deploy token | GitHub repo + PAT or App | Azure Repos + PAT |
| Registry credentials | Project deploy token | GHCR PAT | ACR service principal |
| Secret scanning | Gitleaks in CI | Gitleaks + native secret scanning | Gitleaks in the pipeline |

> **Regardless of platform, the container registry must be reachable from the RKE2 nodes.** With
> GitHub or Azure DevOps in the cloud, either the nodes get egress to it, or images are mirrored
> into a local registry. Confirm this before choosing — it is the constraint that most often
> forces the GitLab answer in a genuinely air-gapped site.

### A4b · Object storage

S3-compatible storage on your own VMs. Loki, Tempo, Mimir, database backups and cluster snapshots
all write here — everything that would use a cloud bucket uses this instead, so the architecture
is identical on-premise and in a cloud.

| Product | Version | Status | Notes |
| ------- | ------- | ------ | ----- |
| **MinIO** | current release | **Selected** | The de-facto on-premise S3. Erasure coding, single binary, straightforward Ansible install. **Verify the licence and the community-edition feature set before committing** — MinIO is AGPLv3 and the vendor has been moving functionality into its commercial product. |
| **SeaweedFS** | 3.x | Alternative | Lighter, replication rather than erasure coding, strong with very large numbers of small objects. Choose if MinIO's licensing becomes a problem. |
| **Ceph RGW** | Reef | Alternative | The right answer at genuinely large scale, and dramatically more to operate. Not proportionate to this deployment. |
| **Garage** | 1.x | Alternative | Small, simple, geo-distribution oriented. Good for a two-site layout; less proven at this workload. |

| Topology | Nodes | Redundancy |
| -------- | ----- | ---------- |
| **Standalone** | 1 | None. A lost disk is lost data. Suitable for UAT only. |
| **Distributed** | 2–4 selectable | Erasure coding across all drives. **Four nodes** is the smallest layout that survives losing a node and still tolerates a drive failure while it is down. |

Rules the console enforces:

- Minimum **4 drives total** — erasure coding has no valid striping below that.
- **Every node must present an identical drive count and size.** MinIO refuses an uneven layout
  rather than silently producing uneven failure tolerance.
- **Sequential hostnames**, so the brace expansion `http://minio-{1...4}/mnt/disk{1...4}` resolves.
- Clock offset under 1 second — S3 request signatures fail outside a 15-minute window.
- Erasure coding is **not a backup**. It replicates deletion faithfully and it lives in one rack.
  Bucket replication to a second site is what makes it disaster recovery.

### A5 · Observability — pick one

**You choose one monitoring stack, and the console integrates that one.** Three platforms that all
store and search logs would mean three retention policies, three sets of dashboards and three
things to patch. The console asks, then deploys the answer — the others are not installed.

| Stack | Components | Status | Choose it when |
| ----- | ---------- | ------ | -------------- |
| **LGTM** | **L**oki (logs) · **G**rafana (dashboards) · **T**empo (traces) · **M**imir (metrics) | **Recommended default** | You want logs, traces and metrics in one pane, deployed into the cluster, and you are running Istio — ambient produces L4 telemetry that Tempo and Mimir consume directly. Needs [object storage](#a4b--object-storage). |
| **OpenSearch** | OpenSearch + OpenSearch Dashboards | Selectable | You want Elasticsearch-style search and analytics without the SSPL licence question. Apache 2.0, and the migration path for an existing Elasticsearch estate. |
| **Elastic Stack** | Elasticsearch · Logstash · Kibana · Fleet · APM | Selectable | You already run it, your team knows Kibana, or the customer mandates it. **This is what the lab has actually tested** at 9.1.4. |

**What changes with the choice:**

| Concern | LGTM | OpenSearch | Elastic |
| ------- | ---- | ---------- | ------- |
| Log shipper | **Alloy** | Data Prepper, or Fluent Bit | **Filebeat** |
| Storage backend | Object storage (S3) | Local or block volumes | Local or block volumes |
| Metrics | Mimir, Prometheus-compatible | Prometheus needed separately | Elastic APM |
| Traces | Tempo | OpenSearch trace analytics | Elastic APM |
| Dashboards | Grafana | OpenSearch Dashboards | Kibana |
| Alerting | Grafana Alerting | OpenSearch Alerting | ElastAlert2 |
| WSO2 gateway logs | Sidecar → Alloy | Sidecar → Data Prepper | Sidecar → Logstash `:5044` |

**Where it runs** is a second question, asked separately:

| Placement | Status | Notes |
| --------- | ------ | ----- |
| **In the RKE2 cluster** | Recommended | One stack, shared by both environments, managed by ArgoCD like everything else. Uses cluster resources and needs object storage or a storage class. |
| On a Docker VM | Selectable | Matches the current lab layout. Independent of cluster health — it still works when the cluster is the thing that is broken, which is exactly when you need it. |

| Concern | Choice | Status | Notes |
| ------- | ------ | ------ | ----- |
| Traces and metrics collection | **OpenTelemetry Collector** | Planned | Vendor-neutral, so the collector stays the same whichever stack you pick. Currently a manual runbook step. |
| Log shipper on every VM and cluster | Alloy, Data Prepper or Filebeat | Planned | Installed to match the chosen stack |

> **Switching later is not free.** The WSO2 gateways ship logs through a Filebeat sidecar to
> Logstash on `:5044`, which is configured in the team's repository. Moving to LGTM means
> re-pointing those sidecars at Alloy. It is a small change, but it is a change to a tested path —
> so pick the target before Production is built, not after.

### A6 · Security and secrets

| Concern | Choice | Status | Notes |
| ------- | ------ | ------ | ----- |
| **Secrets management** | **Infisical** (self-hosted) | **Written, untested** | Open source, self-hostable, and it runs as a Docker stack alongside the existing platform services. Machine identities suit CI and Ansible; the Kubernetes operator syncs secrets into clusters. Replaces passwords travelling through `--extra-vars`. |
| Secrets management | **OpenBao** | Alternative | The Linux Foundation fork of HashiCorp Vault, created after Vault moved to BUSL. Fully open source with Vault's API. Choose this over Infisical if you need dynamic database credentials, PKI issuance, or transit encryption — capabilities Infisical does not match. |
| Secrets management | **HashiCorp Vault** | Alternative | The mature option, but BUSL licensing needs legal review for a customer deployment. Functionally interchangeable with OpenBao for our purposes. |
| **Vulnerability scanning** | **Trivy** | **Selected** | The default, since Aikido is a commercial SaaS platform. One binary covering container images, filesystems, git repos, IaC misconfiguration, Kubernetes clusters, SBOM generation, and secret detection. Runs air-gapped with a mirrored database, and runs in GitLab CI without a subscription. |
| Vulnerability scanning | **Aikido Security** | Optional | Use instead of Trivy where a licence exists. Better triage, reachability analysis, and noise reduction than raw Trivy output. Not assumed — every pipeline must work without it. |
| SBOM | Trivy (CycloneDX / SPDX) | Selected | Generated in CI, attached to releases. |
| Secret detection | **Gitleaks** | Selected | Pre-commit and CI. Already configured in the AI-DLC workflow repo — reuse that config. |
| SAST | **Semgrep** + **Bandit** (Python) | Selected | Also inherited from the AI-DLC repo config. |
| IaC scanning | **Checkov** + Trivy config | Selected | Ansible, Docker Compose, Kubernetes manifests. |
| Kubernetes policy | **Kyverno** | Planned | YAML-native policy, no Rego to learn. Enforce non-root, resource limits, and image provenance. |
| Kubernetes policy | OPA Gatekeeper | Alternative | More expressive, but Rego is a real learning cost for an operations team. |
| Runtime security | Falco | Alternative | Not deployed. Worth revisiting once the clusters carry production traffic. |
| Console access control | **Reverse proxy plus SSO** | Planned | The console currently binds `0.0.0.0:3000` with **no authentication** — see [Known gaps](#known-gaps). |

### A7 · Network and access

| Concern | Choice | Status |
| ------- | ------ | ------ |
| East-west encryption | Istio ambient ztunnel — automatic L4 mTLS | Selected |
| North-south TLS | cert-manager internal CA, or customer PEM | Selected |
| Docker VM TLS | Traefik default certificate, pushed by the console | Selected |
| Automation account | `autoprovision` — sudo, key-based in production | Selected |
| SSH host key verification | Currently disabled for first contact | **Known gap** |

---

## Part B — Control plane and development stack

### B1 · Jump host runtime

Installed by [`bootstrap-jumphost.sh`](bootstrap-jumphost.sh). Everything here must work with
**no internet access and no Node.js on the host**.

| Component | Version | Purpose |
| --------- | ------- | ------- |
| Python | 3.12+ | Control plane runtime |
| **FastAPI** | 0.115+ | HTTP API |
| **Uvicorn** | 0.34+ | ASGI server, port 3000 |
| **Ansible** | 11.x (core 2.18) | Execution engine |
| ansible-runner | 2.4+ | Job isolation |
| SQLite | stdlib | Target values and per-step install status. No database server to operate. |
| `kubectl` | matched to RKE2 1.36 | Cluster operations |
| `helm` | 3.16+ | Chart installs |
| `istioctl` | 1.30 | Must match the installed Istio |

> **The jump host never builds the UI.** The React application is built off-host and its
> output is committed to `app/dist/`, which FastAPI serves as static files. This keeps
> `bootstrap-jumphost.sh` free of Node, npm, and registry access — a hard requirement in an
> air-gapped data centre.

### B2 · Console frontend

Built on a workstation or in GitLab CI, never on the jump host.

| Component | Version | Purpose |
| --------- | ------- | ------- |
| **Node.js** | 22 LTS | Build toolchain only |
| **TypeScript** | 5.7+ | Every workload definition is typed, so a card and its backend action cannot drift apart silently |
| **React** | 19 | UI runtime |
| **Vite** | 7 | Build and dev server, with the dev server proxying to FastAPI on :3000 |
| ~~TanStack Query~~ | — | **Not used.** Server-sent events replaced polling entirely, and the remaining state is one registry plus one status object. A query cache would have been more machinery than the problem has. |
| **React Router** | v7 | Deep-linkable workload URLs, so an operator can paste a link to a failing run |
| **CSS Modules** + custom properties | — | Design tokens as CSS custom properties for the light and dark themes. No UI framework: the visual language is specific, and a component library would be fought more than used. |
| **react-markdown** + remark-gfm | latest | Renders the Requirements, Guide, and Theory tabs from markdown held in the repo |
| **lucide-react** | latest | Icons, tree-shaken |

> **Watch the bundle.** `app/dist/` is committed to git, so every dependency has a permanent
> cost in repository size. Budget: **under 400 KB gzipped**. Justify anything that moves it.

### B3 · Development tooling

Installed locally by whoever works on the tool.

| Concern | Tool | Notes |
| ------- | ---- | ----- |
| Python packaging | **uv** | Fast, lockfile-based. Falls back to `pip` plus `requirements.txt` on the jump host. |
| Python lint and format | **Ruff** | Replaces flake8, isort, and black in one binary |
| Python types | **mypy** | |
| Python tests | **pytest** + httpx | API contract tests against `_track_plan` — the highest-value tests in the codebase, since that function decides what actually runs against production infrastructure |
| Ansible lint | **ansible-lint** + **yamllint** | |
| Ansible tests | `--syntax-check` and `--check` against the static inventory | |
| Frontend tests | **Vitest** + Testing Library | |
| End-to-end | **Playwright** | Optional. Worth it for the danger-zone confirmation flows. |
| Markdown lint | **markdownlint-cli2** | Config already exists in the AI-DLC repo |
| Git hooks | **pre-commit** | Runs Ruff, yamllint, ansible-lint, gitleaks, markdownlint |
| Container and IaC scan | **Trivy** | `trivy fs`, `trivy config` in CI |
| Diagrams | **Excalidraw** | [`architecture.excalidraw`](assets/architecture.excalidraw) |

### B4 · AI-assisted development

| Component | Version | Purpose |
| --------- | ------- | ------- |
| **AI-DLC rules** | 1.0.1 | AWS AI-Driven Development Life Cycle workflow rules, installed as `CLAUDE.md` plus `.aidlc-rule-details/`. Upstream stays checked out at `../aidlc-workflows` to re-install from on version bumps. |
| Claude Code | current | Primary agent harness |

---

## Known gaps

Carried here so they are visible in one place rather than buried in the README.

| Gap | Impact | Planned fix |
| --- | ------ | ----------- |
| Console has **no authentication** and binds `0.0.0.0:3000` | Anyone who reaches the jump host can trigger deployments and read job logs | Reverse proxy plus SSO ([A6](#a6--security-and-secrets)). Until then, restrict port 3000 at the firewall or bind to localhost and use SSH port-forwarding. |
| Passwords travel via `--extra-vars` | Visible in `ps` on the jump host while a job runs | Infisical integration ([A6](#a6--security-and-secrets)) |
| Per-job inventories contain `ansible_password=` | Written `0600`, but still plaintext on disk | Prefer SSH keys for the `autoprovision` account; leave password fields empty |
| `host_key_checking = False` | First-contact automation accepts any host key | Pre-populate `known_hosts` and re-enable for production |
| MSSQL AG derives Pacemaker and certificate passwords from the AG name | Predictable credentials when explicit values are not passed | Always pass explicit values; move to Infisical |
| AG listener registration | `sys.availability_group_listeners` stays empty under `CLUSTER_TYPE=EXTERNAL`; the Pacemaker VIP is the working endpoint | Document the VIP as the supported endpoint |
| OpenTelemetry Collector is a runbook step | Not reproducible | Automate as a console workload |

---

## Related documents

| Document | Covers |
| -------- | ------ |
| [`README.md`](README.md) | Operator flow, start to finish |
| [`planning/version-rke2.md`](./docs/planning/version-rke2.md) | Full version matrix with compatibility reasoning |
| [`planning/vm-requirements-rke2.md`](./docs/planning/vm-requirements-rke2.md) | VM sizing and topology |
| [`planning/00-old-vs-new.md`](./docs/planning/00-old-vs-new.md) | What changed from the Talos-era design and why |
| [`docs/status/service-status.md`](./docs/status/service-status.md) | What has actually been tested in the lab |
