from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "campus_sentinel",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.services.tasks.ai_tasks",
        "app.services.tasks.alert_tasks",
        "app.services.tasks.analytics_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_routes={
        "app.services.tasks.ai_tasks.*": {"queue": "ai_tasks"},
        "app.services.tasks.alert_tasks.*": {"queue": "alerts"},
        "app.services.tasks.analytics_tasks.*": {"queue": "analytics"},
    },
    beat_schedule={
        "compute-csi-every-minute": {
            "task": "app.services.tasks.analytics_tasks.compute_campus_safety_index",
            "schedule": 60.0,
        },
        "train-abd-models-nightly": {
            "task": "app.services.tasks.analytics_tasks.train_abd_models",
            "schedule": 86400.0,
        },
        "cleanup-old-snapshots": {
            "task": "app.services.tasks.analytics_tasks.cleanup_old_snapshots",
            "schedule": 3600.0,
        },
        "send-daily-digest": {
            "task": "app.services.tasks.analytics_tasks.send_daily_digest_email",
            "schedule": 86400.0,  # once per day
        },
        "update-threat-predictions": {
            "task": "app.services.tasks.analytics_tasks.update_threat_predictions",
            "schedule": 300.0,  # every 5 minutes
        },
    },
)
