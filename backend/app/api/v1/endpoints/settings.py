"""
System settings endpoint — reads/updates runtime thresholds.
Values are stored in Redis so changes take effect immediately without restart.
Persisted to .env on disk only if explicitly requested.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from app.models.user import User
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()

_DEFAULTS = {
    "loitering_threshold_secs": 300,
    "crowd_density_threshold": 20,
    "running_speed_threshold": 3.0,
    "alert_cooldown_secs": 60,
    "yolo_confidence_threshold": 0.5,
    "frame_skip": 3,
    "max_cameras": 16,
    "csi_update_interval_secs": 60,
    "abd_contamination_rate": 0.05,
}

_REDIS_KEY = "campus:settings"


def _get_redis():
    from app.db.redis_client import get_redis_client
    return get_redis_client()


async def _load_settings() -> dict:
    try:
        r = await _get_redis()
        raw = await r.get(_REDIS_KEY)
        if raw:
            import json
            overrides = json.loads(raw)
            return {**_DEFAULTS, **overrides}
    except Exception:
        pass
    return dict(_DEFAULTS)


class SystemSettings(BaseModel):
    loitering_threshold_secs: int = Field(300, ge=30, le=3600)
    crowd_density_threshold: int = Field(20, ge=1, le=200)
    running_speed_threshold: float = Field(3.0, ge=0.5, le=20.0)
    alert_cooldown_secs: int = Field(60, ge=10, le=600)
    yolo_confidence_threshold: float = Field(0.5, ge=0.1, le=0.99)
    frame_skip: int = Field(3, ge=1, le=10)
    max_cameras: int = Field(16, ge=1, le=64)
    csi_update_interval_secs: int = Field(60, ge=10, le=600)
    abd_contamination_rate: float = Field(0.05, ge=0.01, le=0.2)


def _require_admin(current_user: User = Depends(get_current_user)) -> User:
    if getattr(current_user, "role", "viewer") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/")
async def get_settings(_: User = Depends(get_current_user)):
    """Return current system settings (defaults merged with Redis overrides)."""
    return await _load_settings()


@router.put("/")
async def update_settings(
    data: SystemSettings,
    _: User = Depends(_require_admin),
):
    """Update system settings in Redis — takes effect immediately."""
    import json
    r = await _get_redis()
    await r.set(_REDIS_KEY, json.dumps(data.model_dump()))

    # Push updated thresholds to config so in-process code picks them up
    from app.core.config import settings as s
    s.LOITERING_THRESHOLD_SECS = data.loitering_threshold_secs
    s.CROWD_DENSITY_THRESHOLD = data.crowd_density_threshold
    s.ALERT_COOLDOWN_SECS = data.alert_cooldown_secs
    s.YOLO_CONFIDENCE_THRESHOLD = data.yolo_confidence_threshold
    s.FRAME_SKIP = data.frame_skip

    return {"message": "Settings updated", "settings": data.model_dump()}


@router.post("/reset")
async def reset_settings(_: User = Depends(_require_admin)):
    """Reset all settings to built-in defaults."""
    r = await _get_redis()
    await r.delete(_REDIS_KEY)
    return {"message": "Settings reset to defaults", "settings": _DEFAULTS}
