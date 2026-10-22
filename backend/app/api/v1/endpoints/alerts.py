import uuid
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.db.database import get_db
from app.models.alert import Alert
from app.models.user import User
from app.schemas.alert import AlertResponse, AlertUpdate, AlertStats
from app.api.v1.endpoints.auth import get_current_user

from app.services.safety_index import publish_campus_safety_index

router = APIRouter()


@router.get("/", response_model=List[AlertResponse])
async def list_alerts(
    skip: int = 0,
    limit: int = 50,
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    camera_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    # Preserve history in storage, but retired zigzag events are not user-facing.
    query = select(Alert).where(~Alert.title.ilike("%zig%zag%")).order_by(Alert.created_at.desc())
    if severity:
        query = query.where(Alert.severity == severity)
    if status:
        query = query.where(Alert.status == status)
    if camera_id:
        query = query.where(Alert.camera_id == camera_id)
    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/stats", response_model=AlertStats)
async def get_alert_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    since = datetime.utcnow() - timedelta(hours=24)
    total = await db.scalar(select(func.count(Alert.id)))
    active = await db.scalar(select(func.count(Alert.id)).where(Alert.status == "active"))
    critical = await db.scalar(select(func.count(Alert.id)).where(Alert.severity == "critical", Alert.status == "active"))
    high = await db.scalar(select(func.count(Alert.id)).where(Alert.severity == "high", Alert.status == "active"))
    medium = await db.scalar(select(func.count(Alert.id)).where(Alert.severity == "medium", Alert.status == "active"))
    low = await db.scalar(select(func.count(Alert.id)).where(Alert.severity == "low", Alert.status == "active"))
    last_24h = await db.scalar(select(func.count(Alert.id)).where(Alert.created_at >= since))
    return AlertStats(total=total, active=active, critical=critical, high=high, medium=medium, low=low, last_24h=last_24h)


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert or "zigzag" in alert.title.lower().replace("-", "").replace(" ", ""):
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: uuid.UUID,
    update_data: AlertUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if update_data.severity:
        alert.severity = update_data.severity
    if update_data.status:
        alert.status = update_data.status
        if update_data.status == "acknowledged":
            alert.acknowledged_by = current_user.id
            alert.acknowledged_at = datetime.utcnow()
        elif update_data.status in {"resolved", "dismissed"}:
            alert.resolved_at = datetime.utcnow()
        else:
            alert.resolved_at = None
    await db.commit()
    await db.refresh(alert)
    await publish_campus_safety_index(db)
    return alert


@router.delete("/{alert_id}", status_code=204)
async def delete_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.delete(alert)
    await db.commit()
    await publish_campus_safety_index(db)
