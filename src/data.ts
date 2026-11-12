export const chartData = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((day, i) => ({ day, records: [38, 52, 45, 70, 61, 84, 96][i] }))
export const events = [
  { id: 'EV-015', date: '2024-06-18', title: 'Port Meridian transmission spike', location: 'LOC-02 · Port Meridian', severity: 'critical', category: 'Epidemiology', summary: 'Wastewater sampling exceeds alert threshold for the third consecutive day.', source: 'ORION / NW-7' },
  { id: 'EV-014', date: '2024-06-17', title: 'Hospital network capacity warning', location: 'LOC-04 · North Cascades', severity: 'high', category: 'Health systems', summary: 'Four facilities report ICU utilization above 85%; staffing shortages emerging.', source: 'State HHS' },
  { id: 'EV-013', date: '2024-06-16', title: 'Variant signal detected', location: 'LOC-01 · Willow County', severity: 'high', category: 'Laboratory', summary: 'A new lineage appears in two independent sequencing runs.', source: 'LAB-008' },
  { id: 'EV-012', date: '2024-06-14', title: 'School absenteeism normalizes', location: 'LOC-03 · East Ridge', severity: 'low', category: 'Community', summary: 'Absenteeism returns to seasonal baseline across 14 districts.', source: 'ORION / EDU-3' },
]
export const evidence = [
  { id: 'EVD-001', type: 'Case report', source: 'Clinic A', uploaded: '18 Jun 2024', status: 'Verified' },
  { id: 'EVD-002', type: 'Laboratory record', source: 'LAB-004', uploaded: '17 Jun 2024', status: 'Verified' },
  { id: 'EVD-003', type: 'Contact interview', source: 'Field team 02', uploaded: '16 Jun 2024', status: 'Pending' },
  { id: 'EVD-004', type: 'Location record', source: 'LOC-02', uploaded: '15 Jun 2024', status: 'Verified' },
]
export const contradictions = [
  { id: 'CON-001', title: 'Onset date mismatch', severity: 'critical', status: 'Unresolved', description: 'Case report and interview record differ by four days.', references: ['EVD-001', 'EVD-003'] },
  { id: 'CON-002', title: 'Conflicting location history', severity: 'high', status: 'Under review', description: 'Two contact records report incompatible travel routes.', references: ['EVD-003', 'EVD-004'] },
  { id: 'CON-003', title: 'Duplicate laboratory accession', severity: 'medium', status: 'Unresolved', description: 'A specimen identifier appears in two source exports.', references: ['EVD-002'] },
]
export const hypotheses = [
  { id: 'H-01', title: 'Community transmission primary', score: 78, supporting: 24, contradicting: 5, summary: 'Distributed exposures explain the current cluster shape.' },
  { id: 'H-02', title: 'Single superspreading event', score: 64, supporting: 15, contradicting: 8, summary: 'A concentrated exposure remains plausible but incomplete.' },
  { id: 'H-03', title: 'Imported introduction', score: 42, supporting: 8, contradicting: 12, summary: 'Early travel links support this possibility, with gaps.' },
]
