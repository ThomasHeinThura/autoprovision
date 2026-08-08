import { useEffect, useRef, useState } from 'react'
import {
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, type Environment } from './lib/api'
import { useStore } from './lib/store'
import { Ribbon } from './components/common'
import { RunSheet } from './components/RunSheet'
import { Topology } from './components/Topology'
import { WorkloadDetail } from './components/WorkloadDetail'
import './app.css'

export function App() {
  const store = useStore()

  if (store.loading) return <div className="center-msg">Loading the control plane…</div>
  if (!store.registry)
    return (
      <div className="center-msg">
        <div>
          <p>
            <strong>The control plane is not answering.</strong>
          </p>
          <p>{store.error ?? 'Check that the API is running on port 3000.'}</p>
        </div>
      </div>
    )

  return (
    <div className="app">
      <Chrome />
      <div className="main">
        <Rail />
        <Routes>
          <Route path="/" element={<Navigate to="/env/shared" replace />} />
          <Route path="/env/:envId" element={<RunSheet />} />
          <Route path="/env/:envId/:workloadId" element={<WorkloadDetail />} />
          <Route path="/topology" element={<Topology />} />
          <Route path="/handbook" element={<Handbook />} />
          <Route path="*" element={<div className="center-msg">No such page.</div>} />
        </Routes>
      </div>
    </div>
  )
}

function Chrome() {
  const store = useStore()
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [user, setUser] = useState(store.sshUser)
  const [pass, setPass] = useState('')

  async function runReady() {
    setBusy(true)
    try {
      const res = await api.runReady(store.values, store.sshUser, store.sshPass)
      await store.refresh()
      setResult(
        res.started.length === 0
          ? 'Nothing was ready to run. Workloads need their configuration filled in and their dependencies complete.'
          : `Started ${res.started.length} workload${res.started.length === 1 ? '' : 's'}.` +
              (res.skipped.length > 0 ? ` Skipped ${res.skipped.length}.` : ''),
      )
    } catch (e) {
      setResult(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
      window.setTimeout(() => setResult(null), 8000)
    }
  }

  return (
    <header className="chrome">
      <div className="mark">
        <span className="org">BIMGOC</span>
        <b>Autoprovision</b>
      </div>

      <div className="spacer" />

      {result && <span className="tag">{result}</span>}

      <button className="conn" type="button" onClick={() => dialogRef.current?.showModal()}>
        <span className="k">SSH</span>
        <span className="mono">{store.sshUser}@</span>
        <span className="tag">{store.sshPass ? 'password set' : 'key'}</span>
      </button>

      <button className="btn" type="button" onClick={() => void store.refresh()}>
        Refresh
      </button>
      <button className="btn primary" type="button" onClick={runReady} disabled={busy}>
        {busy ? 'Starting…' : 'Run ready workloads'}
      </button>

      <dialog ref={dialogRef}>
        <div className="dlg-head">
          <h3 style={{ color: 'var(--ink)' }}>Connection</h3>
        </div>
        <div className="dlg-body">
          <p style={{ margin: 0 }}>
            How Ansible logs in to every target. Prefer a key: run the host bootstrap workload once
            and leave the password empty, so credentials stop being written into inventory files.
          </p>
          <div className="fld">
            <label htmlFor="ssh-user">SSH user</label>
            <input id="ssh-user" value={user} onChange={(e) => setUser(e.target.value)} />
          </div>
          <div className="fld">
            <label htmlFor="ssh-pass">
              SSH password <span className="lock">Not saved</span>
            </label>
            <input
              id="ssh-pass"
              type="password"
              value={pass}
              autoComplete="new-password"
              onChange={(e) => setPass(e.target.value)}
            />
            <span className="hint">
              Held in this browser tab only. Leave empty when key authentication is set up.
            </span>
          </div>
        </div>
        <div className="dlg-foot">
          <button className="btn" type="button" onClick={() => dialogRef.current?.close()}>
            Cancel
          </button>
          <button
            className="btn primary"
            type="button"
            onClick={() => {
              store.setSsh(user, pass)
              dialogRef.current?.close()
            }}
          >
            Use these credentials
          </button>
        </div>
      </dialog>
    </header>
  )
}

function Rail() {
  const store = useStore()
  const location = useLocation()
  const navigate = useNavigate()
  const groups = new Map<string, Environment[]>()

  for (const env of store.registry?.environments ?? []) {
    const list = groups.get(env.group) ?? []
    list.push(env)
    groups.set(env.group, list)
  }

  return (
    <nav className="rail" aria-label="Environments">
      {[...groups].map(([group, envs]) => (
        <div key={group}>
          <h3 className="eyebrow">{group}</h3>
          {envs.map((env) => {
            const workloads = store.byEnv(env.id)
            const done = workloads.filter((w) => store.statusOf(w.id) === 'completed').length
            const active = location.pathname.startsWith(`/env/${env.id}`)
            return (
              <button
                key={env.id}
                className="rail-item"
                type="button"
                aria-current={active ? 'page' : undefined}
                onClick={() => navigate(`/env/${env.id}`)}
              >
                <span className="top">
                  <span className="nm">{env.title}</span>
                  <span className="ct">
                    {done}/{workloads.length}
                  </span>
                </span>
                <span className="ribbon xs">
                  {workloads.map((w) => (
                    <i key={w.id} className={statusClass(store.statusOf(w.id))} />
                  ))}
                </span>
              </button>
            )
          })}
        </div>
      ))}

      <h3 className="eyebrow">Reference</h3>
      <NavLink
        to="/topology"
        className="rail-item"
        style={{ display: 'block' }}
        aria-current={location.pathname === '/topology' ? 'page' : undefined}
      >
        <span className="top">
          <span className="nm">Topology</span>
        </span>
      </NavLink>
      <NavLink
        to="/handbook"
        className="rail-item"
        style={{ display: 'block' }}
        aria-current={location.pathname === '/handbook' ? 'page' : undefined}
      >
        <span className="top">
          <span className="nm">Handbook</span>
        </span>
      </NavLink>
    </nav>
  )
}

function statusClass(status: string): string {
  if (status === 'completed') return 'completed'
  if (status === 'failed') return 'failed'
  if (status === 'running' || status === 'queued' || status === 'partial') return 'running'
  return ''
}

function Handbook() {
  const [pages, setPages] = useState<{ slug: string; title: string; body: string }[] | null>(null)

  useEffect(() => {
    api
      .handbook()
      .then(setPages)
      .catch(() => setPages([]))
  }, [])

  return (
    <main className="stage">
      <div className="stage-head">
        <h1>Handbook</h1>
        <span className="meta">{pages?.length ?? 0} sections</span>
      </div>
      <p className="stage-blurb">
        Every workload's Theory page, assembled into one manual. This is the reasoning behind the
        platform — why each component was chosen, what it protects against, and what it does not.
      </p>

      {pages === null ? (
        <p>Loading…</p>
      ) : pages.length === 0 ? (
        <div className="note">
          No theory pages have been written yet. Add <code>content/&lt;workload&gt;/theory.md</code>{' '}
          and it appears here.
        </div>
      ) : (
        <>
          <nav className="handbook-nav">
            {pages.map((p) => (
              <a key={p.slug} href={`#${p.slug}`}>
                {p.title}
              </a>
            ))}
          </nav>
          {pages.map((p) => (
            <section className="handbook-section doc" id={p.slug} key={p.slug}>
              <Markdown
                remarkPlugins={[remarkGfm]}
                components={{
                  table: ({ children }) => (
                    <div className="table-scroll">
                      <table>{children}</table>
                    </div>
                  ),
                }}
              >
                {p.body}
              </Markdown>
            </section>
          ))}
        </>
      )}
    </main>
  )
}

export { Ribbon }
