from datetime import date
from pydantic import BaseModel, ConfigDict

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
