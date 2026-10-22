"""Unit tests for ByteTracker."""
import numpy as np
import pytest


def test_iou_perfect_overlap():
    from ai_engine.tracking.tracker import ByteTracker
    tracker = ByteTracker(camera_id="test")
    a = np.array([0, 0, 100, 100])
    b = np.array([0, 0, 100, 100])
    assert tracker._iou(a, b) == pytest.approx(1.0)


def test_iou_no_overlap():
    from ai_engine.tracking.tracker import ByteTracker
    import pytest
    tracker = ByteTracker(camera_id="test")
    a = np.array([0, 0, 50, 50])
    b = np.array([100, 100, 200, 200])
    assert tracker._iou(a, b) == 0.0


def test_iou_partial_overlap():
    from ai_engine.tracking.tracker import ByteTracker
    tracker = ByteTracker(camera_id="test")
    a = np.array([0, 0, 100, 100])
    b = np.array([50, 50, 150, 150])
    iou = tracker._iou(a, b)
    assert 0 < iou < 1


def test_update_creates_tracks():
    import numpy as np
    from ai_engine.tracking.tracker import ByteTracker

    tracker = ByteTracker(camera_id="test_create")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    detections = [
        {"class_name": "person", "confidence": 0.9, "bbox": [10, 10, 60, 100], "cx": 35, "cy": 55},
        {"class_name": "person", "confidence": 0.85, "bbox": [200, 50, 280, 200], "cx": 240, "cy": 125},
    ]
    # Need min_hits=1 for immediate track creation in tests
    tracker.min_hits = 1
    tracks = tracker.update(detections, frame)
    assert len(tracks) == 2
