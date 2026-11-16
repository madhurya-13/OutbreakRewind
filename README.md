# Outbreak Rewind · Milestone 7

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

### UI structure (shadcn + Tailwind)

This is a Vite app with its source in `src/`, so the component default is
`src/components/ui`, not a root-level `/components/ui` folder. The `@/*` alias
maps `@/components/ui` to `src/components/ui`, and `components.json` records that
alias for the shadcn CLI. Keeping the folder under `src/` matters: Vite only serves
files inside the project source tree, and TypeScript's `include: ["src"]` only
checks those files. A root-level `components/ui` folder would build but would not
be picked up by the configured aliases or the Vite dependency graph.

Tailwind CSS v4 is installed with `@tailwindcss/vite`; global utilities load from
`src/tailwind.css` without preflight so the existing investigation-console CSS is
not reset. Global design tokens and the original console styles live in
`src/styles.css`, the Hypothesis Lab in `src/hypothesis.css`, and the specimen
dashboard in `src/dashboard.css`.

If you prefer to let the CLI manage a component in a fresh checkout, the project
is already initialized for it:

```powershell
npx shadcn@latest add button
```

For a brand-new Vite + React + TypeScript project, the equivalent setup is:

```powershell
npm create vite@latest my-app -- --template react-ts
cd my-app
npm install tailwindcss @tailwindcss/vite clsx tailwind-merge
npx shadcn@latest init
```

Add `tailwindcss()` to the Vite plugin list, map `@` to `./src` in both
`vite.config.ts` and `tsconfig.app.json`, then add the shadcn aliases
(`@/components`, `@/components/ui`, `@/lib/utils`) to `components.json`.

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

## Milestone 7 · Investigation Rewind

Investigation Rewind is the historical intelligence layer over Milestones 1–6. It answers three
different questions without conflating them:

1. **What was known at a recorded time?** — evidence, records, timeline events, relationships,
   contradictions, hypotheses, and assessments reconstructed at a UTC cutoff.
2. **When did the platform learn it?** — every historical view filters by *recorded* time, not by
   the occurrence date stored on the source record.
3. **What changed since then?** — deterministic comparisons and explanations link every change
   back to stored history events and source records.

The Rewind workspace is at `/rewind`; before-and-after comparison is at `/rewind/compare`.

### Valid time vs recorded time

Every reconstructed view distinguishes **valid time** (when an event, observation, or record was
applicable in the investigation) from **recorded time** (when the information entered Outbreak
Rewind). A laboratory result that describes a Day 1 exposure but was uploaded on Day 8 is absent
from a Day 3 view. At a Day 9 cutoff it appears with its actual upload timestamp. Verification,
correction, dispute, withdrawal, reconstruction, review, and assessment actions are similarly
ordered by the time the platform recorded them.

The source records are never replaced by a derived historical representation. The original
evidence metadata, extracted record, event, relationship, contradiction, and hypothesis rows
remain the provenance targets.

### Historical data architecture

Four additive tables extend the existing Milestone 1–6 schema:

| Table | Purpose |
|---|---|
| `investigation_history_events` | Central append-only event stream across all modules, with actor, entity, event type, previous/new state JSON, source reference, change reason, related event, metadata, and UTC `recorded_at`. |
| `historical_entity_versions` | Append-only version snapshots for mutable entities, with entity type/ID, monotonic version number, state JSON, valid-from/to, recorded-at/by, reason, and source reference. |
| `investigation_snapshots` | Immutable point-in-time snapshots with cutoff, event sequence, entity counts, schema version, SHA-256 integrity hash, creator, and integrity status. |
| `investigation_comparisons` / `investigation_exports` | Persisted comparison results and export metadata with secure download references. |

Existing timeline snapshots, graph snapshots, contradiction snapshots, event audits, hypothesis
versions, assessments, review history, and notes are reused as fallback provenance. The Rewind
tables do not duplicate or delete those records.

Indexes cover investigation plus recorded time, investigation plus entity identity, unique
`(entity_type, entity_id, version_number)` version numbers, and snapshot cutoffs. All timestamps
are stored in UTC and converted to the browser's local timezone only for display.

### Event recording

History recording is integrated into evidence upload and verification, timeline reconstruction and
correction, graph rebuild and relationship review, contradiction detection and review, hypothesis
creation/update/status/archive/evaluation/link/withdraw/note/impact actions, snapshot creation,
comparison, and report export. System processes and investigator actions use distinct actor types.

The route handlers now own the transaction: the business-state write and its history event commit
together. Duplicate no-op reconstructions are suppressed by comparing the new state with the latest
state for the same event type and entity. A failed request rolls back both the state change and its
audit record.

### Snapshots and integrity

`POST /api/rewind/{investigation_id}/snapshots` creates a manual snapshot. The backfill script also
creates milestone snapshots. Supported types are `MANUAL_SNAPSHOT`, `AUTOMATIC_SNAPSHOT`,
`MILESTONE_SNAPSHOT`, `PRE_RECONSTRUCTION_SNAPSHOT`, `POST_RECONSTRUCTION_SNAPSHOT`,
`PRE_ASSESSMENT_SNAPSHOT`, and `POST_ASSESSMENT_SNAPSHOT`.

Snapshots store investigation details, evidence metadata, extracted records, timeline events and
sources, temporal findings, graph nodes/relationships and metrics, contradictions and review
states, hypotheses and assessments, notes, and history references. Large source documents are not
copied into snapshots; hashes and source IDs preserve provenance.

Integrity validation checks JSON deserialization, required sections, the SHA-256 content hash,
schema compatibility, entity counts, and source references. `GET
/api/rewind/{investigation_id}/snapshots/{snapshot_id}/integrity` returns every check. Snapshots are
never updated in place; create a new snapshot to correct one.

### Reconstruction

`reconstruct_investigation_as_of(investigation_id, as_of_timestamp)` validates the investigation
and cutoff, reads history and versions up to the cutoff, reconstructs evidence and extracted
records, timeline events and findings, graph relationships, contradictions, hypotheses and
assessments, then returns a structured state with provenance and a 50-event recent-change window.
The full history is paginated separately by the history API.

Rules applied by the reconstructor:

- Evidence is included only when its upload time is at or before the cutoff.
- Record verification/correction/dispute/withdrawal changes are replayed in recorded-time order.
- Timeline events are excluded when their `recorded_at` is later than the cutoff, even when their
  occurrence date is earlier.
- Event date corrections and verification changes are replayed from audits/versions.
- Relationships are excluded when any supporting evidence was not yet available.
- Contradiction review states and hypothesis assessments are replayed only to the cutoff.
- Current values are used only when no historical version exists, and the response marks that
  fallback through coverage warnings rather than pretending the value was known then.

The UI can still render when history is incomplete. Backfilled events and unversioned older records
produce **PARTIAL** coverage with the warning: “Historical reconstruction is partially available
because some records were not versioned when they were originally created.” The unversioned counts
and backfilled event count are returned in `GET /api/rewind/{investigation_id}/coverage`.

### Comparison engine

`POST /api/rewind/{investigation_id}/compare` accepts either two timestamps or two snapshot IDs.
It compares evidence, extracted records, timeline events/findings, network relationships,
contradictions, and hypotheses. Each difference contains entity type/ID, category, classification
(`ADDED`, `REMOVED`, `MODIFIED`, `STATUS_CHANGED`, `RECLASSIFIED`, `VERIFIED`, `DISPUTED`,
`RESOLVED`, `REOPENED`, `UNKNOWN`), previous/current values, change timestamp, explanation, and
source reference. Summary counts are calculated from the differences; the interface never invents
statistics.

### Hypothesis evolution

`GET /api/rewind/{investigation_id}/hypotheses/{hypothesis_id}/evolution` returns the initial
assumptions, original assessment, every stored assessment with recorded time, previous/new labels,
change explanation, and hypothesis change events. The comparison endpoint can compare snapshots at
the initial assessment, after new evidence, and at the current cutoff. Explanations are deterministic
and explicitly describe available evidence; they do not claim that an assessment proves causation.

### Historical reports

`POST /api/rewind/{investigation_id}/export` generates a real PDF or CSV using the existing PyMuPDF
dependency. The PDF includes investigation overview, cutoff, coverage/limitations, status, evidence,
timeline, network, contradictions, hypotheses/assessments, major changes, investigator decisions,
unresolved questions, source references, generation timestamp, page numbers, and the required
disclaimer. CSV preserves headers, UTC timestamps, event type, module, actor, source, previous state,
and new state. Exports are stored under the application's evidence storage with metadata; downloads
use the authorized export endpoint rather than exposing arbitrary files.

### Rewind API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/rewind/{id}/history` | Paginated chronological event history; filters for event type, module, actor, entity, and date range. |
| GET | `/api/rewind/{id}/history/filters` | Available event types, modules, actors, and entity types. |
| GET | `/api/rewind/{id}/history/{event_id}` | One event with previous/new state and provenance. |
| POST | `/api/rewind/{id}/snapshots` | Create an immutable manual snapshot. |
| GET | `/api/rewind/{id}/snapshots` | List snapshots. |
| GET | `/api/rewind/{id}/snapshots/{snapshot_id}` | Snapshot metadata and contents. |
| GET | `/api/rewind/{id}/snapshots/{snapshot_id}/integrity` | Run all integrity checks. |
| GET | `/api/rewind/{id}/at?as_of=...` | Full point-in-time reconstruction. Add `compact=true` for the UI projection without bulky temporal-relationship, record, and nested provenance collections. |
| GET | `/api/rewind/{id}/at/{timestamp}/summary` | Historical summary. |
| GET | `/api/rewind/{id}/at/{timestamp}/timeline` | Historical timeline. |
| GET | `/api/rewind/{id}/at/{timestamp}/network` | Historical network. |
| GET | `/api/rewind/{id}/at/{timestamp}/contradictions` | Historical contradictions. |
| GET | `/api/rewind/{id}/at/{timestamp}/hypotheses` | Historical hypotheses and assessments. |
| POST | `/api/rewind/{id}/compare` | Compare two snapshots or timestamps. |
| GET | `/api/rewind/{id}/comparisons` | Saved comparisons. |
| GET | `/api/rewind/{id}/hypotheses/{hypothesis_id}/evolution` | Assessment evolution and explanations. |
| GET | `/api/rewind/{id}/hypotheses/{hypothesis_id}/changes` | Hypothesis history changes. |
| POST | `/api/rewind/{id}/export` | Generate PDF or CSV for a cutoff/snapshot. |
| GET | `/api/rewind/{id}/exports` | List generated reports. |
| GET | `/api/rewind/{id}/exports/{export_id}` | Export metadata. |
| GET | `/api/rewind/{id}/exports/{export_id}/download` | Authorized report download. |
| GET | `/api/rewind/{id}/coverage` | Historical coverage and warnings. |
| POST | `/api/rewind/{id}/validate` | Validate reconstruction consistency. |

### Database migration

The Milestone 7 migrations are `0006_investigation_rewind` and
`0007_contradiction_priority`. The first uses guarded table/index creation so an existing SQLite
database whose tables were created by the application startup is adopted without data loss. The
second widens `contradictions.machine_priority` to `TEXT`, because existing ORION values exceed the
original `VARCHAR(24)` limit that SQLite enforced only loosely. Run them from the repository root:

```powershell
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
```

For PostgreSQL, set `DATABASE_URL` as described in Setup; Alembic reads it directly, and the same
`upgrade head` command applies both migrations from an empty database.

### Project ORION walkthrough

The synthetic ORION data is retained. The history backfill script reads existing Milestone 2–6
records and writes append-only events, versions, and milestone snapshots without changing source
records:

```powershell
cd backend
..\.venv\Scripts\python.exe scripts/backfill_rewind_history.py
```

The resulting walkthrough demonstrates the requested lifecycle:

- **Stage 1 — Initial investigation:** 13 evidence documents, 26 reconstructed events, 61
  relationships, and 23 detected contradictions at the first checkpoint. No hypotheses yet.
- **Stage 2 — Additional evidence:** contact and location evidence, new events/relationships, and
  additional contradictions appear as their recorded times pass.
- **Stage 3 — Investigator review:** verification, date correction, relationship dispute,
  contradiction review, and hypothesis evidence reclassification events are in the history stream.
- **Stage 4 — New findings:** additional laboratory/evidence records, new contradictions, and
  changed hypothesis assessments.
- **Stage 5 — Current state:** 40 evidence documents, 197 reconstructed events, 599 relationships,
  128 contradictions, 5 hypotheses, and the latest assessments.

The milestone snapshots are named `Stage 1` through `Stage 5`; the comparison page can compare any
two of them. Records whose history predates tracking are marked as backfilled with PARTIAL coverage.

### Testing

```powershell
# from the repository root
..\.venv\Scripts\python.exe -m pytest backend/tests -q
npm test
npm run build
```

Milestone 7 tests cover history recording, future-evidence exclusion, invalid cutoffs and
investigations, immutable snapshots, integrity checks, comparisons of timestamps, PDF/CSV exports,
hypothesis evolution, and reconstruction validation. Frontend tests cover history filtering,
recorded-time mode, cutoff conversion, coverage warnings, the rewind shell, and the comparison
shell. `python -m compileall -q backend/app` is also run.

### Known limitations

- Historical coverage for records created before Milestone 7 is reconstructed from retained rows
  and timestamps; intermediate values that were overwritten are not recoverable. Coverage is marked
  PARTIAL and is never silently presented as complete.
- Replay is client-side and intentionally does not persist a session. It is read-only and stops at
  the latest recorded event.
- The comparative explanation engine is deterministic and rule-based. No LLM is required, and no
  unsupported causal or scientific conclusion is generated.
- Point-in-time reconstruction is computed per request from append-only versions and audits; it is
  not cached. This favors correctness over a cache that could become stale.
- Snapshot payloads are stored as JSON text. Very large investigations should use PostgreSQL and
  appropriate retention limits; source documents are referenced rather than duplicated.
