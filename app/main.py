from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import asyncio
import json
import os
import subprocess
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANSIBLE_DIR = os.path.join(BASE_DIR, "ansible")
INVENTORY_FILE = os.path.join(ANSIBLE_DIR, "inventory")

app = FastAPI(title="Autoprovision Control Plane", version="0.3.0")


@app.get("/healthz")
async def healthz():
  return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
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
      small { color: #6b7280; }
      code { background: #f3f4f6; padding: 0.1rem 0.25rem; border-radius: 4px; }
      ul { padding-left: 1.1rem; }
      .log { background: #000; color: #0f0; font-family: monospace; font-size: 0.75rem; padding: 0.5rem; border-radius: 4px; max-height: 260px; overflow-y: auto; white-space: pre-wrap; }
    </style>
  </head>
  <body>
    <h1>Autoprovision Control Plane</h1>
    <p><small>Jump host bootstrap completed. FastAPI web UI is running. This UI will call Ansible playbooks and track job state in later iterations.</small></p>
    <div class=\"layout\">
      <div class=\"card\">
        <h2>Environment</h2>
        <form method=\"post\" action=\"/actions/bootstrap-docker\">\n"
        "          <label>\n"
        "            Environment\n"
        "            <select name=\"env\">\n"
        "              <option value=\"lab\">Lab</option>\n"
        "              <option value=\"uat\">UAT</option>\n"
        "              <option value=\"prod\">Production</option>\n"
        "            </select>\n"
        "          </label>\n"
        "          <label>\n"
        "            Docker VM IP\n"
        "            <input name=\"docker_ip\" placeholder=\"192.168.x.x\" />\n"
        "          </label>\n"
        "          <p><small>For now, only the Docker VM IP is used. Values are written to <code>ansible/inventory</code> for a single host.</small></p>\n"
        "          <button type=\"submit\">Phase B: Bootstrap Docker platform (base packages + Docker)</button>\n"
        "        </form>\n"
        "      </div>\n"
        "      <div class=\"card\">\n"
        "        <h2>Last job (docker base)</h2>\n"
        "        <p><small>This shows the last <code>ansible-playbook ansible/docker_vm_base.yml</code> run invoked by the UI.</small></p>\n"
        "        <div id=\"log\" class=\"log\">Logs appear here after you run the job.</div>\n"
        "      </div>\n"
        "    </div>\n"
        "    <script>\n"
        "    fetch('/logs/docker-base').then(r => r.ok ? r.text() : '').then(t => { if (t) document.getElementById('log').textContent = t; });\n"
        "    </script>\n"
        "  </body>\n"
        "</html>\n"""


def _env_to_group(env: str) -> str:
  env = (env or "").lower()
  if env == "lab":
    return "docker_lab"
  if env == "uat":
    return "docker_uat"
  if env == "prod":
    return "docker_prod"
  return "docker_lab"


def _write_inventory(env: str, docker_ip: str) -> None:
  group = _env_to_group(env)
  os.makedirs(os.path.dirname(INVENTORY_FILE), exist_ok=True)
  with open(INVENTORY_FILE, "w", encoding="utf-8") as f:
    f.write(f"[{group}]\n")
    if docker_ip:
      f.write(f"{docker_ip} ansible_user={{ ansible_user | default('ubuntu') }}\n")


async def _run_ansible_playbook(playbook: str, log_path: str) -> int:
  os.makedirs(os.path.dirname(log_path), exist_ok=True)
  cmd = [
    "ansible-playbook",
    "-i",
    INVENTORY_FILE,
    playbook,
  ]
  proc = await asyncio.create_subprocess_exec(
    *cmd,
    cwd=BASE_DIR,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.STDOUT,
  )
  lines = []
  while True:
    line = await proc.stdout.readline()
    if not line:
      break
    text = line.decode("utf-8", errors="replace")
    lines.append(text)
  rc = await proc.wait()
  with open(log_path, "w", encoding="utf-8") as f:
    f.writelines(lines)
  return rc


@app.post("/actions/bootstrap-docker")
async def action_bootstrap_docker(env: str = Form(...), docker_ip: str = Form(...)):
  _write_inventory(env, docker_ip)
  log_path = os.path.join(BASE_DIR, "data", "logs", "docker-base.log")
  rc = await _run_ansible_playbook(os.path.join("ansible", "docker_vm_base.yml"), log_path)
  return RedirectResponse(url="/", status_code=303)


@app.get("/logs/docker-base", response_class=HTMLResponse)
async def get_docker_base_log():
  log_path = os.path.join(BASE_DIR, "data", "logs", "docker-base.log")
  if not os.path.exists(log_path):
    return ""
  with open(log_path, "r", encoding="utf-8") as f:
    return f.read()
