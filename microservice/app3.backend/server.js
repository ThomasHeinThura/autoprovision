// app3.backend — TaskDesk BFF + realtime gateway (PLAN §5.3).
//
//  - BFF: aggregates the core API (app1) + workers' cached report (Valkey) into view-shaped responses.
//  - Realtime: WebSocket at /realtime; subscribes to Valkey pub/sub (app2 publishes taskdesk:events)
//    and fans out to browsers. Also broadcasts on any write it proxies.
//  - (Phase 3) this is where channel-gateway webhooks would land.

import express from "express";
import http from "http";
import { WebSocketServer } from "ws";
import Redis from "ioredis";
import { readFileSync } from "fs";

const OPENAPI_DOC = readFileSync(new URL("./docs.yaml", import.meta.url));

const PORT = process.env.PORT || 8082;
const API_BASE = process.env.API_BASE || "http://localhost:5199";
const REDIS_ADDR = process.env.REDIS_ADDR || ""; // host:port; empty = realtime/cache disabled

// ---- Redis / Valkey (optional) ----
let redis = null, sub = null;
if (REDIS_ADDR) {
  redis = new Redis(`redis://${REDIS_ADDR}`, { lazyConnect: false, maxRetriesPerRequest: 2 });
  sub = new Redis(`redis://${REDIS_ADDR}`);
  sub.subscribe("taskdesk:events").catch((e) => console.error("subscribe failed", e.message));
  sub.on("message", (channel, message) => broadcast({ type: "event", channel, message }));
  redis.on("error", (e) => console.error("redis error:", e.message));
}

// ---- helpers ----
async function apiJson(path) {
  const r = await fetch(API_BASE + path);
  if (!r.ok) throw new Error(`app1 ${path} -> ${r.status}`);
  return r.json();
}

const app = express();
app.use(express.json());
app.use((req, res, next) => {
  res.set("Access-Control-Allow-Origin", "*");
  res.set("Access-Control-Allow-Headers", "*");
  res.set("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  if (req.method === "OPTIONS") return res.sendStatus(204);
  next();
});

// ---- API docs ----
app.get("/api/docs.yaml", (_req, res) => res.type("application/yaml").send(OPENAPI_DOC));

// ---- health ----
app.get("/healthz", (_req, res) => res.json({ status: "ok" }));
app.get("/readyz", async (_req, res) => {
  try {
    await apiJson("/healthz");
    if (redis) await redis.ping();
    res.json({ status: "ready" });
  } catch (e) {
    res.status(503).json({ status: "degraded", error: e.message });
  }
});

// ---- BFF reads ----
app.get("/bff/overview", async (req, res) => {
  try {
    const projects = await apiJson("/api/v1/projects" + (req.query.customer ? `?customer=${req.query.customer}` : ""));
    let report = null;
    if (redis) { const c = await redis.get("taskdesk:report:overview"); if (c) report = JSON.parse(c); }
    const open = projects.reduce((s, p) => s + (p.open || 0), 0);
    const resolved = projects.reduce((s, p) => s + (p.resolved || 0), 0);
    res.json({ projects, report, totals: { projects: projects.length, open, resolved }, realtime: !!redis });
  } catch (e) { res.status(502).json({ error: e.message }); }
});

app.get("/bff/projects", async (req, res) => {
  try { res.json(await apiJson("/api/v1/projects" + (req.query.customer ? `?customer=${req.query.customer}` : ""))); }
  catch (e) { res.status(502).json({ error: e.message }); }
});

app.get("/bff/projects/:key/board", async (req, res) => {
  try {
    const items = await apiJson(`/api/v1/projects/${req.params.key}/workitems`);
    const columns = ["todo", "prog", "wait", "done"];
    const board = Object.fromEntries(columns.map((c) => [c, items.filter((i) => i.status === c)]));
    res.json({ project: req.params.key, columns, board, count: items.length });
  } catch (e) { res.status(502).json({ error: e.message }); }
});

app.get("/bff/workitems/:key", async (req, res) => {
  try { res.json(await apiJson(`/api/v1/workitems/${req.params.key}`)); }
  catch (e) { res.status(502).json({ error: e.message }); }
});

app.get("/bff/modules", async (req, res) => {
  try { res.json(await apiJson("/api/v1/modules" + (req.query.customer ? `?customer=${req.query.customer}` : ""))); }
  catch (e) { res.status(502).json({ error: e.message }); }
});

// ---- BFF writes (proxied to app1, then broadcast so other clients update live) ----
async function proxy(req, res, path) {
  try {
    const r = await fetch(API_BASE + path, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(req.body ?? {}),
    });
    const body = await r.text();
    res.status(r.status).type("application/json").send(body);
    if (r.ok) broadcast({ type: "change", path });
  } catch (e) { res.status(502).json({ error: e.message }); }
}
app.post("/bff/workitems", (req, res) => proxy(req, res, "/api/v1/workitems"));
app.post("/bff/workitems/:key/transition", (req, res) => proxy(req, res, `/api/v1/workitems/${req.params.key}/transition`));
app.post("/bff/workitems/:key/comments", (req, res) => proxy(req, res, `/api/v1/workitems/${req.params.key}/comments`));

// ---- realtime ----
const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: "/realtime" });
const clients = new Set();
wss.on("connection", (ws) => {
  clients.add(ws);
  ws.send(JSON.stringify({ type: "hello", realtime: !!redis }));
  ws.on("close", () => clients.delete(ws));
});
function broadcast(msg) {
  const s = JSON.stringify(msg);
  for (const c of clients) if (c.readyState === 1) c.send(s);
}

server.listen(PORT, () => console.log(`app3 BFF+realtime on :${PORT} (api=${API_BASE} redis=${!!REDIS_ADDR})`));
