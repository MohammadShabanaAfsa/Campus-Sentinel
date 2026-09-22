"""
Decision Agent — evaluates threats, calculates CSI, and creates alerts.
"""
from loguru import logger
from agents.orchestrator.agent_bus import AgentBus


class DecisionAgent:
    NAME = "DecisionAgent"

    def __init__(self):
        self.bus = AgentBus.get_instance()

    def start(self):
        self.bus.subscribe("threats", self._on_threats)
        logger.info(f"{self.NAME} started")

    def _on_threats(self, message: dict):
        try:
            from app.core.config import settings

            camera_id = message["camera_id"]
            # PredictionAgent publishes predictions as a dict keyed by threat_type
            # (see ThreatPredictor.predict), not a list — iterate .values().
            predictions = list(message.get("predictions", {}).values())
            behavior_state = message.get("behavior_state", {})

            # Build alert decisions for threats exceeding the configured threshold
            decisions = []
            for pred in predictions:
                exceeds = pred["probability"] >= settings.THREAT_ALERT_THRESHOLD
                logger.debug(
                    f"[ALERT_DECISION] camera={camera_id} threat={pred['threat_type']} "
                    f"probability={pred['probability']:.3f} threshold={settings.THREAT_ALERT_THRESHOLD} "
                    f"exceeds_threshold={exceeds}"
                )
                if exceeds:
                    alert_data = self._build_alert(camera_id, pred, behavior_state)
                    decisions.append(alert_data)

            if decisions:
                logger.info(f"{self.NAME}: {len(decisions)} alert(s) triggered for camera {camera_id}")
                self.bus.publish("decisions", {
                    "camera_id": camera_id,
                    "timestamp": message.get("timestamp"),
                    "decisions": decisions,
                })

            # Persist predictions to DB
            self._persist_predictions(camera_id, predictions)

        except Exception as e:
            logger.error(f"{self.NAME} error: {e}")

    def _build_alert(self, camera_id: str, prediction: dict, state: dict) -> dict:
        return {
            "camera_id": camera_id,
            "alert_type": prediction["threat_type"],
            "severity": prediction["threat_level"],
            "title": f"Threat Predicted: {prediction['threat_type'].replace('_', ' ').title()}",
            "description": prediction["recommended_action"],
            "threat_score": prediction["probability"],
            "feature_contributions": {
                "crowd_count": state.get("crowd_count", 0) * 0.3,
                "loitering": state.get("loitering_count", 0) * 0.2,
                "anomaly": state.get("anomaly_score", 0) * 0.3,
                "zone_violations": state.get("zone_violations", 0) * 0.2,
            },
        }

    def _persist_predictions(self, camera_id: str, predictions: list):
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import Session
            from app.core.config import settings
            from app.models.prediction import Prediction
            import uuid

            engine = create_engine(settings.SYNC_DATABASE_URL)
            with Session(engine) as session:
                for pred in predictions:
                    p = Prediction(
                        camera_id=uuid.UUID(camera_id) if camera_id != "system" else None,
                        threat_type=pred["threat_type"],
                        probability=pred["probability"],
                        threat_level=pred["threat_level"],
                        recommended_action=pred.get("recommended_action"),
                        model_version=pred.get("model_version", "1.0.0"),
                    )
                    session.add(p)
                session.commit()
        except Exception as e:
            logger.error(f"{self.NAME} DB persist error: {e}")
