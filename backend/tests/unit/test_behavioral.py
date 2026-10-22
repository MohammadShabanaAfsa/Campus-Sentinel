"""Unit tests for behavioral analytics modules."""
import time
import pytest
from unittest.mock import patch, MagicMock


class TestLoiteringDetector:
    def _make_detector(self, threshold=10):
        from ai_engine.behavioral.loitering import LoiteringDetector
        return LoiteringDetector(camera_id="test_cam", threshold_secs=threshold)

    def test_no_alert_short_duration(self):
        det = self._make_detector(threshold=300)
        tracks = [{"track_id": 1, "class_name": "person", "cx": 100, "cy": 100}]
        alerts = det.analyze(tracks)
        assert len(alerts) == 0

    def test_alert_after_threshold(self):
        det = self._make_detector(threshold=5)
        tracks = [{"track_id": 1, "class_name": "person", "cx": 100, "cy": 100}]
        # Simulate time passing
        det._states[1] = __import__("ai_engine.behavioral.loitering", fromlist=["LoiterState"]).LoiterState(
            track_id=1,
            first_seen=time.time() - 10,
            last_seen=time.time(),
            positions=[(100/640, 100/480)] * 20,
        )
        alerts = det.analyze(tracks)
        assert any(a["alert_type"] == "loitering" for a in alerts)

    def test_non_person_ignored(self):
        det = self._make_detector(threshold=1)
        tracks = [{"track_id": 1, "class_name": "car", "cx": 100, "cy": 100}]
        alerts = det.analyze(tracks)
        assert len(alerts) == 0


class TestCrowdAnalyzer:
    def _make_analyzer(self, threshold=5):
        from ai_engine.behavioral.crowd import CrowdAnalyzer
        return CrowdAnalyzer(camera_id="test_cam", density_threshold=threshold)

    def test_no_alert_below_threshold(self):
        analyzer = self._make_analyzer(threshold=20)
        tracks = [{"track_id":i,"class_name": "person", "cx": i * 100, "cy": 100} for i in range(5)]
        alerts = analyzer.analyze(tracks)
        assert not any(a["alert_type"] == "crowd_density" for a in alerts)

    def test_alert_above_threshold(self):
        analyzer = self._make_analyzer(threshold=3)
        tracks = [{"track_id":i,"class_name": "person", "cx": i * 100, "cy": 100} for i in range(5)]
        alerts = analyzer.analyze(tracks)
        assert any(a["alert_type"] == "crowd_density" for a in alerts)


class TestZoneChecker:
    def test_point_in_polygon(self):
        from ai_engine.behavioral.zone_checker import ZoneChecker
        checker = ZoneChecker.__new__(ZoneChecker)
        checker.camera_id = "test"
        checker._zones = []
        checker._alerted_tracks = {}

        polygon = [
            {"x": 0, "y": 0}, {"x": 100, "y": 0},
            {"x": 100, "y": 100}, {"x": 0, "y": 100}
        ]
        assert checker._point_in_polygon(50, 50, polygon) is True
        assert checker._point_in_polygon(150, 50, polygon) is False

    def test_point_on_edge(self):
        from ai_engine.behavioral.zone_checker import ZoneChecker
        checker = ZoneChecker.__new__(ZoneChecker)
        checker.camera_id = "test"
        polygon = [{"x": 0, "y": 0}, {"x": 100, "y": 0},
                   {"x": 100, "y": 100}, {"x": 0, "y": 100}]
        # Points outside
        assert checker._point_in_polygon(200, 200, polygon) is False
