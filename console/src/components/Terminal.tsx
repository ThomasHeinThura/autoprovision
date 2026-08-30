import { useEffect, useMemo, useRef, useState } from 'react'
import { useLogStream } from '../lib/store'

type Filter = 'all' | 'changed' | 'failed'

/** Classifies an Ansible output line so the terminal can colour and filter it. */
function classify(line: string): string {
  if (line.startsWith('PLAY ')) return 'l-play'
  if (line.startsWith('TASK ') || line.startsWith('RUNNING HANDLER')) return 'l-task'
  if (line.startsWith('changed:')) return 'l-changed'
  if (line.startsWith('ok:')) return 'l-ok'
  if (line.startsWith('skipping:') || line.startsWith('ignoring:')) return 'l-skip'
  if (line.startsWith('fatal:') || line.startsWith('failed:') || line.startsWith('ERROR')) return 'l-err'
  if (line.startsWith('✗')) return 'l-err'
  if (line.startsWith('✓') || line.startsWith('▶')) return 'l-recap'
  if (line.startsWith('PLAY RECAP') || /\bfailed=\d/.test(line)) return 'l-recap'
  return ''
}

function matchesFilter(line: string, filter: Filter): boolean {
  if (filter === 'all') return true
  const cls = classify(line)
  if (filter === 'changed') return cls === 'l-changed' || cls === 'l-task' || cls === 'l-play'
  return cls === 'l-err' || cls === 'l-task' || /failed=[1-9]/.test(line)
}

export function Terminal({ workloadId }: { workloadId: string }) {
  const { lines, live } = useLogStream(workloadId)
  const [filter, setFilter] = useState<Filter>('all')
  const [query, setQuery] = useState('')
  const [follow, setFollow] = useState(true)
  const endRef = useRef<HTMLDivElement>(null)

  const visible = useMemo(() => {
    const byFilter = lines.filter((l) => matchesFilter(l, filter))
    if (!query.trim()) return byFilter
    const needle = query.toLowerCase()
    return byFilter.filter((l) => l.toLowerCase().includes(needle))
  }, [lines, filter, query])

  useEffect(() => {
    if (follow) endRef.current?.scrollIntoView({ block: 'end' })
  }, [visible, follow])

  function download() {
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${workloadId}.log`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="term">
      <div className="term-bar">
        <span className="t">Output</span>
        <div className="filters" role="group" aria-label="Filter output">
          {(['all', 'changed', 'failed'] as Filter[]).map((f) => (
            <button
              key={f}
              type="button"
              aria-pressed={filter === f}
              onClick={() => setFilter(f)}
            >
              {f === 'all' ? 'All' : f === 'changed' ? 'Changed' : 'Failed'}
            </button>
          ))}
        </div>
        <input
          type="search"
          placeholder="Find in output"
          aria-label="Find in output"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="right">
          {live && (
            <span className="state st-running">
              <i className="pip" />
              Live
            </span>
          )}
          <label className="chk">
            <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
            Follow
          </label>
          <span className="mono">workload-{workloadId}.log</span>
          <button className="btn sm" type="button" onClick={download} disabled={lines.length === 0}>
            Download
          </button>
        </span>
      </div>

      <pre className="log">
        {visible.length === 0 ? (
          <span className="empty">
            {lines.length === 0
              ? 'No output yet. Use Show plan to see what would run, or Run workload to start.'
              : `No lines match. ${lines.length} hidden by the current filter.`}
          </span>
        ) : (
          visible.map((line, i) => (
            <span key={i} className={classify(line)}>
              {highlight(line, query)}
              {'\n'}
            </span>
          ))
        )}
        <div ref={endRef} />
      </pre>
    </div>
  )
}

function highlight(line: string, query: string) {
  const q = query.trim()
  if (!q) return line
  const idx = line.toLowerCase().indexOf(q.toLowerCase())
  if (idx === -1) return line
  return (
    <>
      {line.slice(0, idx)}
      <mark>{line.slice(idx, idx + q.length)}</mark>
      {line.slice(idx + q.length)}
    </>
  )
}
