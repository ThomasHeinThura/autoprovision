import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, fieldVisible, type Plan } from '../lib/api'
import { useStore } from '../lib/store'
import { FieldInput, StatePip } from './common'
import { Terminal } from './Terminal'

type Tab = 'configure' | 'requirements' | 'guide' | 'theory'

export function WorkloadDetail() {
  const { envId = '', workloadId = '' } = useParams()
  const navigate = useNavigate()
  const store = useStore()
  const wl = store.workload(workloadId)

  const [tab, setTab] = useState<Tab>('configure')
  const [plan, setPlan] = useState<Plan | null>(null)
  const [planError, setPlanError] = useState<string | null>(null)
  const [force, setForce] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ kind: 'note' | 'stop'; text: string } | null>(null)
  const [confirmText, setConfirmText] = useState('')
  const dialogRef = useRef<HTMLDialogElement>(null)
  // An untouched form is not a failure. "At least one node IP is required" in red
  // before you have typed anything reads as something being broken, when the only
  // thing that has happened is that you just arrived.
  const [touched, setTouched] = useState(false)

  const values = wl ? store.valuesFor(wl) : {}
  const status = wl ? store.statusOf(wl.id) : 'idle'
  const readiness = wl ? store.state?.readiness[wl.id] : undefined
  const running = status === 'running' || status === 'queued'

  // Re-plan whenever the form changes: the plan, the inventory and the step list
  // are all derived from the configuration, so showing a stale one would be worse
  // than showing none.
  useEffect(() => {
    if (!wl) return
    let cancelled = false
    const t = window.setTimeout(() => {
      api
        .preview(wl.id, values)
        .then((p) => {
          if (cancelled) return
          setPlan(p.valid ? p : null)
          setPlanError(p.valid ? null : p.error)
        })
        .catch((e) => {
          if (!cancelled) {
            setPlan(null)
            setPlanError(e instanceof Error ? e.message : String(e))
          }
        })
    }, 250)
    return () => {
      cancelled = true
      window.clearTimeout(t)
    }
  }, [wl, JSON.stringify(values)])

  useEffect(() => {
    setTab('configure')
    setNotice(null)
    setForce(false)
    setTouched(false)
  }, [workloadId])

  if (!wl) return <div className="center-msg">No such workload.</div>

  async function startRun(confirm?: string) {
    if (!wl) return
    setBusy(true)
    setNotice(null)
    try {
      await api.run({
        workload: wl.id,
        values,
        force,
        confirm,
        sshUser: store.sshUser,
        sshPass: store.sshPass,
      })
      await store.refresh()
      setNotice({ kind: 'note', text: `${wl.title} started. Output appears below as it arrives.` })
    } catch (e) {
      setNotice({ kind: 'stop', text: e instanceof Error ? e.message : String(e) })
    } finally {
      setBusy(false)
    }
  }

  function onRun() {
    if (wl?.destructive) {
      setConfirmText('')
      dialogRef.current?.showModal()
      return
    }
    void startRun()
  }

  async function onReset() {
    if (!wl) return
    const res = await api.reset(wl.id)
    await store.refresh()
    setNotice({
      kind: 'note',
      text: `Cleared ${res.cleared} recorded step${res.cleared === 1 ? '' : 's'}. The next run reinstalls everything.`,
    })
  }

  const expectedConfirm = (values[wl.confirmField] ?? '').trim()
  const requirementsBadge = plan ? `${plan.steps.length} step${plan.steps.length === 1 ? '' : 's'}` : undefined

  return (
    <section className="detail">
      <div className="d-head">
        <div className="crumb">
          <button type="button" onClick={() => navigate(`/env/${envId}`)}>
            {store.registry?.environments.find((e) => e.id === envId)?.title ?? 'Back'}
          </button>
          <span>›</span>
          <span>
            {wl.ordinal} · {wl.title}
          </span>
        </div>

        <div className="d-title">
          <h1>{wl.title}</h1>
          <StatePip status={status} blocked={readiness && !readiness.ready} />
          <span className="tag">{wl.id}</span>
          {wl.always && <span className="tag accent">always runs</span>}
        </div>

        <p className="d-summary">{wl.summary}</p>

        <div className="d-actions">
          <button
            className={`btn ${wl.destructive ? 'danger' : 'primary'}`}
            type="button"
            onClick={onRun}
            disabled={running || busy || !!planError}
          >
            {running ? 'Running…' : wl.destructive ? 'Run — destroys state' : 'Run workload'}
          </button>
          <button className="btn" type="button" onClick={onReset}>
            Clear install history
          </button>
          <label className="chk">
            <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
            Force — re-run completed steps
          </label>
        </div>

        <div className="tabs" role="tablist">
          {(['configure', 'requirements', 'guide', 'theory'] as Tab[]).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              type="button"
              onClick={() => setTab(t)}
            >
              {t[0]!.toUpperCase() + t.slice(1)}
              {t === 'requirements' && requirementsBadge && (
                <span className="badge">{requirementsBadge}</span>
              )}
            </button>
          ))}
        </div>
      </div>

      {tab === 'configure' ? (
        <div className="pane configure">
          <div className="d-cols">
            <div className="d-form">
              {notice && (
                <div className={`note ${notice.kind === 'stop' ? 'stop' : ''}`} style={{ marginBottom: 12 }}>
                  {notice.text}
                </div>
              )}
              {readiness && !readiness.ready && (
                <div className="note warn" style={{ marginBottom: 12 }}>
                  <strong>Waiting on {readiness.blockedBy.map((b) => `${b.ordinal} · ${b.title}`).join(', ')}.</strong>{' '}
                  You can still run this deliberately — it is excluded from bulk runs until its
                  dependencies complete.
                </div>
              )}
              {planError && (
                <div className={`note ${touched ? 'stop' : ''}`} style={{ marginBottom: 12 }}>
                  {touched ? planError : `Fill in the fields below to build a plan. ${planError}`}
                </div>
              )}

              <div className="field-grid">
                {wl.fields.map((f) => (
                  <FieldInput
                    key={f.key}
                    field={f}
                    value={values[f.key] ?? ''}
                    values={values}
                    onChange={(v) => {
                      setTouched(true)
                      store.setValue(wl.id, f.key, v)
                    }}
                  />
                ))}
              </div>
            </div>

            <aside className="d-side">
              <div className="side-block">
                <h4>Plan</h4>
                {plan ? (
                  <div className="plan">
                    {plan.steps.map((s) => (
                      <div className="plan-step" key={s.label}>
                        <span className={`ic ${s.status}`}>
                          {s.status === 'completed' ? '✓' : s.status === 'failed' ? '✗' : '·'}
                        </span>
                        <span>
                          {s.label}
                          <span className="pb">{s.playbook}</span>
                          {!s.exists && (
                            <span className="missing">This playbook has not been written yet.</span>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="hint">
                    {touched
                      ? 'Resolve the problem above to see the plan.'
                      : 'Fill in the fields to see the plan.'}
                  </p>
                )}
              </div>

              {plan && plan.inventory.length > 0 && (
                <div className="side-block">
                  <h4>Inventory</h4>
                  <div className="plan">
                    {plan.inventory.map((g) => (
                      <div className="plan-step" key={g.group}>
                        <span className="ic">·</span>
                        <span className="mono">
                          [{g.group}] {g.hosts.join(', ')}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {plan && plan.inventory.length === 0 && (
                <div className="side-block">
                  <h4>Inventory</h4>
                  <p className="hint">
                    Runs on the jump host against the cluster's kubeconfig. No SSH to any node.
                  </p>
                </div>
              )}

              <UnblocksList workloadId={wl.id} />
            </aside>
          </div>

          <Terminal workloadId={wl.id} />
        </div>
      ) : (
        <DocPane slug={wl.docs} page={tab} />
      )}

      <dialog ref={dialogRef}>
        <div className="dlg-head">
          <h3>{wl.title}</h3>
        </div>
        <div className="dlg-body">
          <p style={{ margin: 0 }}>{wl.summary}</p>
          {plan && (
            <ul>
              {plan.steps.map((s) => (
                <li key={s.label}>
                  {s.label} <code>{s.playbook}</code>
                </li>
              ))}
            </ul>
          )}
          <div className="fld">
            <label htmlFor="confirm-token">
              Type <code>{expectedConfirm || '(set the target field first)'}</code> to confirm
            </label>
            <input
              id="confirm-token"
              value={confirmText}
              autoComplete="off"
              onChange={(e) => setConfirmText(e.target.value)}
            />
          </div>
        </div>
        <div className="dlg-foot">
          <button className="btn" type="button" onClick={() => dialogRef.current?.close()}>
            Cancel
          </button>
          <button
            className="btn danger"
            type="button"
            disabled={!expectedConfirm || confirmText.trim() !== expectedConfirm}
            onClick={() => {
              dialogRef.current?.close()
              void startRun(confirmText.trim())
            }}
          >
            {wl.title}
          </button>
        </div>
      </dialog>
    </section>
  )
}

function UnblocksList({ workloadId }: { workloadId: string }) {
  const store = useStore()
  const dependents = (store.registry?.workloads ?? []).filter((w) => w.requires.includes(workloadId))
  if (dependents.length === 0) return null
  return (
    <div className="side-block">
      <h4>Unblocks</h4>
      <div className="dep-list">
        {dependents.map((d) => (
          <div key={d.id}>
            <StatePip status={store.statusOf(d.id)} label="" />
            <span>
              {d.ordinal} · {d.title}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function DocPane({ slug, page }: { slug: string; page: string }) {
  const [body, setBody] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setBody(null)
    api
      .content(slug, page)
      .then((t) => !cancelled && setBody(t))
      .catch(() => !cancelled && setBody('This document could not be loaded.'))
    return () => {
      cancelled = true
    }
  }, [slug, page])

  return (
    <div className="pane doc-pane">
      <div className="doc">
        {body === null ? (
          <p>Loading…</p>
        ) : (
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
            {body}
          </Markdown>
        )}
      </div>
    </div>
  )
}

export { fieldVisible }
