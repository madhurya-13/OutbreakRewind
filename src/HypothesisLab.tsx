import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  AlertTriangle, Beaker, CheckCircle2, Clock, FileSearch, GitCompare, History,
  Link2, Loader2, Plus, RefreshCw, ShieldAlert, Trash2, X,
} from 'lucide-react'
import {
  archiveHypothesis, createHypothesis, evaluateHypothesis, fetchHypotheses,
  fetchHypothesisSummary, fetchInvestigations, updateHypothesis,
  type Hypothesis, type HypothesisSummary, type Investigation,
} from './api'
import {
  ASSESSMENT_OPTIONS, CATEGORY_OPTIONS, STATUS_HELP, STATUS_OPTIONS,
  assessmentTone, emptyHypothesisForm, filterHypotheses, formFromHypothesis,
  formToPayload, formatDateTime, humanize, readInvestigation, statusTone,
  validateHypothesisForm, writeInvestigation, type HypothesisForm,
} from './hypothesisUtils'

export const CHART_COLORS = ['#ff6a58', '#7bc9bd', '#e9bd6a', '#b98f7a', '#d8d1bf']

export function useInvestigations() {
  const [items, setItems] = useState<Investigation[]>([])
  useEffect(() => { fetchInvestigations().then(setItems).catch(() => setItems([])) }, [])
  return items.length ? items : [
    { investigation_id: 'ORION-001', investigation_name: 'Project Orion', description: 'Synthetic respiratory outbreak investigation.', outbreak_category: 'Respiratory', status: 'Active', total_cases: 124, evidence_records: 386 },
  ]
}

export function LabTitle({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return <div className="page-title"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>
}

export function Panel({ title, action, children, className = '' }: { title: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><div className="panel-head"><h2>{title}</h2>{action}</div>{children}</section>
}

export function Badge({ children, tone = '' }: { children: ReactNode; tone?: string }) {
  return <span className={`h-badge ${tone}`}>{children}</span>
}

export function Loading({ label }: { label: string }) {
  return <div className="h-loading" role="status"><Loader2 size={18} className="spin"/>{label}</div>
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="h-error" role="alert"><AlertTriangle size={16}/><span>{message}</span>{onRetry && <button className="ghost-btn" onClick={onRetry}><RefreshCw size={14}/>Retry</button>}</div>
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="h-empty"><Beaker size={28}/><b>{title}</b><p>{description}</p>{action}</div>
}

export function Modal({ title, children, onClose, wide = false }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  return <div className="h-modal-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <div className={`h-modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
      <div className="h-modal-head"><h2>{title}</h2><button className="icon-btn" aria-label="Close" onClick={onClose}><X size={18}/></button></div>
      <div className="h-modal-body">{children}</div>
    </div>
  </div>
}

export function ConfirmDialog({ title, message, confirmLabel, onConfirm, onCancel, busy = false }: {
  title: string; message: string; confirmLabel: string; onConfirm: () => void; onCancel: () => void; busy?: boolean
}) {
  return <Modal title={title} onClose={onCancel}>
    <p className="h-muted">{message}</p>
    <div className="h-modal-actions"><button className="ghost-btn" onClick={onCancel}>Cancel</button><button className="danger-btn" disabled={busy} onClick={onConfirm}>{busy ? 'Working…' : confirmLabel}</button></div>
  </Modal>
}

export function InvestigationSelect({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const investigations = useInvestigations()
  return <label className="h-select-label">INVESTIGATION
    <select value={value} onChange={event => onChange(event.target.value)}>
      {investigations.map(item => <option key={item.investigation_id} value={item.investigation_id}>{item.investigation_name} · {item.investigation_id}</option>)}
    </select>
  </label>
}

export function hypothesisLink(hypothesis: Hypothesis, investigationId: string, tab = 'overview') {
  return `/hypotheses/${hypothesis.hypothesis_id}?investigation=${encodeURIComponent(investigationId)}&tab=${tab}`
}

export function HypothesisCard({ hypothesis, investigationId, selected = false, onToggle, onEvaluate, onArchive, busy = false }: {
  hypothesis: Hypothesis
  investigationId: string
  selected?: boolean
  onToggle?: () => void
  onEvaluate?: () => void
  onArchive?: () => void
  busy?: boolean
}) {
  const assessment = hypothesis.assessment ?? hypothesis.latest_assessment ?? null
  return <article className={`panel hypothesis-card ${selected ? 'selected' : ''}`}>
    <div className="h-card-top">
      <div>
        <div className="eyebrow">{humanize(hypothesis.category)}</div>
        <h2><Link to={hypothesisLink(hypothesis, investigationId)}>{hypothesis.title}</Link></h2>
      </div>
      {onToggle && <label className="h-check"><input type="checkbox" checked={selected} onChange={onToggle}/>Compare</label>}
    </div>
    <p>{hypothesis.description}</p>
    <div className="h-badge-row">
      <Badge tone={statusTone(hypothesis.status)}>{humanize(hypothesis.status)}</Badge>
      <Badge tone={assessmentTone(hypothesis.current_assessment)}>{humanize(hypothesis.current_assessment)}</Badge>
      <Badge tone="neutral-tone">v{hypothesis.current_version}</Badge>
    </div>
    <div className="h-card-metrics">
      <span><b>{assessment?.supporting_count ?? 0}</b> supporting</span>
      <span><b>{assessment?.contradicting_count ?? 0}</b> contradicting</span>
      <span><b>{assessment?.unresolved_contradiction_count ?? 0}</b> unresolved</span>
      <span><b>{assessment?.pending_review_count ?? 0}</b> pending</span>
    </div>
    <div className="h-card-foot">
      <span><Clock size={13}/>{formatDateTime(hypothesis.updated_at)}</span>
      <div className="h-card-actions">
        <Link className="ghost-btn" to={hypothesisLink(hypothesis, investigationId)}><FileSearch size={14}/>Open</Link>
        {onEvaluate && <button className="ghost-btn" disabled={busy} onClick={onEvaluate}><RefreshCw size={14}/>Evaluate</button>}
        <Link className="ghost-btn" to={hypothesisLink(hypothesis, investigationId, 'evidence')}><Link2 size={14}/>Evidence</Link>
        <Link className="ghost-btn" to={hypothesisLink(hypothesis, investigationId, 'history')}><History size={14}/>History</Link>
        {onArchive && hypothesis.status !== 'ARCHIVED' && <button className="ghost-btn danger-text" disabled={busy} onClick={onArchive} aria-label={`Archive ${hypothesis.title}`}><Trash2 size={14}/></button>}
      </div>
    </div>
  </article>
}

export function HypothesisFormModal({ investigationId, hypothesis, onClose, onSaved }: {
  investigationId: string; hypothesis?: Hypothesis | null; onClose: () => void; onSaved: (item: Hypothesis) => void
}) {
  const [form, setForm] = useState<HypothesisForm>(hypothesis ? formFromHypothesis(hypothesis) : emptyHypothesisForm())
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [reason, setReason] = useState('')
  const editing = Boolean(hypothesis)
  const update = (key: keyof HypothesisForm, value: string) => setForm(current => ({ ...current, [key]: value }))

  const save = async () => {
    const nextErrors = validateHypothesisForm(form)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    setSaving(true); setError('')
    try {
      const payload = formToPayload(form)
      const saved = hypothesis
        ? await updateHypothesis(hypothesis.hypothesis_id, { ...payload, reason, updated_by: 'investigator' })
        : await createHypothesis(investigationId, { ...payload, created_by: 'investigator' })
      onSaved(saved)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to save the hypothesis.')
    } finally { setSaving(false) }
  }

  return <Modal title={editing ? 'Edit hypothesis' : 'Create a competing hypothesis'} onClose={onClose} wide>
    {error && <ErrorBanner message={error}/>}
    <div className="h-form-grid">
      <label className="span-2">Hypothesis title *
        <input value={form.title} onChange={event => update('title', event.target.value)} placeholder="Shared exposure at the North Quay depot" />
        {errors.title && <small className="field-error">{errors.title}</small>}
      </label>
      <label>Category *
        <select value={form.category} onChange={event => update('category', event.target.value)}>
          {CATEGORY_OPTIONS.map(value => <option key={value} value={value}>{humanize(value)}</option>)}
          <option value="CUSTOM">Custom category…</option>
        </select>
        {errors.category && <small className="field-error">{errors.category}</small>}
      </label>
      {form.category === 'CUSTOM' && <label>Custom category identifier
        <input value={form.customCategory} onChange={event => update('customCategory', event.target.value.toUpperCase())} placeholder="LOCAL_WATER_SOURCE" />
      </label>}
      <label className="span-2">Short description *
        <textarea rows={3} value={form.description} onChange={event => update('description', event.target.value)} placeholder="What does this explanation propose, in two or three sentences?" />
        {errors.description && <small className="field-error">{errors.description}</small>}
      </label>
      <label className="span-2">Detailed explanation
        <textarea rows={4} value={form.detailed_explanation} onChange={event => update('detailed_explanation', event.target.value)} placeholder="Proposed sequence of events, mechanism, and how the explanation accounts for the cases." />
      </label>
      <label>Initial assumptions <small>one per line</small>
        <textarea rows={4} value={form.assumptions} onChange={event => update('assumptions', event.target.value)} placeholder="The reported visit date is approximately accurate." />
      </label>
      <label>Expected observations / predictions <small>one per line</small>
        <textarea rows={4} value={form.predictions} onChange={event => update('predictions', event.target.value)} placeholder="Independent cases should report the same location." />
      </label>
      <label>Known limitations <small>one per line</small>
        <textarea rows={4} value={form.limitations} onChange={event => update('limitations', event.target.value)} placeholder="Location records are interview-based." />
      </label>
      <label>Open questions <small>one per line</small>
        <textarea rows={4} value={form.open_questions} onChange={event => update('open_questions', event.target.value)} placeholder="Which verified records place each case at the location?" />
      </label>
      {editing ? <label className="span-2">Reason for modification
        <input value={reason} onChange={event => setReason(event.target.value)} placeholder="Why is this hypothesis changing?" />
      </label> : <label className="span-2">Initial investigator note
        <textarea rows={3} value={form.initial_notes} onChange={event => update('initial_notes', event.target.value)} placeholder="Optional. State clearly that this is a competing explanation, not a conclusion." />
      </label>}
    </div>
    <div className="h-modal-actions"><button className="ghost-btn" onClick={onClose}>Cancel</button><button className="primary-btn" disabled={saving} onClick={() => void save()}>{saving ? 'Saving…' : editing ? 'Save changes' : 'Create hypothesis'}</button></div>
  </Modal>
}

export function HypothesisLab() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [investigationId, setInvestigationId] = useState(searchParams.get('investigation') || readInvestigation())
  const [items, setItems] = useState<Hypothesis[]>([])
  const [summary, setSummary] = useState<HypothesisSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('ALL')
  const [category, setCategory] = useState('ALL')
  const [assessment, setAssessment] = useState('ALL')
  const [selected, setSelected] = useState<Set<string>>(new Set<string>())
  const [formOpen, setFormOpen] = useState(false)
  const [archiveTarget, setArchiveTarget] = useState<Hypothesis | null>(null)
  const [busyId, setBusyId] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [list, stats] = await Promise.all([
        fetchHypotheses(investigationId, '?page_size=100&include_archived=true'),
        fetchHypothesisSummary(investigationId),
      ])
      setItems(list.items)
      setSummary(stats)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load hypothesis intelligence.')
    } finally { setLoading(false) }
  }, [investigationId])

  useEffect(() => { void load() }, [load])
  useEffect(() => { writeInvestigation(investigationId) }, [investigationId])

  const visible = useMemo(() => filterHypotheses(items, { search, status, category, assessment }), [items, search, status, category, assessment])
  const active = items.filter(item => item.status !== 'ARCHIVED')
  const stats: HypothesisSummary = summary ?? {
    investigation_id: investigationId, total_hypotheses: items.length, active_hypotheses: active.length,
    under_investigation: active.filter(item => item.status === 'UNDER_INVESTIGATION').length,
    with_supporting_evidence: active.filter(item => ['SUBSTANTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE', 'PARTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE'].includes(item.current_assessment)).length,
    significant_contradictions: active.filter(item => item.current_assessment === 'SIGNIFICANT_CONTRADICTIONS').length,
    mixed_evidence: 0, insufficient_information: 0, not_yet_evaluated: 0,
    archived: items.filter(item => item.status === 'ARCHIVED').length,
    requiring_review: active.filter(item => (item.assessment?.pending_review_count ?? 0) > 0).length,
    pending_impact_records: 0, pending_evidence_links: 0,
    recently_updated: active.length, recent_hypotheses: [],
    categories: [], statuses: [], assessment_labels: [],
  }

  const toggle = (id: string) => setSelected(current => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })

  const evaluate = async (hypothesis: Hypothesis) => {
    setBusyId(hypothesis.hypothesis_id); setError(''); setNotice('')
    try {
      const result = await evaluateHypothesis(hypothesis.hypothesis_id)
      setNotice(`${hypothesis.title}: ${humanize(result.assessment_label)}`)
      await load()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Evaluation failed.') }
    finally { setBusyId('') }
  }

  const confirmArchive = async () => {
    if (!archiveTarget) return
    setBusyId(archiveTarget.hypothesis_id); setError('')
    try {
      await archiveHypothesis(archiveTarget.hypothesis_id, 'Archived from the Hypothesis Lab.')
      setArchiveTarget(null); setNotice('Hypothesis archived. Its history and evidence links were retained.'); await load()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to archive the hypothesis.') }
    finally { setBusyId('') }
  }

  const openComparison = () => {
    if (selected.size < 2) { setError('Select at least two hypotheses to compare.'); return }
    navigate(`/hypotheses/compare?investigation=${encodeURIComponent(investigationId)}&ids=${Array.from(selected).join(',')}`)
  }

  return <>
    <LabTitle eyebrow="REASONING / 07" title="Hypothesis Lab" description="Create competing explanations, link traceable evidence, and evaluate qualitative support without the system deciding the answer." action={<div className="h-title-actions"><InvestigationSelect value={investigationId} onChange={value => { setInvestigationId(value); setSelected(new Set<string>()) }}/><button className="primary-btn" onClick={() => setFormOpen(true)}><Plus size={16}/>New hypothesis</button></div>}/>
    {error && <ErrorBanner message={error} onRetry={() => void load()}/>}
    {notice && <div className="h-notice" role="status"><CheckCircle2 size={15}/>{notice}</div>}
    <div className="h-kpi-grid">
      <div className="panel h-kpi"><span>Total hypotheses</span><strong>{stats.total_hypotheses}</strong><small>{stats.active_hypotheses} active</small></div>
      <div className="panel h-kpi"><span>Under investigation</span><strong>{stats.under_investigation}</strong><small>Investigator-controlled status</small></div>
      <div className="panel h-kpi"><span>With supporting evidence</span><strong>{stats.with_supporting_evidence}</strong><small>Qualitative assessment only</small></div>
      <div className="panel h-kpi"><span>Significant contradictions</span><strong>{stats.significant_contradictions}</strong><small>Requires investigator review</small></div>
      <div className="panel h-kpi"><span>Requiring review</span><strong>{stats.requiring_review}</strong><small>{stats.pending_impact_records} impact · {stats.pending_evidence_links} links</small></div>
      <div className="panel h-kpi"><span>Recently updated</span><strong>{stats.recently_updated}</strong><small>Last 7 days</small></div>
    </div>
    <div className="h-toolbar">
      <div className="search wide"><FileSearch size={16}/><input aria-label="Search hypotheses" placeholder="Search title, description, assumptions…" value={search} onChange={event => setSearch(event.target.value)}/></div>
      <select value={status} onChange={event => setStatus(event.target.value)} aria-label="Filter status"><option value="ALL">All statuses</option>{STATUS_OPTIONS.map(value => <option key={value}>{value}</option>)}</select>
      <select value={category} onChange={event => setCategory(event.target.value)} aria-label="Filter category"><option value="ALL">All categories</option>{CATEGORY_OPTIONS.map(value => <option key={value}>{value}</option>)}</select>
      <select value={assessment} onChange={event => setAssessment(event.target.value)} aria-label="Filter assessment"><option value="ALL">All assessments</option>{ASSESSMENT_OPTIONS.map(value => <option key={value}>{value}</option>)}</select>
      <button className="ghost-btn" onClick={openComparison}><GitCompare size={15}/>Compare {selected.size ? `(${selected.size})` : ''}</button>
      <button className="ghost-btn" onClick={() => void load()}><RefreshCw size={15}/>Refresh</button>
    </div>
    {loading ? <Loading label="Loading hypothesis intelligence…"/> : <>
      <div className="h-lab-grid">
        <div>
          {visible.length === 0 ? <EmptyState title={items.length ? 'No hypotheses match the filters' : 'No hypotheses yet'} description={items.length ? 'Clear the filters to see the full set of competing explanations.' : 'Create the first competing explanation and link existing evidence records to begin reasoning.'} action={!items.length ? <button className="primary-btn" onClick={() => setFormOpen(true)}><Plus size={16}/>Create hypothesis</button> : undefined}/> : <div className="h-card-list">
            {visible.map(item => <HypothesisCard key={item.hypothesis_id} hypothesis={item} investigationId={investigationId} selected={selected.has(item.hypothesis_id)} onToggle={() => toggle(item.hypothesis_id)} onEvaluate={() => void evaluate(item)} onArchive={() => setArchiveTarget(item)} busy={busyId === item.hypothesis_id}/>) }
          </div>}
        </div>
        <div className="h-side-stack">
          <Panel title="Recently updated">
            {stats.recent_hypotheses?.length ? <div className="h-recent-list">{stats.recent_hypotheses.map(item => <Link key={item.hypothesis_id} to={`/hypotheses/${item.hypothesis_id}?investigation=${investigationId}`} className="h-recent-row"><b>{item.title}</b><span>{humanize(item.assessment)} · {formatDateTime(item.updated_at)}</span></Link>)}</div> : <p className="h-muted">No active hypothesis has been updated recently.</p>}
          </Panel>
          <Panel title="How assessment works">
            <p className="h-muted small">Labels are derived from reviewed and verified evidence links using documented rules. Counts are not probabilities, and a high count is not proof.</p>
            <ul className="h-rule-list"><li>Supporting and contradicting links are classified by an investigator.</li><li>Strength and reliability are assessed independently.</li><li>Pending links are provisional.</li><li>The system never selects a winning hypothesis.</li></ul>
            <div className="h-caution"><ShieldAlert size={15}/>Comparison is exploratory and does not establish causation.</div>
          </Panel>
          <Panel title="Status definitions"><ul className="h-rule-list">{STATUS_OPTIONS.map(value => <li key={value}><b>{humanize(value)}</b><span>{STATUS_HELP[value]}</span></li>)}</ul></Panel>
        </div>
      </div>
    </>}
    {formOpen && <HypothesisFormModal investigationId={investigationId} onClose={() => setFormOpen(false)} onSaved={saved => { setFormOpen(false); setNotice('Hypothesis created.'); void load(); navigate(hypothesisLink(saved, investigationId)) }}/>}
    {archiveTarget && <ConfirmDialog title="Archive hypothesis" message={`Archive “${archiveTarget.title}”? The hypothesis and all evidence-link, version, assessment, and review history will be retained. It will be removed from active comparison.`} confirmLabel="Archive hypothesis" busy={busyId === archiveTarget.hypothesis_id} onCancel={() => setArchiveTarget(null)} onConfirm={() => void confirmArchive()}/>}
  </>
}
