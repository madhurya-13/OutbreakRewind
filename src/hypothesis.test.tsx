import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { HypothesisCard, EmptyState, ErrorBanner, Loading } from './HypothesisLab'
import {
  assessmentTone, classificationTone, comparisonChartData, emptyHypothesisForm,
  filterHypotheses, formToPayload, groupLinks, parseList, validateHypothesisForm,
} from './hypothesisUtils'
import type { Hypothesis, HypothesisComparison, HypothesisLink } from './api'

const hypothesis = (overrides: Partial<Hypothesis> = {}): Hypothesis => ({
  id: 'HYP-1', hypothesis_id: 'HYP-1', investigation_id: 'ORION-001',
  title: 'Shared exposure at the North Quay depot',
  category: 'SHARED_LOCATION_EXPOSURE',
  description: 'Several early cases may share a common exposure at the depot.',
  detailed_explanation: 'A proposed sequence.', assumptions: ['The date is accurate.'],
  predictions: ['Cases share a location.'], limitations: ['Interview-based.'],
  open_questions: ['Is the visit verified?'], status: 'UNDER_INVESTIGATION',
  current_assessment: 'PARTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE',
  current_version: 3, created_by: 'investigator', created_at: '2024-06-01T10:00:00Z',
  updated_at: '2024-06-02T10:00:00Z',
  assessment: {
    hypothesis_id: 'HYP-1', assessment_label: 'PARTIALLY_SUPPORTED_BY_AVAILABLE_EVIDENCE',
    assessment_summary: 'Partial support from reviewed records.', supporting_count: 2,
    contradicting_count: 1, neutral_count: 1, contextual_count: 1, verified_count: 1,
    pending_review_count: 2, unresolved_contradiction_count: 1, missing_information: ['One pending link.'],
    assessment_details: {}, evaluation_rule_version: '6.2', evaluated_at: '2024-06-02T10:00:00Z',
  },
  ...overrides,
})

const link = (overrides: Partial<HypothesisLink> = {}): HypothesisLink => ({
  id: 'HLNK-1', link_id: 'HLNK-1', hypothesis_id: 'HYP-1', source_type: 'EXTRACTED_RECORD',
  source_id: 'EVD-1_001', source_title: 'P101 · depot visit',
  source_snapshot: { source_type: 'EXTRACTED_RECORD', source_id: 'EVD-1_001', title: 'P101 · depot visit' },
  source_available: true, classification: 'SUPPORTING', explanation: 'The record places P101 at LOC-01.',
  evidence_strength: 'MODERATE', source_reliability: 'HIGH', review_status: 'REVIEWED',
  linked_by: 'investigator', created_at: '2024-06-01T10:00:00Z', updated_at: '2024-06-01T10:00:00Z',
  ...overrides,
})

describe('hypothesis form validation', () => {
  it('requires a meaningful title, description, and valid category', () => {
    const errors = validateHypothesisForm({ ...emptyHypothesisForm(), title: 'A', description: 'short', category: 'CUSTOM', customCategory: 'bad category' })
    expect(errors.title).toBeTruthy()
    expect(errors.description).toBeTruthy()
    expect(errors.category).toBeTruthy()
  })
  it('accepts documented and custom categories and converts list fields', () => {
    const form = { ...emptyHypothesisForm(), title: 'Depot exposure', description: 'A synthetic competing explanation.', assumptions: 'One\nTwo\n' }
    expect(validateHypothesisForm(form)).toEqual({})
    const payload = formToPayload(form)
    expect(payload.assumptions).toEqual(['One', 'Two'])
    expect(parseList('a\n\nb')).toEqual(['a', 'b'])
  })
  it('rejects a malformed custom category', () => {
    expect(validateHypothesisForm({ ...emptyHypothesisForm(), title: 'Valid title', description: 'A long enough description.', category: 'CUSTOM', customCategory: 'local source' }).category).toBeTruthy()
  })
})

describe('hypothesis filtering and grouping', () => {
  const items = [
    hypothesis(),
    hypothesis({ hypothesis_id: 'HYP-2', title: 'Household contact chain', category: 'PERSON_TO_PERSON_CONTACT', status: 'DRAFT', current_assessment: 'INSUFFICIENT_INFORMATION' }),
  ]
  it('filters by search, status, category, and assessment', () => {
    expect(filterHypotheses(items, { search: 'household' })).toHaveLength(1)
    expect(filterHypotheses(items, { status: 'DRAFT' })[0].hypothesis_id).toBe('HYP-2')
    expect(filterHypotheses(items, { category: 'SHARED_LOCATION_EXPOSURE' })[0].hypothesis_id).toBe('HYP-1')
    expect(filterHypotheses(items, { assessment: 'INSUFFICIENT_INFORMATION' })[0].hypothesis_id).toBe('HYP-2')
  })
  it('groups links by their four relationship categories', () => {
    const grouped = groupLinks([
      link(), link({ link_id: 'L2', classification: 'CONTRADICTING' }),
      link({ link_id: 'L3', classification: 'NEUTRAL' }), link({ link_id: 'L4', classification: 'CONTEXTUAL' }),
    ])
    expect(grouped.SUPPORTING).toHaveLength(1)
    expect(grouped.CONTRADICTING[0].link_id).toBe('L2')
    expect(grouped.NEUTRAL[0].link_id).toBe('L3')
    expect(grouped.CONTEXTUAL[0].link_id).toBe('L4')
  })
  it('maps qualitative labels to stable visual tones without numeric scores', () => {
    expect(assessmentTone('SIGNIFICANT_CONTRADICTIONS')).toBe('assessment-contradicted')
    expect(assessmentTone('MIXED_EVIDENCE')).toBe('assessment-mixed')
    expect(classificationTone('SUPPORTING')).toBe('classification-supporting')
  })
})

describe('comparison chart data uses stored values only', () => {
  it('derives bars from comparison entries rather than inventing values', () => {
    const comparison = {
      hypotheses: [
        { hypothesis: hypothesis(), evidence_counts: { SUPPORTING: 2, CONTRADICTING: 1, NEUTRAL: 0, CONTEXTUAL: 3 }, strength_distribution: { STRONG: 1 } },
        { hypothesis: hypothesis({ hypothesis_id: 'HYP-2', title: 'Contact chain' }), evidence_counts: { SUPPORTING: 0, CONTRADICTING: 4, NEUTRAL: 1, CONTEXTUAL: 0 }, strength_distribution: { MODERATE: 2 } },
      ],
    } as unknown as HypothesisComparison
    const data = comparisonChartData(comparison)
    expect(data[0].Supporting).toBe(2)
    expect(data[0].Contradicting).toBe(1)
    expect(data[1].Contradicting).toBe(4)
    expect(data[1].Contextual).toBe(0)
  })
})

describe('hypothesis list rendering', () => {
  it('renders the title, status, assessment, counts, and actions', () => {
    const markup = renderToStaticMarkup(<MemoryRouter><HypothesisCard hypothesis={hypothesis()} investigationId="ORION-001" selected onEvaluate={() => undefined} onToggle={() => undefined}/></MemoryRouter>)
    expect(markup).toContain('Shared exposure at the North Quay depot')
    expect(markup).toContain('Under Investigation')
    expect(markup).toContain('Partially Supported By Available Evidence')
    expect(markup).toContain('2</b> supporting')
    expect(markup).toContain('1</b> contradicting')
    expect(markup).toContain('Open')
    expect(markup).toContain('Evaluate')
  })
  it('renders empty, loading, and error states for the lab', () => {
    expect(renderToStaticMarkup(<EmptyState title="No hypotheses yet" description="Create one."/>)).toContain('No hypotheses yet')
    expect(renderToStaticMarkup(<Loading label="Loading hypothesis intelligence…"/>)).toContain('Loading hypothesis intelligence')
    expect(renderToStaticMarkup(<ErrorBanner message="Backend unavailable"/>)).toContain('Backend unavailable')
  })
})
