# Outbreak Rewind · Milestone 6

Outbreak Rewind is a synthetic public-health investigation console for reconstructing evidence timelines, case relationships, contradictions, and competing hypotheses. **Project Orion contains fictional data only; it is not a clinical or epidemiological decision system.**

## Prerequisites

- Node.js 18+
- Python 3.11+ (3.12 is recommended for the pinned native packages)
- Docker Desktop (optional, for PostgreSQL)

## Setup

### PostgreSQL

```powershell
docker compose up -d db
```

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

The API is available at `http://localhost:8000`; Swagger is at `http://localhost:8000/docs`.

### Local SQLite smoke test

PostgreSQL is optional. The backend defaults to `sqlite:///./orion.db`, stores uploads in
`backend/evidence_storage`, and accepts synthetic CSV, JSON, PDF, and TXT files through
`POST /api/evidence/upload` (multipart field `files`). Files are size-limited, extension and
MIME validated, hashed, extracted, normalized, validated, and assigned a processing status.
Image-only PDFs are rendered and processed with Tesseract OCR. If the local Tesseract executable is unavailable, the upload is retained as `needs_review` with an explicit error. The Docker image installs Tesseract automatically.
Use `GET /api/evidence`, `GET /api/evidence/{id}`, and
`GET /api/evidence/{id}/records` to inspect ingestion and provenance. Extracted records can be manually verified or rejected from the Evidence Vault.

### Frontend

In a second terminal from the project root:

```powershell
npm install
Copy-Item .env.example .env
npm run dev
```

The dashboard is available at `http://localhost:5173`.

## API smoke tests

```powershell
Invoke-RestMethod http://localhost:8000/api/health
Invoke-RestMethod http://localhost:8000/api/investigations
Invoke-RestMethod http://localhost:8000/api/evidence
Invoke-RestMethod http://localhost:8000/api/dashboard/summary
```

## Routes

The frontend includes Overview, Investigations, Evidence Vault, Timeline Reconstruction, Case Network, Contradiction Center, Hypothesis Lab, Investigation Rewind, Reports, and Settings. The dashboard requests live API data where available. If the API is unavailable, the UI explicitly shows a demo-data warning and uses the labelled Project Orion fallback dataset.

## Troubleshooting

- If the API is unavailable, check that `uvicorn` is running and `VITE_API_BASE_URL` matches its port.
- If PostgreSQL is unavailable, check `docker compose ps` and the `DATABASE_URL` in `backend/.env`.
- If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process Bypass` for the current terminal.
- Python 3.14 users may need a Python 3.12 environment because some native wheels are not yet available for every dependency.

## Validation performed

- `npm install`
- `npm run build`
- `python -m compileall -q backend/app`
- `python -m pytest backend/tests -q`
- Docker PostgreSQL health and upload/readback smoke test
- `alembic upgrade head` from `backend`

The frontend build passes. Local image-only PDF OCR requires the Tesseract executable on `PATH`; Docker installs it automatically.
Schema changes are managed with Alembic. For a fresh database, run `cd backend; alembic upgrade head`
before starting the API. Existing Milestone 1/2 databases should be migrated before using the
temporal endpoints.

## Milestone 3 · Temporal reconstruction

The temporal engine is deterministic and does not require an external LLM. It reads normalized
Milestone 2 records, classifies event fields using the centralized taxonomy, preserves original
date values, and stores normalized date bounds with precision and review status. Exact dates are
ordered first; ranges and approximate dates retain their bounds; unknown dates remain unresolved
and sort last. Ambiguous slash dates are never resolved using server locale.

Reconstruction stores `reconstructed_events`, `event_sources`, `temporal_findings`,
`temporal_relationships`, `timeline_snapshots`, and `event_audits`. Re-running reconstruction is
incremental and preserves verified events and historical snapshots. Source links retain evidence
ID, extracted record ID, page/row, source field, original value, and extraction method.

### Temporal API

- `POST /api/timeline/reconstruct/{investigation_id}`
- `GET /api/timeline/{investigation_id}`
- `GET /api/timeline/{investigation_id}/events/{event_id}`
- `GET /api/timeline/{investigation_id}/findings`
- `GET /api/timeline/{investigation_id}/relationships`
- `GET /api/timeline/{investigation_id}/snapshots`
- `GET /api/timeline/{investigation_id}/statistics`
- `GET /api/timeline/{investigation_id}/persons/{person_id}`
- `GET /api/timeline/{investigation_id}/sources/{event_id}`
- `POST /api/timeline/events/{event_id}/verify`
- `PATCH /api/timeline/events/{event_id}`

Upload `synthetic_data/temporal_orion.json` as JSON for a fictional temporal reconstruction
fixture. Expected precision and finding checks are documented in
`synthetic_data/expected_results/temporal_orion.json`.

## Milestone 4 · Case relationship graph

The Case Network is an evidence-backed graph projection over Milestone 2 normalized records and
Milestone 3 reconstructed events. `POST /api/graph/rebuild/{investigation_id}` creates or refreshes
person, location, event, and evidence nodes without duplicating them. Direct contact edges require
an explicit `contact_person_id`; shared-location edges distinguish overlapping intervals from
non-overlapping and incomplete dates; shared-event edges require an explicit `shared_event_id`.

Relationships retain source evidence, reconstructed event IDs, derivation rules, date intervals,
classification (`EXPLICIT`, `INFERRED`, or `POSSIBLE`), and investigator review status. NetworkX
provides descriptive centrality, connected components, communities, bounded neighborhoods, and
shortest paths. These metrics do not represent infection risk or prove transmission.

Graph endpoints include:

- `POST /api/graph/rebuild/{investigation_id}`
- `GET /api/graph/{investigation_id}`
- `GET /api/graph/{investigation_id}/nodes/{node_id}`
- `GET /api/graph/{investigation_id}/relationships/{relationship_id}`
- `GET /api/graph/{investigation_id}/metrics`
- `GET /api/graph/{investigation_id}/persons/{person_id}/network`
- `GET /api/graph/{investigation_id}/locations/{location_id}/network`
- `GET /api/graph/{investigation_id}/paths`
- `PATCH /api/graph/relationships/{relationship_id}/review`

The schema is managed by Alembic revision `0002_graph_schema`, and graph rebuilds preserve
investigator review decisions and provenance.

## Milestone 5 · Contradiction intelligence

Contradiction detection compares stored normalized evidence records, reconstructed events, and
Milestone 3 temporal findings without changing original evidence. The deterministic engine
supports date, location, laboratory result, sample ownership, event-order, and missing-information
findings. Every finding stores field-level comparisons, original and normalized values, evidence
and record references, a rule-based severity reason, an explanation, and a suggested review action.

Run detection with `POST /api/contradictions/detect/{investigation_id}`. Findings are available
through the list, detail, comparison, evidence, statistics, snapshot, and network-context
endpoints. `PATCH /api/contradictions/{contradiction_id}/review` supports under-review,
confirmed, resolved, dismissed, and reopened states; resolve and dismiss require a note and every
action is retained in review history. Repeated detection is idempotent and can reopen findings
when new evidence changes an existing conflict.

The Contradiction Intelligence Center uses live backend data with severity filters, detection
controls, side-by-side comparisons, provenance, explanations, and investigator review actions.
The schema is managed by Alembic revision `0003_contradictions`.

## Milestone 6 · Hypothesis management and evaluation

Milestone 6 adds investigator-controlled hypotheses and qualitative evidence evaluation. Create,
edit, archive, version, annotate, and manually status hypotheses with
`POST /api/hypotheses/{investigation_id}`, `PATCH /api/hypotheses/{hypothesis_id}`, and
`PATCH /api/hypotheses/{hypothesis_id}/status`. Existing evidence documents, extracted records,
timeline events, graph relationships, contradictions, and temporal findings can be linked through
`/api/hypotheses/{hypothesis_id}/evidence`. Duplicate source links are rejected and withdrawn links
remain in history.

`POST /api/hypotheses/{hypothesis_id}/evaluate` stores a reproducible qualitative assessment;
`POST /api/hypotheses/{investigation_id}/compare` compares competing hypotheses without selecting
a winner. Labels are derived from reviewed/verified supporting and contradicting records, while
strength and reliability remain independent qualitative categories—no probabilities are produced.
Every evaluation is retained, and linking or changing evidence creates an investigator-reviewable
impact record. Assessment history, versions, notes, and impacts are available under the documented
`/api/hypotheses` routes. The schema is managed by Alembic revisions `0004_hypotheses` and
`0005_hypothesis_intelligence`; the latter is additive and retains existing Milestone 1–6 rows.

The Hypothesis Lab frontend provides routed overview, detail, comparison, evidence, assessment,
impact, and history views. It is reachable from the sidebar or at `/hypotheses`. The synthetic
ORION scenario can be loaded after the API is running:

```powershell
cd backend
python scripts/seed_hypothesis_scenarios.py
```

Run backend tests with `python -m pytest backend/tests -q` from the project root and frontend
tests with `npm test`. Assessments are qualitative and rule-based (engine rule version v6.2);
strength and source reliability are independent investigator judgements, and the system never
selects a winning hypothesis or produces a probability.
