import type {
  Hypothesis, HypothesisAssessment, HypothesisComparison, HypothesisLink,
} from './api'

export const STATUS_OPTIONS = [
  'DRAFT', 'UNDER_INVESTIGATION', 'SUPPORTED_BY_AVAILABLE_EVIDENCE',
  'CONTRADICTED_BY_AVAILABLE_EVIDENCE', 'INCONCLUSIVE', 'ARCHIVED',
] as const

export const STATUS_HELP: Record<string, string> = {
  DRAFT: 'Being written; not yet an active line of inquiry.',
  UNDER_INVESTIGATION: 'Actively being tested against available evidence.',
  SUPPORTED_BY_AVAILABLE_EVIDENCE: 'The investigator judges that available evidence supports the explanation.',
  CONTRADICTED_BY_AVAILABLE_EVIDENCE: 'The investigator judges that available evidence conflicts with the explanation.',
  INCONCLUSIVE: 'Available evidence does not currently distinguish this explanation.',
  ARCHIVED: 'Retained for audit; no longer part of the active comparison.',
}

export const CATEGORY_OPTIONS = [
  'COMMON_SOURCE_EXPOSURE', 'PERSON_TO_PERSON_CONTACT', 'SHARED_LOCATION_EXPOSURE',
  'MULTIPLE_INDEPENDENT_SOURCES', 'ENVIRONMENTAL_EXPOSURE', 'REPORTING_OR_DATA_ERROR',
  'UNKNOWN_OR_UNCLASSIFIED',
] as const

export const CLASSIFICATION_OPTIONS = ['SUPPORTING', 'CONTRADICTING', 'NEUTRAL', 'CONTEXTUAL'] as const
export const STRENGTH_OPTIONS = ['STRONG', 'MODERATE', 'LIMITED', 'INSUFFICIENT', 'NOT_ASSESSED'] as const
export const RELIABILITY_OPTIONS = ['HIGH', 'MODERATE', 'LOW', 'UNKNOWN', 'NOT_ASSESSED'] as const
export const REVIEW_OPTIONS = ['PENDING_REVIEW', 'REVIEWED', 'VERIFIED', 'DISPUTED', 'WITHDRAWN'] as const
export const SOURCE_TYPE_OPTIONS = [
  'EVIDENCE_DOCUMENT', 'EXTRACTED_RECORD', 'RECONSTRUCTED_EVENT',
  'GRAPH_RELATIONSHIP', 'CONTRADICTION', 'TEMPORAL_FINDING', 'INVESTIGATOR_NOTE',
] as const

export const ASSESSMENT_OPTIONS = [
  'SUBSTANTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE',
  'PARTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE',
  'MIXED_EVIDENCE',
  'LIMITED_SUPPORT',
  'SIGNIFICANT_CONTRADICTIONS',
  'INSUFFICIENT_INFORMATION',
  'NOT_YET_EVALUATED',
] as const

export const INVESTIGATION_STORAGE_KEY = 'orion.investigation'

export function readInvestigation(): string {
  try {
    return window.localStorage.getItem(INVESTIGATION_STORAGE_KEY) || 'ORION-001'
  } catch {
    return 'ORION-001'
  }
}

export function writeInvestigation(value: string): void {
  try { window.localStorage.setItem(INVESTIGATION_STORAGE_KEY, value) } catch { /* storage may be unavailable */ }
}

export function humanize(value: string | null | undefined): string {
  if (!value) return 'Not recorded'
  return value.toLowerCase().replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase())
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'Not recorded'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString(undefined, { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return 'No date'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' })
}

export function sourceTypeLabel(value: string): string {
  return humanize(value)
}

export function assessmentTone(label: string): string {
  if (label.includes('SUBSTANTIALLY')) return 'assessment-substantial'
  if (label.includes('PARTIALLY')) return 'assessment-partial'
  if (label === 'MIXED_EVIDENCE') return 'assessment-mixed'
  if (label === 'SIGNIFICANT_CONTRADICTIONS') return 'assessment-contradicted'
  if (label === 'LIMITED_SUPPORT') return 'assessment-limited'
  if (label === 'INSUFFICIENT_INFORMATION') return 'assessment-insufficient'
  return 'assessment-neutral'
}

export function classificationTone(value: string): string {
  return `classification-${value.toLowerCase()}`
}

export function statusTone(value: string): string {
  return `status-${value.toLowerCase()}`
}

export function reviewTone(value: string): string {
  return `review-${value.toLowerCase()}`
}

export function strengthTone(value: string): string {
  return `strength-${value.toLowerCase()}`
}

export function reliabilityTone(value: string): string {
  return `reliability-${value.toLowerCase()}`
}

export function impactTone(value: string): string {
  return `impact-${value.toLowerCase()}`
}

export function groupLinks(links: HypothesisLink[]): Record<string, HypothesisLink[]> {
  const grouped: Record<string, HypothesisLink[]> = { SUPPORTING: [], CONTRADICTING: [], NEUTRAL: [], CONTEXTUAL: [] }
  for (const link of links) (grouped[link.classification] ||= []).push(link)
  return grouped
}

export function parseList(value: string): string[] {
  return value.split(/\r?\n/).map(item => item.trim()).filter(Boolean)
}

export function listText(values: string[] | undefined): string {
  return (values ?? []).join('\n')
}

export type HypothesisForm = {
  title: string
  category: string
  customCategory: string
  description: string
  detailed_explanation: string
  assumptions: string
  predictions: string
  limitations: string
  open_questions: string
  initial_notes: string
}

export function emptyHypothesisForm(): HypothesisForm {
  return {
    title: '', category: 'UNKNOWN_OR_UNCLASSIFIED', customCategory: '', description: '',
    detailed_explanation: '', assumptions: '', predictions: '', limitations: '',
    open_questions: '', initial_notes: '',
  }
}

export function formFromHypothesis(hypothesis: Hypothesis): HypothesisForm {
  return {
    title: hypothesis.title,
    category: CATEGORY_OPTIONS.includes(hypothesis.category as typeof CATEGORY_OPTIONS[number]) ? hypothesis.category : 'CUSTOM',
    customCategory: CATEGORY_OPTIONS.includes(hypothesis.category as typeof CATEGORY_OPTIONS[number]) ? '' : hypothesis.category,
    description: hypothesis.description,
    detailed_explanation: hypothesis.detailed_explanation ?? '',
    assumptions: listText(hypothesis.assumptions),
    predictions: listText(hypothesis.predictions),
    limitations: listText(hypothesis.limitations),
    open_questions: listText(hypothesis.open_questions),
    initial_notes: '',
  }
}

export function validateHypothesisForm(form: HypothesisForm, requireDetailed = false): Record<string, string> {
  const errors: Record<string, string> = {}
  if (form.title.trim().length < 3) errors.title = 'Title must be at least 3 characters.'
  if (form.title.trim().length > 180) errors.title = 'Title must be 180 characters or fewer.'
  if (form.description.trim().length < 10) errors.description = 'Description must be at least 10 characters.'
  if (requireDetailed && form.detailed_explanation.trim().length < 10) {
    errors.detailed_explanation = 'Detailed explanation must be at least 10 characters.'
  }
  const category = form.category === 'CUSTOM' ? form.customCategory.trim().toUpperCase() : form.category
  if (!/^[A-Z][A-Z0-9_]{2,63}$/.test(category)) {
    errors.category = 'Use a documented category or an uppercase custom category such as LOCAL_WATER_SOURCE.'
  }
  return errors
}

export function formToPayload(form: HypothesisForm): Record<string, unknown> {
  return {
    title: form.title.trim(),
    category: form.category === 'CUSTOM' ? form.customCategory.trim().toUpperCase() : form.category,
    description: form.description.trim(),
    detailed_explanation: form.detailed_explanation.trim(),
    assumptions: parseList(form.assumptions),
    predictions: parseList(form.predictions),
    limitations: parseList(form.limitations),
    open_questions: parseList(form.open_questions),
    initial_notes: form.initial_notes.trim(),
  }
}

export function filterHypotheses(
  items: Hypothesis[],
  filters: { search?: string; status?: string; category?: string; assessment?: string },
): Hypothesis[] {
  const search = (filters.search || '').trim().toLowerCase()
  return items.filter(item => {
    if (filters.status && filters.status !== 'ALL' && item.status !== filters.status) return false
    if (filters.category && filters.category !== 'ALL' && item.category !== filters.category) return false
    if (filters.assessment && filters.assessment !== 'ALL' && item.current_assessment !== filters.assessment) return false
    if (search) {
      const haystack = `${item.title} ${item.description} ${item.detailed_explanation ?? ''} ${item.category}`.toLowerCase()
      if (!haystack.includes(search)) return false
    }
    return true
  })
}

export function distributionData(distribution: Record<string, number> | undefined): Array<{ name: string; count: number }> {
  return Object.entries(distribution || {}).map(([name, count]) => ({ name: humanize(name), count }))
}

export function evidenceChartData(assessment: HypothesisAssessment | null | undefined): Array<{ name: string; count: number }> {
  if (!assessment) return []
  return [
    { name: 'Supporting', count: assessment.supporting_count },
    { name: 'Contradicting', count: assessment.contradicting_count },
    { name: 'Neutral', count: assessment.neutral_count },
    { name: 'Contextual', count: assessment.contextual_count },
  ]
}

export function comparisonChartData(comparison: HypothesisComparison | null): Array<Record<string, string | number>> {
  if (!comparison) return []
  return comparison.hypotheses.map(entry => ({
    name: entry.hypothesis.title.length > 26 ? `${entry.hypothesis.title.slice(0, 24)}…` : entry.hypothesis.title,
    Supporting: entry.evidence_counts.SUPPORTING ?? 0,
    Contradicting: entry.evidence_counts.CONTRADICTING ?? 0,
    Neutral: entry.evidence_counts.NEUTRAL ?? 0,
    Contextual: entry.evidence_counts.CONTEXTUAL ?? 0,
  }))
}

export function comparisonStrengthData(comparison: HypothesisComparison | null): Array<Record<string, string | number>> {
  if (!comparison) return []
  return comparison.hypotheses.map(entry => ({
    name: entry.hypothesis.title.length > 26 ? `${entry.hypothesis.title.slice(0, 24)}…` : entry.hypothesis.title,
    Strong: entry.strength_distribution.STRONG ?? 0,
    Moderate: entry.strength_distribution.MODERATE ?? 0,
    Limited: entry.strength_distribution.LIMITED ?? 0,
    'Not assessed': entry.strength_distribution.NOT_ASSESSED ?? 0,
  }))
}

export function missingSeverityLabel(value: string | undefined): string {
  if (!value) return 'Not assessed'
  return humanize(value)
}

export function shortId(value: string, length = 12): string {
  return value.length > length ? `${value.slice(0, length)}…` : value
}
