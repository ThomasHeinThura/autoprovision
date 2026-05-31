# Service Status

Last update: 2026-05-31

## Marked Success

- Docker VM provision: SUCCESS
- Elastic stack deployment: SUCCESS
- Kibana via Traefik (`https://kibana.example.com/`): SUCCESS

## In Progress

- Dockhand via Traefik (`https://dockhand.example.com/`): INVESTIGATING (currently HTTP 502)
- GitLab via Traefik (`https://gitlab.example.com/`): INVESTIGATING (currently HTTP 404)
- SonarQube via Traefik (`https://sonar.example.com/`): INVESTIGATING (currently HTTP 404)

## Applied Fixes

- Traefik static and dynamic config mounted from docker/traefik.
- Domain variables are exported correctly in Ansible before docker compose commands.
- Platform/GitLab/SonarQube stacks are recreated on deploy to refresh labels/routing.
- SonarQube deployment uses combined compose files with platform compose so `depends_on: postgres` remains valid.
- Dockhand internal backend port is now configurable with default `80`.

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
