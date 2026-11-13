import type { TimelineEvent } from './api'

export function temporalLabel(event: Pick<TimelineEvent, 'event_date' | 'event_end_date' | 'original_date_value' | 'date_precision'>): string {
  if (!event.event_date) return event.original_date_value ? `${event.original_date_value} · unresolved` : 'Date unresolved'
  if (event.event_end_date && event.event_end_date !== event.event_date) return `${event.event_date} to ${event.event_end_date} · ${event.date_precision}`
  return `${event.event_date} · ${event.date_precision}`
}

export function filterTimelineEvents(events: TimelineEvent[], eventType: string, personId: string): TimelineEvent[] {
  return events.filter(event => (eventType === 'ALL' || event.event_type === eventType) && (!personId || event.person_id === personId))
}

export function evidenceSourceUrl(apiUrl: string, evidenceId: string): string {
  return `${apiUrl}/api/evidence/${encodeURIComponent(evidenceId)}/source`
}
