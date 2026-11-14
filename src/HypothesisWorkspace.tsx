import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Check, ChevronRight, GitCompare, Link2, Plus, RefreshCw, ShieldAlert, Trash2 } from 'lucide-react'
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  addHypothesisNote, archiveHypothesis, compareHypotheses, evaluateHypothesis,
  fetchHypotheses, fetchHypothesis, fetchHypothesisAssessments, fetchHypothesisHistory,
  fetchHypothesisImpact, fetchHypothesisNotes, fetchHypothesisSources, fetchHypothesisVersion,
  linkHypothesisEvidence, reviewHypothesisImpact, updateHypothesisEvidence,
  updateHypothesisStatus, withdrawHypothesisEvidence,
  type Hypothesis, type HypothesisAssessment, type HypothesisComparison,
  type HypothesisHistory, type HypothesisImpact, type HypothesisLink, type HypothesisNote,
  type HypothesisSource, type HypothesisVersion,
} from './api'
import {
  ASSESSMENT_OPTIONS, CATEGORY_OPTIONS, CLASSIFICATION_OPTIONS, RELIABILITY_OPTIONS,
  REVIEW_OPTIONS, SOURCE_TYPE_OPTIONS, STATUS_HELP, STATUS_OPTIONS, STRENGTH_OPTIONS,
  assessmentTone, classificationTone, comparisonChartData, comparisonStrengthData,
  distributionData, evidenceChartData, formatDate, formatDateTime, groupLinks, humanize,
  impactTone, missingSeverityLabel, readInvestigation, reliabilityTone, reviewTone,
  sourceTypeLabel, statusTone, strengthTone,
} from './hypothesisUtils'
import {
  Badge, CHART_COLORS, ConfirmDialog, EmptyState, ErrorBanner, HypothesisFormModal,
  InvestigationSelect, LabTitle, Loading, Modal, Panel, hypothesisLink,
} from './HypothesisLab'

/* ------------------------------------------------------------------------- */
/* Evidence linking                                                          */
/* ------------------------------------------------------------------------- */

export function EvidenceLinkModal({ investigationId, hypothesis, onClose, onLinked }: {
  investigationId: string; hypothesis: Hypothesis; onClose: () => void; onLinked: () => void
}) {
  const [sourceType, setSourceType] = useState('')
  const [query, setQuery] = useState('')
  const [sources, setSources] = useState<HypothesisSource[]>([])
  const [selected, setSelected] = useState<HypothesisSource | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [manual, setManual] = useState(false)
  const [manualNote, setManualNote] = useState('')
  const [classification, setClassification] = useState('SUPPORTING')
  const [explanation, setExplanation] = useState('')
  const [strength, setStrength] = useState('NOT_ASSESSED')
  const [reliability, setReliability] = useState('NOT_ASSESSED')
  const [strengthReason, setStrengthReason] = useState('')
  const [reliabilityReason, setReliabilityReason] = useState('')
  const [observations, setObservations] = useState('')
  const [notes, setNotes] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const params = new URLSearchParams({ limit: '300', hypothesis_id: hypothesis.hypothesis_id })
      if (sourceType) params.set('source_type', sourceType)
      if (query.trim()) params.set('q', query.trim())
      const result = await fetchHypothesisSources(investigationId, `?${params.toString()}`)
      setSources(result.items)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load investigation sources.')
    } finally { setLoading(false) }
  }, [hypothesis.hypothesis_id, investigationId, query, sourceType])

  useEffect(() => { void load() }, [load])

  const choose = (source: HypothesisSource) => {
    setSelected(source)
    setManual(false)
    setStrength(source.suggested_strength)
    setReliability(source.suggested_reliability)
    setStrengthReason(source.suggested_strength_reason)
    setReliabilityReason(source.suggested_reliability_reason)
    if (!explanation) setExplanation(`The ${sourceTypeLabel(source.source_type).toLowerCase()} is relevant because it bears directly on the explanation under review.`)
  }

  const submit = async () => {
    setSaving(true); setError('')
    try {
      const sourceId = manual ? manualNote.trim() : selected?.source_id
      if (!sourceId) throw new Error('Select a source record or enter a manual investigator observation.')
      if (explanation.trim().length < 5) throw new Error('An explanation is required for the classification.')
      await linkHypothesisEvidence(hypothesis.hypothesis_id, {
        source_type: manual ? 'INVESTIGATOR_NOTE' : selected?.source_type,
        source_id: sourceId,
        classification,
        explanation: explanation.trim(),
        relevant_observations: observations.trim(),
        evidence_strength: strength,
        source_reliability: reliability,
        strength_reason: strengthReason.trim(),
        reliability_reason: reliabilityReason.trim(),
        investigator_notes: notes.trim(),
        linked_by: 'investigator',
      })
      onLinked()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to link the source.')
    } finally { setSaving(false) }
  }

  return <Modal title={`Link evidence · ${hypothesis.title}`} onClose={onClose} wide>
    {error && <ErrorBanner message={error}/>}
    <div className="h-link-layout">
      <div className="h-source-pane">
        <div className="h-source-toolbar">
          <label>SOURCE TYPE
            <select value={sourceType} onChange={event => setSourceType(event.target.value)}>
              <option value="">All source types</option>
              {SOURCE_TYPE_OPTIONS.filter(value => value !== 'INVESTIGATOR_NOTE').map(value => <option key={value} value={value}>{humanize(value)}</option>)}
            </select>
          </label>
          <label>SEARCH
            <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Person, location, title, ID…" />
          </label>
          <button className="ghost-btn" onClick={() => setManual(current => !current)}>{manual ? 'Use existing record' : 'Add manual observation'}</button>
        </div>
        {manual ? <div className="h-manual">
          <label>Investigator observation *
            <textarea rows={5} value={manualNote} onChange={event => setManualNote(event.target.value)} placeholder="Describe the direct observation. This is a working note, not a documentary source." />
          </label>
        </div> : loading ? <Loading label="Loading investigation sources…"/> : sources.length === 0 ? <EmptyState title="No matching sources" description="Adjust the source type or search. Sources are existing Milestone 2–5 records; the hypothesis engine does not create duplicates."/> : <div className="h-source-list">
          {sources.map(source => <button key={`${source.source_type}-${source.source_id}`} className={`h-source-item ${selected?.source_id === source.source_id && selected?.source_type === source.source_type ? 'selected' : ''} ${source.already_linked ? 'disabled' : ''}`} onClick={() => choose(source)} disabled={source.already_linked}>
            <span className="eyebrow">{humanize(source.source_type)}</span>
            <b>{source.title}</b>
            <small>{source.subtitle} · {source.source_id}</small>
            <span className="h-source-meta">{formatDate(source.date)} · {humanize(source.verification_status)} {source.already_linked ? '· Already linked' : ''}</span>
          </button>)}
        </div>}
      </div>
      <div className="h-link-form">
        <h3>Evidence assessment</h3>
        {selected && !manual && <div className="h-selected-source">
          <b>{selected.title}</b>
          <span>{selected.original_reference}</span>
          <small>{formatDate(selected.date)} · {humanize(selected.verification_status)}</small>
          <details><summary>Relevant source details</summary><pre>{JSON.stringify(selected.details, null, 2)}</pre></details>
        </div>}
        <label>Relationship to hypothesis *
          <select value={classification} onChange={event => setClassification(event.target.value)}>{CLASSIFICATION_OPTIONS.map(value => <option key={value} value={value}>{humanize(value)}</option>)}</select>
        </label>
        <label>Why is this source relevant? *
          <textarea rows={3} value={explanation} onChange={event => setExplanation(event.target.value)} placeholder="Explain the reasoning. This explanation is stored and shown in the assessment." />
        </label>
        <label>Relevant fields or observations
          <input value={observations} onChange={event => setObservations(event.target.value)} placeholder="Person, date, row, location, or field-level detail" />
        </label>
        <div className="h-two-col">
          <label>Evidence strength
            <select value={strength} onChange={event => setStrength(event.target.value)}>{STRENGTH_OPTIONS.map(value => <option key={value} value={value}>{humanize(value)}</option>)}</select>
          </label>
          <label>Source reliability
            <select value={reliability} onChange={event => setReliability(event.target.value)}>{RELIABILITY_OPTIONS.map(value => <option key={value} value={value}>{humanize(value)}</option>)}</select>
          </label>
        </div>
        <label>Why this strength?
          <textarea rows={2} value={strengthReason} onChange={event => setStrengthReason(event.target.value)} />
        </label>
        <label>Why this reliability?
          <textarea rows={2} value={reliabilityReason} onChange={event => setReliabilityReason(event.target.value)} />
        </label>
        <label>Investigator notes
          <textarea rows={2} value={notes} onChange={event => setNotes(event.target.value)} />
        </label>
        <div className="h-modal-actions"><button className="ghost-btn" onClick={onClose}>Cancel</button><button className="primary-btn" disabled={saving} onClick={() => void submit()}>{saving ? 'Linking…' : 'Link source'}</button></div>
      </div>
    </div>
  </Modal>
}

export function LinkEditModal({ link, onClose, onSaved }: { link: HypothesisLink; onClose: () => void; onSaved: () => void }) {
  const [classification, setClassification] = useState(link.classification)
  const [explanation, setExplanation] = useState(link.explanation)
  const [strength, setStrength] = useState(link.evidence_strength)
  const [reliability, setReliability] = useState(link.source_reliability)
  const [strengthReason, setStrengthReason] = useState(link.strength_reason ?? '')
  const [reliabilityReason, setReliabilityReason] = useState(link.reliability_reason ?? '')
  const [reviewStatus, setReviewStatus] = useState(link.review_status)
  const [notes, setNotes] = useState(link.investigator_notes ?? '')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true); setError('')
    try {
      await updateHypothesisEvidence(link.link_id, {
        classification, explanation, evidence_strength: strength, source_reliability: reliability,
        strength_reason: strengthReason, reliability_reason: reliabilityReason,
        review_status: reviewStatus, investigator_notes: notes, updated_by: 'investigator',
      })
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to update the evidence link.')
    } finally { setSaving(false) }
  }

  return <Modal title={`Edit link · ${link.source_title}`} onClose={onClose}>
    {error && <ErrorBanner message={error}/>}
    <div className="h-form-grid">
      <label>Classification<select value={classification} onChange={event => setClassification(event.target.value)}>{CLASSIFICATION_OPTIONS.map(value => <option key={value}>{value}</option>)}</select></label>
      <label>Review status<select value={reviewStatus} onChange={event => setReviewStatus(event.target.value)}>{REVIEW_OPTIONS.map(value => <option key={value}>{value}</option>)}</select></label>
      <label className="span-2">Explanation<textarea rows={3} value={explanation} onChange={event => setExplanation(event.target.value)} /></label>
      <label>Evidence strength<select value={strength} onChange={event => setStrength(event.target.value)}>{STRENGTH_OPTIONS.map(value => <option key={value}>{value}</option>)}</select></label>
      <label>Source reliability<select value={reliability} onChange={event => setReliability(event.target.value)}>{RELIABILITY_OPTIONS.map(value => <option key={value}>{value}</option>)}</select></label>
      <label className="span-2">Strength reason<textarea rows={2} value={strengthReason} onChange={event => setStrengthReason(event.target.value)} /></label>
      <label className="span-2">Reliability reason<textarea rows={2} value={reliabilityReason} onChange={event => setReliabilityReason(event.target.value)} /></label>
      <label className="span-2">Investigator notes<textarea rows={2} value={notes} onChange={event => setNotes(event.target.value)} /></label>
    </div>
    <div className="h-modal-actions"><button className="ghost-btn" onClick={onClose}>Cancel</button><button className="primary-btn" disabled={saving} onClick={() => void save()}>{saving ? 'Saving…' : 'Save link assessment'}</button></div>
  </Modal>
}

/* ------------------------------------------------------------------------- */
/* Detail workspace                                                          */
/* ------------------------------------------------------------------------- */

export function HypothesisDetail() {
  const { hypothesisId = '' } = useParams()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const investigationId = params.get('investigation') || readInvestigation()
  const tab = params.get('tab') || 'overview'
  const [hypothesis, setHypothesis] = useState<Hypothesis | null>(null)
  const [assessment, setAssessment] = useState<HypothesisAssessment | null>(null)
  const [assessments, setAssessments] = useState<HypothesisAssessment[]>([])
  const [impacts, setImpacts] = useState<HypothesisImpact[]>([])
  const [history, setHistory] = useState<HypothesisHistory | null>(null)
  const [notes, setNotes] = useState<HypothesisNote[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editOpen, setEditOpen] = useState(false)
  const [linkOpen, setLinkOpen] = useState(false)
  const [editLink, setEditLink] = useState<HypothesisLink | null>(null)
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [withdrawLink, setWithdrawLink] = useState<HypothesisLink | null>(null)
  const [reviewImpact, setReviewImpact] = useState<HypothesisImpact | null>(null)
  const [version, setVersion] = useState<HypothesisVersion | null>(null)
  const [busy, setBusy] = useState(false)
  const [statusDraft, setStatusDraft] = useState('')
  const [statusReason, setStatusReason] = useState('')
  const [noteDraft, setNoteDraft] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const item = await fetchHypothesis(investigationId, hypothesisId)
      const [assessmentsResult, impactsResult, historyResult, notesResult] = await Promise.all([
        fetchHypothesisAssessments(hypothesisId),
        fetchHypothesisImpact(hypothesisId, '?page_size=100'),
        fetchHypothesisHistory(hypothesisId),
        fetchHypothesisNotes(hypothesisId),
      ])
      setHypothesis(item)
      setAssessments(assessmentsResult)
      setAssessment(assessmentsResult[0] ?? item.latest_assessment ?? null)
      setImpacts(impactsResult.items)
      setHistory(historyResult)
      setNotes(notesResult)
      setStatusDraft(item.status)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load the hypothesis.')
    } finally { setLoading(false) }
  }, [hypothesisId, investigationId])

  useEffect(() => { void load() }, [load])

  const changeTab = (next: string) => {
    const updated = new URLSearchParams(params)
    updated.set('tab', next)
    updated.set('investigation', investigationId)
    setParams(updated, { replace: true })
  }

  const evaluate = async () => {
    if (!hypothesis) return
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await evaluateHypothesis(hypothesis.hypothesis_id)
      setAssessment(result); setNotice(`Assessment updated: ${humanize(result.assessment_label)}`); await load()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Evaluation failed.') }
    finally { setBusy(false) }
  }

  const saveStatus = async () => {
    if (!hypothesis) return
    if (statusDraft === hypothesis.status) { setError('Choose a different status to record a decision.'); return }
    setBusy(true); setError(''); setNotice('')
    try {
      await updateHypothesisStatus(hypothesis.hypothesis_id, statusDraft, statusReason)
      setStatusReason(''); setNotice('Investigator status recorded. The system did not change it automatically.'); await load()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to update status.') }
    finally { setBusy(false) }
  }

  const addNote = async () => {
    if (!hypothesis || !noteDraft.trim()) return
    setBusy(true); setError('')
    try { await addHypothesisNote(hypothesis.hypothesis_id, noteDraft.trim()); setNoteDraft(''); await load() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to add note.') }
    finally { setBusy(false) }
  }

  const confirmArchive = async () => {
    if (!hypothesis) return
    setBusy(true); setError('')
    try { await archiveHypothesis(hypothesis.hypothesis_id, 'Archived from the hypothesis workspace.'); setArchiveOpen(false); setNotice('Hypothesis archived; history retained.'); await load() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to archive hypothesis.') }
    finally { setBusy(false) }
  }

  const confirmWithdraw = async () => {
    if (!withdrawLink) return
    setBusy(true); setError('')
    try { await withdrawHypothesisEvidence(withdrawLink.link_id); setWithdrawLink(null); setNotice('Link withdrawn. The record and its audit history remain available.'); await load() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to withdraw link.') }
    finally { setBusy(false) }
  }

  const restoreLink = async (link: HypothesisLink) => {
    setBusy(true); setError('')
    try { await updateHypothesisEvidence(link.link_id, { review_status: 'PENDING_REVIEW', investigator_notes: 'Link restored for further review.' }); setNotice('Link restored for review.'); await load() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to restore link.') }
    finally { setBusy(false) }
  }

  const submitImpactReview = async (explanation: string) => {
    if (!reviewImpact || !hypothesis) return
    setBusy(true); setError('')
    try { await reviewHypothesisImpact(hypothesis.hypothesis_id, reviewImpact.impact_id, explanation); setReviewImpact(null); setNotice('Impact review recorded. Hypothesis status was not changed automatically.'); await load() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to review impact record.') }
    finally { setBusy(false) }
  }

  const inspectVersion = async (versionNumber: number) => {
    try { setVersion(await fetchHypothesisVersion(hypothesisId, versionNumber)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Unable to load version.') }
  }

  const openComparison = () => {
    if (!hypothesis) return
    navigate(`/hypotheses/compare?investigation=${encodeURIComponent(investigationId)}&ids=${hypothesis.hypothesis_id}`)
  }

  if (loading && !hypothesis) return <><LabTitle eyebrow="REASONING / 07" title="Hypothesis workspace" description="Loading the hypothesis and its evidence position."/><Loading label="Loading hypothesis workspace…"/></>
  if (error && !hypothesis) return <><LabTitle eyebrow="REASONING / 07" title="Hypothesis workspace" description="The requested hypothesis could not be loaded."/><ErrorBanner message={error} onRetry={() => void load()}/></>
  if (!hypothesis) return null

  const tabs = [
    ['overview', 'Overview'], ['evidence', `Evidence${hypothesis.evidence?.length ? ` (${hypothesis.evidence.length})` : ''}`],
    ['assessment', 'Assessment'], ['impact', `Impact${impacts.filter(item => item.requires_review).length ? ` (${impacts.filter(item => item.requires_review).length})` : ''}`],
    ['history', `History${history?.versions.length ? ` (${history.versions.length})` : ''}`],
  ]

  return <>
    <div className="h-detail-top">
      <Link className="ghost-btn" to={`/hypotheses?investigation=${investigationId}`}><ArrowLeft size={15}/>Back to Hypothesis Lab</Link>
      <InvestigationSelect value={investigationId} onChange={value => navigate(`/hypotheses/${hypothesisId}?investigation=${value}&tab=${tab}`)}/>
    </div>
    <LabTitle eyebrow="REASONING / HYPOTHESIS WORKSPACE" title={hypothesis.title} description={hypothesis.description} action={<div className="h-title-actions"><button className="ghost-btn" onClick={() => setEditOpen(true)}>Edit</button><button className="primary-btn" disabled={busy} onClick={() => void evaluate()}><RefreshCw size={15}/>{busy ? 'Evaluating…' : 'Evaluate'}</button><button className="ghost-btn" onClick={openComparison}><GitCompare size={15}/>Compare</button>{hypothesis.status !== 'ARCHIVED' && <button className="ghost-btn danger-text" onClick={() => setArchiveOpen(true)}><Trash2 size={15}/>Archive</button>}</div>}/>
    {error && <ErrorBanner message={error} onRetry={() => void load()}/>}
    {notice && <div className="h-notice" role="status"><Check size={15}/>{notice}</div>}
    <div className="h-badge-row h-detail-badges">
      <Badge tone="neutral-tone">{humanize(hypothesis.category)}</Badge>
      <Badge tone={statusTone(hypothesis.status)}>{humanize(hypothesis.status)}</Badge>
      <Badge tone={assessmentTone(hypothesis.current_assessment)}>{humanize(hypothesis.current_assessment)}</Badge>
      <Badge tone="neutral-tone">Version {hypothesis.current_version}</Badge>
      <span className="h-muted small">Updated {formatDateTime(hypothesis.updated_at)} · Created by {hypothesis.created_by}</span>
    </div>
    <div className="h-tabs" role="tablist">{tabs.map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? 'active' : ''} onClick={() => changeTab(key)}>{label}</button>)}</div>

    {tab === 'overview' && <OverviewTab hypothesis={hypothesis} assessment={assessment} notes={notes} noteDraft={noteDraft} setNoteDraft={setNoteDraft} addNote={addNote} busy={busy} statusDraft={statusDraft} setStatusDraft={setStatusDraft} statusReason={statusReason} setStatusReason={setStatusReason} saveStatus={saveStatus}/>}
    {tab === 'evidence' && <EvidenceTab links={hypothesis.evidence ?? []} onLink={() => setLinkOpen(true)} onEdit={setEditLink} onWithdraw={setWithdrawLink} onRestore={link => void restoreLink(link)} busy={busy}/>}
    {tab === 'assessment' && <AssessmentTab assessment={assessment} assessments={assessments} onEvaluate={() => void evaluate()} busy={busy}/>}
    {tab === 'impact' && <ImpactTab impacts={impacts} onReview={setReviewImpact} onRefresh={() => void load()}/>}
    {tab === 'history' && <HistoryTab history={history} hypothesis={hypothesis} onInspectVersion={versionNumber => void inspectVersion(versionNumber)}/>}

    {editOpen && <HypothesisFormModal investigationId={investigationId} hypothesis={hypothesis} onClose={() => setEditOpen(false)} onSaved={() => { setEditOpen(false); setNotice('Hypothesis updated; a new version was recorded.'); void load() }}/>}
    {linkOpen && <EvidenceLinkModal investigationId={investigationId} hypothesis={hypothesis} onClose={() => setLinkOpen(false)} onLinked={() => { setLinkOpen(false); setNotice('Source linked; assessment recalculated.'); void load() }}/>}
    {editLink && <LinkEditModal link={editLink} onClose={() => setEditLink(null)} onSaved={() => { setEditLink(null); setNotice('Evidence assessment updated; previous values remain in history.'); void load() }}/>}
    {archiveOpen && <ConfirmDialog title="Archive hypothesis" message="Archive this hypothesis? All versions, evidence links, assessments, and investigator decisions are retained." confirmLabel="Archive" busy={busy} onCancel={() => setArchiveOpen(false)} onConfirm={() => void confirmArchive()}/>}
    {withdrawLink && <ConfirmDialog title="Withdraw evidence link" message={`Withdraw “${withdrawLink.source_title}” from this hypothesis? The source record is not deleted, and the link remains in audit history.`} confirmLabel="Withdraw link" busy={busy} onCancel={() => setWithdrawLink(null)} onConfirm={() => void confirmWithdraw()}/>}
    {reviewImpact && <ImpactReviewModal impact={reviewImpact} onClose={() => setReviewImpact(null)} onSubmit={explanation => void submitImpactReview(explanation)} busy={busy}/>}
    {version && <VersionModal version={version} onClose={() => setVersion(null)}/>}
  </>
}

function DetailList({ title, values }: { title: string; values: string[] }) {
  return <div className="h-detail-list"><h3>{title}</h3>{values.length ? <ul>{values.map((value, index) => <li key={`${title}-${index}`}>{value}</li>)}</ul> : <p className="h-muted">None recorded.</p>}</div>
}

function OverviewTab({ hypothesis, assessment, notes, noteDraft, setNoteDraft, addNote, busy, statusDraft, setStatusDraft, statusReason, setStatusReason, saveStatus }: {
  hypothesis: Hypothesis; assessment: HypothesisAssessment | null; notes: HypothesisNote[]
  noteDraft: string; setNoteDraft: (value: string) => void; addNote: () => Promise<void>; busy: boolean
  statusDraft: string; setStatusDraft: (value: string) => void; statusReason: string; setStatusReason: (value: string) => void
  saveStatus: () => Promise<void>
}) {
  return <div className="h-detail-grid">
    <div className="h-side-stack">
      <Panel title="Explanation"><p>{hypothesis.detailed_explanation || 'No detailed explanation recorded.'}</p></Panel>
      <Panel title="Assumptions, predictions, and limits"><div className="h-three-col"><DetailList title="Assumptions" values={hypothesis.assumptions}/><DetailList title="Expected observations" values={hypothesis.predictions}/><DetailList title="Known limitations" values={hypothesis.limitations}/></div></Panel>
      <Panel title="Open questions"><DetailList title="Still unresolved" values={hypothesis.open_questions}/></Panel>
      <Panel title="Investigator notes">
        <div className="h-note-form"><textarea rows={3} value={noteDraft} onChange={event => setNoteDraft(event.target.value)} placeholder="Record an observation. Notes do not automatically change evidence classifications."/><button className="primary-btn" disabled={busy || !noteDraft.trim()} onClick={() => void addNote()}>Add note</button></div>
        <div className="h-note-list">{notes.length ? notes.map(note => <div key={note.id} className="h-note"><p>{note.note}</p><small>{note.created_by} · {formatDateTime(note.created_at)}</small></div>) : <p className="h-muted">No notes yet.</p>}</div>
      </Panel>
    </div>
    <div className="h-side-stack">
      <Panel title="Current assessment">
        <Badge tone={assessmentTone(hypothesis.current_assessment)}>{humanize(hypothesis.current_assessment)}</Badge>
        <p className="h-muted">{assessment?.assessment_summary || 'This hypothesis has not been evaluated. Link evidence, then run an evaluation.'}</p>
        {assessment && <div className="h-mini-metrics"><span><b>{assessment.supporting_count}</b> supporting</span><span><b>{assessment.contradicting_count}</b> contradicting</span><span><b>{assessment.pending_review_count}</b> pending</span><span><b>{assessment.unresolved_contradiction_count}</b> unresolved</span></div>}
        <p className="h-caution"><ShieldAlert size={14}/>{assessment?.assessment_details?.explanation?.disclaimer || 'Assessments are qualitative review aids, not scientific conclusions.'}</p>
      </Panel>
      <Panel title="Investigator status">
        <p className="h-muted small">Status is an investigator decision. Adding evidence may suggest a change, but the system never selects or finalizes it.</p>
        <label>Status<select value={statusDraft} onChange={event => setStatusDraft(event.target.value)}>{STATUS_OPTIONS.map(value => <option key={value} value={value}>{humanize(value)}</option>)}</select></label>
        <p className="h-help">{STATUS_HELP[statusDraft]}</p>
        <label>Reason for decision<textarea rows={3} value={statusReason} onChange={event => setStatusReason(event.target.value)} placeholder="Explain the investigator's reasoning for this status."/></label>
        <button className="primary-btn" disabled={busy || statusDraft === hypothesis.status} onClick={() => void saveStatus()}>Record status decision</button>
      </Panel>
      <Panel title="Provenance"><div className="h-provenance"><span>Created</span><b>{formatDateTime(hypothesis.created_at)}</b><span>Created by</span><b>{hypothesis.created_by}</b><span>Current version</span><b>v{hypothesis.current_version}</b><span>Hypothesis ID</span><b>{hypothesis.hypothesis_id}</b><span>Investigation</span><b>{hypothesis.investigation_id}</b></div></Panel>
    </div>
  </div>
}

function EvidenceTab({ links, onLink, onEdit, onWithdraw, onRestore, busy }: {
  links: HypothesisLink[]; onLink: () => void; onEdit: (link: HypothesisLink) => void
  onWithdraw: (link: HypothesisLink) => void; onRestore: (link: HypothesisLink) => void; busy: boolean
}) {
  const active = links.filter(link => link.review_status !== 'WITHDRAWN')
  const grouped = groupLinks(active)
  const withdrawn = links.filter(link => link.review_status === 'WITHDRAWN')
  return <div className="h-side-stack">
    <Panel title={`Evidence position · ${active.length} active links`} action={<button className="primary-btn" onClick={onLink}><Plus size={15}/>Link evidence</button>}>
      {active.length === 0 ? <EmptyState title="No linked evidence" description="Link an Evidence Vault document, extracted record, timeline event, network relationship, contradiction, temporal finding, or manual observation." action={<button className="primary-btn" onClick={onLink}><Link2 size={15}/>Link first source</button>}/> : <div className="h-groups">
        {CLASSIFICATION_OPTIONS.map(classification => <div className="h-group" key={classification}>
          <h3><Badge tone={classificationTone(classification)}>{humanize(classification)}</Badge><span>{grouped[classification]?.length ?? 0} source(s)</span></h3>
          {(grouped[classification] ?? []).map(link => <LinkCard key={link.link_id} link={link} onEdit={onEdit} onWithdraw={onWithdraw} busy={busy}/>)}
        </div>)}
      </div>}
    </Panel>
    {withdrawn.length > 0 && <Panel title={`Withdrawn links · ${withdrawn.length}`}><p className="h-muted small">Withdrawn links are never deleted. Their source reference and assessment history remain available.</p>{withdrawn.map(link => <LinkCard key={link.link_id} link={link} onEdit={onEdit} onWithdraw={onWithdraw} onRestore={onRestore} busy={busy}/>)}</Panel>}
  </div>
}

function LinkCard({ link, onEdit, onWithdraw, onRestore, busy }: {
  link: HypothesisLink; onEdit: (link: HypothesisLink) => void; onWithdraw: (link: HypothesisLink) => void; onRestore?: (link: HypothesisLink) => void; busy: boolean
}) {
  const snapshot = link.source_snapshot || { source_type: link.source_type, source_id: link.source_id, title: link.source_title }
  return <article className={`h-link-card ${link.review_status === 'WITHDRAWN' ? 'withdrawn' : ''}`}>
    <div className="h-link-card-head">
      <div><span className="eyebrow">{humanize(link.source_type)}</span><b>{snapshot.title || link.source_title}</b><small>{snapshot.original_reference || link.source_id}</small></div>
      <div className="h-badge-row"><Badge tone={classificationTone(link.classification)}>{humanize(link.classification)}</Badge><Badge tone={reviewTone(link.review_status)}>{humanize(link.review_status)}</Badge></div>
    </div>
    <p>{link.explanation}</p>
    {link.relevant_observations && <p className="h-observations"><b>Relevant detail:</b> {link.relevant_observations}</p>}
    <div className="h-link-meta">
      <span><Badge tone={strengthTone(link.evidence_strength)}>{humanize(link.evidence_strength)}</Badge> strength</span>
      <span><Badge tone={reliabilityTone(link.source_reliability)}>{humanize(link.source_reliability)}</Badge> reliability</span>
      <span>{formatDate(snapshot.date)}</span>
      <span>{snapshot.verification_status ? `Source: ${humanize(snapshot.verification_status)}` : 'Source status not recorded'}</span>
      <span>{link.source_available === false ? 'Source no longer available' : 'Source available'}</span>
    </div>
    {(link.strength_reason || link.reliability_reason) && <details className="h-reason"><summary>Why these assessments?</summary><p><b>Strength:</b> {link.strength_reason || 'Not recorded.'}</p><p><b>Reliability:</b> {link.reliability_reason || 'Not recorded.'}</p></details>}
    {link.investigator_notes && <p className="h-muted small">Investigator note: {link.investigator_notes}</p>}
    <div className="h-link-actions">
      <button className="ghost-btn" onClick={() => onEdit(link)} disabled={busy}>Edit assessment</button>
      {link.review_status === 'WITHDRAWN' ? onRestore && <button className="ghost-btn" onClick={() => onRestore(link)} disabled={busy}>Restore link</button> : <button className="ghost-btn danger-text" onClick={() => onWithdraw(link)} disabled={busy}>Withdraw</button>}
      <span className="h-muted small">Linked by {link.linked_by} · {formatDateTime(link.created_at)}</span>
    </div>
  </article>
}

function ChartCard({ title, data, dataKeys, colors }: { title: string; data: any[]; dataKeys: string[]; colors: string[] }) {
  return <div className="h-chart-card"><h3>{title}</h3>{data.length ? <ResponsiveContainer width="100%" height={230}><BarChart data={data}><CartesianGrid stroke="#2c2720" strokeDasharray="3 3"/><XAxis dataKey="name" stroke="#7c7464" tick={{ fontSize: 10 }}/><YAxis allowDecimals={false} stroke="#7c7464"/><Tooltip contentStyle={{ background: '#12100d', border: '1px solid #3b342b' }}/>{dataKeys.length > 1 && <Legend/>}{dataKeys.map((key, index) => <Bar key={key} dataKey={key} fill={colors[index % colors.length]} radius={[2, 2, 0, 0]}/>)}</BarChart></ResponsiveContainer> : <p className="h-muted">No data recorded.</p>}</div>
}

function AssessmentTab({ assessment, assessments, onEvaluate, busy }: {
  assessment: HypothesisAssessment | null; assessments: HypothesisAssessment[]; onEvaluate: () => void; busy: boolean
}) {
  if (!assessment) return <Panel title="Assessment"><EmptyState title="Not yet evaluated" description="Link traceable evidence, then run an evaluation. The engine will store a reproducible qualitative assessment." action={<button className="primary-btn" onClick={onEvaluate} disabled={busy}><RefreshCw size={15}/>Run evaluation</button>}/></Panel>
  const details = assessment.assessment_details || {}
  const explanation = details.explanation
  const strengths = distributionData(details.strength_distribution)
  const reliability = distributionData(details.reliability_distribution)
  return <div className="h-side-stack">
    <div className="h-assessment-head">
      <div><div className="eyebrow">CURRENT QUALITATIVE ASSESSMENT</div><h2>{humanize(assessment.assessment_label)}</h2><p>{assessment.assessment_summary}</p></div>
      <div className="h-badge-row"><Badge tone={assessmentTone(assessment.assessment_label)}>{humanize(assessment.assessment_label)}</Badge><Badge tone="neutral-tone">Rule v{assessment.evaluation_rule_version}</Badge></div>
      <button className="primary-btn" disabled={busy} onClick={onEvaluate}><RefreshCw size={15}/>Re-evaluate</button>
    </div>
    <div className="h-mini-metrics wide"><span><b>{assessment.supporting_count}</b> supporting</span><span><b>{assessment.contradicting_count}</b> contradicting</span><span><b>{assessment.neutral_count}</b> neutral</span><span><b>{assessment.contextual_count}</b> contextual</span><span><b>{assessment.verified_count}</b> verified</span><span><b>{assessment.pending_review_count}</b> pending</span><span><b>{assessment.unresolved_contradiction_count}</b> unresolved</span></div>
    <div className="h-chart-grid">
      <ChartCard title="Evidence relationship counts" data={evidenceChartData(assessment)} dataKeys={['count']} colors={['#ff6a58']}/>
      <ChartCard title="Evidence strength distribution" data={strengths} dataKeys={['count']} colors={['#b98f7a']}/>
      <ChartCard title="Source reliability distribution" data={reliability} dataKeys={['count']} colors={['#7bc9bd']}/>
    </div>
    {explanation && <Panel title="Why this assessment?"><p>{explanation.why}</p><p className="h-muted"><b>Rule decision:</b> {explanation.decision_reason}</p><div className="h-rule-table"><div className="h-rule-row head"><span>Rule</span><span>Result</span><span>Reason</span></div>{(explanation.rules_applied ?? []).map(item => <div className="h-rule-row" key={item.rule}><span>{humanize(item.rule)}</span><span>{item.result ? 'Applied' : 'Not applied'}</span><span>{item.because}</span></div>)}</div></Panel>}
    <div className="h-two-col">
      <Panel title="Influential supporting sources">{explanation?.influential_sources?.length ? explanation.influential_sources.map(source => <div className="h-source-ref" key={source.link_id}><b>{source.source_title}</b><span>{humanize(source.classification)} · {humanize(source.evidence_strength)} strength · {humanize(source.source_reliability)} reliability</span><p>{source.explanation}</p></div>) : <p className="h-muted">No reviewed supporting source is recorded.</p>}</Panel>
      <Panel title="Conflicting sources">{explanation?.conflicting_sources?.length ? explanation.conflicting_sources.map(source => <div className="h-source-ref" key={source.link_id}><b>{source.source_title}</b><span>{humanize(source.classification)} · {humanize(source.evidence_strength)} strength</span><p>{source.explanation}</p></div>) : <p className="h-muted">No reviewed conflicting source is recorded.</p>}</Panel>
    </div>
    <div className="h-two-col">
      <Panel title="Missing information" action={<Badge tone="neutral-tone">{missingSeverityLabel(explanation?.missing_information_severity || details.missing_information_severity)}</Badge>}>
        {assessment.missing_information.length ? <ul className="h-rule-list">{assessment.missing_information.map(item => <li key={item}>{item}</li>)}</ul> : <p className="h-muted">No missing-information indicator was detected by the current rule set.</p>}
      </Panel>
      <Panel title="Assumptions and open questions">
        {explanation?.unverified_assumptions?.length ? <ul className="h-rule-list">{explanation.unverified_assumptions.map(item => <li key={item.assumption}><b>{item.assumption}</b><span>{item.reason}</span></li>)}</ul> : <p className="h-muted">No unaddressed assumption was detected.</p>}
        {explanation?.open_questions?.length ? <><h3>Open questions</h3><ul className="h-rule-list">{explanation.open_questions.map(item => <li key={item}>{item}</li>)}</ul></> : null}
      </Panel>
    </div>
    <Panel title="Recommended next review">{explanation?.recommended_next_review?.length ? <ul className="h-rule-list">{explanation.recommended_next_review.map(item => <li key={item}>{item}</li>)}</ul> : <p className="h-muted">No outstanding workflow item was detected.</p>}<p className="h-caution"><ShieldAlert size={14}/>{explanation?.disclaimer || 'This assessment is not a medical conclusion or finding of causation.'}</p></Panel>
    <Panel title={`Assessment history · ${assessments.length}`}><div className="h-history-list">{assessments.map(item => <details key={item.assessment_id || `${item.evaluated_at}-${item.assessment_label}`} className="h-history-row"><summary><span><Badge tone={assessmentTone(item.assessment_label)}>{humanize(item.assessment_label)}</Badge></span><span>{formatDateTime(item.evaluated_at)}</span><span>{item.supporting_count} support · {item.contradicting_count} conflict · {item.pending_review_count} pending</span></summary><p>{item.assessment_summary}</p><p className="h-muted">Rule version {item.evaluation_rule_version}. This stored snapshot is never overwritten.</p></details>)}</div></Panel>
  </div>
}

function ImpactReviewModal({ impact, onClose, onSubmit, busy }: { impact: HypothesisImpact; onClose: () => void; onSubmit: (explanation: string) => void; busy: boolean }) {
  const [explanation, setExplanation] = useState('')
  return <Modal title="Review impact analysis" onClose={onClose}>
    <div className="h-impact-summary"><Badge tone={impactTone(impact.impact_category)}>{humanize(impact.impact_category)}</Badge><p>{impact.explanation}</p><p className="h-muted">{humanize(impact.previous_assessment)} → {humanize(impact.current_assessment)}</p></div>
    <label>Investigator review note *<textarea rows={4} value={explanation} onChange={event => setExplanation(event.target.value)} placeholder="What did you decide about this impact? This does not automatically change the hypothesis status."/></label>
    <div className="h-modal-actions"><button className="ghost-btn" onClick={onClose}>Cancel</button><button className="primary-btn" disabled={busy || !explanation.trim()} onClick={() => onSubmit(explanation.trim())}>Record review</button></div>
  </Modal>
}

function ImpactTab({ impacts, onReview, onRefresh }: { impacts: HypothesisImpact[]; onReview: (impact: HypothesisImpact) => void; onRefresh: () => void }) {
  const pending = impacts.filter(item => item.requires_review)
  return <div className="h-side-stack">
    <Panel title={`Impact analysis · ${pending.length} awaiting review`} action={<button className="ghost-btn" onClick={onRefresh}><RefreshCw size={14}/>Refresh</button>}>
      <p className="h-muted small">New evidence, corrected records, contradiction changes, and link updates create review prompts. The engine never automatically classifies new evidence as supporting or contradicting.</p>
      {impacts.length === 0 ? <EmptyState title="No impact records yet" description="Impact analysis runs when evidence is uploaded, records are verified, timeline or network relationships change, or a contradiction is reviewed."/> : <div className="h-impact-list">{impacts.map(item => <article className={`h-impact ${item.requires_review ? 'pending' : ''}`} key={item.impact_id}>
        <div className="h-impact-head"><Badge tone={impactTone(item.impact_category)}>{humanize(item.impact_category)}</Badge><span className="eyebrow">{humanize(item.source_type)} · {item.source_id}</span></div>
        <div className="h-impact-change"><span>{humanize(item.previous_assessment)}</span><ChevronRight size={14}/><b>{humanize(item.current_assessment)}</b></div>
        <p>{item.explanation}</p>
        <div className="h-impact-foot"><span>Trigger: {humanize(item.trigger)} · {formatDateTime(item.created_at)}</span>{item.requires_review ? <button className="primary-btn" onClick={() => onReview(item)}>Review impact</button> : <Badge tone="review-verified">Reviewed {item.reviewed_by ? `by ${item.reviewed_by}` : ''}</Badge>}</div>
      </article>)}</div>}
    </Panel>
  </div>
}

function HistoryTab({ history, hypothesis, onInspectVersion }: { history: HypothesisHistory | null; hypothesis: Hypothesis; onInspectVersion: (versionNumber: number) => void }) {
  return <div className="h-side-stack">
    <Panel title={`Version history · ${history?.versions.length ?? 0}`}>
      <p className="h-muted small">Every hypothesis edit, status decision, evidence-link creation, assessment change, and withdrawal creates an append-only version. Previous records are never overwritten.</p>
      <div className="h-version-list">{history?.versions.map(version => <div className="h-version" key={version.id}>
        <div className="h-version-head"><b>v{version.version_number}</b><Badge tone={version.snapshot_data.status === 'ARCHIVED' ? 'status-archived' : assessmentTone(version.snapshot_data.current_assessment)}>{humanize(version.snapshot_data.current_assessment)}</Badge><span>{formatDateTime(version.created_at)}</span></div>
        <p>{version.change_description}</p>
        {version.reason && <p className="h-muted small">Reason: {version.reason}</p>}
        <div className="h-version-foot"><span>By {version.changed_by}</span><span>{version.snapshot_data.evidence_links?.length ?? 0} linked source(s)</span><button className="ghost-btn" onClick={() => onInspectVersion(version.version_number)}>Inspect snapshot</button></div>
      </div>)}</div>
      {!history?.versions.length && <p className="h-muted">No versions recorded.</p>}
    </Panel>
    <Panel title="Investigator action history"><div className="h-action-list">{history?.reviews.length ? history.reviews.map(action => <div className="h-action" key={action.id}><Badge tone="neutral-tone">{humanize(action.action)}</Badge><div><b>{action.performed_by}</b><span>{formatDateTime(action.created_at)}</span><p>{action.explanation || `${action.previous_value || '—'} → ${action.new_value || '—'}`}</p></div></div>) : <p className="h-muted">No review actions recorded.</p>}</div></Panel>
    <Panel title="Hypothesis metadata"><div className="h-provenance"><span>Hypothesis ID</span><b>{hypothesis.hypothesis_id}</b><span>Investigation</span><b>{hypothesis.investigation_id}</b><span>Created</span><b>{formatDateTime(hypothesis.created_at)}</b><span>Last updated</span><b>{formatDateTime(hypothesis.updated_at)}</b><span>Archived</span><b>{hypothesis.archived_at ? formatDateTime(hypothesis.archived_at) : 'No'}</b></div></Panel>
  </div>
}

function VersionModal({ version, onClose }: { version: HypothesisVersion; onClose: () => void }) {
  const snapshot = version.snapshot_data
  return <Modal title={`Hypothesis version ${version.version_number}`} onClose={onClose} wide>
    <div className="h-version-summary"><Badge tone={statusTone(snapshot.status)}>{humanize(snapshot.status)}</Badge><Badge tone={assessmentTone(snapshot.current_assessment)}>{humanize(snapshot.current_assessment)}</Badge><span className="h-muted">{version.change_description} · {formatDateTime(version.created_at)}</span></div>
    <div className="h-form-grid">
      <label className="span-2">Title<input readOnly value={snapshot.title}/></label>
      <label className="span-2">Description<textarea readOnly rows={3} value={snapshot.description}/></label>
      <label>Category<input readOnly value={snapshot.category}/></label>
      <label>Version<input readOnly value={`v${snapshot.current_version}`}/></label>
      <label className="span-2">Assumptions<textarea readOnly rows={3} value={(snapshot.assumptions ?? []).join('\n')}/></label>
      <label className="span-2">Evidence links at this version<textarea readOnly rows={5} value={(snapshot.evidence_links ?? []).map(link => `${link.source_title} · ${link.classification} · ${link.evidence_strength} · ${link.review_status}`).join('\n') || 'No evidence links at this version.'}/></label>
    </div>
    {version.previous_data && Object.keys(version.previous_data).length > 0 && <details className="h-reason"><summary>Previous values stored with this version</summary><pre>{JSON.stringify(version.previous_data, null, 2)}</pre></details>}
    <div className="h-modal-actions"><button className="primary-btn" onClick={onClose}>Close</button></div>
  </Modal>
}

/* ------------------------------------------------------------------------- */
/* Comparison                                                                */
/* ------------------------------------------------------------------------- */

export function HypothesisComparisonPage() {
  const [params, setParams] = useSearchParams()
  const investigationId = params.get('investigation') || readInvestigation()
  const idParam = params.get('ids') || ''
  const ids = idParam.split(',').filter(Boolean)
  const [items, setItems] = useState<Hypothesis[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set(ids))
  const [comparison, setComparison] = useState<HypothesisComparison | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setSelected(new Set(ids))
    fetchHypotheses(investigationId, '?page_size=100&include_archived=false')
      .then(result => setItems(result.items))
      .catch(caught => setError(caught instanceof Error ? caught.message : 'Unable to load hypotheses.'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [investigationId, idParam])

  useEffect(() => {
    let active = true
    if (ids.length < 2) { setComparison(null); setLoading(false); return () => { active = false } }
    setLoading(true); setError('')
    compareHypotheses(investigationId, ids)
      .then(result => { if (active) setComparison(result) })
      .catch(caught => { if (active) setError(caught instanceof Error ? caught.message : 'Unable to compare hypotheses.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [investigationId, idParam])

  const toggle = (id: string) => setSelected(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next })
  const run = () => {
    if (selected.size < 2) { setError('Select at least two hypotheses.'); return }
    const next = new URLSearchParams(params)
    next.set('investigation', investigationId); next.set('ids', Array.from(selected).join(','))
    setParams(next)
  }

  const chartData = comparisonChartData(comparison)
  const strengthData = comparisonStrengthData(comparison)

  return <>
    <div className="h-detail-top"><Link className="ghost-btn" to={`/hypotheses?investigation=${investigationId}`}><ArrowLeft size={15}/>Back to Hypothesis Lab</Link><InvestigationSelect value={investigationId} onChange={value => { const next = new URLSearchParams(params); next.set('investigation', value); setParams(next) }}/></div>
    <LabTitle eyebrow="REASONING / COMPARISON WORKSPACE" title="Competing hypothesis comparison" description="Compare explicit evidence positions side by side. The comparison is exploratory and does not select a correct explanation." action={<button className="primary-btn" onClick={run}><GitCompare size={16}/>Compare selected ({selected.size})</button>}/>
    {error && <ErrorBanner message={error}/>}
    <Panel title="Select hypotheses to compare">
      <div className="h-compare-picker">{items.map(item => <label key={item.hypothesis_id} className={`h-pick-card ${selected.has(item.hypothesis_id) ? 'selected' : ''}`}><input type="checkbox" checked={selected.has(item.hypothesis_id)} onChange={() => toggle(item.hypothesis_id)}/><div><b>{item.title}</b><span>{humanize(item.category)}</span><small><Badge tone={assessmentTone(item.current_assessment)}>{humanize(item.current_assessment)}</Badge></small></div></label>)}</div>
    </Panel>
    {loading ? <Loading label="Building comparison…"/> : ids.length < 2 ? <EmptyState title="Select at least two hypotheses" description="Choose two or more competing explanations from the same investigation to build the comparison matrix."/> : comparison && <>
      <div className="h-caution large"><ShieldAlert size={18}/>{comparison.disclaimer}</div>
      <div className="h-compare-cards">{comparison.hypotheses.map(entry => <div className="panel h-compare-card" key={entry.hypothesis.hypothesis_id}>
        <div className="eyebrow">{humanize(entry.hypothesis.category)}</div><h2>{entry.hypothesis.title}</h2><p>{entry.hypothesis.description}</p>
        <Badge tone={assessmentTone(entry.hypothesis.current_assessment)}>{humanize(entry.hypothesis.current_assessment)}</Badge>
        <div className="h-mini-metrics"><span><b>{entry.evidence_counts.SUPPORTING ?? 0}</b> support</span><span><b>{entry.evidence_counts.CONTRADICTING ?? 0}</b> conflict</span><span><b>{entry.unresolved_contradiction_count}</b> unresolved</span></div>
        <h3>Main assumptions</h3>{entry.assumptions.length ? <ul className="h-rule-list">{entry.assumptions.map(item => <li key={item}>{item}</li>)}</ul> : <p className="h-muted">None recorded.</p>}
        <h3>Assessment summary</h3><p className="h-muted">{entry.assessment?.assessment_summary || 'Not yet evaluated.'}</p>
        {entry.notes[0] && <p className="h-muted small">Latest note: {entry.notes[0].note}</p>}
      </div>)}</div>
      <div className="h-chart-grid two">
        <ChartCard title="Supporting versus contradicting evidence" data={chartData} dataKeys={['Supporting', 'Contradicting', 'Neutral', 'Contextual']} colors={['#7bc9bd', '#ff6a58', '#e9bd6a', '#b98f7a']}/>
        <ChartCard title="Evidence strength distribution" data={strengthData} dataKeys={['Strong', 'Moderate', 'Limited', 'Not assessed']} colors={['#ff6a58', '#b98f7a', '#e9bd6a', '#7c7464']}/>
      </div>
      <Panel title="Comparison matrix"><div className="h-matrix-wrap"><table className="h-matrix"><thead><tr><th>Dimension</th>{comparison.hypotheses.map(entry => <th key={entry.hypothesis.hypothesis_id}>{entry.hypothesis.title}</th>)}</tr></thead><tbody>{comparison.comparison_matrix.map(row => <tr key={row.key}><td>{row.label}</td>{row.cells.map((cell, index) => <td key={`${row.key}-${index}`}>{row.key === 'assessment' ? <Badge tone={assessmentTone(String(cell.value))}>{cell.display}</Badge> : cell.display}</td>)}</tr>)}</tbody></table></div></Panel>
      <Panel title="Comparison insights"><ul className="h-insight-list">{comparison.insights.map(insight => <li key={insight}><Check size={14}/>{insight}</li>)}</ul><p className="h-caution"><ShieldAlert size={14}/>{comparison.disclaimer}</p></Panel>
    </>}
  </>
}
