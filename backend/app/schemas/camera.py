import uuid
from datetime import datetime
from typing import Optional, List, Any
import re
from urllib.parse import urlsplit
from pydantic import BaseModel, field_validator, Field


def validate_camera_source(value: Optional[str]) -> Optional[str]:
    if value is None:
        return value
    value = value.strip()
    if not value:
        raise ValueError("Camera source cannot be empty")
    if value.isdigit():
        return value  # Local webcam index.
    if value.startswith(("http://", "https://", "rtsp://")):
        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ValueError("Invalid camera URL or port") from exc
        if not hostname:
            raise ValueError("Camera URL must include a host")
        if re.fullmatch(r"(?:\d+\.){4}\d+", hostname):
            raise ValueError(
                "Use a colon before the port, for example "
                "http://<phone-ip>:8080/video, not a dot"
            )
        if port == 0:
            raise ValueError("Camera port must be between 1 and 65535")
    return value


class RestrictedZoneCreate(BaseModel):
    name: str
    zone_points: List[dict]
    alert_level: str = "high"
    is_active: bool = True

    @field_validator('zone_points')
    @classmethod
    def normalized_polygon(cls,points):
        import math
        if not 3<=len(points)<=100:raise ValueError('Use 3 to 100 polygon points')
        for p in points:
            if set(p)!={'x','y'} or any(not isinstance(p[k],(int,float)) or not math.isfinite(p[k]) or not 0<=p[k]<=1 for k in ('x','y')):
                raise ValueError('Polygon points must be normalized x/y coordinates from 0 to 1')
        area=sum(p['x']*q['y']-q['x']*p['y'] for p,q in zip(points,points[1:]+points[:1]))
        if abs(area)<1e-6:raise ValueError('Polygon must enclose an area')
        return points

    @field_validator('alert_level')
    @classmethod
    def valid_severity(cls,value):
        if value not in ('low','medium','high','critical'):raise ValueError('Invalid severity')
        return value


class CountingLine(BaseModel):
    points: List[dict]
    enabled: bool = True

    @field_validator('points')
    @classmethod
    def normalized_line(cls,points):
        import math
        if len(points)!=2:raise ValueError('A counting line needs two points')
        for p in points:
            if set(p)!={'x','y'} or any(not isinstance(p[k],(int,float)) or not math.isfinite(p[k]) or not 0<=p[k]<=1 for k in ('x','y')):
                raise ValueError('Line points must be normalized x/y coordinates from 0 to 1')
        if math.dist(tuple(points[0][k] for k in ('x','y')),tuple(points[1][k] for k in ('x','y')))<.01:raise ValueError('Counting line is too short')
        return points


class EmergencyExit(BaseModel):
    id: str = Field(default_factory=lambda:str(uuid.uuid4()))
    name: str = Field(min_length=1,max_length=100)
    points: List[dict]
    enabled: bool = True
    _points=field_validator('points')(RestrictedZoneCreate.normalized_polygon.__func__)


class HoursZone(EmergencyExit):
    start: str
    end: str

    @field_validator('start','end')
    @classmethod
    def valid_hour(cls,value):
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',value):raise ValueError('Use HH:MM hours')
        return value


class PermittedSchedule(BaseModel):
    enabled: bool = False
    start: str = '06:00'
    end: str = '21:00'
    timezone: str = 'Asia/Kolkata'
    zones: List[HoursZone] = Field(default_factory=list,max_length=30)
    _hours=field_validator('start','end')(HoursZone.valid_hour.__func__)

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls,value):
        from zoneinfo import ZoneInfo
        try:ZoneInfo(value)
        except Exception:raise ValueError('Invalid IANA timezone')
        return value


class CampusEventConfiguration(BaseModel):
    schedule: PermittedSchedule = Field(default_factory=PermittedSchedule)
    exit_zones: List[EmergencyExit] = Field(default_factory=list,max_length=30)


class RestrictedZoneResponse(BaseModel):
    id: uuid.UUID
    name: str
    zone_points: List[dict]
    alert_level: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("name")
    @classmethod
    def display_area_wording(cls, value):
        return value.replace("Restricted Zone", "Restricted Area").replace("RESTRICTED ZONE", "RESTRICTED AREA").replace("restricted zone", "restricted area")


class CameraCreate(BaseModel):
    name: str
    location_name: str
    rtsp_url: str
    stream_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    zone_type: str = "general"
    resolution: str = "1920x1080"
    fps: int = 25

    _validate_source = field_validator("rtsp_url", "stream_url")(validate_camera_source)


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    location_name: Optional[str] = None
    rtsp_url: Optional[str] = None
    is_active: Optional[bool] = None
    zone_type: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    _validate_source = field_validator("rtsp_url")(validate_camera_source)


class CameraResponse(BaseModel):
    id: uuid.UUID
    name: str
    location_name: str
    rtsp_url: str
    stream_url: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    zone_type: str
    is_active: bool
    is_recording: bool
    resolution: str
    fps: int
    status: str
    last_heartbeat: Optional[datetime]
    created_at: datetime
    last_error: Optional[str] = None

    model_config = {"from_attributes": True}


class CameraSourceTest(BaseModel):
    rtsp_url: str

    _validate_source = field_validator("rtsp_url")(validate_camera_source)
