"""
Behavior Agent — receives tracks and runs behavioral analytics:
- Loitering
- Crowd density
- Abnormal movement
- Zone violations
- ABD anomaly scoring
"""
from loguru import logger
from agents.orchestrator.agent_bus import AgentBus


class BehaviorAgent:
    NAME = "BehaviorAgent"

    def __init__(self):
        self.bus = AgentBus.get_instance()
        self._loitering_detectors = {}
        self._crowd_analyzers = {}
        self._movement_analyzers = {}
        self._zone_checkers = {}
        self._abd_scorers = {}

    def start(self):
        self.bus.subscribe("tracks", self._on_tracks)
        logger.info(f"{self.NAME} started")

    def _on_tracks(self, message: dict):
        try:
            camera_id = message["camera_id"]
            tracks = message["tracks"]
            frame_w = message.get("frame_width", 1920)
            frame_h = message.get("frame_height", 1080)
            logger.debug(f"[BEHAVIOR] camera={camera_id} received {len(tracks)} tracks for analysis")

            # Run all behavioral analyzers
            all_behaviors = []
            all_behaviors.extend(self._run_loitering(camera_id, tracks))
            all_behaviors.extend(self._run_crowd(camera_id, tracks))
            all_behaviors.extend(self._run_movement(camera_id, tracks))
            all_behaviors.extend(self._run_zones(camera_id, tracks, frame_w, frame_h))
            logger.debug(f"[BEHAVIOR] camera={camera_id} {len(all_behaviors)} behavior(s) flagged by analyzers")

            # Compute ABD anomaly score
            anomaly_score = self._run_abd(camera_id, tracks)
            logger.debug(f"[ABD] camera={camera_id} anomaly_score={anomaly_score:.3f}")

            behavior_state = {
                "camera_id": camera_id,
                "timestamp": message.get("timestamp"),
                "person_count": sum(1 for t in tracks if t.get("class_name") == "person"),
                "anomaly_score": anomaly_score,
                "behaviors": all_behaviors,
                "crowd_count": sum(1 for t in tracks if t.get("class_name") == "person"),
                "loitering_count": sum(1 for b in all_behaviors if b["alert_type"] == "loitering"),
                "zone_violations": sum(1 for b in all_behaviors if b["alert_type"] == "restricted_zone"),
                "formation_density": 0.0,
            }

            # Update Redis behavior state
            self._update_redis_state(camera_id, behavior_state)

            # Persist to behavior_logs (was computed live but never written to DB)
            self._persist_behavior_log(camera_id, behavior_state)

            # Publish to prediction agent
            self.bus.publish("behaviors", behavior_state)

            if all_behaviors:
                logger.info(f"{self.NAME}: {len(all_behaviors)} behaviors detected on camera {camera_id}")

        except Exception as e:
            logger.error(f"{self.NAME} error: {e}")

    def _run_loitering(self, camera_id: str, tracks: list) -> list:
        from ai_engine.behavioral.loitering import LoiteringDetector
        if camera_id not in self._loitering_detectors:
            self._loitering_detectors[camera_id] = LoiteringDetector(camera_id=camera_id)
        return self._loitering_detectors[camera_id].analyze(tracks)

    def _run_crowd(self, camera_id: str, tracks: list) -> list:
        from ai_engine.behavioral.crowd import CrowdAnalyzer
        if camera_id not in self._crowd_analyzers:
            self._crowd_analyzers[camera_id] = CrowdAnalyzer(camera_id=camera_id)
        return self._crowd_analyzers[camera_id].analyze(tracks)

    def _run_movement(self, camera_id: str, tracks: list) -> list:
        from ai_engine.behavioral.movement import MovementAnalyzer
        if camera_id not in self._movement_analyzers:
            self._movement_analyzers[camera_id] = MovementAnalyzer(camera_id=camera_id)
        return self._movement_analyzers[camera_id].analyze(tracks)

    def _run_zones(self, camera_id: str, tracks: list, frame_w: int = 1920, frame_h: int = 1080) -> list:
        from ai_engine.behavioral.zone_checker import ZoneChecker
        if camera_id not in self._zone_checkers:
            self._zone_checkers[camera_id] = ZoneChecker(camera_id=camera_id)
        return self._zone_checkers[camera_id].analyze(tracks, frame_w, frame_h)

    def _run_abd(self, camera_id: str, tracks: list) -> float:
        try:
            from ai_engine.abd.trainer import ABDScorer
            if camera_id not in self._abd_scorers:
                self._abd_scorers[camera_id] = ABDScorer(camera_id=camera_id)
            person_count = sum(1 for t in tracks if t.get("class_name") == "person")
            feature_vec = [person_count, 0.0, 0.0, 0.0, 0.0]
            score = self._abd_scorers[camera_id].score(feature_vec)
            logger.debug(f"[ABD] camera={camera_id} feature_vec={feature_vec} score={score:.3f}")
            return score
        except Exception as e:
            logger.warning(f"[ABD] camera={camera_id} scoring failed, defaulting to 0.0: {e}")
            return 0.0

    # behavior_logs.behavior_type has a DB CHECK constraint against this fixed
    # enum. A couple of analyzers emit values outside it (zone_checker's
    # "restricted_zone", crowd.py's "crowd_density") — those are distinct from
    # this DB constraint's vocabulary, so filter to only what's persistable
    # rather than renaming the analyzers' own alert_type values elsewhere.
    _PERSISTABLE_TYPES = {
        "loitering", "running", "crowd_surge", "restricted_access",
        "abandoned_object", "fight_detected", "abnormal_movement",
        "crowd_formation", "congestion",
    }

    def _persist_behavior_log(self, camera_id: str, state: dict):
        behaviors = [b for b in state["behaviors"] if b["alert_type"] in self._PERSISTABLE_TYPES]
        if not behaviors:
            return
        try:
            from sqlalchemy.orm import Session
            from app.models.behavior import BehaviorLog
            engine = self._get_sync_engine()
            with Session(engine) as session:
                for b in behaviors:
                    session.add(BehaviorLog(
                        camera_id=camera_id,
                        behavior_type=b["alert_type"],
                        person_count=state["person_count"],
                        risk_score=state["anomaly_score"],
                        details={**state, "behavior_detail": b},
                    ))
                session.commit()
        except Exception as e:
            logger.warning(f"[ABD] camera={camera_id} behavior_log persist failed: {e}")

    def _get_sync_engine(self):
        if not hasattr(self, "_sync_engine"):
            from sqlalchemy import create_engine
            from app.core.config import settings
            self._sync_engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True)
        return self._sync_engine

    def _update_redis_state(self, camera_id: str, state: dict):
        import redis as r
        import json
        from app.core.config import settings
        client = r.Redis.from_url(settings.REDIS_URL)
        client.set(f"camera:{camera_id}:behavior_state", json.dumps(state), ex=120)
