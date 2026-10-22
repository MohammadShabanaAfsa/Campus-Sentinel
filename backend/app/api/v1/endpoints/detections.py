import uuid
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.models.detection import Detection
from app.models.user import User
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


@router.get("/")
async def list_detections(
    camera_id: Optional[uuid.UUID] = Query(None),
    object_class: Optional[str] = Query(None),
    since_minutes: int = Query(60, ge=1, le=1440),
    limit: int = Query(200, le=1000),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    since = datetime.utcnow() - timedelta(minutes=since_minutes)
    query = select(Detection).where(Detection.detected_at >= since).order_by(Detection.detected_at.desc()).limit(limit)
    if camera_id:
        query = query.where(Detection.camera_id == camera_id)
    if object_class:
        query = query.where(Detection.object_class == object_class)
    result = await db.execute(query)
    detections = result.scalars().all()
    return [
        {
            "id": d.id,
            "camera_id": str(d.camera_id),
            "detected_at": d.detected_at.isoformat(),
            "object_class": d.object_class,
            "confidence": d.confidence,
            "bbox": {"x": d.bbox_x, "y": d.bbox_y, "w": d.bbox_w, "h": d.bbox_h},
            "track_id": d.track_id,
        }
        for d in detections
    ]
