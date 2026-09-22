"""
ABD Data Seeder — generates realistic synthetic behavior_logs for the last 30 days
so ABD models can be trained immediately without waiting for real camera data.

Usage:
    python -m ai_engine.abd.data_seeder --camera-id <uuid> [--days 30]
"""
import argparse
import random
import uuid
from datetime import datetime, timedelta
from typing import List
from loguru import logger


ZONE_PROFILES = {
    "entrance": {
        "peak_hours": [8, 9, 12, 13, 17, 18],
        "base_person": (5, 20),
        "peak_person": (20, 60),
        "behaviors": ["normal_movement", "loitering", "crowd_density"],
        "risk_base": 0.05,
    },
    "corridor": {
        "peak_hours": [8, 9, 10, 11, 12, 13, 14, 15, 16, 17],
        "base_person": (1, 5),
        "peak_person": (5, 25),
        "behaviors": ["normal_movement", "running", "loitering"],
        "risk_base": 0.03,
    },
    "parking": {
        "peak_hours": [7, 8, 17, 18, 19],
        "base_person": (0, 3),
        "peak_person": (5, 15),
        "behaviors": ["normal_movement", "loitering"],
        "risk_base": 0.08,
    },
    "restricted": {
        "peak_hours": [],
        "base_person": (0, 1),
        "peak_person": (0, 2),
        "behaviors": ["zone_violation", "loitering"],
        "risk_base": 0.15,
    },
    "canteen": {
        "peak_hours": [10, 11, 12, 13, 14, 19, 20],
        "base_person": (3, 10),
        "peak_person": (30, 80),
        "behaviors": ["crowd_density", "crowd_formation", "normal_movement"],
        "risk_base": 0.04,
    },
    "general": {
        "peak_hours": [9, 10, 11, 12, 13, 14, 15, 16],
        "base_person": (2, 10),
        "peak_person": (10, 30),
        "behaviors": ["normal_movement", "loitering"],
        "risk_base": 0.05,
    },
}


def _person_count(hour: int, profile: dict) -> int:
    lo, hi = profile["peak_person"] if hour in profile["peak_hours"] else profile["base_person"]
    return int(random.gauss((lo + hi) / 2, (hi - lo) / 4))


def _risk_score(person_count: int, profile: dict, is_weekend: bool) -> float:
    base = profile["risk_base"]
    crowd_factor = min(1.0, person_count / 50) * 0.3
    weekend_factor = -0.02 if is_weekend else 0.0
    noise = random.gauss(0, 0.03)
    return max(0.0, min(1.0, base + crowd_factor + weekend_factor + noise))


def _behavior_type(hour: int, profile: dict, person_count: int) -> str:
    behaviors = profile["behaviors"]
    if person_count > 40 and "crowd_density" in behaviors:
        return "crowd_density"
    if hour not in profile["peak_hours"] and person_count > 1 and "loitering" in behaviors:
        return random.choice(["loitering", "normal_movement"])
    return random.choice(behaviors)


def generate_logs(camera_id: str, zone_type: str, days: int = 30) -> List[dict]:
    profile = ZONE_PROFILES.get(zone_type, ZONE_PROFILES["general"])
    logs = []
    now = datetime.utcnow()
    start = now - timedelta(days=days)
    current = start

    while current < now:
        hour = current.hour
        is_weekend = current.weekday() >= 5

        # Generate 2–4 log entries per hour (every 15-30 min)
        entries_in_hour = random.randint(2, 4)
        for i in range(entries_in_hour):
            minutes_offset = i * (60 // entries_in_hour) + random.randint(-5, 5)
            ts = current + timedelta(minutes=minutes_offset)
            if ts >= now:
                break

            person_count = max(0, _person_count(hour, profile))
            risk = _risk_score(person_count, profile, is_weekend)
            btype = _behavior_type(hour, profile, person_count)

            logs.append({
                "camera_id": camera_id,
                "behavior_type": btype,
                "person_count": person_count,
                "risk_score": round(risk, 4),
                "duration_secs": random.randint(10, 300) if btype == "loitering" else 0,
                "track_ids": [],
                "metadata": {
                    "seeded": True,
                    "hour": hour,
                    "is_weekend": is_weekend,
                },
                "logged_at": ts,
            })

        current += timedelta(hours=1)

    return logs


def seed_camera(camera_id: str, zone_type: str, days: int = 30):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import settings
    from app.models.behavior import BehaviorLog

    engine = create_engine(settings.SYNC_DATABASE_URL)
    logs = generate_logs(camera_id, zone_type, days)

    logger.info(f"Seeding {len(logs)} behavior logs for camera {camera_id} ({zone_type})")
    with Session(engine) as session:
        for log_data in logs:
            log = BehaviorLog(
                camera_id=uuid.UUID(camera_id),
                behavior_type=log_data["behavior_type"],
                person_count=log_data["person_count"],
                risk_score=log_data["risk_score"],
                duration_secs=log_data["duration_secs"],
                track_ids=log_data["track_ids"],
                metadata=log_data["metadata"],
                logged_at=log_data["logged_at"],
            )
            session.add(log)
        session.commit()

    logger.success(f"Seeded {len(logs)} logs for camera {camera_id}")
    return len(logs)


def seed_all_cameras(days: int = 30):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.core.config import settings
    from app.models.camera import Camera

    engine = create_engine(settings.SYNC_DATABASE_URL)
    with Session(engine) as session:
        cameras = session.execute(select(Camera).where(Camera.is_active == True)).scalars().all()

    total = 0
    for camera in cameras:
        count = seed_camera(str(camera.id), camera.zone_type, days)
        total += count

    logger.success(f"Seeded {total} total logs across {len(cameras)} cameras")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed ABD training data")
    parser.add_argument("--camera-id", help="Specific camera UUID (omit for all cameras)")
    parser.add_argument("--zone-type", default="general", help="Zone type if seeding one camera")
    parser.add_argument("--days", type=int, default=30, help="Days of history to generate")
    args = parser.parse_args()

    if args.camera_id:
        seed_camera(args.camera_id, args.zone_type, args.days)
    else:
        seed_all_cameras(args.days)
