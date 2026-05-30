from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="Autoprovision Control Plane", version="0.2.0")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Minimal control-plane shell: environment form + action buttons.
    return """<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <title>Autoprovision Control Plane</title>
    <style>
      body { font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; background: #f5f5f5; }
      .layout { display: grid; grid-template-columns: minmax(0, 320px) minmax(0, 520px); gap: 2rem; align-items: flex-start; }
      .card { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.5rem; }
      h1 { margin-top: 0; }
      h2 { margin-top: 0; font-size: 1.1rem; }
      label { display: block; margin-top: 0.5rem; font-size: 0.9rem; }
      input, select { width: 100%; padding: 0.35rem 0.5rem; margin-top: 0.15rem; box-sizing: border-box; }
      button { margin-top: 0.75rem; padding: 0.4rem 0.9rem; border-radius: 4px; border: 1px solid #0f766e; background: #0d9488; color: #fff; cursor: pointer; font-size: 0.9rem; }
      button.secondary { border-color: #4b5563; background: #6b7280; }
      button:disabled { opacity: 0.6; cursor: not-allowed; }
      small { color: #6b7280; }
      code { background: #f3f4f6; padding: 0.1rem 0.25rem; border-radius: 4px; }
      ul { padding-left: 1.1rem; }
    </style>
  </head>
  <body>
    <h1>Autoprovision Control Plane</h1>
    <p><small>Jump host bootstrap completed. FastAPI web UI is running. This UI is a thin shell that will later call Ansible playbooks and track job state.</small></p>
    <div class=\"layout\">
      <div class=\"card\">
        <h2>Environment</h2>
        <form>
          <label>
            Environment
            <select name=\"env\">
              <option value=\"lab\">Lab</option>
              <option value=\"uat\">UAT</option>
              <option value=\"prod\">Production</option>
            </select>
          </label>
          <label>
            Docker VM IP
            <input name=\"docker_ip\" placeholder=\"192.168.x.x\" />
          </label>
          <label>
            Talos control plane IPs (comma separated)
            <input name=\"talos_cp\" placeholder=\"10.0.0.10,10.0.0.11,...\" />
          </label>
          <label>
            Talos worker IPs (comma separated)
            <input name=\"talos_workers\" placeholder=\"10.0.0.20,10.0.0.21,...\" />
          </label>
          <label>
            SQL Server host
            <input name=\"sql_host\" placeholder=\"sql.example.internal\" />
          </label>
          <p><small>
            In later versions this form will persist values in SQLite and feed Ansible inventory.
          </small></p>
        </form>
      </div>

      <div class=\"card\">
        <h2>Actions (stubs)</h2>
        <p><small>
          These buttons are placeholders. In the next iteration they will trigger Ansible playbooks for each phase.
        </small></p>
        <form method=\"post\" action=\"/actions/bootstrap-docker\">
          <button type=\"submit\">Phase B: Bootstrap Docker platform</button>
        </form>
        <form method=\"post\" action=\"/actions/create-talos-cluster\">
          <button type=\"submit\">Phase D1: Create Talos cluster + install Cilium</button>
        </form>
        <form method=\"post\" action=\"/actions/install-k8s-platform\">
          <button type=\"submit\">Phase D2: Install Kubernetes platform (Envoy, cert-manager, ArgoCD, Headlamp, OTel)</button>
        </form>
        <form method=\"post\" action=\"/actions/deploy-wso2\">
          <button type=\"submit\">Phase E: Deploy WSO2 APIM &amp; IS via ArgoCD</button>
        </form>
        <form method=\"post\" action=\"/actions/run-migration\">
          <button type=\"submit\" class=\"secondary\">Phase F: Run migration jobs (Elasticsearch &amp; APIM)</button>
        </form>
        <p><small>
          For now, each action returns a JSON stub like <code>{\"status\": \"not_implemented\"}</code>.
        </small></p>
      </div>
    </div>
  </body>
</html>
"""


@app.post("/actions/bootstrap-docker")
async def action_bootstrap_docker():
    # TODO: wire to Ansible playbook for Docker platform (Phase B).
    return JSONResponse({"action": "bootstrap-docker", "status": "not_implemented"})


@app.post("/actions/create-talos-cluster")
async def action_create_talos_cluster():
    # TODO: wire to Ansible playbook that runs talosctl gen/apply/bootstrap + Cilium Helm install.
    return JSONResponse({"action": "create-talos-cluster", "status": "not_implemented"})


@app.post("/actions/install-k8s-platform")
async def action_install_k8s_platform():
    # TODO: wire to Ansible playbook that installs cert-manager, Envoy Gateway, ArgoCD, Headlamp, OTel.
    return JSONResponse({"action": "install-k8s-platform", "status": "not_implemented"})


@app.post("/actions/deploy-wso2")
async def action_deploy_wso2():
    # TODO: wire to Ansible/ArgoCD sync for WSO2 APIM and WSO2 IS.
    return JSONResponse({"action": "deploy-wso2", "status": "not_implemented"})


@app.post("/actions/run-migration")
async def action_run_migration():
    # TODO: wire to Python migration job + Ansible tasks for Elasticsearch and APIM.
    return JSONResponse({"action": "run-migration", "status": "not_implemented"})
