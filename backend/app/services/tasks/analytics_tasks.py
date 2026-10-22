"""Celery periodic tasks: CSI computation, ABD training, cleanup."""
from celery import shared_task
from loguru import logger


@shared_task(name="app.services.tasks.analytics_tasks.compute_campus_safety_index")
def compute_campus_safety_index():
    """Persist campus and per-camera snapshots using the same database formula."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.core.config import settings
    from app.models.camera import Camera
    from app.models.csi import CSIScore
    from app.services.safety_index import get_safety_index_sync, publish_safety_index_sync
    import redis
    engine = create_engine(settings.SYNC_DATABASE_URL)
    r = redis.Redis.from_url(settings.REDIS_URL)
    try:
        with Session(engine) as session:
            cameras = session.execute(select(Camera).where(Camera.is_active == True)).scalars().all()
            campus = get_safety_index_sync(session)
            snapshots = [(None, campus)] + [(camera.id, get_safety_index_sync(session, camera.id)) for camera in cameras]
            for camera_id, data in snapshots:
                session.add(CSIScore(
                    camera_id=camera_id,
                    **{key: data[key] for key in ("overall_score", "risk_level", "crowd_score", "loitering_score", "access_score", "anomaly_score")},
                    historical_score=data["overall_score"],
                    contributing_factors={"active_alerts": data["active_alerts"], "anomaly_count": data["anomaly_count"], "recent_events": data["recent_events"]},
                ))
            session.commit()
            publish_safety_index_sync(session, r)
        logger.info("Database-backed CSI computation complete")
    except Exception:
        logger.exception("CSI computation failed")
    finally:
        r.close()
        engine.dispose()


@shared_task(name="app.services.tasks.analytics_tasks.train_abd_models")
def train_abd_models():
    """Nightly retraining of Adaptive Behavioral DNA models."""
    try:
        from ai_engine.abd.trainer import ABDTrainer
        trainer = ABDTrainer()
        trainer.train_all_zones()
        logger.info("ABD model training complete")
    except Exception as e:
        logger.error(f"ABD training failed: {e}")


@shared_task(name="app.services.tasks.analytics_tasks.cleanup_old_snapshots")
def cleanup_old_snapshots():
    """Remove alert snapshot images older than 7 days."""
    import os
    import glob
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(days=7)
    snapshot_dir = "/app/snapshots"
    if not os.path.exists(snapshot_dir):
        return

    count = 0
    for f in glob.glob(f"{snapshot_dir}/*.jpg"):
        mtime = datetime.fromtimestamp(os.path.getmtime(f))
        if mtime < cutoff:
            os.remove(f)
            count += 1

    logger.info(f"Cleaned up {count} old snapshots")



from app.services.safety_index import score_to_level as _score_to_level


@shared_task(name="app.services.tasks.analytics_tasks.send_daily_digest_email")
def send_daily_digest_email():
    """Send daily security digest to all admin users."""
    try:
        from sqlalchemy import create_engine, select, func
        from sqlalchemy.orm import Session
        from app.core.config import settings
        from app.models.user import User
        from app.models.alert import Alert
        from app.models.csi import CSIScore
        from app.services.email_service import send_alert_email_sync
        from datetime import datetime, timedelta
        import asyncio

        engine = create_engine(settings.SYNC_DATABASE_URL)
        since = datetime.utcnow() - timedelta(hours=24)

        with Session(engine) as session:
            admins = session.execute(
                select(User.email).where(User.role.in_(("admin", "superadmin")), User.is_active == True)
            ).scalars().all()

            total_alerts = session.execute(
                select(func.count()).select_from(Alert).where(Alert.created_at >= since)
            ).scalar_one()

            top_alerts = session.execute(
                select(Alert).where(
                    Alert.created_at >= since,
                    Alert.severity.in_(["critical", "high"])
                ).order_by(Alert.created_at.desc()).limit(5)
            ).scalars().all()

            avg_csi = session.execute(
                select(func.avg(CSIScore.overall_score)).where(CSIScore.recorded_at >= since)
            ).scalar_one()

        if not admins:
            return

        from app.services.email_service import send_digest_email
        import asyncio

        digest_data = {
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "total_alerts": total_alerts,
            "avg_csi": float(avg_csi or 75.0),
            "top_alerts": [{"title": a.title, "severity": a.severity} for a in top_alerts],
        }

        loop = asyncio.new_event_loop()
        loop.run_until_complete(send_digest_email(list(admins), digest_data))
        loop.close()
        logger.info(f"Daily digest sent to {len(admins)} admin(s)")

    except Exception as e:
        logger.error(f"Daily digest failed: {e}")


@shared_task(name="app.services.tasks.analytics_tasks.update_threat_predictions")
def update_threat_predictions():
    """Run RF threat predictor for all active cameras and store results."""
    try:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        from app.core.config import settings
        from app.models.camera import Camera
        from app.models.prediction import Prediction
        import redis
        import json

        engine = create_engine(settings.SYNC_DATABASE_URL)
        r = redis.Redis.from_url(settings.REDIS_URL)

        with Session(engine) as session:
            cameras = session.execute(
                select(Camera).where(Camera.is_active == True, Camera.status == "online")
            ).scalars().all()

            for camera in cameras:
                cam_id = str(camera.id)
                raw = r.get(f"camera:{cam_id}:behavior_state")
                if not raw:
                    continue
                state = json.loads(raw)

                # Build feature vector
                import datetime as dt
                now = dt.datetime.utcnow()
                feature_vector = [
                    now.hour / 23.0,
                    now.weekday() / 6.0,
                    min(state.get("crowd_count", 0) / 50.0, 1.0),
                    state.get("anomaly_score", 0.0),
                    0.0,  # duration_norm
                    0.0,  # prev_person_count
                    0.0,  # prev_risk
                    min(state.get("loitering_count", 0) / 5.0, 1.0),
                    min(state.get("crowd_count", 0) / 10.0, 1.0),
                ]

                from ai_engine.prediction.threat_predictor import ThreatPredictor
                predictor = ThreatPredictor.get_instance(cam_id)
                results = predictor.predict(feature_vec=feature_vector, behavior_state=state)
                logger.debug(f"[THREAT_SCORE] camera={cam_id} predictions={results}")

                for threat_type, threat_data in results.items():
                    pred = Prediction(
                        camera_id=camera.id,
                        threat_type=threat_type,
                        probability=threat_data["probability"],
                        threat_level=threat_data["threat_level"],
                        recommended_action=threat_data["recommended_action"],
                        model_version=threat_data.get("model_version", "1.0.0"),
                        feature_importance={"feature_vector": feature_vector},
                    )
                    session.add(pred)

                # Cache latest predictions in Redis
                r.set(f"camera:{cam_id}:predictions", json.dumps(results), ex=360)

            session.commit()

        # Publish to WebSocket
        all_predictions = {}
        for camera in cameras:
            raw = r.get(f"camera:{str(camera.id)}:predictions")
            if raw:
                all_predictions[str(camera.id)] = json.loads(raw)

        if all_predictions:
            r.publish("csi_updates", json.dumps({
                "type": "predictions_update",
                "predictions": all_predictions,
            }))

        logger.info(f"Threat predictions updated for {len(cameras)} cameras")

    except Exception as e:
        logger.error(f"Threat prediction update failed: {e}")
