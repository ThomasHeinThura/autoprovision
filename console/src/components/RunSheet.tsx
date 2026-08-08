import { useNavigate, useParams } from 'react-router-dom'
import { formatDuration } from '../lib/api'
import { useStore } from '../lib/store'
import { Ribbon, StatePip } from './common'

/** One environment per screen. UAT and Production are separate places, and the
 *  console should never let you act on one while looking at the other. */
export function RunSheet() {
  const { envId = 'shared' } = useParams()
  const navigate = useNavigate()
  const store = useStore()
  const env = store.registry?.environments.find((e) => e.id === envId)
  const workloads = store.byEnv(envId)

  if (!env) return <div className="center-msg">No such environment.</div>

  const done = workloads.filter((w) => store.statusOf(w.id) === 'completed').length
  const running = workloads.filter((w) => store.statusOf(w.id) === 'running')
  const failed = workloads.filter((w) => store.statusOf(w.id) === 'failed')

  return (
    <main className="stage">
      <div className="stage-head">
        <h1>{env.title}</h1>
        {env.meta && <span className="meta">{env.meta}</span>}
        <span className="meta">
          {done} of {workloads.length} complete
        </span>
      </div>
      <p className="stage-blurb">{env.blurb}</p>

      <div className="stage-alerts">
        {running.map((w) => (
          <div className="note" key={w.id}>
            <strong>
              {w.ordinal} · {w.title} is running.
            </strong>{' '}
            {store.state?.readiness &&
              Object.entries(store.state.readiness).filter(([, r]) =>
                r.blockedBy.some((b) => b.id === w.id),
              ).length > 0 && (
                <>
                  {
                    Object.entries(store.state.readiness).filter(([, r]) =>
                      r.blockedBy.some((b) => b.id === w.id),
                    ).length
                  }{' '}
                  workloads are waiting on it.
                </>
              )}
          </div>
        ))}
        {failed.map((w) => (
          <div className="note stop" key={w.id}>
            <strong>
              {w.ordinal} · {w.title} failed.
            </strong>{' '}
            Open it to read the output. Fixing the cause and running again resumes from the failed
            step — completed steps are skipped.
          </div>
        ))}
        {envId === 'danger' && (
          <div className="note stop">
            <strong>These workloads destroy state.</strong> They are excluded from{' '}
            <strong>Run ready workloads</strong>, and each asks you to retype its target before it
            starts. Confirm you have a current backup first.
          </div>
        )}
      </div>

      <section className="sheet">
        <div className="sheet-head">
          <h2>{env.title}</h2>
          <span className="right">
            <span className="tally">
              {done} of {workloads.length} complete
              {running.length > 0 && ` · ${running.length} running`}
              {failed.length > 0 && ` · ${failed.length} failed`}
            </span>
          </span>
        </div>

        {workloads.map((w) => {
          const status = store.statusOf(w.id)
          const readiness = store.state?.readiness[w.id]
          const entry = store.state?.status[w.id]
          const blocked = readiness && !readiness.ready

          return (
            <button
              className={`row${w.destructive ? ' destructive' : ''}`}
              key={w.id}
              type="button"
              onClick={() => navigate(`/env/${envId}/${w.id}`)}
            >
              <span className="ord">{w.ordinal}</span>
              <span className="row-body">
                <span>
                  <span className="nm">{w.title}</span>
                  <span className="why">
                    {blocked && status === 'idle' ? (
                      <>
                        Waiting on{' '}
                        {readiness.blockedBy
                          .map((b) => `${b.ordinal} · ${b.title}`)
                          .join(', ')}
                      </>
                    ) : (
                      w.summary
                    )}
                  </span>
                </span>
                <StatePip status={status} blocked={blocked} />
                <Ribbon entry={entry} />
                <span className="dur">{formatDuration(entry?.durationSeconds)}</span>
              </span>
            </button>
          )
        })}
      </section>
    </main>
  )
}
