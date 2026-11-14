export const API_URL = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || 'http://localhost:8000'
async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`)
  if (!response.ok) throw new Error(`API responded ${response.status}`)
  return response.json() as Promise<T>
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
