"""
Stream control API — start/stop/restart individual camera streams
and expose stream status for health dashboard.
"""
import uuid
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.models.camera import Camera
from app.models.user import User
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


def _get_stream_manager(camera_id: str):
    from ai_engine.vision.stream_manager import StreamManager
    return StreamManager.get_instance(camera_id)


@router.get("/status")
async def get_stream_status(_: User = Depends(get_current_user)):
    """Return live status of every camera's stream (one StreamManager each)."""
    from ai_engine.vision.stream_manager import get_all_statuses
    return get_all_statuses()


@router.post("/{camera_id}/start")
async def start_stream(
    camera_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    cam = result.scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    background_tasks.add_task(_do_start, str(camera_id))
    return {"status": "starting", "camera_id": str(camera_id)}


@router.post("/{camera_id}/stop")
async def stop_stream(
    camera_id: uuid.UUID,
    _: User = Depends(get_current_user),
):
    mgr = _get_stream_manager(str(camera_id))
    mgr.stop()
    return {"status": "stopped", "camera_id": str(camera_id)}


@router.post("/{camera_id}/restart")
async def restart_stream(
    camera_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _: User = Depends(get_current_user),
):
    background_tasks.add_task(_do_restart, str(camera_id))
    return {"status": "restarting", "camera_id": str(camera_id)}


@router.get("/{camera_id}/snapshot")
async def get_latest_snapshot(
    camera_id: uuid.UUID,
    _: User = Depends(get_current_user),
):
    """Return latest JPEG frame as base64 from Redis."""
    from app.db.redis_client import get_redis
    redis = await get_redis()
    frame_b64 = await redis.get(f"camera:{camera_id}:latest_frame")
    if not frame_b64:
        raise HTTPException(status_code=404, detail="No frame available — stream may be offline")
    return {"camera_id": str(camera_id), "frame_b64": frame_b64}


@router.get("/{camera_id}/tracks")
async def get_latest_tracks(
    camera_id: uuid.UUID,
    _: User = Depends(get_current_user),
):
    """Return current track list from Redis."""
    from app.db.redis_client import get_redis
    import json
    redis = await get_redis()
    raw = await redis.get(f"camera:{camera_id}:tracks")
    if not raw:
        return {"tracks": [], "person_count": 0}
    return json.loads(raw)


def _do_start(camera_id: str):
    _get_stream_manager(camera_id).start()


def _do_restart(camera_id: str):
    _get_stream_manager(camera_id).restart()
