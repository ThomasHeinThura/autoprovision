# Backend API reference

[`docs.yaml`](docs.yaml) is the TaskDesk backend (app1) OpenAPI spec in YAML — a snapshot for reviewing the API surface without the stack running.

The app serves the live spec as JSON at `http://localhost:8080/openapi/v1.json` (via `app.MapOpenApi()`).

## Regenerate `docs.yaml`

With the stack up (`docker compose up -d`):

```sh
curl -s http://localhost:8080/openapi/v1.json \
  | python3 -c "import sys,json,yaml; yaml.safe_dump(json.load(sys.stdin), open('api/docs.yaml','w'), sort_keys=False, allow_unicode=True, width=100)"
```

## Endpoints

| Method | Path |
| --- | --- |
| GET | `/api/v1/customers` |
| GET, POST | `/api/v1/projects` |
| GET | `/api/v1/projects/{key}` |
| GET | `/api/v1/projects/{key}/workitems` |
| GET | `/api/v1/workitems/{key}` |
| POST | `/api/v1/workitems` |
| POST | `/api/v1/workitems/{key}/transition` |
| POST | `/api/v1/workitems/{key}/comments` |
| GET | `/api/v1/reports/overview` |
| GET | `/api/v1/modules` |
| POST | `/api/v1/modules/{key}/toggle` |
