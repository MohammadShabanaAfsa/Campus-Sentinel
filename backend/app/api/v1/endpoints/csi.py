import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.models.csi import CSIScore
from app.models.user import User
from app.schemas.csi import CSIScoreResponse
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


@router.get("/campus")
async def get_campus_csi(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Live canonical campus score; does not depend on Celery or Redis cache."""
    from app.services.safety_index import get_campus_safety_index
    from loguru import logger
    try:
        return await get_campus_safety_index(db)
    except Exception:
        logger.exception("Cannot calculate campus CSI from database")
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Campus safety index temporarily unavailable")



@router.get("/latest", response_model=List[CSIScoreResponse])
async def get_latest_csi(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    """Return latest CSI score per camera."""
    result = await db.execute(
        select(CSIScore).order_by(CSIScore.recorded_at.desc()).limit(50)
    )
    return result.scalars().all()


@router.get("/history")
async def get_csi_history(
    camera_id: Optional[uuid.UUID] = Query(None),
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(hours=hours)
    query = select(CSIScore).where(CSIScore.recorded_at >= since).order_by(CSIScore.recorded_at.asc())
    if camera_id:
        query = query.where(CSIScore.camera_id == camera_id)
    result = await db.execute(query.limit(2000))
    scores = result.scalars().all()
    return [
        {
            "time": s.recorded_at.isoformat(),
            "score": s.overall_score,
            "risk_level": s.risk_level,
            "camera_id": str(s.camera_id) if s.camera_id else None,
        }
        for s in scores
    ]
