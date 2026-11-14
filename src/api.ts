export const API_URL = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || 'http://localhost:8000'
async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`)
  const raw = await response.text()
  let payload: unknown = null
  try { payload = raw ? JSON.parse(raw) : null } catch { payload = raw }
  if (!response.ok) {
    const detail = payload && typeof payload === 'object' && 'detail' in payload ? (payload as { detail: unknown }).detail : null
    throw new Error(typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : `API responded ${response.status}`)
  }
  return payload as T
}
export type Investigation = { investigation_id: string; investigation_name: string; description: string; outbreak_category: string; status: string; total_cases: number; evidence_records: number }
export const fetchHealth = () => get<{ status: string }>('/api/health')
export const fetchInvestigations = () => get<Investigation[]>('/api/investigations')
export const fetchDashboard = () => get<Record<string, number>>('/api/dashboard/summary')
export const fetchEvidence = () => get<unknown[]>('/api/evidence')
export type Evidence = { evidence_id: string; evidence_type: string; source: string; investigation_id: string; uploaded_at: string; verification_status: string; status: string; format?: string; record_count?: number; checksum?: string }
export const fetchEvidenceRecords = () => get<Evidence[]>('/api/evidence')
export const fetchEvidenceDetail = (id: string) => get<Evidence & { provenance: Record<string, string>; validation_errors: string[] }>(`/api/evidence/${id}`)
export const fetchEvidenceRows = (id: string) => get<{ evidence_id: string; records: Record<string, unknown>[] }>(`/api/evidence/${id}/records`)
export const verifyEvidenceRecord = (recordId: string, verified: boolean) =>
  fetch(`${API_URL}/api/evidence/records/${encodeURIComponent(recordId)}/verify?verified=${verified}`, { method: 'PATCH' }).then(async response => {
    if (!response.ok) throw new Error((await response.text()) || `Verification failed (${response.status})`)
    return response.json() as Promise<{ record_id: string; verification_status: string }>
  })
export async function uploadEvidence(files: File[], category = 'Other', onProgress?: (value: number) => void): Promise<{ items: Evidence[] }> {
  const body = new FormData()
  files.forEach(file => body.append('files', file))
  body.append('category', category)
  onProgress?.(10)
  const response = await fetch(`${API_URL}/api/evidence/upload`, { method: 'POST', body })
  onProgress?.(100)
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(detail || `Upload failed (${response.status})`)
  }
  return response.json() as Promise<{ items: Evidence[] }>
}
export const fetchEvents = () => get<unknown[]>('/api/events')
export type TimelineEvent = {
  event_id: string; investigation_id: string; person_id?: string; event_type: string; event_description: string
  event_date?: string; event_end_date?: string; date_precision: string; date_confidence: number
  original_date_value?: string; date_interpretation?: string; report_date?: string
  location_id?: string; location_name?: string; temporal_status: string; verification_status: string
  classification_confidence: number; sources?: Array<{ evidence_id: string; extracted_record_id?: string; source_page?: number; source_row?: number; source_field?: string }>
}
export type TimelineFinding = { finding_id: string; event_id?: string; related_event_id?: string; finding_type: string; severity: string; description: string; review_status: string }
export type TimelineStatistics = { total_events: number; identified_event_types: string[]; exact_dates: number; approximate_dates: number; events_requiring_review: number; unresolved_dates: number; potential_duplicate_groups: number; temporal_findings: number }
export const fetchTimeline = (investigationId: string, params = '') => get<TimelineEvent[]>(`/api/timeline/${investigationId}${params}`)
export const fetchTimelineFindings = (investigationId: string) => get<TimelineFinding[]>(`/api/timeline/${investigationId}/findings`)
export const fetchTimelineStatistics = (investigationId: string) => get<TimelineStatistics>(`/api/timeline/${investigationId}/statistics`)
export const reconstructTimeline = (investigationId: string) => fetch(`${API_URL}/api/timeline/reconstruct/${investigationId}`, { method: 'POST' }).then(async response => {
  if (!response.ok) throw new Error((await response.text()) || `Reconstruction failed (${response.status})`)
  return response.json() as Promise<{ event_count: number; version_number: number }>
})
export const verifyTimelineEvent = (eventId: string, verified = true) => fetch(`${API_URL}/api/timeline/events/${encodeURIComponent(eventId)}/verify?verified=${verified}`, { method: 'POST' }).then(async response => {
  if (!response.ok) throw new Error((await response.text()) || `Verification failed (${response.status})`)
  return response.json() as Promise<{ event_id: string; verification_status: string }>
})
export type GraphNode = { id: string; node_type: string; entity_id: string; display_label: string; metadata: Record<string, unknown> }
export type GraphRelationship = { id: string; source: string; target: string; relationship_type: string; classification: string; confidence?: number; derivation_method: string; explanation: string; start_date?: string; end_date?: string; verification_status: string; sources: Array<{ evidence_id?: string; reconstructed_event_id?: string; extracted_record_id?: string; source_description: string }> }
export type GraphPayload = { investigation_id: string; nodes: GraphNode[]; relationships: GraphRelationship[] }
export const fetchGraph = (investigationId: string, params = '') => get<GraphPayload>(`/api/graph/${investigationId}${params}`)
export const rebuildGraph = (investigationId: string) => fetch(`${API_URL}/api/graph/rebuild/${investigationId}`, { method: 'POST' }).then(async response => {
  if (!response.ok) throw new Error((await response.text()) || `Graph rebuild failed (${response.status})`)
  return response.json() as Promise<{ node_count: number; relationship_count: number; snapshot_version: number }>
})
export const fetchGraphRelationship = (investigationId: string, relationshipId: string) => get<GraphRelationship>(`/api/graph/${investigationId}/relationships/${encodeURIComponent(relationshipId)}`)
export const reviewGraphRelationship = (relationshipId: string, verificationStatus: 'VERIFIED' | 'REJECTED' | 'UNVERIFIED', reviewerNote: string) =>
  fetch(`${API_URL}/api/graph/relationships/${encodeURIComponent(relationshipId)}/review`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ verification_status: verificationStatus, reviewer_note: reviewerNote }) }).then(async response => {
    if (!response.ok) throw new Error((await response.text()) || `Relationship review failed (${response.status})`)
    return response.json() as Promise<GraphRelationship>
  })
export const fetchGraphMetrics = (investigationId: string) => get<Record<string, unknown>>(`/api/graph/${investigationId}/metrics`)
export type Contradiction = { contradiction_id: string; contradiction_type: string; title: string; summary: string; severity: string; status: string; affected_entity_type?: string; affected_entity_id?: string; affected_event_id?: string; explanation: string; suggested_action: string; detection_rule: string; last_detected_at: string; comparisons: Array<{ field_name: string; source_a_value: string; source_b_value: string; normalized_a_value: string; normalized_b_value: string; comparison_rule: string; explanation: string }>; evidence: Array<{ evidence_id?: string; extracted_record_id?: string; reconstructed_event_id?: string; original_value?: string; normalized_value?: string; comparison_role: string }>; reviews: Array<{ reviewer: string; action: string; review_note: string; previous_status: string; new_status: string; created_at: string }> }
export const detectContradictions = (investigationId: string) => fetch(`${API_URL}/api/contradictions/detect/${investigationId}`, { method: 'POST' }).then(async response => { if (!response.ok) throw new Error((await response.text()) || `Detection failed (${response.status})`); return response.json() as Promise<{ detected_count: number; new_count: number; snapshot_version: number }> })
export const fetchContradictions = (investigationId: string, params = '') => get<{ items: Contradiction[]; total: number; page: number; page_size: number }>(`/api/contradictions/${investigationId}${params}`)
export const reviewContradiction = (id: string, action: 'UNDER_REVIEW' | 'CONFIRMED_CONFLICT' | 'RESOLVED' | 'DISMISSED' | 'REOPENED', reviewNote: string) => fetch(`${API_URL}/api/contradictions/${encodeURIComponent(id)}/review`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, review_note: reviewNote }) }).then(async response => { if (!response.ok) throw new Error((await response.text()) || `Review failed (${response.status})`); return response.json() as Promise<Contradiction> })
export const fetchContradictionStats = (investigationId: string) => get<{ total: number; by_severity: Record<string, number>; by_status: Record<string, number>; by_type: Record<string, number> }>(`/api/contradictions/${investigationId}/statistics`)

export type Paged<T> = { items: T[]; total: number; page: number; page_size: number }

export type AssessmentCounts = {
  SUPPORTING?: number; CONTRADICTING?: number; NEUTRAL?: number; CONTEXTUAL?: number
  verified?: number; reviewed?: number; pending_review?: number; disputed?: number
  withdrawn?: number; missing_sources?: number; unresolved_contradictions?: number; total_linked?: number
}

export type AssessmentSource = {
  link_id: string; source_type: string; source_id: string; source_title: string
  classification: string; evidence_strength: string; source_reliability: string
  review_status: string; explanation: string
}

export type AssessmentExplanation = {
  rule_version: string
  assessment_meaning: string
  why: string
  decision_reason: string
  rules_applied: Array<{ rule: string; result: boolean; because: string }>
  influential_sources: AssessmentSource[]
  conflicting_sources: AssessmentSource[]
  neutral_sources: AssessmentSource[]
  contextual_sources: AssessmentSource[]
  unverified_sources: AssessmentSource[]
  unresolved_contradictions: Array<{ contradiction_id: string; title: string; status: string; classification: string; link_id: string }>
  unverified_assumptions: Array<{ assumption: string; status: string; link_id: string | null; reason: string }>
  assumption_coverage: Array<{ assumption: string; status: string; link_id: string | null; reason: string }>
  missing_information: string[]
  missing_information_severity: string
  open_questions: string[]
  recommended_next_review: string[]
  strength_definitions: Record<string, string>
  classification_definitions: Record<string, string>
  disclaimer: string
}

export type AssessmentDetails = {
  rule_version?: string
  evaluated_by?: string
  counts?: AssessmentCounts
  strength_distribution?: Record<string, number>
  reliability_distribution?: Record<string, number>
  review_status_distribution?: Record<string, number>
  sources?: HypothesisLink[]
  explanation?: AssessmentExplanation
  missing_information_severity?: string
  evaluation_rules?: Array<{ rule: string; result: boolean; because: string }>
  supported_by?: string[]
  contradicted_by?: string[]
}

export type HypothesisAssessment = {
  assessment_id?: string
  id?: string
  hypothesis_id: string
  assessment_label: string
  assessment_summary: string
  supporting_count: number
  contradicting_count: number
  neutral_count: number
  contextual_count: number
  verified_count: number
  pending_review_count: number
  unresolved_contradiction_count: number
  strong_count?: number
  moderate_count?: number
  limited_count?: number
  missing_information: string[]
  assessment_details: AssessmentDetails
  evaluation_rule_version: string
  evaluated_at: string
}

export type Hypothesis = {
  id: string
  hypothesis_id: string
  investigation_id: string
  title: string
  category: string
  description: string
  detailed_explanation?: string
  assumptions: string[]
  predictions: string[]
  limitations: string[]
  open_questions: string[]
  status: string
  current_assessment: string
  current_version: number
  created_by: string
  created_at: string
  updated_at: string
  archived_at?: string | null
  assessment?: HypothesisAssessment | null
  latest_assessment?: HypothesisAssessment | null
  evidence?: HypothesisLink[]
  notes_count?: number
  pending_impact_count?: number
}

export type SourceSnapshot = {
  source_type: string
  source_id: string
  title: string
  subtitle?: string
  date?: string | null
  verification_status?: string
  original_reference?: string
  details?: Record<string, unknown>
  source_available?: boolean
}

export type HypothesisLink = {
  id: string
  link_id: string
  hypothesis_id: string
  source_type: string
  source_id: string
  source_title: string
  source_snapshot: SourceSnapshot
  source_available: boolean
  classification: string
  explanation: string
  relevant_observations?: string
  evidence_strength: string
  source_reliability: string
  strength_reason?: string
  reliability_reason?: string
  review_status: string
  investigator_notes?: string
  linked_by: string
  reviewed_by?: string
  reviewed_at?: string | null
  created_at: string
  updated_at: string
}

export type HypothesisSource = SourceSnapshot & {
  suggested_strength: string
  suggested_strength_reason: string
  strength_considerations: string[]
  suggested_reliability: string
  suggested_reliability_reason: string
  reliability_considerations: string[]
  already_linked?: boolean
}

export type HypothesisSummary = {
  investigation_id: string
  total_hypotheses: number
  active_hypotheses: number
  under_investigation: number
  with_supporting_evidence: number
  significant_contradictions: number
  mixed_evidence: number
  insufficient_information: number
  not_yet_evaluated: number
  archived: number
  requiring_review: number
  pending_impact_records: number
  pending_evidence_links: number
  recently_updated: number
  recent_hypotheses: Array<{ hypothesis_id: string; title: string; status: string; assessment: string; updated_at: string }>
  categories: string[]
  statuses: string[]
  assessment_labels: string[]
}

export type ComparisonRow = { key: string; label: string; cells: Array<{ value: unknown; display: string }> }
export type HypothesisComparisonEntry = {
  hypothesis: Hypothesis
  assessment: HypothesisAssessment | null
  evidence_counts: Record<string, number>
  strength_distribution: Record<string, number>
  reliability_distribution: Record<string, number>
  review_status_distribution: Record<string, number>
  verified_count: number
  pending_review_count: number
  unresolved_contradiction_count: number
  missing_information: string[]
  open_questions: string[]
  assumptions: string[]
  notes: Array<{ note: string; created_by: string; created_at: string }>
  pending_impact_count: number
  links: HypothesisLink[]
}
export type HypothesisComparison = {
  investigation_id: string
  hypothesis_ids: string[]
  hypotheses: HypothesisComparisonEntry[]
  comparison_matrix: ComparisonRow[]
  insights: string[]
  disclaimer: string
  explanation: string
  rule_version: string
}

export type HypothesisImpact = {
  id: string
  impact_id: string
  hypothesis_id: string
  source_type: string
  source_id: string
  impact_category: string
  previous_assessment: string
  current_assessment: string
  explanation: string
  trigger: string
  requires_review: boolean
  reviewed: boolean
  reviewed_by?: string
  reviewed_at?: string | null
  review_note?: string
  created_at: string
}

export type HypothesisVersion = {
  id: string
  hypothesis_id: string
  version_number: number
  snapshot_data: Hypothesis & { evidence_links?: HypothesisLink[] }
  previous_data: Partial<Hypothesis>
  change_description: string
  reason: string
  changed_by: string
  created_at: string
}

export type HypothesisNote = {
  id: string
  hypothesis_id: string
  note: string
  created_by: string
  created_at: string
  updated_at: string
}

export type HypothesisReviewAction = {
  id: string
  hypothesis_id: string
  action: string
  previous_value: string
  new_value: string
  explanation: string
  performed_by: string
  created_at: string
}

export type HypothesisHistory = {
  versions: HypothesisVersion[]
  reviews: HypothesisReviewAction[]
  assessments: HypothesisAssessment[]
}

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(`${API_URL}${path}`, init)
  const raw = await response.text()
  let payload: unknown = null
  try { payload = raw ? JSON.parse(raw) : null } catch { payload = raw }
  if (!response.ok) {
    const detail = payload && typeof payload === 'object' && 'detail' in payload ? (payload as { detail: unknown }).detail : null
    const message = typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : (raw || `API responded ${response.status}`)
    throw new Error(message)
  }
  return payload as T
}

export const fetchHypotheses = (investigationId: string, params = '') => get<Paged<Hypothesis>>(`/api/hypotheses/${investigationId}${params}`)
export const fetchHypothesis = (investigationId: string, id: string) => get<Hypothesis>(`/api/hypotheses/${investigationId}/${encodeURIComponent(id)}`)
export const fetchHypothesisSummary = (investigationId: string) => get<HypothesisSummary>(`/api/hypotheses/${investigationId}/summary`)
export const fetchHypothesisSources = (investigationId: string, params = '') => get<{ investigation_id: string; items: HypothesisSource[]; total: number }>(`/api/hypotheses/${investigationId}/sources${params}`)
export const createHypothesis = (investigationId: string, body: Record<string, unknown>) => request<Hypothesis>(`/api/hypotheses/${investigationId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const updateHypothesis = (id: string, body: Record<string, unknown>) => request<Hypothesis>(`/api/hypotheses/${encodeURIComponent(id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const updateHypothesisStatus = (id: string, status: string, explanation = '', updatedBy = 'investigator') => request<Hypothesis>(`/api/hypotheses/${encodeURIComponent(id)}/status`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status, explanation, updated_by: updatedBy }) })
export const archiveHypothesis = (id: string, reason = '', archivedBy = 'investigator') => request<Hypothesis>(`/api/hypotheses/${encodeURIComponent(id)}?reason=${encodeURIComponent(reason)}&archived_by=${encodeURIComponent(archivedBy)}`, { method: 'DELETE' })
export const fetchHypothesisEvidence = (id: string, params = '') => get<HypothesisLink[]>(`/api/hypotheses/${encodeURIComponent(id)}/evidence${params}`)
export const linkHypothesisEvidence = (id: string, body: Record<string, unknown>) => request<HypothesisLink>(`/api/hypotheses/${encodeURIComponent(id)}/evidence`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const updateHypothesisEvidence = (linkId: string, body: Record<string, unknown>) => request<HypothesisLink>(`/api/hypotheses/evidence/${encodeURIComponent(linkId)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const withdrawHypothesisEvidence = (linkId: string, withdrawnBy = 'investigator') => request<HypothesisLink>(`/api/hypotheses/evidence/${encodeURIComponent(linkId)}?withdrawn_by=${encodeURIComponent(withdrawnBy)}`, { method: 'DELETE' })
export const evaluateHypothesis = (id: string) => request<HypothesisAssessment>(`/api/hypotheses/${encodeURIComponent(id)}/evaluate`, { method: 'POST' })
export const evaluateInvestigationHypotheses = (investigationId: string) => request<{ investigation_id: string; items: Array<{ hypothesis_id: string; title: string; previous_assessment: string; assessment: HypothesisAssessment }>; evaluated_count: number; rule_version: string; disclaimer: string }>(`/api/hypotheses/evaluate/${investigationId}`, { method: 'POST' })
export const fetchHypothesisAssessment = (id: string) => get<HypothesisAssessment>(`/api/hypotheses/${encodeURIComponent(id)}/assessment`)
export const fetchHypothesisAssessments = (id: string) => get<HypothesisAssessment[]>(`/api/hypotheses/${encodeURIComponent(id)}/assessments`)
export const compareHypotheses = (investigationId: string, hypothesisIds: string[]) => request<HypothesisComparison>(`/api/hypotheses/${investigationId}/compare`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ hypothesis_ids: hypothesisIds }) })
export const fetchHypothesisImpact = (id: string, params = '') => get<Paged<HypothesisImpact>>(`/api/hypotheses/${encodeURIComponent(id)}/impact${params}`)
export const fetchInvestigationImpact = (investigationId: string, params = '') => get<Paged<HypothesisImpact>>(`/api/hypotheses/${investigationId}/impact${params}`)
export const reviewHypothesisImpact = (hypothesisId: string, impactId: string, explanation: string, reviewedBy = 'investigator') => request<HypothesisImpact>(`/api/hypotheses/${encodeURIComponent(hypothesisId)}/impact/${encodeURIComponent(impactId)}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ explanation, reviewed_by: reviewedBy }) })
export const fetchHypothesisHistory = (id: string) => get<HypothesisHistory>(`/api/hypotheses/${encodeURIComponent(id)}/history`)
export const fetchHypothesisVersion = (id: string, versionNumber: number) => get<HypothesisVersion>(`/api/hypotheses/${encodeURIComponent(id)}/versions/${versionNumber}`)
export const fetchHypothesisNotes = (id: string) => get<HypothesisNote[]>(`/api/hypotheses/${encodeURIComponent(id)}/notes`)
export const addHypothesisNote = (id: string, note: string, createdBy = 'investigator') => request<HypothesisNote>(`/api/hypotheses/${encodeURIComponent(id)}/notes`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note, created_by: createdBy }) })
