from datetime import date
from pydantic import BaseModel, ConfigDict
from typing import Literal

class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    date: date
    title: str
    location: str
    severity: str
    category: str
    summary: str
    source: str

class HealthRead(BaseModel):
    status: str
    database: str


class EventCorrection(BaseModel):
    actor: str = "investigator"
    event_description: str | None = None
    event_type: str | None = None
    person_id: str | None = None
    location_id: str | None = None
    location_name: str | None = None
    event_date: date | None = None
    event_end_date: date | None = None
    temporal_status: Literal["NORMAL", "WARNING", "REQUIRES_REVIEW", "UNRESOLVED"] | None = None
