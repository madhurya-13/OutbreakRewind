# Outbreak Rewind · Milestone 1

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

The frontend build passes. API import validation is environment-dependent when the host blocks native Pydantic DLLs; PostgreSQL connectivity requires Docker to be running.
