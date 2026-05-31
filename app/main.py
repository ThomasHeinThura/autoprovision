from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import asyncio
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANSIBLE_DIR = os.path.join(BASE_DIR, "ansible")
INVENTORY_FILE = os.path.join(ANSIBLE_DIR, "inventory")

app = FastAPI(title="Autoprovision Control Plane", version="0.4.0")

# ─── helpers ──────────────────────────────────────────────────────────────────

def _env_to_group(env: str) -> str:
    m = {"lab": "docker_lab", "uat": "docker_uat", "prod": "docker_prod"}
    return m.get((env or "").lower(), "docker_lab")


def _write_inventory(env: str, docker_ip: str, ssh_user: str, ssh_pass: str) -> None:
    group = _env_to_group(env)
    os.makedirs(ANSIBLE_DIR, exist_ok=True)
    with open(INVENTORY_FILE, "w", encoding="utf-8") as f:
        f.write(f"[docker_vm]\n")
        line = f"{docker_ip} ansible_user={ssh_user}"
        if ssh_pass:
            line += f" ansible_password={ssh_pass} ansible_become_password={ssh_pass}"
        line += " ansible_become=true ansible_become_method=sudo\n"
        f.write(line)
        f.write(f"\n[{group}]\n")
        f.write(f"{docker_ip}\n")


async def _run_playbook(playbook_rel: str, log_name: str, extra_vars: dict = None) -> int:
    log_path = os.path.join(BASE_DIR, "data", "logs", log_name)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    cmd = [
        "ansible-playbook",
        "-i", INVENTORY_FILE,
        os.path.join(BASE_DIR, playbook_rel),
    ]
    if extra_vars:
        import json
        cmd += ["--extra-vars", json.dumps(extra_vars)]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=BASE_DIR,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    with open(log_path, "w", encoding="utf-8") as lf:
        async for chunk in proc.stdout:
            lf.write(chunk.decode("utf-8", errors="replace"))
    await proc.wait()
    return proc.returncode


def _read_log(name: str) -> str:
    p = os.path.join(BASE_DIR, "data", "logs", name)
    if not os.path.exists(p):
        return "No log yet."
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


# ─── routes ───────────────────────────────────────────────────────────────────

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index():
    log_base = _read_log("docker-base.log")
    log_platform = _read_log("docker-platform.log")
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Autoprovision Control Plane</title>
    <style>
      body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #f5f5f5; }}
      .grid {{ display: grid; grid-template-columns: 320px 1fr; gap: 1.5rem; }}
      .col {{ display: flex; flex-direction: column; gap: 1rem; }}
      .card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.25rem; }}
      h1 {{ margin-top: 0; }}
      h2 {{ margin: 0 0 .75rem; font-size: 1rem; }}
      label {{ display: block; margin-top: .4rem; font-size: .875rem; color: #374151; }}
      input, select {{ width: 100%; padding: .3rem .45rem; margin-top: .1rem; box-sizing: border-box; border: 1px solid #d1d5db; border-radius: 4px; }}
      button {{ display: block; width: 100%; margin-top: .6rem; padding: .4rem; border-radius: 4px;
                border: 1px solid #0f766e; background: #0d9488; color: #fff; cursor: pointer; font-size: .875rem; text-align: left; }}
      button.grey {{ border-color: #6b7280; background: #6b7280; }}
      .badge {{ display: inline-block; padding: .1rem .45rem; border-radius: 9999px; font-size: .75rem;
                background: #d1fae5; color: #065f46; margin-left: .4rem; }}
      .log {{ background: #111; color: #4ade80; font-family: monospace; font-size: .7rem;
              padding: .5rem; border-radius: 4px; max-height: 220px; overflow-y: auto; white-space: pre-wrap; }}
      small {{ color: #6b7280; }}
      code {{ background: #f3f4f6; padding: .1rem .2rem; border-radius: 3px; }}
      hr {{ border: none; border-top: 1px solid #e5e7eb; margin: .75rem 0; }}
    </style>
  </head>
  <body>
    <h1>Autoprovision Control Plane <span style="font-size:.9rem;color:#6b7280;">v0.4.0</span></h1>
    <p><small>Jump host is ready. Use the forms below to provision Docker VM and Kubernetes cluster.</small></p>

    <div class="grid">
      <!-- LEFT: env + SSH form -->
      <div class="col">
        <div class="card">
          <h2>&#9881; Environment &amp; SSH</h2>
          <p><small>Shared form — saved to Ansible inventory before each action.</small></p>
          <form id="env-form">
            <label>Environment
              <select name="env" id="f-env">
                <option value="lab">Lab</option>
                <option value="uat">UAT</option>
                <option value="prod">Production</option>
              </select>
            </label>
            <label>Docker VM IP
              <input id="f-docker-ip" name="docker_ip" placeholder="192.168.x.x" />
            </label>
            <label>SSH username
              <input id="f-ssh-user" name="ssh_user" placeholder="ubuntu" value="ubuntu" />
            </label>
            <label>SSH password (leave empty to use key)
              <input id="f-ssh-pass" name="ssh_pass" type="password" placeholder="••••••••" />
            </label>
          </form>
        </div>

        <!-- Phase D/E/F stubs -->
        <div class="card">
          <h2>&#9749; Kubernetes phases</h2>
          <small>Stubs — will be wired next.</small>
          <button class="grey" disabled>Phase D1: Create Talos cluster + Cilium</button>
          <button class="grey" disabled>Phase D2: Install K8s platform (Envoy, ArgoCD, Headlamp, OTel)</button>
          <button class="grey" disabled>Phase E: Deploy WSO2 via ArgoCD</button>
          <button class="grey" disabled>Phase F: Run migration jobs</button>
        </div>
      </div>

      <!-- RIGHT: Docker actions + logs -->
      <div class="col">
        <div class="card">
          <h2>&#128040; Phase B1 — Docker VM base setup</h2>
          <p><small>Installs git, curl, wget, Docker CE on the Docker VM. Clones this repo to <code>/opt/autoprovision</code>.</small></p>
          <button onclick="submitAction('/actions/bootstrap-docker', 'log-base')">&#9654; Run Phase B1: Bootstrap Docker base</button>
          <hr/>
          <small>Last run output:</small>
          <div class="log" id="log-base">{log_base}</div>
        </div>

        <div class="card">
          <h2>&#128679; Phase B2 — Start platform stack (Postgres + Traefik + Dockhand)</h2>
          <p><small>Runs <code>docker compose -f docker-compose.platform.yml up -d</code> on the Docker VM.</small></p>
          <button onclick="submitAction('/actions/platform-up', 'log-platform')">&#9654; Run Phase B2: Start platform stack</button>
          <hr/>
          <small>Last run output:</small>
          <div class="log" id="log-platform">{log_platform}</div>
        </div>
      </div>
    </div>

    <script>
    function formData() {{
      return {{
        env:       document.getElementById('f-env').value,
        docker_ip: document.getElementById('f-docker-ip').value,
        ssh_user:  document.getElementById('f-ssh-user').value,
        ssh_pass:  document.getElementById('f-ssh-pass').value,
      }};
    }}
    function submitAction(endpoint, logId) {{
      const d = formData();
      if (!d.docker_ip) {{ alert('Docker VM IP is required'); return; }}
      document.getElementById(logId).textContent = 'Running...';
      fetch(endpoint, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(d),
      }})
      .then(r => r.json())
      .then(data => {{
        document.getElementById(logId).textContent = data.log || JSON.stringify(data);
      }})
      .catch(e => {{
        document.getElementById(logId).textContent = 'Error: ' + e;
      }});
    }}
    </script>
  </body>
</html>"""


@app.post("/actions/bootstrap-docker")
async def action_bootstrap_docker(request: Request):
    body = await request.json()
    env      = body.get("env", "lab")
    docker_ip = body.get("docker_ip", "")
    ssh_user  = body.get("ssh_user", "ubuntu")
    ssh_pass  = body.get("ssh_pass", "")
    if not docker_ip:
        return JSONResponse({"error": "docker_ip required"}, status_code=400)
    _write_inventory(env, docker_ip, ssh_user, ssh_pass)
    rc = await _run_playbook("ansible/docker_vm_base.yml", "docker-base.log")
    log = _read_log("docker-base.log")
    return JSONResponse({"rc": rc, "log": log})


@app.post("/actions/platform-up")
async def action_platform_up(request: Request):
    body = await request.json()
    env      = body.get("env", "lab")
    docker_ip = body.get("docker_ip", "")
    ssh_user  = body.get("ssh_user", "ubuntu")
    ssh_pass  = body.get("ssh_pass", "")
    if not docker_ip:
        return JSONResponse({"error": "docker_ip required"}, status_code=400)
    _write_inventory(env, docker_ip, ssh_user, ssh_pass)
    rc = await _run_playbook("ansible/docker_platform_up.yml", "docker-platform.log")
    log = _read_log("docker-platform.log")
    return JSONResponse({"rc": rc, "log": log})


@app.post("/actions/create-talos-cluster")
async def action_create_talos():
    return JSONResponse({"action": "create-talos-cluster", "status": "not_implemented"})


@app.post("/actions/install-k8s-platform")
async def action_k8s_platform():
    return JSONResponse({"action": "install-k8s-platform", "status": "not_implemented"})


@app.post("/actions/deploy-wso2")
async def action_deploy_wso2():
    return JSONResponse({"action": "deploy-wso2", "status": "not_implemented"})


@app.post("/actions/run-migration")
async def action_run_migration():
    return JSONResponse({"action": "run-migration", "status": "not_implemented"})
