"""Historical PDF and CSV report generation using the existing PyMuPDF dependency."""
from __future__ import annotations

import csv
import io
import textwrap
from datetime import datetime
from typing import Any

import pymupdf as fitz
from sqlalchemy.orm import Session

from ...config import settings
from ...models import InvestigationExport, InvestigationSnapshot
from .historical_reconstructor import reconstruct_investigation_as_of
from .history_recorder import record_history_event
from .utils import dumps, iso, loads, new_id, parse_timestamp, utcnow

DISCLAIMER = (
    "This report represents a reconstruction of information recorded in Outbreak Rewind at "
    "the selected historical cutoff. It is an investigative aid, not a medical diagnosis, "
    "proof of transmission, or definitive determination of disease causation."
)


def _clean(value: Any) -> str:
    return str(value if value is not None else "").encode("latin-1", "replace").decode("latin-1")


def _pdf_lines(state: dict[str, Any]) -> list[tuple[str, int]]:
    summary = state.get("summary") or {}
    coverage = state.get("coverage") or {}
    investigation = state.get("investigation") or {}
    history = state.get("history") or state.get("recent_changes") or []
    lines: list[tuple[str, int]] = []
    lines.append((f"Historical investigation report: {investigation.get('investigation_name', state['investigation_id'])}", 16))
    lines.append((f"Cutoff: {state.get('as_of')}  |  Generated: {iso(utcnow())}", 9))
    lines.append((f"Mode: {state.get('mode')}  |  Historical coverage: {coverage.get('status')}", 9))
    lines.append((DISCLAIMER, 8))
    sections = [
        ("1. Investigation overview", [f"{investigation.get('investigation_id')} - {investigation.get('investigation_name')}", f"Status: {investigation.get('status')} | Category: {investigation.get('outbreak_category')}", f"Description: {investigation.get('description')}"]),
        ("2. Selected historical cutoff", [state.get("as_of"), f"Tracked since: {coverage.get('tracked_since') or 'not available'}"]),
        ("3. Historical data coverage", [f"Status: {coverage.get('status')}", *coverage.get("warnings", [])]),
        ("4. Investigation status at the selected time", [f"Status: {investigation.get('status')}", f"Known cases: {investigation.get('total_cases')}"]),
        ("5. Evidence available at that time", [f"{item.get('evidence_id')} | {item.get('filename')} | {item.get('status')} | uploaded {item.get('uploaded_at')}" for item in state.get("evidence") or []] or ["No evidence was recorded by this cutoff."]),
        ("6. Timeline reconstruction", [f"{item.get('event_id')} | {item.get('event_date') or 'date unresolved'} | {item.get('event_type')} | {item.get('event_description')} | {item.get('verification_status')}" for item in (state.get("timeline") or {}).get("events") or []] or ["No reconstructed events were recorded by this cutoff."]),
        ("7. Network relationships", [f"{item.get('relationship_id')} | {item.get('relationship_type')} | {item.get('verification_status')}" for item in (state.get("network") or {}).get("relationships") or []] or ["No network relationships were recorded by this cutoff."]),
        ("8. Contradictions and review states", [f"{item.get('contradiction_id')} | {item.get('title')} | {item.get('severity')} | {item.get('status')}" for item in state.get("contradictions") or []] or ["No contradictions were recorded by this cutoff."]),
        ("9. Hypotheses and assessments", [f"{item.get('hypothesis_id')} | {item.get('title')} | {item.get('status')} | {(item.get('assessment') or {}).get('assessment_label', item.get('current_assessment'))}" for item in state.get("hypotheses") or []] or ["No hypotheses were recorded by this cutoff."]),
        ("10. Major changes during the selected period", [f"{item.get('recorded_at')} | {item.get('event_type')} | {item.get('description')}" for item in history] or ["No history events were recorded."]),
        ("11. Investigator decisions", [f"{item.get('recorded_at')} | {item.get('actor_id')} | {item.get('description')}" for item in history if item.get("actor_type") == "INVESTIGATOR"] or ["No investigator actions were recorded in the selected window."]),
        ("12. Unresolved questions", [f"Unresolved contradictions: {summary.get('unresolved_contradiction_count', 0)}", f"Temporal findings requiring review: {summary.get('temporal_finding_count', 0)}"]),
        ("13. Source references", [f"{item.get('evidence_id')} | {item.get('filename')} | {item.get('checksum')}" for item in state.get("evidence") or []] or ["No source references."]),
        ("14. Historical reconstruction limitations", coverage.get("warnings", []) or ["No known coverage limitations for the selected cutoff."]),
        ("15. Report generation timestamp", [iso(utcnow())]),
    ]
    for title, content in sections:
        lines.append((title, 12))
        for value in content:
            lines.append((_clean(value), 9))
    lines.append((DISCLAIMER, 8))
    return lines


def _render_pdf(state: dict[str, Any], path: Any) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    y = 58
    page_number = 1
    for text, size in _pdf_lines(state):
        width = 595 - 80
        wrapped = textwrap.wrap(text, width=max(20, int(width / (size * 0.55)))) or [""]
        for line in wrapped:
            if y > 790:
                page.insert_text((40, 815), f"Page {page_number}", fontsize=8, color=(0.4, 0.4, 0.4))
                page = document.new_page(width=595, height=842)
                page_number += 1
                y = 58
            page.insert_text((40, y), line, fontsize=size, color=(0.08, 0.07, 0.06))
            y += size + 4
        y += 5
    page.insert_text((40, 815), f"Page {page_number}", fontsize=8, color=(0.4, 0.4, 0.4))
    document.set_metadata({"title": f"Outbreak Rewind historical report {state.get('investigation_id')}", "subject": "Historical investigation reconstruction", "author": "Outbreak Rewind"})
    document.save(path)
    document.close()


def _render_csv(state: dict[str, Any], path: Any) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["investigation_id", "cutoff", "event_id", "recorded_at", "event_type", "module", "entity_type", "entity_id", "actor_type", "actor_id", "description", "change_reason", "previous_state", "new_state", "source_reference"])
    for item in state.get("history") or state.get("recent_changes") or []:
        writer.writerow([
            state.get("investigation_id"), state.get("as_of"), item.get("event_id"), item.get("recorded_at"),
            item.get("event_type"), item.get("module"), item.get("entity_type"), item.get("entity_id"),
            item.get("actor_type"), item.get("actor_id"), item.get("description"), item.get("change_reason"),
            dumps(item.get("previous_state")), dumps(item.get("new_state")), dumps(item.get("source_reference")),
        ])
    path.write_text(buffer.getvalue(), encoding="utf-8")


def generate_investigation_export(
    db: Session,
    investigation_id: str,
    *,
    export_type: str = "PDF",
    cutoff_timestamp: str | datetime | None = None,
    snapshot_id: str | None = None,
    generated_by: str = "investigator",
) -> InvestigationExport:
    export_type = export_type.upper()
    if export_type not in {"PDF", "CSV"}:
        raise ValueError("Export type must be PDF or CSV")
    snapshot = db.get(InvestigationSnapshot, snapshot_id) if snapshot_id else None
    if snapshot_id and (not snapshot or snapshot.investigation_id != investigation_id):
        raise ValueError("Snapshot not found in this investigation")
    cutoff = parse_timestamp(cutoff_timestamp, field="cutoff_timestamp") if cutoff_timestamp else (snapshot.event_cutoff if snapshot else utcnow())
    state = loads(snapshot.snapshot_data, {}) if snapshot else reconstruct_investigation_as_of(investigation_id, cutoff, db)
    item = InvestigationExport(
        export_id=new_id("IEXP"), investigation_id=investigation_id, export_type=export_type,
        cutoff_timestamp=cutoff, snapshot_reference=snapshot_id, file_reference="",
        generated_by=generated_by, generated_at=utcnow(), export_status="PROCESSING",
        metadata_json=dumps({"coverage": state.get("coverage")}),
    )
    db.add(item)
    db.flush()
    directory = settings.storage_dir_path / "rewind_exports"
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{item.export_id}.{export_type.lower()}"
    path = directory / filename
    try:
        if export_type == "PDF":
            _render_pdf(state, path)
        else:
            _render_csv(state, path)
        item.file_reference = f"rewind_exports/{filename}"
        item.export_status = "COMPLETED"
        item.metadata_json = dumps({"coverage": state.get("coverage"), "summary": state.get("summary"), "filename": filename})
        record_history_event(
            db, investigation_id, "REPORT_GENERATED", "INVESTIGATION_EXPORT", item.export_id,
            f"Generated {export_type} historical report for cutoff {cutoff.isoformat()}.",
            previous_state={}, new_state={"export_type": export_type, "cutoff": iso(cutoff), "status": "COMPLETED"},
            actor_type="INVESTIGATOR", actor_id=generated_by, source_reference={"export_id": item.export_id},
        )
    except Exception as exc:
        item.export_status = "FAILED"
        item.metadata_json = dumps({"error": str(exc)})
        raise
    return item


def export_path(item: InvestigationExport) -> Any:
    path = (settings.storage_dir_path / item.file_reference).resolve()
    root = (settings.storage_dir_path / "rewind_exports").resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path