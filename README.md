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

## 4. Verify the web UI

From your browser, open the URL printed by the script, for example:

```text
http://192.168.139.64:3000/
```

You should see a minimal placeholder page:

- Title: **Autoprovision Control Plane**
- Text: "Jump host bootstrap completed. FastAPI web UI is running."

Health check endpoint:

```text
http://192.168.139.64:3000/healthz
```

Returns:

```json
{"status": "ok"}
```

This confirms that:

- The jump host has Python, Ansible, talosctl.
- The virtualenv is working.
- Uvicorn is serving `app.main:app` on port 3000.

---

## 5. Next steps (not implemented yet)

The current UI is only a placeholder. The next steps are:

1. **Service cards and forms**
   - Implement the service cards described in `installation-steps.md`.
   - Add forms for environment selection (Lab/UAT/Prod), Docker VM IP, Talos node IPs, SQL Server details, etc.

2. **Ansible integration**
   - Wire buttons in the UI to run Ansible playbooks via `ansible-runner`.
   - Implement roles/playbooks for:
     - Docker platform (PostgreSQL, Traefik, Dockhand, GitLab, SonarQube, ELK, ElastAlert2).
     - Talos cluster creation and Cilium install.
     - Kubernetes platform services (cert-manager, Envoy Gateway, ArgoCD, Headlamp, OTel).
     - WSO2 APIM/IS deployment and migration jobs.

3. **State and job history**
   - Replace the placeholder `state.db` logic with real migrations.
   - Store environments, variables, job history, and statuses in SQLite.
   - Expose job logs and history through the UI.

4. **Docker VM automation**
   - On the Docker VM, use Ansible from the jump host to:
     - Install base tools (`git`, `curl`, `wget`, Docker).
     - Clone `autoprovision` repository.
     - Run Docker compose stacks from `docker/uat/*` or `docker/prod/*` in the defined order.

All of these steps are described at a high level in `installation-steps.md`. The README focuses only on getting the jump host ready and the web UI running.
