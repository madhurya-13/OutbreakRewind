const API_URL = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || 'http://localhost:8000'
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
