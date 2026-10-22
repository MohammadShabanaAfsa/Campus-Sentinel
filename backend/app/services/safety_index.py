"""Canonical CSI: recent database alerts and incidents, with severity/time decay.

Component values are safety scores (100 means no matching recent events),
not detector counts or raw anomaly probabilities. Each database record is
counted once; alerts and manually recorded incidents are separate records.
"""
import json
from datetime import datetime, timedelta, timezone
from loguru import logger

SEVERITY_PENALTIES = {"low": 2, "medium": 5, "high": 10, "critical": 20}
RESOLVED_STATUSES = {"resolved", "closed", "dismissed"}
COMPONENT_TYPES = {
    "crowd": {"crowd", "crowd_surge", "crowd_density", "overcrowding", "crowd_formation"},
    "loitering": {"loitering", "prolonged_presence"},
    "access": {"unauthorized_access", "zone_violation", "restricted_zone", "intrusion"},
    "anomaly": {"anomaly", "behavioral_anomaly", "abd_anomaly", "unusual_behavior", "abnormal_movement"},
}


def score_to_level(score):
    for threshold, level in ((90, "safe"), (75, "low_risk"), (60, "moderate"), (40, "high_risk")):
        if score >= threshold:
            return level
    return "critical"


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def calculate_campus_safety_index(events, now=None):
    """Pure calculation accepting Alert/Incident objects or matching dictionaries."""
    now = _utc(now or datetime.now(timezone.utc))
    penalty = 0.0
    component_penalties = {name: 0.0 for name in COMPONENT_TYPES}
    active_alerts = anomaly_count = recent_events = 0
    for event in events:
        get = event.get if isinstance(event, dict) else lambda key, default=None: getattr(event, key, default)
        created_at = get("created_at")
        if created_at is None:
            logger.warning("Skipping CSI event without a creation timestamp")
            continue
        age_hours = max(0.0, (now - _utc(created_at)).total_seconds() / 3600)
        age_factor = max(0.0, 1 - age_hours / 24)
        if age_factor == 0:
            continue
        severity = str(get("severity", "medium")).lower()
        if severity not in SEVERITY_PENALTIES:
            logger.warning(f"Unknown CSI severity {severity!r}; applying medium penalty")
        resolved = str(get("status", "open")).lower() in RESOLVED_STATUSES
        impact = SEVERITY_PENALTIES.get(severity, 5) * age_factor * (0.25 if resolved else 1.0)
        penalty += impact
        recent_events += 1
        active_alerts += int(not resolved)
        event_type = str(get("alert_type") or get("incident_type", "")).lower()
        for component, types in COMPONENT_TYPES.items():
            if event_type in types:
                component_penalties[component] += impact
                if component == "anomaly":
                    anomaly_count += 1

    def safety(value):
        return max(0, min(100, round(100 - value)))

    score = safety(penalty)
    components = {name: safety(value) for name, value in component_penalties.items()}
    return {
        "overall_score": score,
        "risk_level": score_to_level(score),
        **{f"{name}_score": value for name, value in components.items()},
        "active_alerts": active_alerts,
        "anomaly_count": anomaly_count,
        "recent_events": recent_events,
        "updated_at": now.isoformat(),
    }


def event_queries(now, camera_id=None):
    from sqlalchemy import select
    from app.models.alert import Alert
    from app.models.incident import Incident
    since = now - timedelta(hours=24)
    queries = [select(model).where(model.created_at >= since) for model in (Alert, Incident)]
    if camera_id is not None:
        queries = [query.where(model.camera_id == camera_id) for query, model in zip(queries, (Alert, Incident))]
    return queries


async def get_campus_safety_index(db):
    now = datetime.now(timezone.utc)
    events = []
    for query in event_queries(now):
        result = await db.execute(query)
        events.extend(result.scalars().all())
    return calculate_campus_safety_index(events, now)


def get_safety_index_sync(session, camera_id=None):
    now = datetime.now(timezone.utc)
    events = []
    for query in event_queries(now, camera_id):
        events.extend(session.execute(query).scalars().all())
    return calculate_campus_safety_index(events, now)


def csi_message(data):
    return {"type": "csi_update", "overall": data["overall_score"], **data}


async def publish_campus_safety_index(db):
    """After a committed mutation; failures preserve the mutation and polling recovers."""
    try:
        from app.db.redis_client import get_redis
        data = await get_campus_safety_index(db)
        redis = await get_redis()
        await redis.publish("csi_updates", json.dumps(csi_message(data)))
        return data
    except Exception:
        logger.exception("CSI recalculation/broadcast failed after database mutation; polling will retry")


def publish_safety_index_sync(session, redis):
    data = get_safety_index_sync(session)
    redis.set("campus:csi:overall", json.dumps(data), ex=120)
    redis.publish("csi_updates", json.dumps(csi_message(data)))
    return data
