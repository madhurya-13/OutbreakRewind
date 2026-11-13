import { useEffect, useMemo, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Activity, AlertTriangle, Archive, Beaker, Bell, BookOpen, ChevronRight, FileText, GitBranch, LayoutDashboard, Menu, Search, Settings, ShieldCheck, Users, X } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ReactFlow, Background, Controls, type Edge, type Node } from 'reactflow'
import 'reactflow/dist/style.css'
import { API_URL, fetchDashboard, fetchHealth, fetchInvestigations, fetchEvidenceRecords, fetchEvidenceDetail, fetchEvidenceRows, uploadEvidence, verifyEvidenceRecord, fetchTimeline, fetchTimelineFindings, fetchTimelineStatistics, reconstructTimeline, verifyTimelineEvent, fetchGraph, rebuildGraph, reviewGraphRelationship, type Evidence, type Investigation, type TimelineEvent, type TimelineFinding, type TimelineStatistics, type GraphPayload, type GraphRelationship } from './api'
import { chartData, evidence, contradictions, hypotheses } from './data'
import { evidenceSourceUrl, temporalLabel } from './timeline'

const nav = [
  { to: '/', label: 'Overview', Icon: LayoutDashboard }, { to: '/investigations', label: 'Investigations', Icon: Activity },
  { to: '/evidence', label: 'Evidence Vault', Icon: Archive }, { to: '/timeline', label: 'Timeline Reconstruction', Icon: GitBranch },
  { to: '/network', label: 'Case Network', Icon: Users }, { to: '/contradictions', label: 'Contradiction Center', Icon: AlertTriangle },
  { to: '/hypotheses', label: 'Hypothesis Lab', Icon: Beaker }, { to: '/rewind', label: 'Investigation Rewind', Icon: BookOpen },
  { to: '/reports', label: 'Reports', Icon: FileText }, { to: '/settings', label: 'Settings', Icon: Settings },
]

function Shell({ children, connected }: { children: React.ReactNode; connected: boolean }) {
  const [open, setOpen] = useState(false)
  const location = useLocation()
  return <div className="app-shell">
    <aside className={open ? 'sidebar open' : 'sidebar'}>
      <div className="brand"><div className="brand-mark">OR</div><div><strong>OUTBREAK<br />REWIND</strong><small>Evidence. Connections. Clarity.</small></div><button className="icon-btn mobile-close" onClick={() => setOpen(false)}><X size={18}/></button></div>
      <div className="rail-label">INVESTIGATION COMMAND CENTER</div>
      <nav>{nav.map(({ to, label, Icon }) => <NavLink key={to} to={to} onClick={() => setOpen(false)} className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}><Icon size={16}/><span>{label}</span>{location.pathname === to && <ChevronRight className="nav-chevron" size={14}/>}</NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="system-card"><span className={connected ? 'status-dot' : 'status-dot warning'}/><span><b>{connected ? 'Backend connected' : 'Demo data mode'}</b><small>{connected ? 'API responding' : 'API unavailable'}</small></span></div></div>
    </aside>
    {open && <div className="scrim" onClick={() => setOpen(false)}/>}
    <main className="main"><header><button className="icon-btn menu-btn" onClick={() => setOpen(true)}><Menu size={20}/></button><div className="crumb">PROJECT ORION <span>/</span> {location.pathname === '/' ? 'OVERVIEW' : location.pathname.slice(1).toUpperCase()}</div><div className="header-actions"><div className="search"><Search size={16}/><input aria-label="Search" placeholder="Search investigations..." /></div><button className="icon-btn" aria-label="Notifications"><Bell size={18}/><i className="notification-dot"/></button><div className="avatar">MC</div></div></header>{!connected && <div className="connection-warning"><AlertTriangle size={15}/> Backend unavailable — showing clearly labelled synthetic demonstration data.</div>}{children}</main>
  </div>
}

function Title({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: React.ReactNode }) { return <div className="page-title"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div> }
function Panel({ title, children }: { title: string; children: React.ReactNode }) { return <section className="panel"><div className="panel-head"><h2>{title}</h2></div>{children}</section> }

function Overview({ investigations, summary }: { investigations: Investigation[]; summary: Record<string, number> }) {
  const kpis = [{ label: 'Active investigations', value: summary.active_investigations ?? 8, Icon: Activity }, { label: 'Total cases', value: summary.total_cases ?? 124, Icon: Users }, { label: 'Evidence records', value: summary.evidence_records ?? 386, Icon: Archive }, { label: 'Unresolved contradictions', value: summary.unresolved_contradictions ?? 12, Icon: AlertTriangle }, { label: 'Active hypotheses', value: summary.active_hypotheses ?? 18, Icon: Beaker }]
  return <><Title eyebrow="SITUATIONAL AWARENESS / 01" title="Investigation Command Center" description="Synthetic Project Orion workspace for reconstructing evidence, relationships, and evolving hypotheses." action={<span className="live-pill"><span className="status-dot"/> SYNTHETIC DATA</span>}/>
    <div className="kpi-grid">{kpis.map(({ label, value, Icon }) => <div className="panel kpi" key={label}><Icon size={18}/><span>{label}</span><strong>{value}</strong><small>Project Orion · demonstration</small></div>)}</div>
    <div className="dashboard-grid"><Panel title="Evidence submissions · last 7 days"><div className="chart"><ResponsiveContainer width="100%" height={250}><AreaChart data={chartData}><CartesianGrid stroke="#243449" strokeDasharray="3 3"/><XAxis dataKey="day" stroke="#71839a"/><YAxis stroke="#71839a"/><Tooltip contentStyle={{ background: '#101b2b', border: '1px solid #2e435c' }}/><Area type="monotone" dataKey="records" stroke="#4dc7d7" fill="#4dc7d7" fillOpacity={0.14}/></AreaChart></ResponsiveContainer></div></Panel>
      <Panel title="Critical alerts"><div className="alert-list">{contradictions.slice(0, 3).map(c => <div className="alert-row" key={c.id}><AlertTriangle size={16}/><div><b>{c.title}</b><span>{c.severity} · {c.status}</span></div></div>)}</div></Panel></div>
    <Panel title="Investigation overview"><div className="table-wrap"><table><thead><tr><th>ID</th><th>Investigation</th><th>Category</th><th>Cases</th><th>Evidence</th><th>Status</th></tr></thead><tbody>{investigations.map(i => <tr key={i.investigation_id}><td>{i.investigation_id}</td><td><b>{i.investigation_name}</b><small>{i.description}</small></td><td>{i.outbreak_category}</td><td>{i.total_cases}</td><td>{i.evidence_records}</td><td><span className={`tag ${i.status.toLowerCase()}`}>{i.status}</span></td></tr>)}</tbody></table></div></Panel>
  </>
}

function Investigations({ investigations }: { investigations: Investigation[] }) { return <><Title eyebrow="CASE MANAGEMENT / 02" title="Investigations" description="Review active and archived outbreak investigations." action={<button className="primary-btn">+ Create investigation</button>}/><div className="toolbar"><div className="search wide"><Search size={16}/><input placeholder="Filter investigations..." /></div><div className="filter active">ALL STATUS</div><div className="filter">ACTIVE</div></div><div className="cards-grid">{investigations.map(i => <div className="panel investigation-card" key={i.investigation_id}><span className="eyebrow">{i.investigation_id}</span><h2>{i.investigation_name}</h2><p>{i.description}</p><div className="metric-foot"><span>{i.outbreak_category}</span><span className="tag active">{i.status}</span></div><div className="card-stats"><span><b>{i.total_cases}</b> cases</span><span><b>{i.evidence_records}</b> evidence</span></div></div>)}</div></> }
function EvidenceVault() {
  const [items, setItems] = useState<Evidence[]>([])
  const [files, setFiles] = useState<File[]>([])
  const [status, setStatus] = useState('Loading evidence…')
  const [progress, setProgress] = useState(0)
  const [category, setCategory] = useState('Other')
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState<{ item: Evidence; rows: Record<string, unknown>[] } | null>(null)
  const load = () => fetchEvidenceRecords().then(setItems).then(() => setStatus('')).catch(() => setStatus('Unable to load evidence from the backend.'))
  useEffect(() => { void load() }, [])
  const visible = items.filter(item => filter === 'all' || item.format === filter || item.status === filter)
  const showDetail = async (item: Evidence) => { try { const [rows, detail] = await Promise.all([fetchEvidenceRows(item.evidence_id), fetchEvidenceDetail(item.evidence_id)]); setSelected({ item: detail, rows: rows.records }) } catch { setStatus('Unable to load evidence detail.') } }
  const verify = async (recordId: string, verified: boolean) => {
    try {
      await verifyEvidenceRecord(recordId, verified)
      setSelected(current => current ? { ...current, rows: current.rows.map(row => row.record_id === recordId ? { ...row, verification_status: verified ? 'VERIFIED' : 'REJECTED' } : row) } : current)
    } catch (error) { setStatus(error instanceof Error ? error.message : 'Unable to update verification.') }
  }
  const submit = async () => {
    if (!files.length) return
    setStatus('Uploading and extracting…')
    try { await uploadEvidence(files, category, setProgress); setFiles([]); setProgress(0); setStatus('Upload complete'); load() }
    catch (error) { setStatus(error instanceof Error ? error.message : 'Upload failed') }
  }
  return <><Title eyebrow="EVIDENCE MANAGEMENT / 03" title="Evidence Vault" description="Upload and review synthetic evidence records." action={<label className="primary-btn">Choose files<input type="file" multiple accept=".csv,.json,.pdf,.txt" hidden onChange={event => setFiles(Array.from(event.target.files ?? []))}/></label>}/><div className="panel upload-panel"><p>CSV, JSON, PDF, or TXT · maximum 15 MB per file</p><label>Category <select value={category} onChange={event => setCategory(event.target.value)}>{['Case Report','Laboratory Report','Contact Tracing Record','Location Record','Investigator Observation','Other'].map(value => <option key={value}>{value}</option>)}</select></label>{files.length > 0 && <><span>{files.map(file => file.name).join(', ')}</span><button className="primary-btn" onClick={submit}>Upload {files.length} file{files.length > 1 ? 's' : ''}</button></>}{progress > 0 && <progress value={progress} max="100"/>}{status && <p role="status">{status}</p>}</div><div className="toolbar"><button className={filter === 'all' ? 'filter active' : 'filter'} onClick={() => setFilter('all')}>ALL</button>{['csv','json','pdf','txt','validated','needs_review','failed'].map(value => <button key={value} className={filter === value ? 'filter active' : 'filter'} onClick={() => setFilter(value)}>{value.toUpperCase()}</button>)}</div><Panel title={`${visible.length} backend evidence records`}><div className="table-wrap"><table><thead><tr><th>Evidence ID</th><th>Format</th><th>Source</th><th>Uploaded</th><th>Records</th><th>Status</th></tr></thead><tbody>{visible.map(item => <tr key={item.evidence_id} onClick={() => void showDetail(item)}><td><b>{item.evidence_id}</b></td><td>{item.format ?? item.evidence_type}</td><td>{item.source}</td><td>{item.uploaded_at.slice(0, 10)}</td><td>{item.record_count ?? '—'}</td><td><span className={`tag ${item.status}`}>{item.status}</span></td></tr>)}</tbody></table></div></Panel>{selected && <Panel title={`Evidence detail · ${selected.item.evidence_id}`}><p><b>{selected.item.source}</b> · {selected.item.status} · SHA-256 {selected.item.checksum}</p><div className="record-list">{selected.rows.map(row => <div className="panel" key={String(row.record_id)}><pre>{JSON.stringify(row, null, 2)}</pre>{typeof row.record_id === 'string' && <div className="metric-foot"><span>Verification: {String(row.verification_status ?? 'PENDING')}</span><span><button className="filter" onClick={() => void verify(row.record_id as string, true)}>Verify</button><button className="filter" onClick={() => void verify(row.record_id as string, false)}>Reject</button></span></div>}</div>)}</div><button className="filter" onClick={() => setSelected(null)}>Close detail</button></Panel>}</>
}
function Timeline() {
  const investigationId = 'ORION-001'
  const [items, setItems] = useState<TimelineEvent[]>([])
  const [findings, setFindings] = useState<TimelineFinding[]>([])
  const [stats, setStats] = useState<TimelineStatistics | null>(null)
  const [selected, setSelected] = useState<TimelineEvent | null>(null)
  const [eventType, setEventType] = useState('ALL')
  const [person, setPerson] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [includeUnresolved, setIncludeUnresolved] = useState(true)
  const [status, setStatus] = useState('Loading reconstructed timeline…')
  const load = async () => {
    try {
      const query = new URLSearchParams()
      if (eventType !== 'ALL') query.set('event_type', eventType)
      if (person.trim()) query.set('person_id', person.trim())
      if (dateFrom) query.set('date_from', dateFrom)
      if (dateTo) query.set('date_to', dateTo)
      query.set('include_unresolved', String(includeUnresolved))
      const [timeline, timelineFindings, timelineStats] = await Promise.all([
        fetchTimeline(investigationId, `?${query.toString()}`), fetchTimelineFindings(investigationId), fetchTimelineStatistics(investigationId),
      ])
      setItems(timeline); setFindings(timelineFindings); setStats(timelineStats); setStatus(timeline.length ? '' : 'No reconstructed events yet. Run reconstruction to build the timeline.')
    } catch { setStatus('Unable to load the reconstructed timeline from the backend.') }
  }
  useEffect(() => { void load() }, [eventType, person, dateFrom, dateTo, includeUnresolved])
  const reconstruct = async () => {
    setStatus('Reconstructing timeline…')
    try { await reconstructTimeline(investigationId); await load() } catch (error) { setStatus(error instanceof Error ? error.message : 'Timeline reconstruction failed.') }
  }
  const verify = async (event: TimelineEvent) => {
    try { await verifyTimelineEvent(event.event_id, true); setSelected({ ...event, verification_status: 'VERIFIED' }); await load() }
    catch (error) { setStatus(error instanceof Error ? error.message : 'Unable to verify event.') }
  }
  const eventTypes = stats?.identified_event_types ?? []
  return <><Title eyebrow="RECONSTRUCTION / 04" title="Timeline Reconstruction" description="Deterministic temporal reconstruction with source-level traceability." action={<button className="primary-btn" onClick={() => void reconstruct}>Reconstruct timeline</button>}/><div className="toolbar timeline-controls"><label className="filter">EVENT TYPE <select value={eventType} onChange={event => setEventType(event.target.value)}><option>ALL</option>{eventTypes.map(type => <option key={type}>{type}</option>)}</select></label><label className="filter">PERSON <input value={person} onChange={event => setPerson(event.target.value)} placeholder="P001" /></label><label className="filter">FROM <input type="date" value={dateFrom} onChange={event => setDateFrom(event.target.value)} /></label><label className="filter">TO <input type="date" value={dateTo} onChange={event => setDateTo(event.target.value)} /></label><label className="filter"><input type="checkbox" checked={includeUnresolved} onChange={event => setIncludeUnresolved(event.target.checked)} /> SHOW UNCERTAIN</label><button className="filter" onClick={() => void load}>REFRESH</button></div>{stats && <div className="kpi-grid timeline-kpis"><div className="panel kpi"><span>Total events</span><strong>{stats.total_events}</strong></div><div className="panel kpi"><span>Exact dates</span><strong>{stats.exact_dates}</strong></div><div className="panel kpi"><span>Needs review</span><strong>{stats.events_requiring_review}</strong></div><div className="panel kpi"><span>Findings</span><strong>{stats.temporal_findings}</strong></div></div>}{status && <p className="connection-warning" role="status">{status}</p>}<div className="timeline">{items.map(item => <div className="timeline-item" key={item.event_id}><div className="timeline-date"><b>{item.event_date ? item.event_date.slice(-2) : '??'}</b><span>{item.event_date ? item.event_date.slice(5, 7) : 'DATE'}</span></div><div className="timeline-line"><span className={`timeline-dot ${item.temporal_status === 'NORMAL' ? 'low' : 'medium'}`}/></div><button className="timeline-card timeline-card-button" onClick={() => setSelected(item)}><div className="event-meta"><span className={`tag ${item.temporal_status === 'NORMAL' ? 'low' : 'high'}`}>{item.event_type}</span><span>{item.event_id} · {item.person_id ?? 'Unresolved person'}</span></div><h2>{item.event_description}</h2><p>{temporalLabel(item)}</p><div className="timeline-location">{item.location_name ?? 'Location unresolved'} · {item.verification_status}</div></button></div>)}</div>{findings.length > 0 && <Panel title="Temporal findings"><div className="alert-list">{findings.map(finding => <div className="alert-row" key={finding.finding_id}><AlertTriangle size={16}/><div><b>{finding.finding_type}</b><span>{finding.description}</span></div></div>)}</div></Panel>}{selected && <Panel title={`Event detail · ${selected.event_id}`}><div className="event-detail"><p><b>{selected.event_type}</b> · {selected.person_id ?? 'Unresolved person'} · {selected.temporal_status}</p><p>{selected.event_description}</p><p>Original date: {selected.original_date_value ?? 'Unknown'} · Normalized: {selected.event_date ?? 'Unresolved'}{selected.event_end_date ? ` to ${selected.event_end_date}` : ''} · {selected.date_precision}</p><p>Sources: {selected.sources?.map(source => <button className="text-link" key={source.evidence_id} onClick={() => window.open(evidenceSourceUrl(API_URL, source.evidence_id), '_blank', 'noopener,noreferrer')}>{source.evidence_id} ↗</button>) || 'None'}</p><button className="primary-btn" onClick={() => void verify(selected)}>Verify event</button><button className="filter" onClick={() => setSelected(null)}>Close</button></div></Panel>}</>
}
function Network() {
  const investigationId = 'ORION-001'
  const [graph, setGraph] = useState<GraphPayload | null>(null)
  const [selected, setSelected] = useState<GraphRelationship | null>(null)
  const [type, setType] = useState('ALL')
  const [status, setStatus] = useState('Loading graph…')
  const [includePossible, setIncludePossible] = useState(true)
  const load = async () => {
    try {
      const query = new URLSearchParams()
      if (type !== 'ALL') query.set('relationship_type', type)
      query.set('include_possible', String(includePossible))
      const value = await fetchGraph(investigationId, `?${query.toString()}`)
      setGraph(value); setStatus(value.nodes.length ? '' : 'No graph projection exists yet. Rebuild from evidence and timeline data.')
    } catch { setStatus('Unable to load the case network from the backend.') }
  }
  useEffect(() => { void load() }, [type, includePossible])
  const rebuild = async () => {
    setStatus('Rebuilding evidence-backed graph…')
    try { await rebuildGraph(investigationId); await load() } catch (error) { setStatus(error instanceof Error ? error.message : 'Graph rebuild failed.') }
  }
  const review = async (value: 'VERIFIED' | 'REJECTED') => {
    if (!selected) return
    try { const updated = await reviewGraphRelationship(selected.id, value, `Reviewed in Case Network.`); setSelected(updated); await load() }
    catch (error) { setStatus(error instanceof Error ? error.message : 'Unable to review relationship.') }
  }
  const nodes: Node[] = (graph?.nodes ?? []).map((node, index) => ({ id: node.id, position: { x: (index % 4) * 230, y: Math.floor(index / 4) * 120 }, data: { label: `${node.display_label} · ${node.node_type}` }, className: `graph-node ${node.node_type.toLowerCase()}` }))
  const edges: Edge[] = (graph?.relationships ?? []).map(edge => ({ id: edge.id, source: edge.source, target: edge.target, label: edge.relationship_type, animated: edge.classification === 'POSSIBLE', className: `graph-edge ${edge.classification.toLowerCase()}`, data: edge }))
  const types = Array.from(new Set((graph?.relationships ?? []).map(item => item.relationship_type))).sort()
  return <><Title eyebrow="RELATIONSHIP ANALYSIS / 05" title="Case Network" description="Evidence-backed connections for investigative exploration. Connections do not establish infection or transmission." action={<button className="primary-btn" onClick={() => void rebuild}>Rebuild graph</button>}/><div className="toolbar timeline-controls"><label className="filter">RELATIONSHIP <select value={type} onChange={event => setType(event.target.value)}><option>ALL</option>{types.map(value => <option key={value}>{value}</option>)}</select></label><label className="filter"><input type="checkbox" checked={includePossible} onChange={event => setIncludePossible(event.target.checked)} /> INCLUDE POSSIBLE</label><button className="filter" onClick={() => { setType('ALL'); setIncludePossible(true) }}>CLEAR FILTERS</button></div>{status && <p className="connection-warning" role="status">{status}</p>}<div className="network-layout"><div className="network-panel panel"><div className="graph-legend"><span>PERSON</span><span>LOCATION</span><span>EVENT</span><span>EXPLICIT / INFERRED / POSSIBLE</span></div><ReactFlow nodes={nodes} edges={edges} fitView onEdgeClick={(_, edge) => setSelected(edge.data as GraphRelationship)}><Background color="#294057"/><Controls/></ReactFlow></div>{selected && <Panel title={`Relationship · ${selected.relationship_type}`}><div className="event-detail"><p><b>{selected.classification}</b> · {selected.verification_status}</p><p>{selected.explanation}</p><p>{selected.start_date ?? 'Unknown date'}{selected.end_date ? ` to ${selected.end_date}` : ''} · confidence {selected.confidence ?? 'not assigned'}</p><p>Derivation: {selected.derivation_method}</p><p>Sources: {selected.sources.map(source => <span key={`${source.evidence_id}-${source.reconstructed_event_id}`} className="source-chip">{source.evidence_id ?? 'event'} {source.reconstructed_event_id ?? ''}</span>)}</p><button className="primary-btn" onClick={() => void review('VERIFIED')}>Verify</button><button className="filter" onClick={() => void review('REJECTED')}>Reject</button></div></Panel>}</div></>
}
function Contradictions() { return <><Title eyebrow="QUALITY CONTROL / 06" title="Contradiction Center" description="Conflicts requiring analyst review before conclusions are updated."/><div className="cards-grid">{contradictions.map(c => <div className="panel contradiction" key={c.id}><div className="metric-foot"><span className={`tag ${c.severity}`}>{c.severity}</span><span>{c.status}</span></div><h2>{c.title}</h2><p>{c.description}</p><small>Evidence references: {c.references.join(', ')}</small></div>)}</div></> }
function Hypotheses() { return <><Title eyebrow="REASONING / 07" title="Hypothesis Lab" description="Competing sample hypotheses. Scores are illustrative assessments, not real probabilities."/><div className="cards-grid">{hypotheses.map(h => <div className="panel hypothesis" key={h.id}><span className="eyebrow">{h.id}</span><h2>{h.title}</h2><div className="score">{h.score}<small>/ 100 assessment</small></div><div className="metric-foot"><span>Supporting: {h.supporting}</span><span>Contradicting: {h.contradicting}</span></div><p>{h.summary}</p></div>)}</div></> }
function SimplePage({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children: React.ReactNode }) { return <><Title eyebrow={eyebrow} title={title} description={description}/><Panel title="Project Orion sample workspace">{children}</Panel></> }

export default function App() {
  const [connected, setConnected] = useState(false); const [investigations, setInvestigations] = useState<Investigation[]>([]); const [summary, setSummary] = useState<Record<string, number>>({})
  useEffect(() => { Promise.all([fetchHealth(), fetchInvestigations(), fetchDashboard()]).then(([, inv, dash]) => { setConnected(true); setInvestigations(inv); setSummary(dash) }).catch(() => { setConnected(false); setInvestigations([]) }) }, [])
  const shown = useMemo(() => investigations.length ? investigations : [{ investigation_id: 'ORION-001', investigation_name: 'Project Orion', description: 'Fictional respiratory outbreak investigation.', outbreak_category: 'Respiratory', status: 'Active', total_cases: 124, evidence_records: 386 }], [investigations])
  return <Shell connected={connected}><Routes><Route path="/" element={<Overview investigations={shown} summary={summary}/>}/><Route path="/investigations" element={<Investigations investigations={shown}/>}/><Route path="/evidence" element={<EvidenceVault/>}/><Route path="/timeline" element={<Timeline/>}/><Route path="/network" element={<Network/>}/><Route path="/contradictions" element={<Contradictions/>}/><Route path="/hypotheses" element={<Hypotheses/>}/><Route path="/rewind" element={<SimplePage eyebrow="VERSION HISTORY / 08" title="Investigation Rewind" description="Compare clearly labelled sample versions as new evidence changes an assessment."><div className="version-list">{['v1.0 · Initial signal','v1.1 · Laboratory evidence added','v1.2 · Contact record contradiction flagged'].map(v => <div className="alert-row" key={v}><BookOpen size={16}/><b>{v}</b><span>Sample version</span></div>)}</div></SimplePage>}/><Route path="/reports" element={<SimplePage eyebrow="OUTPUTS / 09" title="Reports" description="Preview an investigation report and evidence summary before export."><p>Report preview: Project Orion currently contains {evidence.length} linked evidence records and {hypotheses.length} competing hypotheses.</p><button className="primary-btn">Export preview</button></SimplePage>}/><Route path="/settings" element={<SimplePage eyebrow="CONFIGURATION / 10" title="Settings" description="Profile, interface, and application preferences."><div className="settings-list"><p><ShieldCheck size={16}/> Backend connection: {connected ? 'Connected' : 'Unavailable (demo mode)'}</p><p><Settings size={16}/> Interface theme: Dark investigative console</p><p><FileText size={16}/> Data policy: synthetic demonstration data only</p></div></SimplePage>}/><Route path="*" element={<Navigate to="/" replace/>}/></Routes></Shell>
}
