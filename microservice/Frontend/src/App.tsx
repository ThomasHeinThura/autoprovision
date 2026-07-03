import { useEffect, useState } from "react";
import { get, post } from "./api";
import { useRealtime } from "./useRealtime";
import { Avatar, Chip, COLS, Pri, StatTile, STATUS, TypeTag } from "./ui";

type Role = "customer" | "team";

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
  const [view, setView] = useState<string>(role === "team" ? "dashboard" : "projects");
  const [projectKey, setProjectKey] = useState<string | null>(null);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [rev, setRev] = useState(0);
  const live = useRealtime(() => setRev((r) => r + 1));

  const openBoard = (key: string) => { setProjectKey(key); setView("board"); };

  const nav =
    role === "team"
      ? [["dashboard", "Dashboard"], ["projects", "Projects"]]
      : [["projects", "Projects"]];

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
          {view === "projects" && <Projects openBoard={openBoard} rev={rev} />}
          {view === "board" && projectKey && <Board projectKey={projectKey} role={role} rev={rev} bump={() => setRev((r) => r + 1)} openItem={setOpenKey} back={() => setView("projects")} />}
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
  return (
    <>
      <PageHead title="Dashboard" sub="Live across all customers and projects." />
      <div className="stats">
        <StatTile n={t.projects} label="Projects" color="var(--blue)" />
        <StatTile n={t.open} label="Open work items" color="var(--amber)" />
        <StatTile n={t.resolved} label="Resolved" color="var(--green)" />
        <StatTile n={d.report ? d.report.unassigned : "—"} label="Unassigned (workers)" color="var(--breach)" />
      </div>
      <h3 className="section">Projects</h3>
      <div className="cards-grid">
        {d.projects.map((p: any) => <ProjectCard key={p.key} p={p} onOpen={() => openBoard(p.key)} />)}
      </div>
    </>
  );
}

/* ---------------- Projects ---------------- */
function Projects({ openBoard, rev }: { openBoard: (k: string) => void; rev: number }) {
  const [ps, setPs] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { get("/bff/projects").then(setPs).catch((e) => setErr(e.message)); }, [rev]);
  if (err) return <ErrorCard msg={err} />;
  if (!ps) return <div className="empty">Loading…</div>;
  return (
    <>
      <PageHead title="Projects" sub="Engagements across all customers." />
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
      <div className="board">
        {COLS.map((c) => (
          <div className="col" key={c}>
            <div className="col-head"><Chip s={c} /><span className="n">{b.board[c].length}</span></div>
            {b.board[c].map((w: any) => (
              <div className="wcard" key={w.key} onClick={() => openItem(w.key)}>
                <div className="row1"><span className="key">{w.key}</span><TypeTag t={w.type} /></div>
                <div className="t">{w.title}</div>
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
  const load = () => get(`/bff/workitems/${itemKey}`).then(setW);
  useEffect(() => { load(); }, [itemKey]);

  const transition = async (status: string) => { await post(`/bff/workitems/${itemKey}/transition`, { status }); await load(); bump(); };
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
                  <Field k="Assignee">{w.assignee ? <span className="row1"><Avatar name={w.assignee} size={24} /> {w.assignee}</span> : <span className="muted">Unassigned</span>}</Field>
                  <Field k="Reporter"><span className="row1"><Avatar name={w.requester} size={24} /> {w.requester}</span></Field>
                  <Field k="Project">{w.project}</Field>
                </div>
              </div>
            </div>
          </>
        )}
      </aside>
    </>
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
