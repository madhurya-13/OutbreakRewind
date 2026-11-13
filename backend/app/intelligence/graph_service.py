"""Evidence-backed case relationship graph projection and analysis."""
from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any

import networkx as nx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    EvidenceRecord, EventSource, GraphNode, GraphRelationship, GraphSnapshot,
    ReconstructedEvent, RelationshipReviewHistory, RelationshipSource,
)

RELATIONSHIP_TYPES = {
    "DIRECT_CONTACT", "HOUSEHOLD_CONTACT", "WORKPLACE_CONTACT", "REPORTED_CONTACT", "SHARED_EVENT",
    "SHARED_LOCATION", "SAME_LOCATION_OVERLAPPING_TIME", "REPEATED_LOCATION_VISIT",
    "POSSIBLE_LOCATION_EXPOSURE", "TEMPORAL_PROXIMITY", "OVERLAPPING_EVENT_INTERVAL",
    "SEQUENTIAL_LOCATION_VISIT", "SHARED_EVIDENCE_REFERENCE", "COMMON_SOURCE_RECORD", "LABORATORY_LINK",
    "PERSON_EVENT", "EVENT_LOCATION", "EVENT_EVIDENCE",
}
CLASSIFICATIONS = {"EXPLICIT", "INFERRED", "POSSIBLE"}
REVIEW_STATUSES = {"UNVERIFIED", "VERIFIED", "REJECTED"}

def _node_id(kind: str, entity: str) -> str:
    return f"{kind.lower()}:{entity}"

def _date_bounds(event: ReconstructedEvent) -> tuple[date | None, date | None]:
    return event.event_date, event.event_end_date or event.event_date

def _overlap(left: ReconstructedEvent, right: ReconstructedEvent) -> tuple[date | None, date | None]:
    left_start, left_end = _date_bounds(left)
    right_start, right_end = _date_bounds(right)
    if not left_start or not right_start:
        return None, None
    start, end = max(left_start, right_start), min(left_end or left_start, right_end or right_start)
    return (start, end) if start <= end else (None, None)

def _event_sources(db: Session, event_ids: set[str]) -> list[EventSource]:
    if not event_ids:
        return []
    return list(db.scalars(select(EventSource).where(EventSource.event_id.in_(event_ids))).all())

def _serialize_node(node: GraphNode) -> dict[str, Any]:
    return {
        "id": node.node_id, "node_type": node.node_type, "entity_id": node.entity_id,
        "display_label": node.display_label, "metadata": json.loads(node.metadata_json),
    }

def _serialize_relationship(db: Session, relationship: GraphRelationship) -> dict[str, Any]:
    sources = db.scalars(select(RelationshipSource).where(RelationshipSource.relationship_id == relationship.relationship_id)).all()
    return {
        "id": relationship.relationship_id, "source": relationship.source_node_id, "target": relationship.target_node_id,
        "relationship_type": relationship.relationship_type, "classification": relationship.relationship_classification,
        "confidence": relationship.confidence, "derivation_method": relationship.derivation_method,
        "explanation": relationship.explanation, "start_date": relationship.start_date.isoformat() if relationship.start_date else None,
        "end_date": relationship.end_date.isoformat() if relationship.end_date else None,
        "verification_status": relationship.verification_status,
        "sources": [{column.name: getattr(source, column.name) for column in source.__table__.columns} for source in sources],
    }

def _ensure_node(db: Session, investigation_id: str, node_type: str, entity_id: str, label: str, metadata: dict[str, Any], now: datetime, nodes: dict[str, GraphNode]) -> GraphNode:
    node_id = _node_id(node_type, entity_id)
    node = nodes.get(node_id)
    if node is None:
        node = GraphNode(node_id=node_id, investigation_id=investigation_id, node_type=node_type, entity_id=entity_id,
                         display_label=label, metadata_json=json.dumps(metadata, default=str), created_at=now, updated_at=now)
        db.add(node)
        nodes[node_id] = node
    else:
        node.display_label, node.updated_at = label, now
        if metadata:
            node.metadata_json = json.dumps(metadata, default=str)
    return node

def _add_relationship(db: Session, investigation_id: str, source: GraphNode, target: GraphNode, relationship_type: str,
                      classification: str, confidence: float | None, method: str, explanation: str,
                      start: date | None, end: date | None, source_rows: list[tuple[str | None, str | None, str | None, str]],
                      now: datetime, relationships: dict[tuple[str, str, str], GraphRelationship]) -> None:
    if not source_rows:
        return
    key = (source.node_id, target.node_id, relationship_type)
    relationship = relationships.get(key)
    if relationship is None:
        relationship_id = f"GR-{uuid.uuid5(uuid.NAMESPACE_URL, '|'.join((investigation_id, *key))).hex[:16].upper()}"
        relationship = GraphRelationship(
            relationship_id=relationship_id, investigation_id=investigation_id, source_node_id=source.node_id,
            target_node_id=target.node_id, relationship_type=relationship_type, relationship_classification=classification,
            confidence=confidence, derivation_method=method, explanation=explanation, start_date=start, end_date=end,
            verification_status="UNVERIFIED", created_at=now, updated_at=now,
        )
        db.add(relationship)
        relationships[key] = relationship
        db.flush()
    else:
        relationship.updated_at = now
        if start and (not relationship.start_date or start < relationship.start_date): relationship.start_date = start
        if end and (not relationship.end_date or end > relationship.end_date): relationship.end_date = end
    existing = {(row.evidence_id, row.reconstructed_event_id, row.extracted_record_id) for row in db.scalars(select(RelationshipSource).where(RelationshipSource.relationship_id == relationship.relationship_id)).all()}
    existing.update(
        (row.evidence_id, row.reconstructed_event_id, row.extracted_record_id)
        for row in db.new
        if isinstance(row, RelationshipSource) and row.relationship_id == relationship.relationship_id
    )
    for evidence_id, event_id, record_id, description in source_rows:
        key_source = (evidence_id, event_id, record_id)
        if key_source not in existing:
            db.add(RelationshipSource(relationship_id=relationship.relationship_id, evidence_id=evidence_id, reconstructed_event_id=event_id,
                                      extracted_record_id=record_id, source_description=description))
            existing.add(key_source)

def rebuild_graph(investigation_id: str, db: Session) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    events = list(db.scalars(select(ReconstructedEvent).where(ReconstructedEvent.investigation_id == investigation_id)).all())
    evidence = list(db.scalars(select(EvidenceRecord).where(EvidenceRecord.investigation_id == investigation_id)).all())
    existing_nodes = {node.node_id: node for node in db.scalars(select(GraphNode).where(GraphNode.investigation_id == investigation_id)).all()}
    nodes = existing_nodes
    for node in nodes.values():
        if node.node_type == "PERSON":
            metadata = json.loads(node.metadata_json)
            metadata["event_count"], metadata["location_count"] = 0, 0
            node.metadata_json = json.dumps(metadata)
        elif node.node_type == "LOCATION":
            metadata = json.loads(node.metadata_json)
            metadata["event_count"] = 0
            node.metadata_json = json.dumps(metadata)
    relationships = {(item.source_node_id, item.target_node_id, item.relationship_type): item for item in db.scalars(select(GraphRelationship).where(GraphRelationship.investigation_id == investigation_id)).all()}
    event_sources = _event_sources(db, {event.event_id for event in events})
    sources_by_event: dict[str, list[EventSource]] = {}
    for source in event_sources: sources_by_event.setdefault(source.event_id, []).append(source)
    for event in events:
        event_node = _ensure_node(db, investigation_id, "EVENT", event.event_id, event.event_description, {
            "event_type": event.event_type, "event_date_start": event.event_date.isoformat() if event.event_date else None,
            "event_date_end": event.event_end_date.isoformat() if event.event_end_date else None, "date_precision": event.date_precision,
            "person_id": event.person_id, "location_id": event.location_id, "verification_status": event.verification_status,
        }, now, nodes)
        event_source_rows = [(source.evidence_id, event.event_id, source.extracted_record_id, f"Reconstructed event source field {source.source_field or 'unknown'}") for source in sources_by_event.get(event.event_id, [])]
        if event.person_id:
            person = _ensure_node(db, investigation_id, "PERSON", event.person_id, event.person_id, {"person_id": event.person_id, "event_count": 0, "location_count": 0, "verification_status": event.verification_status}, now, nodes)
            metadata = json.loads(person.metadata_json); metadata["event_count"] = metadata.get("event_count", 0) + 1
            person.metadata_json = json.dumps(metadata)
            _add_relationship(db, investigation_id, person, event_node, "PERSON_EVENT", "EXPLICIT", 1.0, "event.person_id", "The person is explicitly associated with this reconstructed event.", *(_date_bounds(event)), event_source_rows, now, relationships)
        if event.location_id or event.location_name:
            location_id = event.location_id or event.location_name or "unknown"
            location = _ensure_node(db, investigation_id, "LOCATION", location_id, event.location_name or location_id, {"location_id": event.location_id, "location_name": event.location_name, "event_count": 0}, now, nodes)
            metadata = json.loads(location.metadata_json); metadata["event_count"] = metadata.get("event_count", 0) + 1
            location.metadata_json = json.dumps(metadata)
            _add_relationship(db, investigation_id, event_node, location, "EVENT_LOCATION", "EXPLICIT", 1.0, "event.location_id", "The reconstructed event names this location.", *(_date_bounds(event)), event_source_rows, now, relationships)
        for source in sources_by_event.get(event.event_id, []):
            evidence_item = next((item for item in evidence if item.id == source.evidence_id), None)
            if evidence_item:
                evidence_node = _ensure_node(db, investigation_id, "EVIDENCE", evidence_item.id, evidence_item.filename, {"evidence_id": evidence_item.id, "evidence_type": evidence_item.category, "uploaded_at": evidence_item.uploaded_at.isoformat(), "processing_status": evidence_item.status}, now, nodes)
                _add_relationship(db, investigation_id, event_node, evidence_node, "EVENT_EVIDENCE", "EXPLICIT", 1.0, "event_sources", "The event is traceable to this source evidence.", *(_date_bounds(event)), event_source_rows, now, relationships)
    people_events: dict[str, list[ReconstructedEvent]] = {}
    for event in events:
        if event.person_id: people_events.setdefault(event.person_id, []).append(event)
    shared_groups: dict[str, list[tuple[str, ReconstructedEvent, EvidenceRecord, dict[str, Any]]]] = {}
    for item in evidence:
        for record in json.loads(item.records_json):
            person = record.get("person_id") or record.get("case_id") or record.get("patient_id")
            contact = record.get("contact_person_id") or record.get("contact_id")
            source_event = next((event for event in people_events.get(str(person), []) if any(source.extracted_record_id == record.get("record_id") for source in sources_by_event.get(event.event_id, []))), None) if person else None
            shared_event_id = record.get("shared_event_id") or record.get("gathering_id")
            if shared_event_id and person and source_event:
                shared_groups.setdefault(str(shared_event_id), []).append((str(person), source_event, item, record))
            if person and contact and str(person) != str(contact):
                rows = [(item.id, source_event.event_id if source_event else None, record.get("record_id"), "Explicit contact_person_id in normalized evidence record")]
                left = _ensure_node(db, investigation_id, "PERSON", str(person), str(person), {}, now, nodes)
                right = _ensure_node(db, investigation_id, "PERSON", str(contact), str(contact), {}, now, nodes)
                _add_relationship(db, investigation_id, left, right, "DIRECT_CONTACT", "EXPLICIT", 1.0, "evidence.contact_person_id", "These individuals are explicitly named as contacts in the source record.", *(_date_bounds(source_event) if source_event else (None, None)), rows, now, relationships)
    for group in shared_groups.values():
        for index, (left_person, left_event, left_evidence, left_record) in enumerate(group):
            for right_person, right_event, right_evidence, right_record in group[index + 1:]:
                if left_person == right_person:
                    continue
                start, end = _overlap(left_event, right_event)
                source_rows = [
                    (left_evidence.id, left_event.event_id, left_record.get("record_id"), "Shared event identifier in normalized evidence record"),
                    (right_evidence.id, right_event.event_id, right_record.get("record_id"), "Shared event identifier in normalized evidence record"),
                ]
                _add_relationship(
                    db, investigation_id, nodes[_node_id("PERSON", left_person)], nodes[_node_id("PERSON", right_person)],
                    "SHARED_EVENT", "INFERRED" if start else "POSSIBLE", 0.8 if start else 0.4,
                    "shared_event_id", "Both individuals are linked to the same documented event record. This does not establish transmission.",
                    start, end, source_rows, now, relationships,
                )
    location_groups: dict[str, list[ReconstructedEvent]] = {}
    for event in events:
        if event.location_id or event.location_name: location_groups.setdefault(event.location_id or event.location_name or "", []).append(event)
    for group in location_groups.values():
        for index, left_event in enumerate(group):
            for right_event in group[index + 1:]:
                if not left_event.person_id or not right_event.person_id or left_event.person_id == right_event.person_id: continue
                start, end = _overlap(left_event, right_event)
                if not sources_by_event.get(left_event.event_id) or not sources_by_event.get(right_event.event_id): continue
                location_type = "SAME_LOCATION_OVERLAPPING_TIME" if start else ("POSSIBLE_LOCATION_EXPOSURE" if not left_event.event_date or not right_event.event_date else "REPEATED_LOCATION_VISIT")
                classification = "INFERRED" if start else "POSSIBLE"
                explanation = ("These individuals have reconstructed events at the same location during overlapping intervals. "
                               "This does not establish direct contact or transmission.") if start else "These individuals share a location, but the available intervals do not establish overlap."
                source_rows = [(source.evidence_id, source.event_id, source.extracted_record_id, "Location event provenance") for source in sources_by_event[left_event.event_id] + sources_by_event[right_event.event_id]]
                left = nodes[_node_id("PERSON", left_event.person_id)]; right = nodes[_node_id("PERSON", right_event.person_id)]
                _add_relationship(db, investigation_id, left, right, location_type, classification, 0.75 if start else 0.35, "same location and interval comparison", explanation, start, end, source_rows, now, relationships)
    db.flush()
    graph = nx.Graph()
    graph.add_nodes_from(node.node_id for node in nodes.values())
    graph.add_edges_from((item.source_node_id, item.target_node_id) for item in relationships.values())
    metrics = graph_metrics_from_graph(graph, relationships.values())
    version = (db.scalar(select(GraphSnapshot.snapshot_version).where(GraphSnapshot.investigation_id == investigation_id).order_by(GraphSnapshot.snapshot_version.desc())) or 0) + 1
    db.add(GraphSnapshot(snapshot_id=f"GS-{uuid.uuid4().hex[:16].upper()}", investigation_id=investigation_id, snapshot_version=version,
                         node_count=len(nodes), relationship_count=len(relationships), metrics_json=json.dumps(metrics), filters_json="{}", created_at=now))
    db.commit()
    return {"investigation_id": investigation_id, "snapshot_version": version, "node_count": len(nodes), "relationship_count": len(relationships), "metrics": metrics}

def graph_metrics_from_graph(graph: nx.Graph, relationships: Any) -> dict[str, Any]:
    relationship_list = list(relationships)
    return {
        "total_nodes": graph.number_of_nodes(), "total_relationships": graph.number_of_edges(),
        "relationship_counts": dict(Counter(item.relationship_type for item in relationship_list)),
        "connected_components": nx.number_connected_components(graph) if graph.number_of_nodes() else 0,
        "degree_centrality": nx.degree_centrality(graph) if graph.number_of_nodes() else {},
        "betweenness_centrality": nx.betweenness_centrality(graph) if graph.number_of_nodes() else {},
        "communities": [sorted(group) for group in nx.connected_components(graph)],
        "interpretation": "Descriptive network structure only; not infection risk or proof of transmission.",
    }

def graph_payload(investigation_id: str, db: Session, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    filters = filters or {}
    nodes = list(db.scalars(select(GraphNode).where(GraphNode.investigation_id == investigation_id)).all())
    relationships = list(db.scalars(select(GraphRelationship).where(GraphRelationship.investigation_id == investigation_id)).all())
    if filters.get("node_type"): nodes = [node for node in nodes if node.node_type == filters["node_type"]]
    allowed_nodes = {node.node_id for node in nodes}
    if filters.get("relationship_type"): relationships = [item for item in relationships if item.relationship_type == filters["relationship_type"]]
    if filters.get("verification_status"): relationships = [item for item in relationships if item.verification_status == filters["verification_status"]]
    selected_node_ids: set[str] | None = None
    if filters.get("person_id"):
        selected_node_ids = {node.node_id for node in nodes if node.node_type == "PERSON" and node.entity_id == filters["person_id"]}
    if filters.get("location_id"):
        selected_node_ids = {node.node_id for node in nodes if node.node_type == "LOCATION" and node.entity_id == filters["location_id"]}
    if selected_node_ids is not None:
        relationships = [item for item in relationships if item.source_node_id in selected_node_ids or item.target_node_id in selected_node_ids]
        allowed_nodes = selected_node_ids | {item.source_node_id for item in relationships} | {item.target_node_id for item in relationships}
    relationships = [item for item in relationships if item.source_node_id in allowed_nodes and item.target_node_id in allowed_nodes]
    if not filters.get("include_possible", True): relationships = [item for item in relationships if item.relationship_classification != "POSSIBLE"]
    if filters.get("start_date"): relationships = [item for item in relationships if not item.end_date or item.end_date >= filters["start_date"]]
    if filters.get("end_date"): relationships = [item for item in relationships if not item.start_date or item.start_date <= filters["end_date"]]
    used = {item.source_node_id for item in relationships} | {item.target_node_id for item in relationships}
    return {"investigation_id": investigation_id, "nodes": [_serialize_node(node) for node in nodes if node.node_id in used or not relationships], "relationships": [_serialize_relationship(db, item) for item in relationships]}

def relationship_detail(db: Session, relationship_id: str) -> dict[str, Any] | None:
    item = db.get(GraphRelationship, relationship_id)
    return _serialize_relationship(db, item) if item else None

def network_for_person(investigation_id: str, person_id: str, db: Session, depth: int = 1) -> dict[str, Any]:
    payload = graph_payload(investigation_id, db)
    graph = nx.Graph()
    graph.add_edges_from((item["source"], item["target"]) for item in payload["relationships"])
    root = _node_id("PERSON", person_id)
    reachable = set(nx.single_source_shortest_path_length(graph, root, cutoff=max(1, min(depth, 3)))) if root in graph else {root}
    return {"person_id": person_id, "depth": max(1, min(depth, 3)), "nodes": [item for item in payload["nodes"] if item["id"] in reachable], "relationships": [item for item in payload["relationships"] if item["source"] in reachable and item["target"] in reachable]}

def paths_for_people(investigation_id: str, source_person: str, target_person: str, db: Session) -> dict[str, Any]:
    payload = graph_payload(investigation_id, db)
    graph = nx.Graph()
    graph.add_edges_from((item["source"], item["target"], {"id": item["id"]}) for item in payload["relationships"])
    source, target = _node_id("PERSON", source_person), _node_id("PERSON", target_person)
    if source not in graph or target not in graph or not nx.has_path(graph, source, target): return {"source_person": source_person, "target_person": target_person, "path": None, "relationships": []}
    path = nx.shortest_path(graph, source, target)
    ids = [graph.edges[left, right]["id"] for left, right in zip(path, path[1:])]
    by_id = {item["id"]: item for item in payload["relationships"]}
    return {"source_person": source_person, "target_person": target_person, "path": path, "relationships": [by_id[item] for item in ids]}
