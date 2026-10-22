import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class PredictionResponse(BaseModel):
    id: int
    predicted_at: datetime
    camera_id: Optional[uuid.UUID]
    threat_type: str
    probability: float
    threat_level: str
    predicted_window_secs: int
    recommended_action: Optional[str]
    model_version: Optional[str]
    feature_importance: dict

    # model_version is data, while actual BaseModel API names stay protected.
    model_config = {"from_attributes": True, "protected_namespaces": ("model_validate", "model_dump")}
