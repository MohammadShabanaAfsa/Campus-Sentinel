import uuid
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.models.camera import Camera
from app.models.classroom import ClassroomConfig, ClassroomMetric
from app.models.user import User
from app.schemas.classroom import (
    ClassroomConfigUpdate, ClassroomConfigResponse,
    ClassroomMetricResponse, ClassroomOverviewItem,
)
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


async def _get_classroom_camera(db: AsyncSession, camera_id: uuid.UUID) -> Camera:
    camera = await db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    if camera.zone_type != "classroom":
        raise HTTPException(status_code=400, detail="Camera is not configured as a classroom")
    return camera


@router.get("/", response_model=List[ClassroomOverviewItem])
async def list_classrooms(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Multi-classroom monitoring overview — every classroom-tagged camera
    with its most recent Class Attention Index snapshot."""
    cameras = (await db.execute(
        select(Camera).where(Camera.zone_type == "classroom")
    )).scalars().all()

    overview = []
    for cam in cameras:
        latest = (await db.execute(
            select(ClassroomMetric)
            .where(ClassroomMetric.camera_id == cam.id)
            .order_by(ClassroomMetric.recorded_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        overview.append(ClassroomOverviewItem(
            camera_id=cam.id,
            camera_name=cam.name,
            location_name=cam.location_name,
            status=cam.status,
            latest_metric=latest,
        ))
    return overview


@router.get("/{camera_id}/config", response_model=ClassroomConfigResponse)
async def get_classroom_config(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    await _get_classroom_camera(db, camera_id)
    config = await db.get(ClassroomConfig, camera_id)
    if not config:
        # Auto-create with defaults on first access, so the dashboard always
        # has something to render/edit.
        config = ClassroomConfig(camera_id=camera_id)
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config


@router.put("/{camera_id}/config", response_model=ClassroomConfigResponse)
async def update_classroom_config(
    camera_id: uuid.UUID,
    data: ClassroomConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    await _get_classroom_camera(db, camera_id)
    config = await db.get(ClassroomConfig, camera_id)
    if not config:
        config = ClassroomConfig(camera_id=camera_id)
        db.add(config)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(config, field, value)

    await db.commit()
    await db.refresh(config)

    # If this camera's stream is already running, refresh its live monitor's
    # config immediately rather than waiting for a stream/backend restart.
    from ai_engine.classroom.classroom_monitor import ClassroomMonitor
    cam_id_str = str(camera_id)
    if cam_id_str in ClassroomMonitor._instances:
        ClassroomMonitor._instances[cam_id_str].refresh_config()

    return config


@router.get("/{camera_id}/metrics/latest", response_model=Optional[ClassroomMetricResponse])
async def get_latest_metric(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    await _get_classroom_camera(db, camera_id)
    result = await db.execute(
        select(ClassroomMetric)
        .where(ClassroomMetric.camera_id == camera_id)
        .order_by(ClassroomMetric.recorded_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/{camera_id}/metrics/history", response_model=List[ClassroomMetricResponse])
async def get_metric_history(
    camera_id: uuid.UUID,
    hours: int = Query(4, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    await _get_classroom_camera(db, camera_id)
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(ClassroomMetric)
        .where(ClassroomMetric.camera_id == camera_id, ClassroomMetric.recorded_at >= since)
        .order_by(ClassroomMetric.recorded_at.asc())
        .limit(2000)
    )
    return result.scalars().all()
