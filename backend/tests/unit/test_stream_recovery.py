"""Camera restart regressions without database, Redis, or detector startup."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location(
    "stream_recovery", Path(__file__).resolve().parents[3] / "ai-engine/vision/stream_manager.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StreamRecoveryTests(unittest.TestCase):
    def test_restart_waits_for_capture_to_exit_before_starting(self):
        manager = module.StreamManager("test-camera")
        old_thread = Mock()
        old_thread.is_alive.return_value = True
        manager.thread = old_thread

        def finish_capture(timeout):
            self.assertTrue(manager._stop_event.is_set())
            old_thread.is_alive.return_value = False

        old_thread.join.side_effect = finish_capture
        manager.start = Mock(return_value=True)
        self.assertTrue(manager.restart())
        old_thread.join.assert_called_once_with(timeout=35)
        manager.start.assert_called_once()

    def test_restart_does_not_duplicate_a_blocked_capture(self):
        manager = module.StreamManager("test-camera")
        manager.thread = Mock()
        manager.thread.is_alive.return_value = True
        manager.start = Mock()
        self.assertFalse(manager.restart())
        manager.start.assert_not_called()
        self.assertTrue(manager._stop_event.is_set())

    def test_restart_starts_a_previously_stopped_camera(self):
        manager = module.StreamManager("test-camera")
        manager.start = Mock(return_value=True)
        self.assertTrue(manager.restart())
        manager.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()

def test_timeout_reconnect_uses_same_classroom_source_without_fallback(monkeypatch):
    import numpy as np
    from ai_engine.vision import camera_manager as cameras
    source='http://fixture.invalid:8080/video'
    checks=iter(['Camera source unreachable: connection timed out',None])
    monkeypatch.setattr(cameras,'check_http_source',lambda url:next(checks))
    monkeypatch.setattr(cameras.time,'sleep',lambda _:None)
    cap=Mock();cap.isOpened.return_value=True;cap.read.return_value=(True,np.zeros((100,100,3),np.uint8))
    factory=Mock(return_value=cap);monkeypatch.setattr(cameras.cv2,'VideoCapture',factory)
    camera=cameras.CameraManager('classroom-fixture',source,enable_fallback=False)
    assert not camera.open() and 'timed out' in camera.last_error
    assert camera.reconnect() and camera.camera_id=='classroom-fixture'
    assert camera.active_source==source and not camera.using_fallback
    assert camera.read()[0]
    assert factory.call_count==1 and factory.call_args.args[0]==source
    camera.release()
