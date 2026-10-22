import uuid
from datetime import datetime
from typing import Optional, Any, Literal
from pydantic import BaseModel, field_validator


class AlertResponse(BaseModel):
    id: uuid.UUID
    camera_id: Optional[uuid.UUID]
    alert_type: str
    severity: str
    title: str
    description: Optional[str]
    status: str
    threat_score: float
    csi_at_alert: Optional[float]
    explanation: dict
    snapshot_path: Optional[str]
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("title", "description")
    @classmethod
    def display_area_wording(cls, value):
        if value is None:
            return value
        return value.replace("Restricted Zone", "Restricted Area").replace("restricted zone", "restricted area").replace("RESTRICTED ZONE", "RESTRICTED AREA")


class AlertUpdate(BaseModel):
    status: Optional[Literal["active", "acknowledged", "resolved", "dismissed"]] = None
    severity: Optional[Literal["low", "medium", "high", "critical"]] = None


class AlertStats(BaseModel):
    total: int
    active: int
    critical: int
    high: int
    medium: int
    low: int
    last_24h: int
