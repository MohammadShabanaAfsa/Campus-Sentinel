"""
Admin endpoints — triggered actions for super-users/operators.
Requires admin role.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from app.db.database import get_db
from app.models.user import User
from app.api.v1.endpoints.auth import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def _require_admin(current_user: User = Depends(get_current_user)) -> User:
    if getattr(current_user, "role", "viewer") not in ("admin", "superadmin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


@router.post("/train-abd")
async def trigger_abd_training(
    _: User = Depends(_require_admin),
):
    """Queue an immediate ABD model retraining job."""
    try:
        from app.services.tasks.analytics_tasks import train_abd_models
        task = train_abd_models.delay()
        return {"message": "ABD training queued", "task_id": task.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue training: {e}")


@router.post("/compute-csi")
async def trigger_csi_computation(
    _: User = Depends(_require_admin),
):
    """Trigger immediate CSI computation for all cameras."""
    try:
        from app.services.tasks.analytics_tasks import compute_campus_safety_index
        task = compute_campus_safety_index.delay()
        return {"message": "CSI computation queued", "task_id": task.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue CSI computation: {e}")


@router.post("/seed-data")
async def seed_development_data(
    days: int = 30,
    _: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Seed synthetic behavior data for development/testing (admin only)."""
    try:
        from sqlalchemy import select
        from app.models.camera import Camera

        result = await db.execute(select(Camera).where(Camera.is_active == True))
        cameras = result.scalars().all()

        if not cameras:
            raise HTTPException(status_code=400, detail="No active cameras found. Add cameras first.")

        from app.core.celery_app import celery_app

        @celery_app.task
        def _seed_task():
            from ai_engine.abd.data_seeder import seed_all_cameras
            seed_all_cameras(days=days)

        task = _seed_task.delay()
        return {
            "message": f"Seeding {days} days of data for {len(cameras)} cameras",
            "task_id": task.id,
            "camera_count": len(cameras),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send-digest")
async def send_daily_digest(
    _: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Send the daily security digest email to all admin users."""
    try:
        from sqlalchemy import select, func
        from app.models.user import User as UserModel
        from app.models.alert import Alert
        from app.models.csi import CSIScore
        from app.services.email_service import send_digest_email
        from datetime import datetime, timedelta

        since = datetime.utcnow() - timedelta(hours=24)

        # Gather stats
        alert_count = (await db.execute(
            select(func.count()).select_from(Alert).where(Alert.created_at >= since)
        )).scalar_one()

        top_alerts = (await db.execute(
            select(Alert).where(
                Alert.created_at >= since,
                Alert.severity.in_(["critical", "high"])
            ).order_by(Alert.created_at.desc()).limit(5)
        )).scalars().all()

        avg_csi_row = (await db.execute(
            select(func.avg(CSIScore.overall_score)).where(CSIScore.recorded_at >= since)
        )).scalar_one()

        admins = (await db.execute(
            select(UserModel.email).where(UserModel.role.in_(("admin", "superadmin")), UserModel.is_active == True)
        )).scalars().all()

        digest_data = {
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "total_alerts": alert_count,
            "avg_csi": float(avg_csi_row or 75.0),
            "top_alerts": [
                {"title": a.title, "severity": a.severity} for a in top_alerts
            ],
        }

        await send_digest_email(list(admins), digest_data)
        return {"message": f"Digest sent to {len(admins)} admin(s)", "recipients": list(admins)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
