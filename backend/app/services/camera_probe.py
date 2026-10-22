"""Bounded native camera test using the same capture path as live streams."""
import json
import os
import subprocess
import sys
from pathlib import Path


def test_camera_source(source: str, timeout: float = 5.0) -> dict:
    # A subprocess bounds even a video driver that ignores OpenCV timeouts.
    # subprocess.run kills and waits for the child when the deadline expires.
    env = os.environ.copy()
    backend = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = backend + os.pathsep + env.get("PYTHONPATH", "")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.services.camera_probe", "--worker"],
            input=json.dumps({"rtsp_url": source}), capture_output=True,
            text=True, timeout=timeout, env=env, cwd=backend,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        return _failure("Failed to open video stream")
    except subprocess.TimeoutExpired:
        return _failure("Camera source unreachable: connection timed out")
    except (ValueError, OSError):
        return _failure("Failed to test video stream")


def _failure(message: str, reachable: bool = False, opened: bool = False) -> dict:
    return {"reachable": reachable, "opened": opened, "frame_read": False, "message": message}


def _worker(source: str) -> dict:
    from ai_engine.vision.camera_manager import CameraManager
    manager = CameraManager("source-test", source, enable_fallback=False, reconnect_delay=0)
    try:
        if not manager.open():
            return _failure(manager.last_error or "Failed to open video stream", manager.reachable, manager.opened)
        ret, frame = manager.read()
        if not ret or frame is None:
            return _failure("No frames received", reachable=True, opened=True)
        return {"reachable": True, "opened": True, "frame_read": True, "message": "Camera stream is working"}
    finally:
        manager.release()


if __name__ == "__main__":
    data = json.loads(sys.stdin.read())
    print(json.dumps(_worker(data["rtsp_url"])))
