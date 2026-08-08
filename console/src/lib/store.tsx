/** Control-plane state, shared across the console.
 *
 * Deliberately hand-rolled rather than a data library: the whole surface is one
 * registry that never changes, one state object that is re-fetched, and per-
 * workload form values. A query cache would be more machinery than the problem
 * has, and this stays readable to whoever inherits it.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  api,
  type ControlPlaneState,
  type Registry,
  type Workload,
  type WorkloadStatus,
} from './api'

interface Store {
  registry: Registry | null
  state: ControlPlaneState | null
  loading: boolean
  error: string | null

  values: Record<string, Record<string, string>>
  setValue: (workload: string, key: string, value: string) => void
  valuesFor: (workload: Workload) => Record<string, string>

  sshUser: string
  sshPass: string
  setSsh: (user: string, pass: string) => void

  refresh: () => Promise<void>
  statusOf: (workloadId: string) => WorkloadStatus
  byEnv: (envId: string) => Workload[]
  workload: (id: string) => Workload | undefined
}

const Ctx = createContext<Store | null>(null)

export function StoreProvider({ children }: { children: ReactNode }) {
  const [registry, setRegistry] = useState<Registry | null>(null)
  const [state, setState] = useState<ControlPlaneState | null>(null)
  const [values, setValues] = useState<Record<string, Record<string, string>>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sshUser, setSshUser] = useState('autoprovision')
  // Held in memory only, and never sent to /api/targets. It reaches the server
  // once per run, is written into a 0600 inventory, and is never persisted here.
  const [sshPass, setSshPass] = useState('')
  const seeded = useRef(false)

  const refresh = useCallback(async () => {
    try {
      const next = await api.state()
      setState(next)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [reg, st] = await Promise.all([api.registry(), api.state()])
        if (cancelled) return
        setRegistry(reg)
        setState(st)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  // Seed form values once: registry defaults first, then anything saved.
  useEffect(() => {
    if (seeded.current || !registry || !state) return
    seeded.current = true
    const next: Record<string, Record<string, string>> = {}
    for (const w of registry.workloads) {
      const defaults: Record<string, string> = {}
      for (const f of w.fields) defaults[f.key] = f.default
      next[w.id] = { ...defaults, ...(state.targets[w.id] ?? {}) }
    }
    setValues(next)
  }, [registry, state])

  // A slow background refresh keeps status honest across restarts and across a
  // second operator working in another browser. Live output comes from SSE, not
  // from this, so the interval can be lazy.
  useEffect(() => {
    const id = window.setInterval(refresh, 6000)
    return () => window.clearInterval(id)
  }, [refresh])

  const setValue = useCallback((workload: string, key: string, value: string) => {
    setValues((prev) => ({ ...prev, [workload]: { ...(prev[workload] ?? {}), [key]: value } }))
  }, [])

  const store = useMemo<Store>(
    () => ({
      registry,
      state,
      loading,
      error,
      values,
      setValue,
      valuesFor: (w) => values[w.id] ?? {},
      sshUser,
      sshPass,
      setSsh: (u, p) => {
        setSshUser(u)
        setSshPass(p)
      },
      refresh,
      statusOf: (id) => {
        if (state?.busy.includes(id)) return 'running'
        return state?.status[id]?.status ?? 'idle'
      },
      byEnv: (envId) => (registry?.workloads ?? []).filter((w) => w.env === envId),
      workload: (id) => registry?.workloads.find((w) => w.id === id),
    }),
    [registry, state, loading, error, values, setValue, sshUser, sshPass, refresh],
  )

  return <Ctx.Provider value={store}>{children}</Ctx.Provider>
}

export function useStore(): Store {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useStore must be used inside StoreProvider')
  return ctx
}

/** Streams a workload's output over server-sent events.
 *
 * Replaces the previous console's approach of re-fetching the entire log every
 * 1.5 seconds — with six parallel runs that was megabytes a second of bytes the
 * browser already had.
 */
export function useLogStream(workloadId: string) {
  const [lines, setLines] = useState<string[]>([])
  const [live, setLive] = useState(false)

  useEffect(() => {
    setLines([])
    let source: EventSource | null = null
    let cancelled = false

    api
      .log(workloadId)
      .then((existing) => {
        if (cancelled) return
        if (existing) setLines(existing.split('\n'))
      })
      .catch(() => undefined)
      .finally(() => {
        if (cancelled) return
        source = new EventSource(`/api/stream/${workloadId}`)
        source.onmessage = (e) => setLines((prev) => [...prev, e.data])
        source.addEventListener('reset', () => setLines([]))
        source.addEventListener('status', (e) => setLive((e as MessageEvent).data === 'running'))
        source.onerror = () => setLive(false)
      })

    return () => {
      cancelled = true
      source?.close()
    }
  }, [workloadId])

  return { lines, live }
}
