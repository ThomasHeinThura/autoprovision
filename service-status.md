# Service Status

Last update: 2026-06-05
Scope: consolidated from all workspace Markdown files.

## Finished and Tested (current lab state)

- MSSQL HA AG (SQL Server 2025, 3-node, Pacemaker): PASSED
	- 3 replicas Online + quorate; `ag_cluster-clone` promotable; virtual IP 192.168.51.40 Started on primary; connectivity via the VIP confirmed.
	- Corosync split-brain fixed (removed Ubuntu 127.0.1.1 mapping + pinned ring0_addr to LAN IP via `addr=`).
	- AG listener: created manually in SSMS. KNOWN GAP — playbook Phase 5b ran without error but did not register the listener (`sys.availability_group_listeners` empty on EXTERNAL/Pacemaker); the Pacemaker VIP is the working endpoint regardless.
- RKE2 Kubernetes cluster (3-node): PASSED
	- 1 control-plane (cp) + 2 workers (wn1, wn2), all `Ready` on `v1.36.1+rke2r2`.
	- Core system pods Running: canal, coredns (+autoscaler), metrics-server, snapshot-controller, kube-proxy on all nodes; helm-install jobs Completed.
- Docker VM base bootstrap (Phase B1): PASSED
	- Latest result: `ok=10 changed=5 unreachable=0 failed=0`.
- Platform stack (Phase B2: Postgres + Traefik + Dockhand): PASSED
	- Latest result: `ok=13 changed=6 unreachable=0 failed=0`.
	- Postgres health check: `healthy`.
- ELK stack (Phase B3): PASSED
	- Latest result: `ok=9 changed=2 unreachable=0 failed=0`.
- GitLab stack: PASSED
	- Latest result: `ok=18 changed=5 unreachable=0 failed=0`.
	- GitLab readiness check passed.
	- Runner verify message: `rc=0` (registered and reachable).
- SonarQube stack: PASSED
	- Latest result: `ok=10 changed=4 unreachable=0 failed=0`.
- Web access checks: PASSED
	- Dockhand, GitLab, and SonarQube are HTTP 200 and browser-accessible.
- Jump host to Docker VM deployment flow: PASSED

## Done (documented in Markdown)

- Docker VM base bootstrap (Phase B1): DONE
	- Evidence: README shows successful Ansible result `ok=8 changed=1 unreachable=0 failed=0`.
- Platform stack startup (Phase B2: Postgres + Traefik + Dockhand): DONE
	- Evidence: README shows Postgres health `healthy` and final `ok=7 changed=2 unreachable=0 failed=0`.
- ELK stack deployment (Phase B3): DONE
	- Evidence: README documents ELK deployed and expected running containers.
- Kibana through Traefik: DONE
	- Evidence: previously recorded as success in this file and still retained.

## In Progress / Investigating

- No active Docker-platform blockers reported in the latest run.

## Not Marked Done in Markdown (planned or target state)

- Full Kubernetes platform service rollout (cert-manager, Envoy, ArgoCD, Headlamp, OTel)
- WSO2 APIM/IS production rollout through ArgoCD
- Migration and lifecycle validation phases (F)
- Full MVP Definition of Done checklist in updated-mvp.md
- Note: Kubernetes is provided by the RKE2 cluster (above); Talos rollout is no longer the active path.

## Applied Fixes Recorded

- Traefik static and dynamic config mounted from docker/traefik.
- Domain variables exported in Ansible before docker compose commands.
- Platform, GitLab, and SonarQube stacks recreated on deploy to refresh routing labels.
- SonarQube deploy uses combined compose with platform compose so `depends_on: postgres` stays valid.
- Dockhand internal backend port is configurable, default `80`.
- Stack playbooks now self-heal remote repo checkout before compose commands.

## Next Run Order

1. ~~Kubernetes cluster~~ — DONE (RKE2 3-node cluster up).
2. Install Kubernetes platform services (cert-manager, Envoy Gateway, ArgoCD, Headlamp, OTel).
3. Deploy WSO2 via ArgoCD.

## Verify Commands

- `curl -Lvk https://dockhand.example.com/`
- `curl -Lvk https://kibana.example.com/`
- `curl -Lvk https://gitlab.example.com/`
- `curl -Lvk https://sonar.example.com/`
