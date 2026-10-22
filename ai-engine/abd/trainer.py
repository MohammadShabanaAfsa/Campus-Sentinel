"""
Adaptive Behavioral DNA (ABD) Trainer.
Learns normal behavior profiles per camera zone using Isolation Forest.
"""
import numpy as np
import pickle
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from loguru import logger
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


class ABDTrainer:
    MODEL_DIR = "/app/models/abd"

    def __init__(self):
        os.makedirs(self.MODEL_DIR, exist_ok=True)

    def train_all_zones(self):
        """Fetch historical data and train ABD models per camera/hour/day slot."""
        try:
            from sqlalchemy import create_engine, select, text
            from sqlalchemy.orm import Session
            from app.core.config import settings
            from app.models.camera import Camera
            from app.models.abd import ABDProfile

            engine = create_engine(settings.SYNC_DATABASE_URL)

            with Session(engine) as session:
                cameras = session.execute(select(Camera).where(Camera.is_active == True)).scalars().all()

                for camera in cameras:
                    logger.info(f"Training ABD for camera {camera.id} ({camera.name})")
                    self._train_camera(session, str(camera.id), camera.zone_type)

        except Exception as e:
            logger.error(f"ABD training failed: {e}")

    def _train_camera(self, session, camera_id: str, zone_type: str):
        """Train 168 models (24h × 7days) per camera."""
        from sqlalchemy import text

        for day_of_week in range(7):
            for hour_of_day in range(24):
                features = self._extract_features(session, camera_id, hour_of_day, day_of_week)
                if len(features) < 10:
                    continue

                X = np.array(features)
                scaler = StandardScaler()
                X_scaled = scaler.fit_transform(X)

                model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
                model.fit(X_scaled)

                model_key = f"{camera_id}_{day_of_week}_{hour_of_day}"
                model_path = os.path.join(self.MODEL_DIR, f"{model_key}.pkl")

                with open(model_path, "wb") as f:
                    pickle.dump({"model": model, "scaler": scaler}, f)

                # Update ABD profile in DB
                self._update_profile(session, camera_id, zone_type, hour_of_day, day_of_week, X, model_path)

        session.commit()

    def _extract_features(self, session, camera_id: str, hour_of_day: int, day_of_week: int) -> List[List[float]]:
        """Extract feature vectors from historical behavior logs."""
        from sqlalchemy import text

        result = session.execute(
            text("""
                SELECT
                    AVG(person_count)::float,
                    MAX(person_count)::float,
                    AVG(risk_score)::float,
                    AVG(duration_secs)::float,
                    COUNT(*)::float
                FROM behavior_logs
                WHERE camera_id = :camera_id
                    AND EXTRACT(DOW FROM logged_at) = :dow
                    AND EXTRACT(HOUR FROM logged_at) = :hour
                    AND logged_at >= NOW() - INTERVAL '30 days'
                GROUP BY date_trunc('hour', logged_at)
            """),
            {"camera_id": camera_id, "dow": day_of_week, "hour": hour_of_day}
        )
        rows = result.fetchall()
        return [[float(v or 0) for v in row] for row in rows]

    def _update_profile(self, session, camera_id: str, zone_type: str,
                        hour_of_day: int, day_of_week: int, X: np.ndarray, model_path: str):
        from app.models.abd import ABDProfile
        from sqlalchemy import select
        import uuid

        result = session.execute(
            select(ABDProfile).where(
                ABDProfile.camera_id == uuid.UUID(camera_id),
                ABDProfile.hour_of_day == hour_of_day,
                ABDProfile.day_of_week == day_of_week,
            )
        ).scalar_one_or_none()

        if result:
            result.avg_person_count = float(X[:, 0].mean())
            result.max_person_count = float(X[:, 1].max())
            result.avg_movement_speed = 0.0
            result.sample_count = len(X)
            result.model_path = model_path
            result.last_trained = datetime.utcnow()
        else:
            profile = ABDProfile(
                camera_id=uuid.UUID(camera_id),
                zone_type=zone_type,
                hour_of_day=hour_of_day,
                day_of_week=day_of_week,
                avg_person_count=float(X[:, 0].mean()),
                max_person_count=float(X[:, 1].max()),
                sample_count=len(X),
                model_path=model_path,
                last_trained=datetime.utcnow(),
            )
            session.add(profile)


class ABDScorer:
    """Real-time anomaly scoring using trained ABD models."""

    def __init__(self, camera_id: str, model_dir: str = "/app/models/abd"):
        self.camera_id = camera_id
        self.model_dir = model_dir
        self._model_cache: Dict = {}

    def score(self, feature_vector: List[float]) -> float:
        """Return anomaly score 0–1 (1 = most anomalous)."""
        now = datetime.utcnow()
        hour = now.hour
        dow = now.weekday()
        key = f"{self.camera_id}_{dow}_{hour}"
        model_path = os.path.join(self.model_dir, f"{key}.pkl")

        if not os.path.exists(model_path):
            return 0.0

        if key not in self._model_cache:
            with open(model_path, "rb") as f:
                self._model_cache[key] = pickle.load(f)

        bundle = self._model_cache[key]
        X = np.array([feature_vector])
        X_scaled = bundle["scaler"].transform(X)
        score = bundle["model"].score_samples(X_scaled)[0]
        # Isolation Forest: more negative = more anomalous
        normalized = max(0.0, min(1.0, (-score + 0.5)))
        return float(normalized)
