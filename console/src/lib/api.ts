/** Typed client for the control plane API.
 *
 * Every shape here mirrors app/workloads.py and app/main.py. The registry is
 * served rather than duplicated, so a workload cannot exist in one place and not
 * the other — the drift that let two cards silently lose their settings.
 */

export type FieldType = 'text' | 'password' | 'textarea' | 'select' | 'number'

export interface SelectOption {
  value: string
  label: string
  hint?: string
}

export interface Field {
  key: string
  label: string
  type: FieldType
  default: string
  placeholder: string
  hint: string
  options?: SelectOption[]
  showIf?: Record<string, string[]>
  /** Value is one or more machine addresses. Drives the topology view. */
  hosts?: boolean
}

export interface Workload {
  id: string
  env: string
  ordinal: string
  title: string
  summary: string
  action: string
  fields: Field[]
  requires: string[]
  destructive: boolean
  confirmField: string
  always: boolean
  docs: string
}

export interface Environment {
  id: string
  group: string
  title: string
  blurb: string
  meta: string
}

export interface Registry {
  environments: Environment[]
  workloads: Workload[]
}

export type StepStatus = 'completed' | 'failed' | 'pending'
export type WorkloadStatus = 'idle' | 'partial' | 'completed' | 'failed' | 'queued' | 'running'

export interface StatusEntry {
  status: WorkloadStatus
  steps: Record<string, StepStatus>
  durationSeconds: number | null
}

export interface Readiness {
  ready: boolean
  blockedBy: { id: string; ordinal: string; title: string }[]
}

export interface ControlPlaneState {
  targets: Record<string, Record<string, string>>
  status: Record<string, StatusEntry>
  readiness: Record<string, Readiness>
  busy: string[]
}

export interface PlanStep {
  label: string
  playbook: string
  exists: boolean
  always: boolean
  status: StepStatus
}

export interface Plan {
  workload: string
  /** False when the configuration is incomplete or contradictory. Not an HTTP
   *  error — preview is called as the operator types. */
  valid: boolean
  error: string | null
  inventory: { group: string; hosts: string[] }[]
  steps: PlanStep[]
  needsCert: boolean
  destructive: boolean
}

export interface TopologyHost {
  host: string
  roles: string[]
  environments: string[]
  workloads: { id: string; ordinal: string; title: string; status: WorkloadStatus }[]
  /** True when one machine carries more than one role. */
  shared: boolean
}

export interface Topology {
  hosts: TopologyHost[]
  totalHosts: number
  environments: { id: string; title: string; hostCount: number; networks: string[] }[]
  operations: { id: string; hostCount: number }[]
  sharedHosts: string[]
  unconfigured: { id: string; env: string; ordinal: string; title: string }[]
  /** Saved state referring to environments no longer in config/environments.yml. */
  orphanedEnvironments: string[]
}

export class ApiError extends Error {}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const text = await res.text()
  let body: unknown = text
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    /* plain text endpoint */
  }
  if (!res.ok) {
    const message =
      body && typeof body === 'object' && 'error' in body
        ? String((body as { error: unknown }).error)
        : `Request failed (${res.status})`
    throw new ApiError(message)
  }
  return body as T
}

export const api = {
  registry: () => req<Registry>('/api/registry'),
  state: () => req<ControlPlaneState>('/api/state'),

  saveTarget: (workload: string, values: Record<string, string>) =>
    req<{ saved: boolean }>('/api/targets', {
      method: 'POST',
      body: JSON.stringify({ workload, values }),
    }),

  preview: (workload: string, values: Record<string, string>) =>
    req<Plan>('/api/preview', {
      method: 'POST',
      body: JSON.stringify({ workload, values }),
    }),

  run: (opts: {
    workload: string
    values: Record<string, string>
    force?: boolean
    confirm?: string
    sshUser: string
    sshPass: string
  }) =>
    req<{ runId: string }>('/api/run', {
      method: 'POST',
      body: JSON.stringify({
        workload: opts.workload,
        values: opts.values,
        force: opts.force ?? false,
        confirm: opts.confirm ?? '',
        ssh_user: opts.sshUser,
        ssh_pass: opts.sshPass,
      }),
    }),

  runReady: (values: Record<string, Record<string, string>>, sshUser: string, sshPass: string) =>
    req<{
      started: { workload: string; runId: string }[]
      skipped: { workload: string; reason: string }[]
      excludedDestructive: string[]
    }>('/api/run-ready', {
      method: 'POST',
      body: JSON.stringify({ values, ssh_user: sshUser, ssh_pass: sshPass }),
    }),

  reset: (workload: string) =>
    req<{ cleared: number }>('/api/reset', {
      method: 'POST',
      body: JSON.stringify({ workload }),
    }),

  log: (workload: string) => req<string>(`/api/log/${workload}`),
  content: (slug: string, page: string) => req<string>(`/api/content/${slug}/${page}`),
  handbook: () => req<{ slug: string; title: string; body: string }[]>('/api/handbook'),
  topology: () => req<Topology>('/api/topology'),
}

/** True when this field should be shown, given the current values of its siblings. */
export function fieldVisible(field: Field, values: Record<string, string>): boolean {
  if (!field.showIf) return true
  return Object.entries(field.showIf).every(([key, allowed]) =>
    allowed.includes(values[key] ?? ''),
  )
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  const s = Math.round(seconds)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return `${m}m ${String(s % 60).padStart(2, '0')}s`
}
