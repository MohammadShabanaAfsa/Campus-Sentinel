import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class CSIScoreResponse(BaseModel):
    id: int
    recorded_at: datetime
    camera_id: Optional[uuid.UUID]
    overall_score: float
    crowd_score: float
    loitering_score: float
    access_score: float
    anomaly_score: float
    historical_score: float
    risk_level: str
    contributing_factors: dict

    model_config = {"from_attributes": True}
