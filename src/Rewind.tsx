import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, CalendarClock, Camera, Check, ChevronLeft, ChevronRight,
  Download, FileText, GitCompare, History, Pause, Play, RefreshCw,
  ShieldCheck, SkipBack, SkipForward, Square,
} from 'lucide-react'
import {
  API_URL, compareRewind, createRewindSnapshot, exportRewind, fetchHypothesisEvolution,
  fetchRewindAt, fetchRewindCoverage, fetchRewindHistory, fetchRewindHistoryFilters,
  fetchRewindSnapshots, type HypothesisEvolution, type RewindComparison, type RewindCoverage,
  type RewindHistoryEvent, type RewindSnapshot, type RewindState,
} from './api'
import './rewind.css'

const INVESTIGATION_ID = 'ORION-001'
const PLAYBACK_SPEEDS = [0.5, 1, 2, 5, 10] as const

export function formatRewindTime(value?: string | null): string {
  if (!value) return 'Not recorded'
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) return value
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function toInputValue(value?: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) return ''
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function fromInputValue(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? '' : date.toISOString()
}

export function isHistorical(asOf: string, latest?: string | null): boolean {
  if (!asOf) return false
  return new Date(asOf).valueOf() < new Date(latest || Date.now()).valueOf() - 1500
}

export function filterHistory(
  items: RewindHistoryEvent[],
  filters: { module?: string; eventType?: string; actor?: string; search?: string; dateFrom?: string; dateTo?: string },
): RewindHistoryEvent[] {
  const term = (filters.search || '').trim().toLowerCase()
  return items.filter(item => {
    if (filters.module && filters.module !== 'ALL' && item.module !== filters.module) return false
    if (filters.eventType && filters.eventType !== 'ALL' && item.event_type !== filters.eventType) return false
    if (filters.actor && filters.actor !== 'ALL' && item.actor_id !== filters.actor) return false
    if (filters.dateFrom && item.recorded_at < filters.dateFrom) return false
    if (filters.dateTo && item.recorded_at > filters.dateTo) return false
    if (term && !`${item.description} ${item.event_type} ${item.entity_id} ${item.actor_id}`.toLowerCase().includes(term)) return false
    return true
  })
}

function moduleClass(module: string): string {
  return `rewind-module-${module.toLowerCase()}`
}

function human(value: string): string {
  return value.split('_').join(' ').toLowerCase().replace(/\b\w/g, (letter: string) => letter.toUpperCase())
}

function historicalStatus(state: RewindState | null): string {
  return state?.investigation.status || 'Unknown'
}

export function CoverageBanner({ coverage }: { coverage: RewindCoverage | null }) {
  if (!coverage) return null
  const partial = coverage.status !== 'COMPLETE'
  return <div className={`rewind-coverage ${partial ? 'partial' : 'complete'}`} role="status">
    <ShieldCheck size={16}/>
    <div><strong>{partial ? 'Partial historical coverage' : 'Complete historical coverage'}</strong><span>{coverage.warnings[0] || coverage.reconstruction_note}</span></div>
    {coverage.tracked_since && <small>Tracked since {formatRewindTime(coverage.tracked_since)}</small>}
  </div>
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return <div className="rewind-stat"><span>{label}</span><b>{value}</b></div>
}

function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="rewind-empty"><History size={22}/><h3>{title}</h3>{children && <p>{children}</p>}</div>
}

async function loadAllHistory(): Promise<{ items: RewindHistoryEvent[]; total: number }> {
  const first = await fetchRewindHistory(INVESTIGATION_ID, '?page=1&page_size=500')
  if (first.items.length >= first.total) return first
  const remaining = await fetchRewindHistory(INVESTIGATION_ID, `?page=2&page_size=500`)
  return { ...first, items: [...first.items, ...remaining.items] }
}

export default function RewindPage() {
  const navigate = useNavigate()
  const [history, setHistory] = useState<RewindHistoryEvent[]>([])
  const [filters, setFilters] = useState({ event_types: [] as string[], modules: [] as string[], actors: [] as string[], entity_types: [] as string[] })
  const [coverage, setCoverage] = useState<RewindCoverage | null>(null)
  const [snapshots, setSnapshots] = useState<RewindSnapshot[]>([])
  const [state, setState] = useState<RewindState | null>(null)
  const [latest, setLatest] = useState<string>('')
  const [asOf, setAsOf] = useState('')
  const [cutoffInput, setCutoffInput] = useState('')
  const [selectedEvent, setSelectedEvent] = useState<RewindHistoryEvent | null>(null)
  const [tab, setTab] = useState<'overview' | 'evidence' | 'timeline' | 'network' | 'contradictions' | 'hypotheses'>('overview')
  const [module, setModule] = useState('ALL')
  const [eventType, setEventType] = useState('ALL')
  const [actor, setActor] = useState('ALL')
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [playing, setPlaying] = useState(false)
  const [replayIndex, setReplayIndex] = useState(0)
  const [speed, setSpeed] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionStatus, setActionStatus] = useState('')
  const [evolution, setEvolution] = useState<HypothesisEvolution | null>(null)
  const requestNumber = useRef(0)

  const loadAt = async (value: string) => {
    if (!value) return
    const request = ++requestNumber.current
    setLoading(true)
    try {
      const next = await fetchRewindAt(INVESTIGATION_ID, value)
      if (request !== requestNumber.current) return
      setState(next)
      setAsOf(next.as_of)
      setCutoffInput(toInputValue(next.as_of))
      setCoverage(next.coverage)
      setError('')
    } catch (cause) {
      if (request === requestNumber.current) setError(cause instanceof Error ? cause.message : 'Unable to reconstruct this historical state.')
    } finally {
      if (request === requestNumber.current) setLoading(false)
    }
  }

  const loadOverview = async () => {
    try {
      const [historyData, filterData, snapshotData, coverageData] = await Promise.all([
        loadAllHistory(),
        fetchRewindHistoryFilters(INVESTIGATION_ID),
        fetchRewindSnapshots(INVESTIGATION_ID),
        fetchRewindCoverage(INVESTIGATION_ID),
      ])
      setHistory(historyData.items)
      setFilters(filterData)
      setSnapshots(snapshotData)
      setCoverage(coverageData)
      const latestMoment = historyData.items[historyData.items.length - 1]?.recorded_at || new Date().toISOString()
      setLatest(latestMoment)
      setReplayIndex(Math.max(0, historyData.items.length - 1))
      await loadAt(new Date().toISOString())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load Investigation Rewind.')
      setLoading(false)
    }
  }

  useEffect(() => { void loadOverview() }, [])

  const filteredHistory = useMemo(() => filterHistory(history, { module, eventType, actor, search, dateFrom, dateTo }), [history, module, eventType, actor, search, dateFrom, dateTo])
  const historical = isHistorical(asOf, latest)
  const eventPosition = useMemo(() => {
    if (!state) return -1
    return Math.min(history.length - 1, Math.max(-1, (state.summary.history_event_count ?? 0) - 1))
  }, [state, history.length])
  const displayIndex = playing ? replayIndex : Math.max(0, eventPosition)

  const chooseEvent = (item: RewindHistoryEvent, index?: number) => {
    setSelectedEvent(item)
    setPlaying(false)
    if (typeof index === 'number') setReplayIndex(index)
    void loadAt(item.recorded_at)
  }

  const step = (direction: -1 | 1) => {
    const nextIndex = Math.max(0, Math.min(history.length - 1, eventPosition + direction))
    if (history[nextIndex]) chooseEvent(history[nextIndex], nextIndex)
  }

  useEffect(() => {
    if (!playing || !history.length) return
    const timer = window.setTimeout(() => {
      const nextIndex = replayIndex + 1
      if (nextIndex >= history.length) {
        setPlaying(false)
        setActionStatus('Replay reached the latest recorded event.')
        return
      }
      setReplayIndex(nextIndex)
      setSelectedEvent(history[nextIndex])
      void loadAt(history[nextIndex].recorded_at)
    }, 1000 / speed)
    return () => window.clearTimeout(timer)
  }, [playing, replayIndex, speed, history])

  const startReplay = () => {
    if (!history.length) return
    const start = eventPosition >= history.length - 1 ? 0 : Math.max(0, eventPosition)
    setReplayIndex(start)
    setSelectedEvent(history[start])
    setPlaying(true)
    setActionStatus('Replay advances through recorded events and reloads the historical state at each step.')
    void loadAt(history[start].recorded_at)
  }

  const stopReplay = () => {
    setPlaying(false)
    setActionStatus('Replay stopped. The selected historical state remains read-only.')
  }

  const returnToCurrent = () => {
    setPlaying(false)
    setSelectedEvent(null)
    setEvolution(null)
    setReplayIndex(Math.max(0, history.length - 1))
    void loadAt(new Date().toISOString())
  }

  const saveSnapshot = async () => {
    const name = window.prompt('Snapshot name', `Investigator snapshot · ${new Date().toLocaleString()}`)
    if (!name) return
    try {
      const created = await createRewindSnapshot(INVESTIGATION_ID, { name, event_cutoff: asOf, created_by: 'investigator', snapshot_type: 'MANUAL_SNAPSHOT' })
      setSnapshots(current => [created, ...current])
      setActionStatus(`Snapshot ${created.snapshot_name} created.`)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Snapshot creation failed.') }
  }

  const runExport = async (type: 'PDF' | 'CSV') => {
    setActionStatus(`Generating ${type} report…`)
    try {
      const result = await exportRewind(INVESTIGATION_ID, { export_type: type, cutoff_timestamp: asOf })
      if (!result.download_url) throw new Error('The report file is unavailable.')
      const anchor = document.createElement('a')
      anchor.href = `${API_URL}${result.download_url}`
      anchor.download = ''
      document.body.appendChild(anchor); anchor.click(); anchor.remove()
      setActionStatus(`${type} report generated for the selected cutoff.`)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Report generation failed.') }
  }

  const openEvolution = async (hypothesisId: string) => {
    try {
      setEvolution(await fetchHypothesisEvolution(INVESTIGATION_ID, hypothesisId, asOf))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to load hypothesis evolution.') }
  }

  const snapshotAt = (value: string) => { setPlaying(false); void loadAt(value) }
  const viewFromInput = () => { const value = fromInputValue(cutoffInput); if (value) void loadAt(value) }
  const statusClass = historical ? 'historical' : 'current'

  return <div className="rewind-page">
    <div className="rewind-heading">
      <div><div className="eyebrow">HISTORICAL INTELLIGENCE / 08</div><h1>Investigation Rewind</h1><p>Reconstruct what was recorded at any point, compare assessments, and replay the evidence trail without changing the live investigation.</p></div>
      <div className="rewind-heading-actions"><button className="ghost-btn" onClick={() => navigate('/rewind/compare')}><GitCompare size={15}/>Compare states</button><button className="primary-btn" onClick={() => void saveSnapshot()}><Camera size={15}/>Snapshot</button></div>
    </div>

    <div className={`rewind-mode ${statusClass}`}>
      <span className="rewind-mode-dot"/><b>{historical ? 'HISTORICAL VIEW — READ ONLY' : 'CURRENT RECORDED STATE'}</b>
      <span>{historical ? `Viewing ${formatRewindTime(asOf)}. Later-recorded evidence is excluded.` : 'Viewing the latest recorded investigation state.'}</span>
      {historical && <button className="rewind-return" onClick={returnToCurrent}>Return to current investigation</button>}
    </div>

    <div className="rewind-context">
      <div><span>INVESTIGATION</span><b>Project Orion</b><small>ORION-001 · {historicalStatus(state)}</small></div>
      <div><span>LATEST EVENT</span><b>{formatRewindTime(latest)}</b><small>{history.length} recorded changes</small></div>
      <div><span>LATEST SNAPSHOT</span><b>{snapshots[0]?.snapshot_name || 'None recorded'}</b><small>{snapshots[0] ? formatRewindTime(snapshots[0].created_at) : 'Create one from this view'}</small></div>
      <div><span>SELECTED CUTOFF</span><b>{formatRewindTime(asOf)}</b><small>{state?.coverage.status || 'Checking coverage'} historical coverage</small></div>
    </div>

    <CoverageBanner coverage={coverage}/>
    {error && <div className="rewind-error" role="alert"><AlertTriangle size={16}/>{error}</div>}
    {actionStatus && <p className="rewind-status" role="status">{actionStatus}</p>}

    <section className="panel rewind-controls">
      <div className="rewind-control-row">
        <label className="rewind-field"><span>HISTORICAL CUTOFF</span><input type="datetime-local" value={cutoffInput} onChange={event => setCutoffInput(event.target.value)}/></label>
        <button className="primary-btn" onClick={viewFromInput} disabled={!cutoffInput}><CalendarClock size={15}/>View state</button>
        <label className="rewind-field"><span>SNAPSHOT</span><select value="" onChange={event => { const value = event.target.value; if (value) snapshotAt(value) }}><option value="">Choose a snapshot</option>{snapshots.map(item => <option key={item.snapshot_id} value={item.event_cutoff}>{item.snapshot_name} · {formatRewindTime(item.event_cutoff)}</option>)}</select></label>
        <div className="rewind-step-controls">
          <button className="ghost-btn" title="Jump to beginning" onClick={() => history[0] && chooseEvent(history[0], 0)} disabled={!history.length}><SkipBack size={15}/></button>
          <button className="ghost-btn" title="Previous event" onClick={() => step(-1)} disabled={eventPosition <= 0}><ChevronLeft size={15}/>Previous</button>
          <button className="ghost-btn" title="Next event" onClick={() => step(1)} disabled={eventPosition >= history.length - 1}><ChevronRight size={15}/>Next</button>
          <button className="ghost-btn" title="Jump to latest" onClick={returnToCurrent}><SkipForward size={15}/>Latest</button>
        </div>
      </div>
      <div className="rewind-control-row replay-row">
        <button className="primary-btn" onClick={startReplay} disabled={!history.length || playing}><Play size={15}/>Play</button>
        <button className="ghost-btn" onClick={() => setPlaying(false)} disabled={!playing}><Pause size={15}/>Pause</button>
        <button className="ghost-btn" onClick={stopReplay} disabled={!playing}><Square size={14}/>Stop</button>
        <label className="rewind-field speed"><span>SPEED</span><select value={speed} onChange={event => setSpeed(Number(event.target.value))}>{PLAYBACK_SPEEDS.map(value => <option key={value} value={value}>{value}x</option>)}</select></label>
        <div className="rewind-progress"><div><span style={{ width: `${history.length ? ((displayIndex + 1) / history.length) * 100 : 0}%` }}/></div><small>Event {history.length ? displayIndex + 1 : 0} of {history.length} · {filteredHistory.length} shown</small></div>
        <button className="ghost-btn" onClick={() => void runExport('CSV')}><Download size={15}/>CSV</button>
        <button className="ghost-btn" onClick={() => void runExport('PDF')}><FileText size={15}/>PDF</button>
      </div>
    </section>

    {loading && <div className="rewind-loading"><RefreshCw className="spin" size={17}/>Reconstructing recorded state…</div>}

    <div className="rewind-layout">
      <aside className="panel rewind-history-panel">
        <div className="rewind-panel-head"><div><span className="eyebrow">RECORDED HISTORY</span><h2>{history.length} changes</h2></div><History size={18}/></div>
        <div className="rewind-history-filters">
          <input aria-label="Search history" placeholder="Search events, entities, actors…" value={search} onChange={event => setSearch(event.target.value)}/>
          <div><select aria-label="Filter module" value={module} onChange={event => setModule(event.target.value)}><option value="ALL">All modules</option>{filters.modules.map(value => <option key={value}>{value}</option>)}</select><select aria-label="Filter event type" value={eventType} onChange={event => setEventType(event.target.value)}><option value="ALL">All event types</option>{filters.event_types.map(value => <option key={value}>{value}</option>)}</select></div>
          <div><select aria-label="Filter actor" value={actor} onChange={event => setActor(event.target.value)}><option value="ALL">All actors</option>{filters.actors.map(value => <option key={value}>{value}</option>)}</select></div>
          <div className="rewind-date-filters"><label>From<input type="date" value={dateFrom} onChange={event => setDateFrom(event.target.value)}/></label><label>To<input type="date" value={dateTo} onChange={event => setDateTo(event.target.value)}/></label></div>
        </div>
        <div className="rewind-history-list">
          {filteredHistory.length ? filteredHistory.map((item, index) => <button key={item.event_id} className={`rewind-event ${selectedEvent?.event_id === item.event_id ? 'selected' : ''}`} onClick={() => chooseEvent(item, history.indexOf(item))}>
            <span className={`rewind-event-marker ${moduleClass(item.module)}`}/>
            <div><div className="rewind-event-top"><span className={`rewind-event-type ${moduleClass(item.module)}`}>{human(item.event_type)}</span><time>{formatRewindTime(item.recorded_at)}</time></div><p>{item.description}</p><small>{item.actor_type} · {item.actor_id} · {item.entity_type} {item.entity_id}</small>{selectedEvent?.event_id === item.event_id && <span className="rewind-event-selected"><Check size={12}/>Selected cutoff</span>}</div>
          </button>) : <Empty title="No events match the filters">Clear the filters to see the recorded investigation history.</Empty>}
        </div>
      </aside>

      <main className="rewind-detail">
        <div className="rewind-tabs" role="tablist">
          {(['overview', 'evidence', 'timeline', 'network', 'contradictions', 'hypotheses'] as const).map(value => <button key={value} role="tab" aria-selected={tab === value} className={tab === value ? 'active' : ''} onClick={() => setTab(value)}>{human(value)}</button>)}
        </div>

        {tab === 'overview' && <div className="rewind-tab-panel">
          <div className="rewind-stats">
            <Stat label="EVIDENCE AVAILABLE" value={state?.summary.evidence_count ?? '—'}/>
            <Stat label="RECONSTRUCTED EVENTS" value={state?.summary.event_count ?? '—'}/>
            <Stat label="RELATIONSHIPS" value={state?.summary.relationship_count ?? '—'}/>
            <Stat label="CONTRADICTIONS" value={state?.summary.contradiction_count ?? '—'}/>
            <Stat label="HYPOTHESES" value={state?.summary.hypothesis_count ?? '—'}/>
            <Stat label="UNRESOLVED" value={state?.summary.unresolved_contradiction_count ?? '—'}/>
          </div>
          <div className="rewind-two-col">
            <section className="panel"><div className="panel-head"><h2>State at {formatRewindTime(asOf)}</h2></div><div className="rewind-copy"><p><b>{state?.investigation.investigation_name}</b> is recorded as <b>{historicalStatus(state)}</b> with {state?.investigation.total_cases ?? 'an unknown number of'} known cases.</p><p>{state?.investigation.description}</p><p className="muted">{historical ? 'This view excludes information recorded after the selected cutoff. It is read-only.' : 'This is the latest reconstructed state from recorded information, not a live operational feed.'}</p></div></section>
            <section className="panel"><div className="panel-head"><h2>Historical coverage</h2></div><div className="rewind-copy"><p><b>{state?.coverage.status || 'Unknown'}</b> coverage · {state?.coverage.event_count ?? 0} history events · {state?.coverage.version_count ?? 0} entity versions.</p><p className="muted">{state?.coverage.reconstruction_note}</p>{state?.coverage.warnings.map(warning => <p key={warning} className="rewind-warning"><AlertTriangle size={13}/>{warning}</p>)}</div></section>
          </div>
          <section className="panel"><div className="panel-head"><h2>Snapshots</h2><span className="rewind-count">{snapshots.length}</span></div><div className="rewind-snapshot-list">{snapshots.length ? snapshots.map(item => <button key={item.snapshot_id} className="rewind-snapshot" onClick={() => snapshotAt(item.event_cutoff)}><Camera size={15}/><span><b>{item.snapshot_name}</b><small>{human(item.snapshot_type)} · cutoff {formatRewindTime(item.event_cutoff)}</small></span><span className={`rewind-integrity ${item.integrity_status.toLowerCase()}`}>{item.integrity_status}</span></button>) : <Empty title="No snapshots yet">Create an immutable snapshot from the selected cutoff.</Empty>}</div></section>
        </div>}

        {tab === 'evidence' && <section className="panel rewind-tab-panel"><div className="panel-head"><h2>Evidence available at cutoff</h2><span className="rewind-count">{state?.evidence.length ?? 0}</span></div>{state?.evidence.length ? <div className="table-wrap"><table><thead><tr><th>Evidence</th><th>Source</th><th>Status</th><th>Uploaded</th><th>Records</th><th>Versioned</th></tr></thead><tbody>{state.evidence.map(item => <tr key={item.evidence_id}><td><b>{item.evidence_id}</b><small>{item.category}</small></td><td>{item.filename}</td><td><span className={`tag ${item.status}`}>{item.status}</span></td><td>{formatRewindTime(item.uploaded_at)}</td><td>{item.record_count}</td><td>{item.versioned ? <span className="rewind-yes"><Check size={12}/>Yes</span> : <span className="rewind-no">Fallback</span>}</td></tr>)}</tbody></table></div> : <Empty title="No evidence recorded by this cutoff"/>}</section>}

        {tab === 'timeline' && <section className="panel rewind-tab-panel"><div className="panel-head"><h2>Historical timeline</h2><span className="rewind-count">{state?.timeline.events.length ?? 0}</span></div>{state?.timeline.events.length ? <div className="rewind-timeline-list">{state.timeline.events.map(event => <div className="rewind-timeline-event" key={String(event.event_id)}><span className="rewind-timeline-dot"/><div><div><b>{String(event.event_type)}</b><time>{String(event.event_date || 'Date unresolved')}</time></div><p>{String(event.event_description)}</p><small>{String(event.person_id || 'Person unresolved')} · {String(event.verification_status)} · {String(event.date_precision)}</small>{Array.isArray(event.sources) && event.sources.length > 0 && <details><summary>{event.sources.length} source reference(s)</summary>{event.sources.map((source: Record<string, unknown>, index: number) => <p key={index}>{String(source.evidence_id)} · {String(source.extracted_record_id || 'document')} · {String(source.source_field || 'source')}</p>)}</details>}</div></div>)}</div> : <Empty title="No reconstructed events at this cutoff"/>}</section>}

        {tab === 'network' && <section className="panel rewind-tab-panel"><div className="panel-head"><h2>Historical network</h2><span className="rewind-count">{state?.network.metrics.relationship_count ?? 0} relationships</span></div><div className="rewind-metrics">{Object.entries(state?.network.metrics || {}).map(([key, value]) => <Stat key={key} label={human(key)} value={value}/>)}</div>{state?.network.relationships.length ? <div className="table-wrap"><table><thead><tr><th>Relationship</th><th>Type</th><th>Classification</th><th>Status</th><th>Dates</th></tr></thead><tbody>{state.network.relationships.map(item => <tr key={String(item.relationship_id)}><td>{String(item.relationship_id)}</td><td>{String(item.relationship_type)}</td><td>{String(item.relationship_classification)}</td><td>{String(item.verification_status)}</td><td>{String(item.start_date || 'unknown')} – {String(item.end_date || 'unknown')}</td></tr>)}</tbody></table></div> : <Empty title="No relationships recorded at this cutoff"/>}</section>}

        {tab === 'contradictions' && <section className="panel rewind-tab-panel"><div className="panel-head"><h2>Historical contradictions</h2><span className="rewind-count">{state?.contradictions.length ?? 0}</span></div>{state?.contradictions.length ? <div className="table-wrap"><table><thead><tr><th>Finding</th><th>Type</th><th>Severity</th><th>Status</th><th>Detected</th></tr></thead><tbody>{state.contradictions.map(item => <tr key={String(item.contradiction_id)}><td><b>{String(item.contradiction_id)}</b><small>{String(item.title)}</small></td><td>{String(item.contradiction_type)}</td><td><span className={`tag ${String(item.severity).toLowerCase()}`}>{String(item.severity)}</span></td><td>{String(item.status)}</td><td>{formatRewindTime(String(item.first_detected_at))}</td></tr>)}</tbody></table></div> : <Empty title="No contradictions recorded at this cutoff"/>}</section>}

        {tab === 'hypotheses' && <section className="panel rewind-tab-panel"><div className="panel-head"><h2>Historical hypotheses</h2><span className="rewind-count">{state?.hypotheses.length ?? 0}</span></div>{state?.hypotheses.length ? <div className="rewind-hypothesis-list">{state.hypotheses.map(item => { const assessment = item.assessment as Record<string, unknown> | null; return <button key={String(item.hypothesis_id)} className="rewind-hypothesis" onClick={() => void openEvolution(String(item.hypothesis_id))}><div><span className="eyebrow">{String(item.hypothesis_id)}</span><h3>{String(item.title)}</h3><p>{String(item.description)}</p><small>{String(item.status)} · version {String(item.current_version)} · {Array.isArray(item.evidence_links) ? item.evidence_links.length : 0} linked source(s)</small></div><div className="rewind-assessment"><span>ASSESSMENT AT CUTOFF</span><b>{assessment?.assessment_label ? human(String(assessment.assessment_label)) : human(String(item.current_assessment || 'NOT YET EVALUATED'))}</b><small>Open evolution <ChevronRight size={12}/></small></div></button> })}</div> : <Empty title="No hypotheses recorded at this cutoff"/>}</section>}

        {evolution && <section className="panel rewind-evolution"><div className="panel-head"><h2>Hypothesis evolution · {evolution.title}</h2><button className="icon-btn" aria-label="Close evolution" onClick={() => setEvolution(null)}>×</button></div><div className="rewind-evolution-grid"><div><h3>Assessment timeline</h3>{evolution.assessment_table.length ? <div className="rewind-assessment-table">{evolution.assessment_table.map((row, index) => <div key={`${row.recorded_date}-${index}`}><time>{formatRewindTime(row.recorded_date)}</time><b>{human(row.assessment)}</b><p>{row.change_explanation}</p></div>)}</div> : <p className="muted">No assessment was recorded at or before this cutoff.</p>}</div><div><h3>Recorded changes</h3><div className="rewind-change-list">{evolution.changes.slice(0, 20).map((change, index) => <div key={`${String(change.entity_id)}-${index}`}><b>{human(String(change.change_type))}</b><time>{formatRewindTime(String(change.occurred_at))}</time><p>{String(change.description)}</p></div>)}</div></div></div><p className="rewind-disclaimer">{evolution.disclaimer}</p></section>}
      </main>
    </div>
  </div>
}

export function RewindComparisonPage() {
  const [history, setHistory] = useState<RewindHistoryEvent[]>([])
  const [snapshots, setSnapshots] = useState<RewindSnapshot[]>([])
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [snapshotA, setSnapshotA] = useState('')
  const [snapshotB, setSnapshotB] = useState('')
  const [comparison, setComparison] = useState<RewindComparison | null>(null)
  const [category, setCategory] = useState('ALL')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    Promise.all([loadAllHistory(), fetchRewindSnapshots(INVESTIGATION_ID)]).then(([historyData, snapshotData]) => {
      setHistory(historyData.items); setSnapshots(snapshotData)
      const first = historyData.items[0]?.recorded_at || ''
      const last = historyData.items[historyData.items.length - 1]?.recorded_at || new Date().toISOString()
      setFrom(toInputValue(first)); setTo(toInputValue(last))
    }).catch(cause => setError(cause instanceof Error ? cause.message : 'Unable to load comparison inputs.'))
  }, [])

  const runComparison = async () => {
    setBusy(true); setError('')
    try {
      const payload: Record<string, unknown> = { save: true, created_by: 'investigator' }
      if (snapshotA) payload.snapshot_a_id = snapshotA; else payload.timestamp_a = fromInputValue(from)
      if (snapshotB) payload.snapshot_b_id = snapshotB; else payload.timestamp_b = fromInputValue(to)
      setComparison(await compareRewind(INVESTIGATION_ID, payload))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Comparison failed.') }
    finally { setBusy(false) }
  }

  const filtered = comparison?.differences.filter(item => category === 'ALL' || item.category === category) || []
  return <div className="rewind-page">
    <div className="rewind-heading"><div><Link className="rewind-back" to="/rewind"><ArrowLeft size={14}/>Back to Investigation Rewind</Link><div className="eyebrow">HISTORICAL INTELLIGENCE / COMPARISON</div><h1>Before & After</h1><p>Compare two recorded investigation states using real history events and immutable snapshots.</p></div></div>
    {error && <div className="rewind-error" role="alert"><AlertTriangle size={16}/>{error}</div>}
    <section className="panel rewind-compare-controls"><div><label className="rewind-field"><span>FIRST CUTOFF</span><input type="datetime-local" value={from} onChange={event => { setFrom(event.target.value); setSnapshotA('') }}/></label><label className="rewind-field"><span>OR SNAPSHOT A</span><select value={snapshotA} onChange={event => setSnapshotA(event.target.value)}><option value="">Use first cutoff</option>{snapshots.map(item => <option key={item.snapshot_id} value={item.snapshot_id}>{item.snapshot_name}</option>)}</select></label></div><div><label className="rewind-field"><span>SECOND CUTOFF</span><input type="datetime-local" value={to} onChange={event => { setTo(event.target.value); setSnapshotB('') }}/></label><label className="rewind-field"><span>OR SNAPSHOT B</span><select value={snapshotB} onChange={event => setSnapshotB(event.target.value)}><option value="">Use second cutoff</option>{snapshots.map(item => <option key={item.snapshot_id} value={item.snapshot_id}>{item.snapshot_name}</option>)}</select></label></div><button className="primary-btn" onClick={() => void runComparison()} disabled={busy || (!from && !snapshotA) || (!to && !snapshotB)}><GitCompare size={15}/>{busy ? 'Comparing…' : 'Compare states'}</button></section>
    {comparison && <><section className="panel rewind-comparison-summary"><div className="rewind-comparison-head"><div><span className="eyebrow">RECORDED DIFFERENCE</span><h2>{comparison.summary}</h2><p>{comparison.state_a.as_of} → {comparison.state_b.as_of}</p></div><div className="rewind-comparison-totals"><Stat label="ADDED" value={comparison.by_change_type.ADDED || 0}/><Stat label="REMOVED" value={comparison.by_change_type.REMOVED || 0}/><Stat label="MODIFIED" value={(comparison.by_change_type.MODIFIED || 0) + (comparison.by_change_type.RECLASSIFIED || 0)}/></div></div><p className="rewind-disclaimer">{comparison.disclaimer}</p></section>
      <div className="rewind-compare-filters"><button className={category === 'ALL' ? 'filter active' : 'filter'} onClick={() => setCategory('ALL')}>ALL</button>{Object.keys(comparison.by_category).map(key => <button key={key} className={category === key ? 'filter active' : 'filter'} onClick={() => setCategory(key)}>{human(key)} ({comparison.by_category[key]})</button>)}</div>
      <section className="panel"><div className="panel-head"><h2>Differences</h2><span className="rewind-count">{filtered.length}</span></div>{filtered.length ? <div className="rewind-difference-list">{filtered.map((item, index) => <details key={`${item.entity_type}-${item.entity_id}-${index}`} className={`rewind-difference ${item.difference_type.toLowerCase()}`}><summary><span className="rewind-difference-type">{human(item.difference_type)}</span><b>{human(item.category)} · {item.entity_id}</b><time>{formatRewindTime(item.change_timestamp)}</time></summary><p>{item.explanation}</p><div className="rewind-difference-values"><div><span>PREVIOUS</span><pre>{JSON.stringify(item.previous_value, null, 2)}</pre></div><div><span>CURRENT</span><pre>{JSON.stringify(item.current_value, null, 2)}</pre></div></div><small>Source: {JSON.stringify(item.source_reference)}</small></details>)}</div> : <Empty title="No differences in this category"/>}</section></>}
    {!comparison && !busy && <Empty title="Select two recorded states">Choose timestamps or immutable snapshots. The comparison reports only actual stored differences.</Empty>}
  </div>
}