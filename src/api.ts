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
export const fetchEvents = () => get<unknown[]>('/api/events')
