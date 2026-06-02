# Autoprovision

Control plane and automation for bootstrapping the jump host, Docker platform, and Talos/Kubernetes stack.

This repository contains:

- `bootstrap-jumphost.sh` – one-shot script to prepare a fresh jump host.
- `installation-steps.md` – detailed operator flow and planning document.
- `talos-installation.md` – lab Talos/Kubernetes install guide for 1 control plane and 2 workers.
- `production-talos-installation.md` – production Talos/Kubernetes install guide for 3 control planes and 5 workers.
- `updated-mvp.md` – MVP scope and environment model.
- `vm-requirements.md` – VM sizing for Lab, UAT, and Production.
- `version.md` – version matrix (Talos, Cilium, Elastic, GitLab, WSO2, etc.).
- `wso2_apim.md` – WSO2 APIM design and migration notes.
- `app/` – Python FastAPI web UI (control plane).
- `ansible/` – Ansible playbooks for all phases.
- `docker/` – Docker compose files for the platform stack and ELK.

---

## 1. Prerequisites on the jump host

Use a clean Ubuntu/Debian-style VM for the jump host.

Install basic tools first:

```bash
sudo apt update
sudo apt install -y git curl wget sshpass
```

---

## 2. Clone the repository

On the jump host:

```bash
cd ~
git clone https://github.com/ThomasHeinThura/autoprovision.git
cd autoprovision
```

---

## 3. Run the bootstrap script (once)

```bash
chmod +x bootstrap-jumphost.sh
./bootstrap-jumphost.sh
```

What this script does:

- Installs system dependencies (git, curl, Python 3, venv, pip, Ansible, sshpass, talosctl, kubectl, helm, cilium CLI).
- Creates a Python virtualenv in `.venv/`.
- Installs Python dependencies from `requirements.txt` (FastAPI, Uvicorn, Ansible).
- Creates `data/` directories for state, logs, inventory, generated env files.
- Starts the FastAPI web UI on port `3000` using `uvicorn app.main:app`.
- Prints the URL to open at the end.

Example output:

```text
[INFO]  Bootstrap complete.
Open: http://<jump-host-ip>:3000/
```

To stop the web UI:

```bash
pkill -f "uvicorn app.main:app"
```

To restart:

```bash
./bootstrap-jumphost.sh
```

---

## 4. Prepare the Docker VM automation user (one-time)

On the Docker VM, create a dedicated automation user:

```bash
ssh existing-admin@<docker-vm-ip>

sudo adduser autoprovision
sudo usermod -aG sudo autoprovision
sudo visudo -f /etc/sudoers.d/autoprovision
```

Add:

```text
autoprovision ALL=(ALL) NOPASSWD:ALL
```

Verify:

```bash
su - autoprovision
sudo id
# Expected: uid=0(root) ... without password prompt
```

In the web UI, enter:

- SSH username: `autoprovision`
- SSH password: the password set with `adduser`

---

## 5. Open the web UI and fill the form

```text
http://<jump-host-ip>:3000/
```

Fill the **"Environment & SSH"** form:

Two one-screen pages are now available:

- Docker page: `http://<jump-host-ip>:3000/docker`

| Field | Example |
|---|---|
| Environment | `lab` / `uat` / `prod` |
| Docker VM IP | `192.168.79.131` |
| SSH username | `autoprovision` |
| SSH password | your password |
| Dockhand domain | `dockhand.example.com` |
| Kibana domain | `kibana.example.com` |
| GitLab domain | `gitlab.example.com` |

---

## 6. Phase B1 — Docker VM base setup

Click **"Run Phase B1: Bootstrap Docker base"**.

What it does on the Docker VM:

- Updates apt cache.
- Installs base packages: `git`, `curl`, `wget`, `ca-certificates`, `gnupg`, `lsb-release`.
- Installs Docker CE using the official convenience script.
- Ensures the `docker` service is enabled and started.
- Adds the automation user to the `docker` group.
- Clones this repo into `/home/<automation-user>/autoprovision`.

Expected final log line:

```text
ok=8  changed=1  unreachable=0  failed=0
```

Verify on Docker VM:

```bash
docker --version
ls ~/autoprovision
```

---

## 7. Phase B2 — Start platform stack (Postgres + Traefik + Dockhand)

Click **"Run Phase B2: Start platform stack"**.

What it does on the Docker VM:

- Uses `/home/<automation-user>/autoprovision/docker` as the compose directory.
- Pulls Postgres 17, Traefik v3, and Dockhand images.
- Runs `docker compose -f docker-compose.platform.yml up -d`.
- Waits for the `pg-platform` Postgres container healthcheck to report `healthy` (retries up to 20 times, 5s delay).

Expected log output:

```text
TASK [Show compose directory]
ok: "Using compose_dir=/home/autoprovision/autoprovision/docker"

TASK [Pull latest platform images (Postgres, Traefik, Dockhand)]
changed: ...

TASK [Bring up platform stack (Postgres + Traefik + Dockhand)]
changed: ...

TASK [Wait for Postgres to be healthy]
ok: ...

TASK [Report Postgres health status]
ok: "Postgres health: healthy"

ok=7  changed=2  unreachable=0  failed=0
```

Verify on Docker VM:

```bash
docker ps
# Expect: pg-platform (healthy), traefik, dockhand
```

---

## 8. Phase B3 — ELK stack (Elasticsearch + Logstash + Kibana + Fleet + APM)

### 8a. Before running B3: verify kibana.yml has encryption keys

The ELK stack is committed to `docker/elk/` inside this repo.  
Kibana requires encryption keys for Fleet to work. Without them you will see:

```text
Unable to initialize Fleet
Agent binary source needs encrypted saved object api key to be set
```

The `kibana/config/kibana.yml` inside `docker/elk/` already includes:

```yaml
xpack.encryptedSavedObjects.encryptionKey: "Add-more-than-32-characters-for-the-key-value"
xpack.fleet.agents.tlsCheckDisabled: true
```

**Before your first deployment**, replace the placeholder with a real 32+ character key:

```bash
# Generate a key (run once, keep the output)
openssl rand -hex 32
```

Edit `docker/elk/kibana/config/kibana.yml` and replace the placeholder value, then commit to the repo so B3 picks it up automatically.

The file also pre-declares the `Agent Policy APM Server` policy (and Fleet Server Policy) under `xpack.fleet.agentPolicies`, which means the APM agent will find its policy on first boot without manual Kibana UI steps.

### 8b. Run B3

Click **"Phase B3: Deploy ELK stack"**.

What it does on the Docker VM:

1. Confirms the ELK directory exists at `/home/<automation-user>/autoprovision/docker/elk`.
2. Runs initial user setup (one-time per stack):

   ```bash
   docker compose up setup
   ```

   This creates built-in users (`elastic`, `logstash_internal`, `kibana_system`, etc.) with passwords from the `.env` file.

3. Starts all services:

   ```bash
   docker compose \
     -f docker-compose.yml \
     -f extensions/fleet/fleet-compose.yml \
     -f extensions/fleet/agent-apmserver-compose.yml \
     up -d
   ```

   Services started:

   | Container | Role | Port |
   |---|---|---|
   | `elk-elasticsearch-1` | Elasticsearch | 9200, 9300 |
   | `elk-logstash-1` | Logstash | 5044, 50000, 9600 |
   | `elk-kibana-1` | Kibana UI | 5601 |
   | `elk-fleet-server-1` | Fleet Server | 8220 |
   | `elk-apm-server-1` | APM Agent | 8200 |

Expected final log line:

```text
ELK stack (Elasticsearch, Logstash, Kibana, Fleet, APM Server) deployed from /home/.../docker/elk.
```

Verify on Docker VM:

```bash
docker ps
# Expect all 5 ELK containers running

curl -u elastic:changeme http://localhost:9200
# Expect JSON with cluster_name: docker-cluster
```

### 8c. APM Server startup sequence

The APM container (`elk-apm-server-1`) connects to Fleet and looks for `Agent Policy APM Server`.

Normal sequence on first boot:

1. Early restarts with `connect: connection refused` — **normal**, Kibana is still starting.
2. `Kibana server is not ready yet` — **normal**, Kibana is initializing.
3. Fleet starts, policy `Agent Policy APM Server` is found (pre-declared in `kibana.yml`), agent enrolls and stays `Up`.

If `elk-apm-server-1` keeps restarting with `policy not found` after Kibana is healthy, check:

```bash
docker logs elk-kibana-1 | tail -20
docker logs elk-fleet-server-1 | tail -20
```

---

## 9. GitLab first login and Runner registration (required once)

After GitLab stack is up, complete this one-time setup.

### 9a. Get the initial GitLab root password

On the Docker VM:

```bash
docker exec gitlab cat /etc/gitlab/initial_root_password
```

Use that password to log in as user `root` at:

- `https://<your-gitlab-domain>/`

### 9b. Create a Runner token in GitLab UI

In GitLab UI, go to:

1. Admin
2. CI/CD
3. Runners
4. New instance runner

Copy the generated runner token.

### 9c. Register runner through Autoprovision

1. In Autoprovision UI, open **GitLab Stack**.
2. Paste the token into **GitLab Runner Token (optional, not saved)**.
3. Click Deploy.

The playbook will register the runner and verify it.

### 9d. Manual registration fallback (optional)

If you need manual fallback:

```bash
docker exec -it gitlab-runner gitlab-runner register \
   --non-interactive \
   --url "https://gitlab.example.com" \
   --token "<RUNNER_TOKEN_FROM_GITLAB_UI>" \
   --executor "docker" \
   --docker-image "alpine:latest" \
   --description "local-docker-runner" \
   --docker-privileged \
   --docker-volumes "/var/run/docker.sock:/var/run/docker.sock" \
   --docker-volumes "/cache" \
   --docker-volumes "/etc/gitlab-runner/certs/gitlab.example.com.crt:/usr/local/share/ca-certificates/local-dev-ca.crt:ro" \
   --docker-pull-policy "if-not-present" \
   --docker-extra-hosts "gitlab.example.com:host-gateway" \
   --docker-extra-hosts "registry.example.com:host-gateway"
```

Verify:

```bash
docker exec gitlab-runner gitlab-runner verify
```

---

## 10. Default ELK credentials

The `docker-elk` stack uses credentials defined in `docker/elk/.env`.

Defaults (do not use as-is in production):

| Service | Username | Password |
|---|---|---|
| Elasticsearch | `elastic` | `changeme` |
| Kibana | `elastic` | `changeme` |
| Logstash internal | `logstash_internal` | `changeme` |

Access:

- Kibana UI: `http://<docker-vm-ip>:5601` → login: `elastic` / `changeme`
- Elasticsearch API: `curl -u elastic:changeme http://<docker-vm-ip>:9200`
- APM intake: `http://<docker-vm-ip>:8200`
- Fleet Server: `http://<docker-vm-ip>:8220`

**To change passwords:** edit `docker/elk/.env` before running B3. Run `docker compose up setup` again after changing passwords.

---

## 11. Health checks and quick troubleshooting

### Platform stack (B2)

```bash
docker ps | grep -E 'pg-platform|traefik|dockhand'
```

Expected: all `Up` and `pg-platform` shows `(healthy)`.

### ELK stack (B3)

```bash
# All containers
docker ps

# Elasticsearch
curl -u elastic:changeme http://localhost:9200/_cluster/health

# Kibana
curl http://localhost:5601/api/status | python3 -m json.tool | grep overall

# Fleet Server
curl http://localhost:8220/api/status

# APM
curl http://localhost:8200/
```

### Common issues

| Symptom | Cause | Fix |
|---|---|---|
| `open .../docker-compose.platform.yml: no such file or directory` | Repo not cloned or stale on Docker VM | Re-run Phase B1 |
| `pull access denied for dockhand/dockhand` | Wrong image name | Fixed in repo: image is `fnsys/dockhand:latest` |
| Postgres health check never passes | Container crash or slow start | Run `docker logs pg-platform`; check `.env` passwords |
| `Unable to initialize Fleet` / `encrypted saved object api key` | Missing `xpack.encryptedSavedObjects.encryptionKey` in `kibana.yml` | Set a 32+ char key in `docker/elk/kibana/config/kibana.yml` and restart Kibana |
| APM restarts: `policy not found` | Fleet has no `Agent Policy APM Server` policy | Verify `kibana.yml` has `xpack.fleet.agentPolicies` block; restart Kibana and Fleet |
| `Kibana server is not ready yet` | Kibana still initializing | Wait 60-90s; check `docker logs elk-kibana-1` |
| GitLab Runner gets `404 Not Found` or `403 Forbidden` on `/api/v4/jobs/request` | Runner uses placeholder/invalid token or wrong token type | Create a new instance runner token in GitLab UI, paste into Autoprovision GitLab Runner Token field, and re-run GitLab Stack |

---

For Kubernetes phases (D1, D2), WSO2 deployment (E), and migration jobs (F), see `installation-steps.md` and `updated-mvp.md`.
