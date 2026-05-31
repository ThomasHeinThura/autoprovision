# Autoprovision

Control plane and automation for bootstrapping the jump host, Docker platform, and Talos/Kubernetes stack.

This repository contains:

- `bootstrap-jumphost.sh` – one-shot script to prepare a fresh jump host.
- `installation-steps.md` – detailed operator flow and planning document.
- `updated-mvp.md` – MVP scope and environment model.
- `vm-requirements.md` – VM sizing for Lab, UAT, and Production.
- `version.md` – version matrix (Talos, Cilium, Elastic, GitLab, WSO2, etc.).
- `wso2_apim.md` – WSO2 APIM design and migration notes.
- `app/` – Python FastAPI web UI (control plane).

---

## 1. Prerequisites on the jump host

Use a clean Ubuntu/Debian-style VM for the jump host.

Install basic tools first:

```bash
sudo apt update
sudo apt install -y git curl wget sshpass
```

(If you run a different distro, install `git`, `curl`, `wget`, and `sshpass` with the equivalent package manager.)

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

Make the script executable and run it with bash:

```bash
chmod +x bootstrap-jumphost.sh
./bootstrap-jumphost.sh
```

What this script does:

- Installs system dependencies (git, curl, Python 3, venv, pip, Ansible, ansible-runner, sshpass, talosctl).
- Creates a Python virtualenv in `.venv/`.
- Installs Python dependencies from `requirements.txt` (FastAPI, Uvicorn, Ansible, ansible-runner).
- Creates `data/` directories for state, logs, inventory, generated env files.
- Initializes an empty SQLite DB at `data/state.db` (placeholder until the app manages migrations).
- Starts the FastAPI web UI on port `3000` using `uvicorn app.main:app`.
- Prints the URL to open at the end.

Example output:

```text
[INFO]  Preparing data directories...
[INFO]  Initializing empty state DB at /home/<user>/autoprovision/data/state.db...
[INFO]  Starting Python web UI on port 3000...
[INFO]  Web UI started via uvicorn (app.main:app).

[INFO]  Bootstrap complete.
Open: http://192.168.139.64:3000/
```

To stop the web UI later:

```bash
pkill -f "uvicorn app.main:app"
```

Then restart with:

```bash
./bootstrap-jumphost.sh
```

---

## 4. Prepare the Docker VM automation user (one-time)

For security and clarity, use a **dedicated automation user** on the Docker VM instead of a personal account.

On the Docker VM (example user `autoprovision`):

```bash
# SSH into the Docker VM once as an existing sudo-capable user
ssh existing-admin@<docker-vm-ip>

# 1) Create the automation user
sudo adduser autoprovision

# 2) (Optional but common) add it to the sudo group
sudo usermod -aG sudo autoprovision

# 3) Give it passwordless sudo via a sudoers snippet
sudo visudo -f /etc/sudoers.d/autoprovision
```

Add:

```text
autoprovision ALL=(ALL) NOPASSWD:ALL
```

Save and exit.

Verify the automation user:

```bash
su - autoprovision
sudo -l
sudo id
```

Expected:

- `sudo -l` shows `NOPASSWD: ALL` for `autoprovision`.
- `sudo id` prints `uid=0(root) gid=0(root) groups=0(root)` without prompting for a password.

This is a **one-time** requirement per environment image. Once the Docker VM (or template) has this user set up, all future runs from the jump host will work without manual SSH.

In the web UI, you will then use:

- SSH username: `autoprovision`.
- SSH password: the login password you set with `adduser`.

Ansible will log in as this automation user and use `sudo` (become) without prompting for a password.

---

## 5. Run Phases B1–B3 from the web UI

1. Open the web UI

   ```text
   http://<jump-host-ip>:3000/
   ```

2. Fill the "Environment & SSH" form:

   - Environment: `lab`, `uat`, or `prod`.
   - Docker VM IP: the IP address of your Docker platform VM.
   - SSH username: `autoprovision` (or your automation user).
   - SSH password: password for that user (leave empty if using SSH key).
   - Dockhand domain: e.g. `dockhand.example.com`.
   - Kibana domain: e.g. `kibana.example.com`.
   - GitLab domain (reserved for later): e.g. `gitlab.example.com`.

3. Phase B1 — Docker VM base setup

   - Click **"Run Phase B1: Bootstrap Docker base"**.
   - What it does on the Docker VM:
     - Updates apt cache.
     - Installs base packages (`git`, `curl`, `wget`, `ca-certificates`, `gnupg`, `lsb-release`).
     - Installs Docker CE using the official convenience script.
     - Ensures the `docker` service is enabled and started.
     - Adds the automation user to the `docker` group.
     - Clones this repo into `/home/<automation-user>/autoprovision`.
   - The log panel shows each task and the final Ansible recap.

4. Phase B2 — Start platform stack (Postgres + Traefik + Dockhand)

   - Click **"Run Phase B2: Start platform stack"**.
   - What it does on the Docker VM:
     - Uses `/home/<automation-user>/autoprovision/docker` as the compose directory.
     - Runs `docker compose -f docker-compose.platform.yml pull` to pull the Postgres, Traefik, and Dockhand images.
     - Runs `docker compose -f docker-compose.platform.yml up -d`.
     - Waits for the `pg-platform` container healthcheck to report `healthy`.
   - The log panel prints:
     - The compose directory.
     - Pull/start output.
     - `Postgres health: healthy` when the database is ready.
   - After success, you should see on the Docker VM:

     ```bash
     docker ps
     # ... pg-platform (Postgres), traefik, dockhand all running
     ```

5. Phase B3 — ELK stack (docker-elk)

   - Click **"Phase B3: Deploy ELK stack"**.
   - What it does on the Docker VM:
     - Clones or updates `https://github.com/deviantony/docker-elk.git` into `/home/<automation-user>/autoprovision/docker/elk`.
     - Runs initial setup:

       ```bash
       docker compose up setup
       ```

       This initializes built-in users (`elastic`, `logstash_internal`, `kibana_system`, etc.) with passwords from `.env` in the `docker-elk` repo.

     - Starts Elasticsearch, Logstash, Kibana, Fleet Server, and APM Server with:

       ```bash
       docker compose \
         -f docker-compose.yml \
         -f extensions/fleet/fleet-compose.yml \
         -f extensions/fleet/agent-apmserver-compose.yml \
         up -d
       ```

   - The log panel prints the ELK directory, setup output, and a final message:

     ```text
     ELK stack (Elasticsearch, Logstash, Kibana, Fleet, APM Server) deployed from /home/<automation-user>/autoprovision/docker/elk.
     ```

---

## 6. Default ELK credentials

The `docker-elk` stack uses credentials defined in its `.env` file. By default (if you do not change `.env`):

- **Elasticsearch & Kibana user:** `elastic`
- **Password:** `changeme`

After Phase B3 completes and containers are healthy:

- Elasticsearch API:

  ```bash
  curl -u elastic:changeme http://<docker-vm-ip>:9200
  ```

- Kibana UI:

  ```text
  http://<docker-vm-ip>:5601
  ```

  Log in with `elastic` / `changeme` and then rotate passwords as required.

Note: the Fleet-managed APM Server container (`elk-apm-server-1`) looks for an agent policy named `Agent Policy APM Server` in Fleet. Until that policy exists in Kibana/Fleet, the APM container may restart with a "policy not found" error. This does not affect the core ELK stack (Elasticsearch, Logstash, Kibana, Fleet Server).

---

## 7. Health checks and troubleshooting

- Platform stack:

  ```bash
  docker ps
  # Expect: pg-platform, traefik, dockhand running
  ```

- ELK core services:

  ```bash
  docker ps
  # Expect: elk-elasticsearch-1, elk-logstash-1, elk-kibana-1, elk-fleet-server-1
  ```

- APM Server:

  ```bash
  docker logs elk-apm-server-1
  # If you see "policy not found" for "Agent Policy APM Server", create that policy in Kibana Fleet before relying on APM.
  ```

For more in-depth observability and Kubernetes deployment steps, see `installation-steps.md` and `updated-mvp.md`.
