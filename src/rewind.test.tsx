import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import RewindPage, { CoverageBanner, RewindComparisonPage, filterHistory, fromInputValue, isHistorical, toInputValue } from './Rewind'
import type { RewindCoverage, RewindHistoryEvent } from './api'

const event = (overrides: Partial<RewindHistoryEvent> = {}): RewindHistoryEvent => ({
  event_id: 'IEVT-1', investigation_id: 'ORION-001', event_type: 'EVIDENCE_RECORD_VERIFIED',
  module: 'EVIDENCE', entity_type: 'EXTRACTED_RECORD', entity_id: 'EVD-1_001', entity_version: 1,
  description: 'A contact record was verified.', actor_type: 'INVESTIGATOR', actor_id: 'investigator',
  source_reference: {}, change_reason: '', metadata: {}, recorded_at: '2024-06-02T10:00:00Z',
  ...overrides,
})

const coverage = (overrides: Partial<RewindCoverage> = {}): RewindCoverage => ({
  status: 'PARTIAL', tracked_since: '2024-06-01T10:00:00Z', event_count: 12, version_count: 4,
  unversioned_entity_counts: { evidence: 2 }, warnings: ['Some records predate historical versioning.'],
  reconstruction_note: 'Only records with a known recorded time are reconstructed.', ...overrides,
})

describe('rewind timeline filtering', () => {
  const items = [event(), event({ event_id: 'IEVT-2', module: 'NETWORK', event_type: 'RELATIONSHIP_DISPUTED', actor_id: 'system', recorded_at: '2024-06-03T10:00:00Z', description: 'A relationship was disputed.' })]
  it('filters by module, event type, actor, search, and recorded date', () => {
    expect(filterHistory(items, { module: 'NETWORK' })).toHaveLength(1)
    expect(filterHistory(items, { eventType: 'EVIDENCE_RECORD_VERIFIED' })[0].event_id).toBe('IEVT-1')
    expect(filterHistory(items, { actor: 'system' })[0].event_id).toBe('IEVT-2')
    expect(filterHistory(items, { search: 'contact record' })[0].event_id).toBe('IEVT-1')
    expect(filterHistory(items, { dateFrom: '2024-06-03T00:00:00Z' })[0].event_id).toBe('IEVT-2')
    expect(filterHistory(items, { module: 'ALL', eventType: 'ALL' })).toHaveLength(2)
  })
})

describe('rewind historical mode and timestamps', () => {
  it('marks a cutoff before the latest event as historical', () => {
    expect(isHistorical('2024-06-01T10:00:00Z', '2024-06-03T10:00:00Z')).toBe(true)
    expect(isHistorical('2024-06-03T10:00:00Z', '2024-06-03T10:00:00Z')).toBe(false)
  })
  it('round-trips a datetime-local cutoff into an ISO timestamp', () => {
    const value = toInputValue('2024-06-03T10:00:00Z')
    expect(value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
    expect(fromInputValue(value)).toMatch(/Z$/)
  })
})

describe('rewind rendering', () => {
  it('shows the coverage warning when historical records are incomplete', () => {
    const markup = renderToStaticMarkup(<CoverageBanner coverage={coverage()}/>)
    expect(markup).toContain('Partial historical coverage')
    expect(markup).toContain('Some records predate historical versioning')
  })
  it('renders the rewind workspace and read-only mode shell', () => {
    const markup = renderToStaticMarkup(<MemoryRouter><RewindPage/></MemoryRouter>)
    expect(markup).toContain('Investigation Rewind')
    expect(markup).toContain('CURRENT RECORDED STATE')
    expect(markup).toContain('Play')
    expect(markup).toContain('Compare states')
  })
  it('renders the comparison workspace', () => {
    const markup = renderToStaticMarkup(<MemoryRouter><RewindComparisonPage/></MemoryRouter>)
    expect(markup).toContain('Before &amp; After')
    expect(markup).toContain('FIRST CUTOFF')
  })
})