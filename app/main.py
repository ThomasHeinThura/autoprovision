from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Autoprovision Control Plane", version="0.1.0")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index():
    # Minimal placeholder UI. The real UI will be implemented later
    # with templates, HTMX, and environment/service forms.
    return """<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <title>Autoprovision Control Plane</title>
    <style>
      body { font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; }
      .card { border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.5rem; max-width: 640px; }
      h1 { margin-top: 0; }
      code { background: #f5f5f5; padding: 0.1rem 0.25rem; border-radius: 4px; }
    </style>
  </head>
  <body>
    <div class=\"card\">
      <h1>Autoprovision Control Plane</h1>
      <p>Jump host bootstrap completed. FastAPI web UI is running.</p>
      <p>
        Next steps:
      </p>
      <ol>
        <li>Implement service cards and environment forms under <code>app/</code>.</li>
        <li>Wire buttons to Ansible via <code>ansible-runner</code>.</li>
        <li>Expose job logs and status history from the SQLite state DB.</li>
      </ol>
      <p>For now, you can use <code>/healthz</code> for a basic readiness check.</p>
    </div>
  </body>
</html>
"""
