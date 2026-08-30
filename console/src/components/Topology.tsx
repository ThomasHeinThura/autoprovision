import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Topology as TopologyData } from '../lib/api'
import { StatePip } from './common'

/** Every machine this control plane is managing.
 *
 * At three machines you keep the estate in your head. At fifty you do not, and
 * nothing else in the system can answer "what am I actually managing?" — the
 * inventories are written per run and Ansible keeps no memory between them.
 */
export function Topology() {
  const [data, setData] = useState<TopologyData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    api
      .topology()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  if (error) return <main className="stage"><div className="note stop">{error}</div></main>
  if (!data) return <main className="stage"><p>Loading…</p></main>

  const totalConfigured = data.environments.reduce((n, e) => n + e.hostCount, 0)

  return (
    <main className="stage">
      <div className="stage-head">
        <h1>Topology</h1>
        <span className="meta">
          {data.totalHosts} machine{data.totalHosts === 1 ? '' : 's'} across{' '}
          {data.environments.filter((e) => e.hostCount > 0).length} environment
          {data.environments.filter((e) => e.hostCount > 0).length === 1 ? '' : 's'}
        </span>
      </div>
      <p className="stage-blurb">
        Derived from what you have configured, not from a discovery scan — so a machine you
        entered but never provisioned still appears here, which is usually what you want to see.
        Nothing in this platform assumes a particular machine count.
      </p>

      <div className="stage-alerts">
        {data.orphanedEnvironments.length > 0 && (
          <div className="note warn">
            <strong>
              Saved state refers to {data.orphanedEnvironments.length} environment
              {data.orphanedEnvironments.length === 1 ? '' : 's'} that no longer exist
              {data.orphanedEnvironments.length === 1 ? 's' : ''}:
            </strong>{' '}
            {data.orphanedEnvironments.map((e) => (
              <code key={e}>{e}</code>
            ))}
            . Renaming an environment in <code>config/environments.yml</code> orphans its recorded
            install status. Nothing is broken, but that history is no longer reachable.
          </div>
        )}

        {data.sharedHosts.length > 0 && (
          <div className="note warn">
            <strong>
              {data.sharedHosts.length} machine{data.sharedHosts.length === 1 ? '' : 's'} carr
              {data.sharedHosts.length === 1 ? 'ies' : 'y'} more than one role.
            </strong>{' '}
            Fine in a lab. In production it means one reboot takes out two things, and the
            database competes with whatever else lives there for page cache.
          </div>
        )}

        {data.totalHosts === 0 && (
          <div className="note">
            <strong>Nothing configured yet.</strong> Fill in a workload's addresses and it appears
            here. Start with an environment on the left.
          </div>
        )}
      </div>

      {data.environments.some((e) => e.hostCount > 0) && (
        <section className="sheet" style={{ marginBottom: 16 }}>
          <div className="sheet-head">
            <h2>Machines per environment</h2>
            <span className="right">
              <span className="tally">{totalConfigured} assignments</span>
            </span>
          </div>
          <div className="env-counts">
            {data.environments.map((e) => (
              <button
                key={e.id}
                type="button"
                className="env-count"
                onClick={() => navigate(`/env/${e.id}`)}
              >
                <span className="n">{e.hostCount}</span>
                <span className="t">{e.title}</span>
                <span className="s mono">{e.networks.join(' · ') || '—'}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {data.hosts.length > 0 && (
        <section className="sheet" style={{ marginBottom: 16 }}>
          <div className="sheet-head">
            <h2>Machines</h2>
            <span className="right">
              <a className="btn sm" href="/api/topology/inventory" download>
                Download inventory
              </a>
            </span>
          </div>
          <div className="table-scroll">
            <table className="hosts">
              <thead>
                <tr>
                  <th>Address</th>
                  <th>Roles</th>
                  <th>Environment</th>
                  <th>Workloads</th>
                </tr>
              </thead>
              <tbody>
                {data.hosts.map((h) => (
                  <tr key={h.host} className={h.shared ? 'shared' : undefined}>
                    <td className="mono">{h.host}</td>
                    <td>
                      {h.roles.map((r) => (
                        <span className="tag" key={r} style={{ marginRight: 4 }}>
                          {r}
                        </span>
                      ))}
                    </td>
                    <td>{h.environments.join(', ')}</td>
                    <td>
                      <span className="wl-links">
                        {h.workloads.map((w) => (
                          <button
                            key={w.id + w.ordinal}
                            type="button"
                            className="wl-link"
                            onClick={() => navigate(`/env/${w.id.split('_')[0]}/${w.id}`)}
                          >
                            <StatePip status={w.status} label="" />
                            {w.ordinal} · {w.title}
                          </button>
                        ))}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {data.unconfigured.length > 0 && (
        <section className="sheet">
          <div className="sheet-head">
            <h2>Workloads with no machines yet</h2>
            <span className="right">
              <span className="tally">{data.unconfigured.length}</span>
            </span>
          </div>
          <div className="unconfigured">
            {data.unconfigured.map((w) => (
              <button
                key={w.id}
                type="button"
                className="wl-link"
                onClick={() => navigate(`/env/${w.env}/${w.id}`)}
              >
                <span className="mono">{w.env}</span> {w.ordinal} · {w.title}
              </button>
            ))}
          </div>
        </section>
      )}
    </main>
  )
}
