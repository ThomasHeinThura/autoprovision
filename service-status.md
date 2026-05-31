# Service Status

Last update: 2026-05-31
Scope: consolidated from all workspace Markdown files.

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

- Dockhand via Traefik (https://dockhand.example.com/): INVESTIGATING (HTTP 502)
- GitLab via Traefik (https://gitlab.example.com/): INVESTIGATING (HTTP 404)
- SonarQube via Traefik (https://sonar.example.com/): INVESTIGATING (HTTP 404)
- GitLab Runner registration/config stability: INVESTIGATING

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

1. Run Platform Stack from UI.
2. Run ELK Stack from UI.
3. Run GitLab Stack from UI.
4. Run SonarQube Stack from UI.

## Verify Commands

- `curl -Lvk https://dockhand.example.com/`
- `curl -Lvk https://kibana.example.com/`
- `curl -Lvk https://gitlab.example.com/`
- `curl -Lvk https://sonar.example.com/`
