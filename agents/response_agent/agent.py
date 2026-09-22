"""
Response Agent — receives alert decisions and dispatches them:
- Dashboard (WebSocket via Redis pub/sub)
- Database persistence
- Email (mock)
- SMS (mock)
"""
from loguru import logger
from agents.orchestrator.agent_bus import AgentBus


class ResponseAgent:
    NAME = "ResponseAgent"

    def __init__(self):
        self.bus = AgentBus.get_instance()

    def start(self):
        self.bus.subscribe("decisions", self._on_decisions)
        logger.info(f"{self.NAME} started")

    def _on_decisions(self, message: dict):
        try:
            camera_id = message["camera_id"]
            for decision in message.get("decisions", []):
                self._dispatch(camera_id, decision)
        except Exception as e:
            logger.error(f"{self.NAME} error: {e}")

    def _dispatch(self, camera_id: str, alert_data: dict):
        from app.services.tasks.alert_tasks import create_and_dispatch_alert
        create_and_dispatch_alert.delay(camera_id, alert_data)
        logger.info(f"{self.NAME}: Dispatched alert '{alert_data['title']}' for camera {camera_id}")


# ─── Orchestrator entry point ─────────────────────────────────────────────────
def start_all_agents():
    """Start all agents in daemon threads."""
    import threading
    from agents.vision_agent.agent import VisionAgent
    from agents.behavior_agent.agent import BehaviorAgent
    from agents.prediction_agent.agent import PredictionAgent
    from agents.decision_agent.agent import DecisionAgent

    bus = AgentBus.get_instance()

    agents = [VisionAgent(), BehaviorAgent(), PredictionAgent(), DecisionAgent(), ResponseAgent()]
    for agent in agents:
        agent.start()

    bus.start_listening()
    logger.info("All agents started and listening")
    return agents
