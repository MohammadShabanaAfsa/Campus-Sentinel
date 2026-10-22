import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from app.db.database import get_db
from app.models.prediction import Prediction
from app.models.user import User
from app.schemas.prediction import PredictionResponse
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


@router.get("/", response_model=List[PredictionResponse])
async def list_predictions(
    camera_id: Optional[uuid.UUID] = Query(None),
    threat_level: Optional[str] = Query(None),
    hours: int = Query(6, ge=1, le=48),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    since = datetime.utcnow() - timedelta(hours=hours)
    query = (
        select(Prediction)
        .where(Prediction.predicted_at >= since)
        .order_by(Prediction.predicted_at.desc())
        .limit(200)
    )
    if camera_id:
        query = query.where(Prediction.camera_id == camera_id)
    if threat_level:
        query = query.where(Prediction.threat_level == threat_level)
    result = await db.execute(query)
    return result.scalars().all()
