"""
Pytest configuration — sets up environment variables and
patches external dependencies for unit/integration tests.
"""
import os
import sys
import pytest

# Add project roots to path so ai_engine and agents are importable
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set test environment variables before any app imports
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_DB", "campus_sentinel_test")
os.environ.setdefault("POSTGRES_USER", "cs_admin")
os.environ.setdefault("POSTGRES_PASSWORD", "test_pass")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PASSWORD", "")
os.environ.setdefault("SECRET_KEY", "test-secret-key-minimum-32-chars-long!!")
os.environ.setdefault("YOLO_MODEL_PATH", "yolov8n.pt")
os.environ.setdefault("YOLO_DEVICE", "cpu")


@pytest.fixture(autouse=True)
def reset_singleton_instances():
    """Clear singleton caches between tests to avoid state leakage."""
    yield
    try:
        from ai_engine.vision.detector import YOLODetector
        YOLODetector._instances.clear()
    except Exception:
        pass
    try:
        from ai_engine.tracking.tracker import ByteTracker
        ByteTracker._instances.clear()
    except Exception:
        pass
