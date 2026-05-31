# Service Status

Last update: 2026-05-31
Scope: consolidated from all workspace Markdown files.

## Finished and Tested (current lab state)

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

- Talos cluster rollout phases (D1, D2)
- Full Kubernetes platform service rollout (cert-manager, Envoy, ArgoCD, Headlamp, OTel)
- WSO2 APIM/IS production rollout through ArgoCD
- Migration and lifecycle validation phases (F)
- Full MVP Definition of Done checklist in updated-mvp.md

## Applied Fixes Recorded

- Traefik static and dynamic config mounted from docker/traefik.
- Domain variables exported in Ansible before docker compose commands.
- Platform, GitLab, and SonarQube stacks recreated on deploy to refresh routing labels.
- SonarQube deploy uses combined compose with platform compose so `depends_on: postgres` stays valid.
- Dockhand internal backend port is configurable, default `80`.
- Stack playbooks now self-heal remote repo checkout before compose commands.

## Next Run Order

1. Start Kubernetes setup (Talos cluster creation flow).
2. Install Kubernetes platform services (cert-manager, Envoy Gateway, ArgoCD, Headlamp, OTel).
3. Deploy WSO2 via ArgoCD.

## Verify Commands

- `curl -Lvk https://dockhand.example.com/`
- `curl -Lvk https://kibana.example.com/`
- `curl -Lvk https://gitlab.example.com/`
- `curl -Lvk https://sonar.example.com/`
