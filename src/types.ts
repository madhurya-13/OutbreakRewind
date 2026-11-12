export type Severity = 'critical' | 'high' | 'medium' | 'low'
export interface EventRecord { id: string; date: string; title: string; location: string; severity: Severity; category: string; summary: string; source: string }
export interface Signal { id: string; label: string; value: string; delta: string; status: 'up' | 'down' | 'stable' }
