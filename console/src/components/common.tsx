/** Small shared pieces: the step ribbon, state pips, and form inputs. */

import type { Field, StatusEntry, WorkloadStatus } from '../lib/api'
import { fieldVisible } from '../lib/api'

const LABELS: Record<WorkloadStatus, string> = {
  idle: 'Not run',
  partial: 'Partial',
  completed: 'Complete',
  failed: 'Failed',
  queued: 'Queued',
  running: 'Running',
}

export function StatePip({
  status,
  blocked,
  label,
}: {
  status: WorkloadStatus
  blocked?: boolean
  label?: string
}) {
  if (blocked && status === 'idle') {
    return (
      <span className="state st-blocked">
        <i className="pip" />
        {label ?? 'Waiting'}
      </span>
    )
  }
  return (
    <span className={`state st-${status}`}>
      <i className="pip" />
      {label ?? LABELS[status]}
    </span>
  )
}

/** The signature device. Segments are discrete plays, never a percentage. */
export function Ribbon({
  entry,
  size = 'sm',
  fallback = 1,
}: {
  entry?: StatusEntry
  size?: 'xs' | 'sm' | 'lg'
  fallback?: number
}) {
  const steps = entry ? Object.entries(entry.steps) : []
  if (steps.length === 0) {
    return (
      <span className={`ribbon ${size}`} aria-hidden="true">
        {Array.from({ length: fallback }, (_, i) => (
          <i key={i} />
        ))}
      </span>
    )
  }
  return (
    <span
      className={`ribbon ${size}`}
      role="img"
      aria-label={`${steps.filter(([, s]) => s === 'completed').length} of ${steps.length} steps complete`}
    >
      {steps.map(([label, status]) => (
        <i key={label} className={status} title={`${label} — ${status}`} />
      ))}
    </span>
  )
}

export function FieldInput({
  field,
  value,
  values,
  onChange,
}: {
  field: Field
  value: string
  values: Record<string, string>
  onChange: (v: string) => void
}) {
  if (!fieldVisible(field, values)) return null

  const id = `f-${field.key}`
  const describedBy = field.hint ? `${id}-hint` : undefined

  return (
    <div className="fld">
      <label htmlFor={id}>
        {field.label}
        {field.type === 'password' && <span className="lock">Not saved</span>}
      </label>

      {field.type === 'textarea' ? (
        <textarea
          id={id}
          value={value}
          placeholder={field.placeholder}
          aria-describedby={describedBy}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : field.type === 'select' ? (
        <select
          id={id}
          value={value}
          aria-describedby={describedBy}
          onChange={(e) => onChange(e.target.value)}
        >
          {field.options?.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          type={field.type === 'password' ? 'password' : 'text'}
          value={value}
          placeholder={field.placeholder}
          aria-describedby={describedBy}
          autoComplete={field.type === 'password' ? 'new-password' : 'off'}
          onChange={(e) => onChange(e.target.value)}
        />
      )}

      {/* A select's chosen option carries its own explanation; showing both the
          generic hint and the option hint would be two labels doing one job. */}
      {field.type === 'select' && field.options?.find((o) => o.value === value)?.hint ? (
        <span className="hint" id={describedBy}>
          {field.options.find((o) => o.value === value)?.hint}
        </span>
      ) : field.hint ? (
        <span className="hint" id={describedBy}>
          {field.hint}
        </span>
      ) : null}
    </div>
  )
}
