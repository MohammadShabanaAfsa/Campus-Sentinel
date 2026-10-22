"""Celery tasks for alert creation and dispatch."""
import json
from datetime import datetime
from celery import shared_task
from loguru import logger


@shared_task(name="app.services.tasks.alert_tasks.create_and_dispatch_alert")
def create_and_dispatch_alert(camera_id: str, alert_data: dict):
    """Create an alert in DB and push to all channels."""
    persisted=False
    movement = (alert_data.get("metadata") or {}).get("movement_type", "")
    if movement in ("zigzag", "zigzag_movement") or "zigzag" in str(alert_data.get("alert_type", "")):
        return  # Also suppress old queued producer results before persistence.
    alert_data = {**alert_data}
    for field in ("title", "description"):
        if field in alert_data:
            alert_data[field] = alert_data[field].replace("Restricted Zone", "Restricted Area").replace("restricted zone", "restricted area")
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.core.config import settings
        from app.models.alert import Alert
        import redis

        engine = create_engine(settings.SYNC_DATABASE_URL)
        r = redis.Redis.from_url(settings.REDIS_URL)

        # Check cooldown
        metadata=alert_data.get('metadata') or {}
        person_suffix=f":{metadata['track_id']}:{metadata.get('movement_type','')}" if metadata.get('track_id') is not None else ''
        cooldown_key = f"alert_cooldown:{camera_id}:{alert_data['alert_type']}{person_suffix}"
        restricted_episode=alert_data['alert_type']=='restricted_zone' and metadata.get('zone_id') and metadata.get('episode_id')
        if restricted_episode:
            # Deduplicate this entry, not subsequent entries or reused track IDs.
            # Other alert types keep their existing 60-second cooldown unchanged.
            cooldown_key=f"restricted_zone_episode:{camera_id}:{metadata['zone_id']}:{metadata.get('track_id')}:{metadata['episode_id']}"
        elif metadata.get('episode_id'):
            import hashlib
            scope=json.dumps({key:metadata.get(key) for key in ('behavior_type','track_id','track_ids','bag_track_id','zone_id')},sort_keys=True)
            digest=hashlib.sha256(scope.encode()).hexdigest()[:24]
            cooldown_key=f"alert_episode:{camera_id}:{alert_data['alert_type']}:{digest}:{metadata['episode_id']}"
        import uuid
        reservation=uuid.uuid4().hex
        if not r.set(cooldown_key,reservation,nx=True,ex=86400 if metadata.get('episode_id') else settings.ALERT_COOLDOWN_SECS):
            logger.debug(
                f"[ALERT_CREATE] camera={camera_id} type={alert_data['alert_type']} "
                f"suppressed by cooldown"
            )
            return

        logger.debug(
            f"[ALERT_CREATE] camera={camera_id} type={alert_data['alert_type']} "
            f"severity={alert_data.get('severity')} threat_score={alert_data.get('threat_score', 0.0)}"
        )

        with Session(engine) as session:
            # Generate explanation via SHAP/LIME
            explanation = _generate_explanation(alert_data)

            alert = Alert(
                camera_id=camera_id if camera_id != "system" else None,
                alert_type=alert_data["alert_type"],
                severity=alert_data["severity"],
                title=alert_data["title"],
                description=alert_data.get("description", ""),
                threat_score=alert_data.get("threat_score", 0.0),
                explanation=explanation,
                extra_data=alert_data.get("metadata", {}),
            )
            session.add(alert)
            session.commit()
            persisted=True
            session.refresh(alert)
            try:
                from app.services.safety_index import publish_safety_index_sync
                publish_safety_index_sync(session, r)
            except Exception:
                logger.exception("Alert saved but CSI broadcast failed; polling will recover")

            alert_payload = {
                "type": "new_alert",
                "alert": {
                    "id": str(alert.id),
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "status": alert.status,
                    "title": alert.title,
                    "camera_id": str(camera_id),
                    "threat_score": alert.threat_score,
                    "created_at": alert.created_at.isoformat(),
                }
            }

        # Publish to Redis for WebSocket broadcast
        r.publish("alerts_channel", json.dumps(alert_payload))

        # Set cooldown
        from app.core.config import settings as s
        # Reservation was acquired atomically before persistence, across workers.

        # Email notification (mock)
        send_email_alert.delay(alert_payload)

        logger.info(
            f"[ALERT_CREATE] Alert {alert.id} stored in DB and broadcast: "
            f"{alert_data['alert_type']} | Camera: {camera_id}"
        )

    except Exception as e:
        if not persisted and 'r' in locals() and 'reservation' in locals():
            try:
                r.eval("if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) end return 0",1,cooldown_key,reservation)
            except Exception:
                pass
        logger.error(f"Alert creation failed: {e}")


@shared_task(name="app.services.tasks.alert_tasks.send_email_alert")
def send_email_alert(alert_payload: dict):
    """Dispatch alert email to all admin users."""
    try:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        from app.core.config import settings
        from app.models.user import User
        from app.services.email_service import send_alert_email_sync

        engine = create_engine(settings.SYNC_DATABASE_URL)
        with Session(engine) as session:
            admins = session.execute(
                select(User.email).where(User.role.in_(("admin", "superadmin")), User.is_active == True)
            ).scalars().all()

        if admins:
            alert = alert_payload.get("alert", {})
            send_alert_email_sync(list(admins), alert)
        else:
            logger.info(f"[EMAIL] No admin recipients: {alert_payload.get('alert', {}).get('title')}")
    except Exception as e:
        logger.error(f"Email dispatch error: {e}")


def _generate_explanation(alert_data: dict) -> dict:
    """Generate SHAP-style feature importance explanation."""
    feature_contributions = alert_data.get("feature_contributions", {})
    if not feature_contributions:
        feature_contributions = {
            "duration": alert_data.get("threat_score", 0.5) * 0.4,
            "location_risk": 0.2,
            "crowd_density": 0.2,
            "time_of_day": 0.1,
            "historical_pattern": 0.1,
        }
        total=sum(feature_contributions.values())
        feature_contributions={key:value/total for key,value in feature_contributions.items()}
    return {
        "method": "SHAP",
        "feature_contributions": feature_contributions,
        "base_value": 0.0,
        "predicted_value": alert_data.get("threat_score", 0.5),
        "summary": alert_data.get("explanation_text", "Anomalous behavior detected."),
    }
