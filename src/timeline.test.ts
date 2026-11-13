import { describe, expect, it } from 'vitest'
import { evidenceSourceUrl, filterTimelineEvents, temporalLabel } from './timeline'
import type { TimelineEvent } from './api'

const event = (overrides: Partial<TimelineEvent> = {}): TimelineEvent => ({
  event_id: 'EVT-1', investigation_id: 'ORION-001', event_type: 'SYMPTOM_ONSET',
  event_description: 'Symptoms', date_precision: 'DAY', date_confidence: 0.9,
  temporal_status: 'NORMAL', verification_status: 'PENDING', classification_confidence: 0.9,
  ...overrides,
})

describe('timeline helpers', () => {
  it('filters by event type and person', () => {
    expect(filterTimelineEvents([event(), event({ event_id: 'EVT-2', event_type: 'RECOVERY', person_id: 'P002' })], 'SYMPTOM_ONSET', '')).toHaveLength(1)
    expect(filterTimelineEvents([event({ person_id: 'P001' })], 'ALL', 'P002')).toHaveLength(0)
  })
  it('does not render uncertain dates as exact dates', () => {
    expect(temporalLabel(event({ original_date_value: 'June 2024', event_date: '2024-06-01', event_end_date: '2024-06-30', date_precision: 'MONTH' }))).toContain('to 2024-06-30')
    expect(temporalLabel(event({ original_date_value: 'unknown', date_precision: 'UNKNOWN' }))).toContain('unresolved')
  })
  it('builds encoded source navigation URLs', () => {
    expect(evidenceSourceUrl('http://localhost:8000', 'EVD/1')).toBe('http://localhost:8000/api/evidence/EVD%2F1/source')
  })
})
