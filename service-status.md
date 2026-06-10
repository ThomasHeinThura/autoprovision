# Service Status

Last update: 2026-06-10
Scope: consolidated lab state (RKE2 + Istio ambient + WSO2 + MSSQL + Docker stacks).

## Finished and Tested (current lab state)

- WSO2 APIM + IS on RKE2 with Istio AMBIENT: PASSED ✅ (latest test)
	- WSO2 APIM (CP + internal/external gateways) and Identity Server deployed via the web-UI
	  workloads (`k8s_wso2.yml` renders `WSO2_APIM_KUBE_ISTIO/` and applies it).
	- Istio 1.30 ambient (istiod + istio-cni + ztunnel, RKE2 CNI paths) — no sidecars, no
	  istio-ingressgateway.
	- ONE shared Gateway API `Gateway` (`shared-gateway` in `istio-system`) → one MetalLB IP for
	  ALL hosts; TLS secret `wso2-ingress-cert` in `istio-system` (Gateway API `certificateRefs`).
	- WSO2 connected to MSSQL on Linux.
- MSSQL HA AG (SQL Server 2025, 3-node, Pacemaker, CLUSTER_TYPE=EXTERNAL): PASSED
	- 3 replicas Online + quorate; `ag_cluster-clone` promotable; virtual IP 192.168.51.40
	  Started on primary; connectivity via the VIP confirmed.
	- Corosync split-brain fixed (removed Ubuntu 127.0.1.1 mapping + pinned ring0_addr to LAN IP
	  via `addr=`).
	- AG listener: created manually in SSMS. KNOWN GAP — playbook Phase 5b ran without error but
	  did not register the listener (`sys.availability_group_listeners` empty on
	  EXTERNAL/Pacemaker); the Pacemaker VIP is the working endpoint regardless.
- RKE2 Kubernetes cluster (3-node): PASSED
	- 1 control-plane (cp) + 2 workers (wn1, wn2), all `Ready` on `v1.36.1+rke2r2`.
	- Core system pods Running: canal, coredns (+autoscaler), metrics-server,
	  snapshot-controller, kube-proxy on all nodes; helm-install jobs Completed.
- In-cluster add-ons via web-UI workloads (`k8s_addons.yml`): PASSED
	- MetalLB (FRR-K8s), Istio ambient + shared Gateway, cert-manager + internal CA
	  (`ca-issuer` ClusterIssuer), ArgoCD (HTTPRoute on shared gateway), Headlamp.
- Certificate workloads: WORKING
	- `Certificate — Kubernetes` (k8s_cert.yml): TLS secret for the shared gateway —
	  **namespace default is `istio-system`** (the only place the ambient shared Gateway reads
	  it). Paste a PEM to rotate yearly, or leave PEMs empty for cert-manager auto-issue/renew
	  from the internal CA.
	- `Certificate — Traefik` (traefik_cert.yml): default cert for all Docker-VM routers.
- Docker VM base bootstrap (Phase B1): PASSED — `ok=10 changed=5 unreachable=0 failed=0`.
- Platform stack (Phase B2: Postgres + Traefik + Dockhand): PASSED — Postgres `healthy`.
- ELK stack (Phase B3): PASSED.
- GitLab stack: PASSED — readiness check passed; runner registered (`rc=0`).
- SonarQube stack: PASSED.
- Web access checks: PASSED — Dockhand, GitLab, SonarQube HTTP 200 and browser-accessible.
- Jump host to Docker VM deployment flow: PASSED.

## New (added 2026-06-10, not yet run in the lab)

- **RKE2 etcd Snapshots** workload (`ansible/k8s_etcd_backup.yml`, web UI → Backups & DR):
  daily etcd snapshot schedule on every server (drop-in config, rolling restart) + on-demand
  snapshot + retention. Run it after the next cluster install.
- **MSSQL Scheduled Backups** workload (`ansible/mssql_backup.yml`, web UI → Backups & DR):
  FULL daily + LOG every 15 min + retention; primary-aware (safe on all AG nodes — backups
  follow failover). Point the backup dir at NFS/NAS for real DR.

## In Progress / Investigating

- No active blockers. Next lab cycle: reroll to the restore point and re-run the full flow
  from scratch to validate end-to-end repeatability.

## Remaining (target state)

- Migration and lifecycle validation (Phase F): ELK 8.14 → 9.1.4 snapshot/restore migration,
  WSO2 APIM credential migration job, ElastAlert2 base rules, end-to-end alert validation.
- ArgoCD GitOps handover for WSO2 (manifests in GitLab, ArgoCD `Application`s) — currently
  deployed by the web-UI workload directly.
- OpenTelemetry Collector (runbook step).
- Run the new backup workloads (etcd + MSSQL) and verify a restore once each.

## Applied Fixes Recorded

- Istio ambient on RKE2 needs the STANDARD CNI paths (`/etc/cni/net.d`, `/opt/cni/bin`) —
  k3s/rancher paths make istio-cni-node hang 0/1.
- Single shared ingress Gateway (one MetalLB IP for all hosts); cert lives in `istio-system`.
- Cert workload default namespace set to `istio-system` (was a sidecar-era multi-namespace list).
- MSSQL HADR restart made non-blocking + memory cap (no D-Bus hang); rate-limit kill +
  SSH-blip tolerance during init; stop running sqlservr before `mssql-conf setup`.
- Corosync split-brain: removed 127.0.1.1 mapping, pinned ring0_addr.
- Traefik static/dynamic config mounted from docker/traefik; stacks recreated on deploy to
  refresh routing labels; stack playbooks self-heal remote repo checkout.
- SonarQube deploy uses combined compose with platform compose so `depends_on: postgres` stays
  valid; Dockhand internal backend port configurable (default 80).
- Security tightening (2026-06-10): inventory files with SSH passwords now written 0600;
  Traefik certs dir 0700; mssql_ag fails early on a half-set db_admin_user/password pair.

## Next Run Order (full reroll rehearsal)

1. Bootstrap jump host → web UI.
2. Parallel tracks: GitLab · ELK · MSSQL (AG + single) · RKE2 clusters.
3. Per cluster: Istio card (MetalLB + ambient + shared Gateway) → cert-manager card →
   Certificate — Kubernetes (istio-system) → ArgoCD → Headlamp.
4. WSO2 APIM + IS cards (mssql_host = AG VIP / UAT instance).
5. **Backups & DR cards: etcd snapshots + MSSQL backups** (new).
6. Phase F migration/validation.

## Verify Commands

- `kubectl get svc -n istio-system shared-gateway-istio` — the ONE ingress IP
- `kubectl get gateway,httproute -A`
- `istioctl ztunnel-config workloads | head` — ambient enrollment
- `curl -Lvk https://apim.example.com/` (and internal-gw / external-gw / wso2is hosts)
- `curl -Lvk https://dockhand.example.com/` · `https://kibana.example.com/` ·
  `https://gitlab.example.com/` · `https://sonar.example.com/`
- `sudo crm status` / `sudo pcs status` — AG primary + VIP
- `ls /var/lib/rancher/rke2/server/db/snapshots` — etcd snapshots (after running the workload)
- `tail /var/log/mssql-backup.log` — MSSQL backup runs (after running the workload)
