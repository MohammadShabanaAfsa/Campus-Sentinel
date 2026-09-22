"""
Prediction Agent — receives behavior states and runs LSTM/RF threat prediction.
"""
from loguru import logger
from agents.orchestrator.agent_bus import AgentBus


class PredictionAgent:
    NAME = "PredictionAgent"

    def __init__(self):
        self.bus = AgentBus.get_instance()
        self._predictors = {}

    def start(self):
        self.bus.subscribe("behaviors", self._on_behavior_state)
        logger.info(f"{self.NAME} started")

    def _on_behavior_state(self, message: dict):
        try:
            camera_id = message["camera_id"]
            predictor = self._get_predictor(camera_id)
            predictions = predictor.predict(behavior_state=message)
            logger.debug(
                f"[THREAT_SCORE] camera={camera_id} "
                f"{ {t: round(p['probability'], 3) for t, p in predictions.items()} }"
            )

            if predictions:
                self.bus.publish("threats", {
                    "camera_id": camera_id,
                    "timestamp": message.get("timestamp"),
                    "predictions": predictions,
                    "behavior_state": message,
                })
                logger.info(f"{self.NAME}: {len(predictions)} threats predicted for camera {camera_id}")

        except Exception as e:
            logger.error(f"{self.NAME} error: {e}")

    def _get_predictor(self, camera_id: str):
        from ai_engine.prediction.threat_predictor import ThreatPredictor
        if camera_id not in self._predictors:
            self._predictors[camera_id] = ThreatPredictor(camera_id=camera_id)
        return self._predictors[camera_id]
