import { useEffect, useState } from "react";
import { get, post } from "./api";
import { useRealtime } from "./useRealtime";
import { Avatar, Burn, Chip, COLS, Pri, Sla, StatTile, STATUS, TypeTag } from "./ui";

type Role = "customer" | "team";

// Demo customer identity for the portal (until Keycloak/access-code auth lands, PLAN §8).
const CUSTOMER = { key: "ACME", name: "Acme Corp", contact: "Jane Doe" };

export default function App() {
  const [role, setRole] = useState<Role | null>(null);
  const [dark, setDark] = useState(true);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "" : "light";
  }, [dark]);

  if (!role) return <Login onLogin={setRole} />;
  return <Shell role={role} dark={dark} toggleTheme={() => setDark((d) => !d)} onLogout={() => setRole(null)} />;
}

/* ---------------- Login ---------------- */
function Login({ onLogin }: { onLogin: (r: Role) => void }) {
  const [side, setSide] = useState<Role>("team");
  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="logo">T</div>
        <h1>Sign in to TaskDesk</h1>
        <p className="sub">{side === "team" ? "Deliver work across your customers" : "Track your tickets & projects"}</p>
        <div className="seg">
          <button className={side === "customer" ? "active" : ""} onClick={() => setSide("customer")}>I'm a Customer</button>
          <button className={side === "team" ? "active" : ""} onClick={() => setSide("team")}>I'm a Team member</button>
        </div>
        <label className="fld"><span>Email</span><input defaultValue={side === "team" ? "sam@taskdesk.io" : "jane@acme.com"} /></label>
        <label className="fld"><span>Password</span><input type="password" defaultValue="••••••••" /></label>
        <button className="btn primary" style={{ width: "100%", justifyContent: "center" }} onClick={() => onLogin(side)}>Sign in</button>
        <div className="demo-note">Demo — no auth yet (Keycloak is Phase 4). Data is live from the core API via the BFF.</div>
      </div>
    </div>
  );
}

/* ---------------- Shell ---------------- */
function Shell({ role, dark, toggleTheme, onLogout }: { role: Role; dark: boolean; toggleTheme: () => void; onLogout: () => void }) {
  const [view, setView] = useState<string>(role === "team" ? "dashboard" : "portal");
  const [projectKey, setProjectKey] = useState<string | null>(null);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [rev, setRev] = useState(0);
  const live = useRealtime(() => setRev((r) => r + 1));

  const openBoard = (key: string) => { setProjectKey(key); setView("board"); };
  const bump = () => setRev((r) => r + 1);

  const nav =
    role === "team"
      ? [["dashboard", "Dashboard"], ["projects", "Projects"]]
      : [["portal", "Overview"], ["mytickets", "My tickets"], ["projects", "Projects"], ["submit", "Submit ticket"]];

  return (
    <>
      <div className="topbar">
        <div className="brand"><span className="logo">T</span> TaskDesk <small>{role === "team" ? "Delivery workspace" : "Acme Corp"}</small></div>
        <div className="spacer" />
        <div className="live"><span className={"dot" + (live ? "" : " off")} /> {live ? "Realtime connected" : "Reconnecting…"}</div>
        <button className="iconbtn" title="Theme" onClick={toggleTheme}>{dark ? "🌙" : "☀"}</button>
        <span className="avatar" onClick={onLogout} title="Sign out" style={{ cursor: "pointer", background: "var(--charcoal)" }}>{role === "team" ? "SR" : "JD"}</span>
      </div>

      <div className="app">
        <aside className="sidebar">
          <div className="side-label">{role === "team" ? "Work" : "Support"}</div>
          <nav className="nav">
            {nav.map(([k, label]) => (
              <a key={k} className={view === k || (k === "projects" && view === "board") ? "active" : ""} onClick={() => { setProjectKey(null); setView(k); }}>
                {label}
              </a>
            ))}
          </nav>
        </aside>

        <main className="main">
          {view === "dashboard" && <Dashboard rev={rev} openBoard={openBoard} />}
          {view === "portal" && <PortalHome rev={rev} openBoard={openBoard} openItem={setOpenKey} />}
          {view === "mytickets" && <MyTickets rev={rev} openItem={setOpenKey} />}
          {view === "submit" && <SubmitTicket onDone={() => { bump(); setView("mytickets"); }} />}
          {view === "projects" && <Projects openBoard={openBoard} rev={rev} customer={role === "customer" ? CUSTOMER.key : undefined} />}
          {view === "board" && projectKey && <Board projectKey={projectKey} role={role} rev={rev} bump={bump} openItem={setOpenKey} back={() => setView("projects")} />}
        </main>
      </div>

      {openKey && <Drawer itemKey={openKey} role={role} onClose={() => setOpenKey(null)} bump={() => setRev((r) => r + 1)} />}
    </>
  );
}

/* ---------------- Dashboard ---------------- */
function Dashboard({ rev, openBoard }: { rev: number; openBoard: (k: string) => void }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { get("/bff/overview").then(setD).catch((e) => setErr(e.message)); }, [rev]);
  if (err) return <ErrorCard msg={err} />;
  if (!d) return <div className="empty">Loading…</div>;
  const t = d.totals;
  const r = d.report;
  return (
    <>
      <PageHead title="Dashboard" sub="Live across all customers and projects." />
      <div className="stats">
        <StatTile n={t.projects} label="Projects" color="var(--blue)" />
        <StatTile n={t.open} label="Open work items" color="var(--amber)" />
        <StatTile n={r ? `${r.compliancePct}%` : "—"} label="SLA compliance" color="var(--green)" />
        <StatTile n={r ? r.breaching : "—"} label="SLA breaching" color="var(--breach)" />
      </div>
      <h3 className="section">Projects</h3>
      <div className="cards-grid">
        {d.projects.map((p: any) => <ProjectCard key={p.key} p={p} onOpen={() => openBoard(p.key)} />)}
      </div>
    </>
  );
}

/* ---------------- Projects ---------------- */
function Projects({ openBoard, rev, customer }: { openBoard: (k: string) => void; rev: number; customer?: string }) {
  const [ps, setPs] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { get("/bff/projects" + (customer ? `?customer=${customer}` : "")).then(setPs).catch((e) => setErr(e.message)); }, [rev, customer]);
  if (err) return <ErrorCard msg={err} />;
  if (!ps) return <div className="empty">Loading…</div>;
  return (
    <>
      <PageHead title="Projects" sub={customer ? "Your engagements." : "Engagements across all customers."} />
      <div className="cards-grid">{ps.map((p) => <ProjectCard key={p.key} p={p} onOpen={() => openBoard(p.key)} />)}</div>
    </>
  );
}

function ProjectCard({ p, onOpen }: { p: any; onOpen: () => void }) {
  const accent = String(p.serviceType || "").includes("Managed") ? "var(--amber)" : "var(--green)";
  return (
    <div className="card pcard" style={{ borderTop: `3px solid ${accent}` }} onClick={onOpen}>
      <div className="pc-top"><span className="key">{p.key}</span><span className="label-tag">{p.type}</span></div>
      <h3>{p.name}</h3>
      <div className="sub">{p.customer}</div>
      <div className="pc-foot"><span>{p.open} open</span><span>{p.resolved} done</span><Avatar name={p.lead} size={26} /></div>
    </div>
  );
}

/* ---------------- Customer portal ---------------- */
function TicketRow({ w, onOpen }: { w: any; onOpen: () => void }) {
  return (
    <div className="trow" onClick={onOpen}>
      <span className="key">{w.key}</span>
      <TypeTag t={w.type} />
      <span className="t">{w.title}</span>
      <div className="rt">
        {w.slaState && w.slaState !== "none" && <Sla state={w.slaState} dueAt={w.slaDueAt} />}
        <Pri p={w.priority} />
        <Chip s={w.status} />
      </div>
    </div>
  );
}

function PortalHome({ rev, openBoard, openItem }: { rev: number; openBoard: (k: string) => void; openItem: (k: string) => void }) {
  const [ps, setPs] = useState<any[] | null>(null);
  const [tks, setTks] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    get(`/bff/projects?customer=${CUSTOMER.key}`).then(setPs).catch((e) => setErr(e.message));
    get(`/bff/portal/tickets?customer=${CUSTOMER.key}`).then(setTks).catch((e) => setErr(e.message));
  }, [rev]);
  if (err) return <ErrorCard msg={err} />;
  if (!ps || !tks) return <div className="empty">Loading…</div>;
  const open = tks.filter((t) => t.status !== "done");
  const atRisk = open.filter((t) => t.slaState === "risk" || t.slaState === "breached").length;
  const resolved = tks.length - open.length;
  return (
    <>
      <PageHead title={`Welcome, ${CUSTOMER.contact}`} sub={`${CUSTOMER.name} — support & projects overview.`} />
      <div className="stats">
        <StatTile n={open.length} label="Open tickets" color="var(--amber)" />
        <StatTile n={ps.length} label="Active projects" color="var(--blue)" />
        <StatTile n={atRisk} label="SLA at risk" color="var(--breach)" />
        <StatTile n={resolved} label="Resolved" color="var(--green)" />
      </div>
      <h3 className="section">Recent tickets</h3>
      {open.slice(0, 6).map((t) => <TicketRow key={t.key} w={t} onOpen={() => openItem(t.key)} />)}
      {open.length === 0 && <div className="empty">No open tickets. 🎉</div>}
      <h3 className="section">Your projects</h3>
      <div className="cards-grid">{ps.map((p) => <ProjectCard key={p.key} p={p} onOpen={() => openBoard(p.key)} />)}</div>
    </>
  );
}

function MyTickets({ rev, openItem }: { rev: number; openItem: (k: string) => void }) {
  const [tks, setTks] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState("all");
  useEffect(() => {
    const q = filter === "all" ? "" : `&status=${filter}`;
    get(`/bff/portal/tickets?customer=${CUSTOMER.key}${q}`).then(setTks).catch((e) => setErr(e.message));
  }, [rev, filter]);
  if (err) return <ErrorCard msg={err} />;
  return (
    <>
      <PageHead title="My tickets" sub="All requests across your projects, with live SLA." />
      <div className="filterbar">
        {[["all", "All"], ...COLS.map((c) => [c, STATUS[c].label])].map(([k, label]) => (
          <button key={k} className={filter === k ? "active" : ""} onClick={() => setFilter(k)}>{label}</button>
        ))}
      </div>
      {!tks ? <div className="empty">Loading…</div> : tks.length === 0 ? <div className="empty">No tickets here.</div> :
        tks.map((t) => <TicketRow key={t.key} w={t} onOpen={() => openItem(t.key)} />)}
    </>
  );
}

function SubmitTicket({ onDone }: { onDone: () => void }) {
  const [ps, setPs] = useState<any[]>([]);
  const [projectKey, setProjectKey] = useState("");
  const [priority, setPriority] = useState("med");
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { get(`/bff/projects?customer=${CUSTOMER.key}`).then((r) => { setPs(r); if (r[0]) setProjectKey(r[0].key); }); }, []);

  const submit = async () => {
    if (!projectKey || !title.trim()) { setErr("Pick a project and enter a title."); return; }
    setBusy(true); setErr(null);
    try {
      await post("/bff/workitems", { projectKey, type: "ticket", title, description: desc, priority, requester: CUSTOMER.contact, assignee: null });
      onDone();
    } catch (e: any) { setErr(e.message); setBusy(false); }
  };

  return (
    <>
      <PageHead title="Submit a ticket" sub="Raise a support request — we'll triage and respond per your SLA." />
      <div className="card form-card">
        <label className="fld"><span>Project</span>
          <select value={projectKey} onChange={(e) => setProjectKey(e.target.value)}>
            {ps.map((p) => <option key={p.key} value={p.key}>{p.key} — {p.name}</option>)}
          </select>
        </label>
        <label className="fld"><span>Priority</span>
          <select value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="low">Low</option><option value="med">Medium</option>
            <option value="high">High</option><option value="urgent">Urgent</option>
          </select>
        </label>
        <label className="fld"><span>Title</span><input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Short summary of the issue" /></label>
        <label className="fld"><span>Description</span><textarea style={{ minHeight: 110 }} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="What happened, steps to reproduce, impact…" /></label>
        {err && <div className="muted" style={{ color: "var(--breach)", marginBottom: 10 }}>{err}</div>}
        <button className="btn primary" disabled={busy} onClick={submit}>{busy ? "Submitting…" : "Submit ticket"}</button>
      </div>
    </>
  );
}

/* ---------------- Board ---------------- */
function Board({ projectKey, role, rev, openItem, back }: any) {
  const [b, setB] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { get(`/bff/projects/${projectKey}/board`).then(setB).catch((e) => setErr(e.message)); }, [projectKey, rev]);
  if (err) return <ErrorCard msg={err} />;
  if (!b) return <div className="empty">Loading…</div>;
  return (
    <>
      <div className="breadcrumb"><a onClick={back}>Projects</a> › {projectKey}</div>
      <PageHead title={projectKey} sub={`${b.count} work items`} />
      <ContractPanel projectKey={projectKey} rev={rev} />
      <div className="board">
        {COLS.map((c) => (
          <div className="col" key={c}>
            <div className="col-head"><Chip s={c} /><span className="n">{b.board[c].length}</span></div>
            {b.board[c].map((w: any) => (
              <div className="wcard" key={w.key} onClick={() => openItem(w.key)}>
                <div className="row1"><span className="key">{w.key}</span><TypeTag t={w.type} /></div>
                <div className="t">{w.title}</div>
                {w.slaState && w.slaState !== "none" && <div style={{ marginBottom: 8 }}><Sla state={w.slaState} dueAt={w.slaDueAt} /></div>}
                <div className="meta"><Pri p={w.priority} /><Avatar name={w.assignee} size={24} /></div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </>
  );
}

/* ---------------- Work-item drawer ---------------- */
function Drawer({ itemKey, role, onClose, bump }: any) {
  const [w, setW] = useState<any>(null);
  const [tab, setTab] = useState("comments");
  const [text, setText] = useState("");
  const [internal, setInternal] = useState(false);
  const [assignVal, setAssignVal] = useState("");
  const [mins, setMins] = useState("");
  const [note, setNote] = useState("");
  const [msVal, setMsVal] = useState<string | null>(null);
  const load = () => get(`/bff/workitems/${itemKey}`).then((x) => { setW(x); setAssignVal(x.assignee ?? ""); });
  useEffect(() => { load(); }, [itemKey]);

  const transition = async (status: string) => { await post(`/bff/workitems/${itemKey}/transition`, { status }); await load(); bump(); };
  const assign = async () => { await post(`/bff/workitems/${itemKey}/assign`, { assignee: assignVal.trim() || null }); await load(); bump(); };
  const logTime = async () => {
    const m = parseInt(mins, 10);
    if (!m || m <= 0) return;
    try {
      await post(`/bff/workitems/${itemKey}/time`, { author: "Sam Rivera", minutes: m, note });
      setMins(""); setNote(""); setMsVal(null); bump();
    } catch (e: any) {
      setMsVal(e.message?.includes("403") ? "Managed-service module is off for this customer." : e.message);
    }
  };
  const comment = async () => {
    if (!text.trim()) return;
    await post(`/bff/workitems/${itemKey}/comments`, { author: role === "team" ? "Sam Rivera" : "Jane Doe", body: text, isInternal: role === "team" && internal });
    setText(""); setInternal(false); await load(); bump();
  };

  const visibleComments = (w?.comments || []).filter((c: any) => (role === "customer" ? !c.isInternal : true));

  return (
    <>
      <div className="overlay open" onClick={onClose} />
      <aside className="drawer open">
        {!w ? <div className="empty">Loading…</div> : (
          <>
            <div className="drawer-head"><TypeTag t={w.type} /><span className="key">{w.key}</span>
              <button className="close" onClick={onClose}>✕</button></div>
            <div className="drawer-body">
              <h2>{w.title}</h2>
              <div className="muted" style={{ marginBottom: 16 }}>{w.description}</div>
              <div className="drawer-grid">
                <div>
                  <div className="tabs">
                    <button className={tab === "comments" ? "active" : ""} onClick={() => setTab("comments")}>Conversation ({visibleComments.length})</button>
                    <button className={tab === "activity" ? "active" : ""} onClick={() => setTab("activity")}>Activity</button>
                  </div>
                  {tab === "activity" ? (
                    <ul className="activity">{(w.activity || []).map((a: any, i: number) => <li key={i}>{a.actor} {a.detail}</li>)}</ul>
                  ) : (
                    <>
                      <div className="chat">
                        {visibleComments.map((c: any, i: number) => (
                          <div key={i} className={"msg " + (c.isInternal ? "internal" : c.author === (role === "team" ? "Sam Rivera" : "Jane Doe") ? "me" : "them")}>
                            <div className="mh">{c.author}{c.isInternal && <span className="internal-flag">Internal</span>}</div>
                            <div>{c.body}</div>
                          </div>
                        ))}
                        {visibleComments.length === 0 && <div className="empty">No messages yet.</div>}
                      </div>
                      <div className="composer">
                        <textarea placeholder={role === "team" ? "Reply to the customer…" : "Message the support team…"} value={text} onChange={(e) => setText(e.target.value)} />
                        <div className="composer-actions">
                          {role === "team" && <label className="toggle"><input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> Internal note</label>}
                          <button className="btn primary sm" onClick={comment}>Send</button>
                        </div>
                      </div>
                    </>
                  )}
                </div>
                <div>
                  <Field k="Status">{role === "team" ? (
                    <select value={w.status} onChange={(e) => transition(e.target.value)}>
                      {COLS.map((c) => <option key={c} value={c}>{STATUS[c].label}</option>)}
                    </select>) : <Chip s={w.status} />}
                  </Field>
                  <Field k="Priority"><Pri p={w.priority} /></Field>
                  {w.slaState && w.slaState !== "none" && <Field k="SLA"><Sla state={w.slaState} dueAt={w.slaDueAt} /></Field>}
                  <Field k="Assignee">
                    {role === "team" ? (
                      <div className="inline-form">
                        <input placeholder="Unassigned" value={assignVal} onChange={(e) => setAssignVal(e.target.value)} onKeyDown={(e) => e.key === "Enter" && assign()} />
                        <button className="btn sm" onClick={assign}>Save</button>
                      </div>
                    ) : w.assignee ? <span className="row1"><Avatar name={w.assignee} size={24} /> {w.assignee}</span> : <span className="muted">Unassigned</span>}
                  </Field>
                  <Field k="Reporter"><span className="row1"><Avatar name={w.requester} size={24} /> {w.requester}</span></Field>
                  <Field k="Project">{w.project}</Field>
                  {role === "team" && (
                    <Field k="Log time (hour bank)">
                      <div className="inline-form">
                        <input style={{ width: 70 }} type="number" min={1} placeholder="min" value={mins} onChange={(e) => setMins(e.target.value)} />
                        <input placeholder="note" value={note} onChange={(e) => setNote(e.target.value)} />
                        <button className="btn sm" onClick={logTime}>Log</button>
                      </div>
                      {msVal && <div className="muted" style={{ marginTop: 6, color: "var(--breach)" }}>{msVal}</div>}
                    </Field>
                  )}
                </div>
              </div>
            </div>
          </>
        )}
      </aside>
    </>
  );
}

/* ---------------- Managed-service contract strip ---------------- */
function fmtDate(s: string) { return new Date(s).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }); }

function ContractPanel({ projectKey, rev }: { projectKey: string; rev: number }) {
  const [c, setC] = useState<any>(null);
  // 403 (managed_service off) or a Delivery project with no contract → render nothing.
  useEffect(() => { get(`/bff/projects/${projectKey}/contract`).then(setC).catch(() => setC(null)); }, [projectKey, rev]);
  if (!c || c.hasContract === false) return null;
  const hb = c.hourBank;
  const statusCls = c.status === "Active" ? "good" : c.status === "Expired" ? "bad" : "warn";
  return (
    <div className="card contract">
      <div className="ctop">
        <strong>Managed service</strong>
        <span className={"badge " + statusCls}>{c.status}</span>
        <span className="muted" style={{ marginLeft: "auto" }}>{c.coverage}</span>
      </div>
      <div className="cgrid">
        <div style={{ gridColumn: "span 2", minWidth: 220 }}>
          <div className="kv">
            <div className="k">Hour bank</div>
            <div className="v">{hb.remaining}h left <span className="muted">of {hb.contracted}h · {hb.used}h used</span></div>
          </div>
          <div style={{ marginTop: 8 }}><Burn pct={hb.usedPct} /></div>
        </div>
        <div className="kv"><div className="k">Contract ends</div><div className="v">{fmtDate(c.period.end)} <span className="muted">· {c.period.daysRemaining}d</span></div></div>
        <div className="kv"><div className="k">Kickoff</div><div className="v">{c.kickoff.status}</div></div>
      </div>
      {c.recentDeductions?.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="kv"><div className="k">Recent time</div></div>
          {c.recentDeductions.map((d: any, i: number) => (
            <div key={i} className="muted" style={{ fontSize: 12.5, display: "flex", gap: 10, marginTop: 4 }}>
              <span style={{ fontWeight: 600, color: "var(--text)" }}>{d.hours}h</span>
              <span>{d.author}</span>
              <span style={{ opacity: 0.85 }}>{d.note}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------- bits ---------------- */
function PageHead({ title, sub }: { title: string; sub?: string }) {
  return <div className="page-head"><div><h1>{title}</h1>{sub && <p>{sub}</p>}</div></div>;
}
function Field({ k, children }: any) { return <div className="field"><div className="fk">{k}</div>{children}</div>; }
function ErrorCard({ msg }: { msg: string }) {
  return <div className="card pad" style={{ color: "var(--breach)" }}>Couldn't reach the API — is the stack up? <div className="muted" style={{ marginTop: 6 }}>{msg}</div></div>;
}
