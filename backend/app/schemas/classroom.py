import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class ClassroomConfigUpdate(BaseModel):
    expected_students: Optional[int] = None
    teaching_zone: Optional[List[dict]] = None
    sleeping_secs_threshold: Optional[float] = None
    talking_secs_threshold: Optional[float] = None


class ClassroomConfigResponse(BaseModel):
    camera_id: uuid.UUID
    expected_students: int
    teaching_zone: Optional[List[dict]]
    sleeping_secs_threshold: float
    talking_secs_threshold: float
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClassroomMetricResponse(BaseModel):
    id: int
    recorded_at: datetime
    camera_id: uuid.UUID
    present_count: int
    expected_count: int
    missing_count: int
    sleeping_count: int
    talking_count: int
    attentive_count: int
    faculty_present: bool
    faculty_engagement_score: float
    attention_index: float
    details: dict

    model_config = {"from_attributes": True}


class ClassroomOverviewItem(BaseModel):
    """One row in the multi-classroom monitoring overview."""
    camera_id: uuid.UUID
    camera_name: str
    location_name: str
    status: str
    latest_metric: Optional[ClassroomMetricResponse] = None
