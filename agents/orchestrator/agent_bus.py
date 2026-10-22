"""
Agent Communication Bus.
Agents publish messages to channels; subscribed agents process them.
Uses Redis pub/sub for decoupled, async communication.
"""
import json
import redis
import threading
from typing import Callable, Dict, List
from loguru import logger


class AgentBus:
    """Central message bus for inter-agent communication."""

    CHANNELS = {
        "raw_frames":     "bus:raw_frames",
        "detections":     "bus:detections",
        "tracks":         "bus:tracks",
        "behaviors":      "bus:behaviors",
        "threats":        "bus:threats",
        "decisions":      "bus:decisions",
        "responses":      "bus:responses",
    }

    _instance = None

    def __init__(self, redis_url: str):
        self._redis = redis.Redis.from_url(redis_url)
        self._pubsub = self._redis.pubsub()
        self._handlers: Dict[str, List[Callable]] = {}
        self._listener_thread: threading.Thread | None = None

    @classmethod
    def get_instance(cls) -> "AgentBus":
        if cls._instance is None:
            from app.core.config import settings
            cls._instance = cls(redis_url=settings.REDIS_URL)
        return cls._instance

    def publish(self, channel_key: str, message: dict):
        channel = self.CHANNELS.get(channel_key, channel_key)
        self._redis.publish(channel, json.dumps(message))

    def subscribe(self, channel_key: str, handler: Callable):
        channel = self.CHANNELS.get(channel_key, channel_key)
        if channel not in self._handlers:
            self._handlers[channel] = []
            self._pubsub.subscribe(channel)
        self._handlers[channel].append(handler)
        logger.debug(f"AgentBus: subscribed handler to {channel}")

    def start_listening(self):
        """Start background listener thread."""
        def _listen():
            for message in self._pubsub.listen():
                if message["type"] != "message":
                    continue
                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()
                handlers = self._handlers.get(channel, [])
                try:
                    data = json.loads(message["data"])
                except Exception:
                    continue
                for handler in handlers:
                    try:
                        handler(data)
                    except Exception as e:
                        logger.error(f"AgentBus handler error on {channel}: {e}")

        self._listener_thread = threading.Thread(target=_listen, daemon=True)
        self._listener_thread.start()
        logger.info("AgentBus listener started")
