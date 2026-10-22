from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from datetime import datetime, timedelta
from app.db.database import get_db
from app.models.detection import Detection
from app.models.alert import Alert
from app.models.behavior import BehaviorLog
from app.models.user import User
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


@router.get("/summary")
async def get_analytics_summary(
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    since = datetime.utcnow() - timedelta(hours=hours)

    total_detections = await db.scalar(
        select(func.count(Detection.id)).where(Detection.detected_at >= since)
    )
    person_detections = await db.scalar(
        select(func.count(Detection.id)).where(
            Detection.detected_at >= since,
            Detection.object_class == "person"
        )
    )
    total_alerts = await db.scalar(
        select(func.count(Alert.id)).where(Alert.created_at >= since)
    )
    critical_alerts = await db.scalar(
        select(func.count(Alert.id)).where(
            Alert.created_at >= since,
            Alert.severity == "critical"
        )
    )
    behavior_anomalies = await db.scalar(
        select(func.count(BehaviorLog.id)).where(BehaviorLog.logged_at >= since)
    )

    return {
        "period_hours": hours,
        "total_detections": total_detections or 0,
        "person_detections": person_detections or 0,
        "total_alerts": total_alerts or 0,
        "critical_alerts": critical_alerts or 0,
        "behavior_anomalies": behavior_anomalies or 0,
        "generated_at": datetime.utcnow().isoformat(),
    }


@router.get("/detections/by-hour")
async def detections_by_hour(
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        text("""
            SELECT
                date_trunc('hour', detected_at) AS hour,
                object_class,
                COUNT(*) AS count
            FROM detections
            WHERE detected_at >= :since
            GROUP BY hour, object_class
            ORDER BY hour ASC
        """),
        {"since": since}
    )
    rows = result.fetchall()
    return [{"hour": str(r[0]), "object_class": r[1], "count": r[2]} for r in rows]


@router.get("/behavior/distribution")
async def behavior_distribution(
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(BehaviorLog.behavior_type, func.count(BehaviorLog.id).label("count"))
        .where(BehaviorLog.logged_at >= since)
        .group_by(BehaviorLog.behavior_type)
    )
    rows = result.fetchall()
    return [{"behavior_type": r[0], "count": r[1]} for r in rows]
