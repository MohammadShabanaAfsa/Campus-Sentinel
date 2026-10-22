"""
Integration tests for the end-to-end stream detection pipeline.
These use a synthetic video source (pure OpenCV) so no real camera is needed.
"""
import cv2
import numpy as np
import pytest
import threading
import time


def generate_test_frame(width: int = 640, height: int = 480) -> np.ndarray:
    """Create a synthetic frame with a moving rectangle (simulating a person)."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:] = (20, 20, 35)  # Dark background
    # Fake "person" rectangle
    cv2.rectangle(frame, (100, 50), (180, 300), (180, 180, 180), -1)
    return frame


class TestByteTrackerPipeline:
    def test_tracker_initializes(self):
        from ai_engine.tracking.tracker import ByteTracker
        tracker = ByteTracker(camera_id="integration_test")
        assert tracker is not None
        assert tracker.camera_id == "integration_test"

    def test_track_persists_across_frames(self):
        from ai_engine.tracking.tracker import ByteTracker
        tracker = ByteTracker(camera_id="persist_test", min_hits=1)
        frame = generate_test_frame()

        det = {"class_name": "person", "confidence": 0.9,
               "bbox": [90.0, 45.0, 185.0, 305.0], "cx": 137.5, "cy": 175.0,
               "class_id": 0, "width": 95, "height": 260}

        # Frame 1
        tracks1 = tracker.update([det], frame)
        assert len(tracks1) == 1
        track_id = tracks1[0]["track_id"]

        # Frame 2 — slightly moved
        det["cx"] = 140.0
        det["bbox"] = [92.0, 45.0, 188.0, 305.0]
        tracks2 = tracker.update([det], frame)
        assert len(tracks2) == 1
        # Same track should persist
        assert tracks2[0]["track_id"] == track_id

    def test_track_removed_when_lost(self):
        from ai_engine.tracking.tracker import ByteTracker
        tracker = ByteTracker(camera_id="lost_test", min_hits=1, max_age=2)
        frame = generate_test_frame()

        det = {"class_name": "person", "confidence": 0.9,
               "bbox": [90.0, 45.0, 185.0, 305.0], "cx": 137.5, "cy": 175.0,
               "class_id": 0, "width": 95, "height": 260}

        tracker.update([det], frame)

        # 3 frames with no detection — should remove track (max_age=2)
        for _ in range(3):
            tracks = tracker.update([], frame)
        assert len(tracks) == 0


class TestFrameAnnotator:
    def test_annotates_without_crash(self):
        from ai_engine.vision.frame_annotator import FrameAnnotator
        annotator = FrameAnnotator()
        frame = generate_test_frame()
        tracks = [
            {"track_id": 1, "class_name": "person", "confidence": 0.92,
             "bbox": [90, 45, 185, 305], "cx": 137, "cy": 175,
             "position_history": [(0.2, 0.3), (0.21, 0.32)]}
        ]
        result = annotator.draw(frame.copy(), tracks)
        assert result.shape == frame.shape

    def test_empty_tracks_no_crash(self):
        from ai_engine.vision.frame_annotator import FrameAnnotator
        annotator = FrameAnnotator()
        frame = generate_test_frame()
        result = annotator.draw(frame.copy(), [])
        assert result is not None


class TestStreamManager:
    def test_get_instance_singleton(self):
        from ai_engine.vision.stream_manager import StreamManager
        m1 = StreamManager.get_instance('integration-camera-a')
        m2 = StreamManager.get_instance('integration-camera-a')
        assert m1 is m2
        assert StreamManager.get_instance('integration-camera-b') is not m1

    def test_status_empty(self):
        from ai_engine.vision.stream_manager import StreamManager
        # Fresh instance for this test
        mgr = StreamManager('integration-empty-camera')
        status = mgr.get_status()
        assert isinstance(status, dict)
