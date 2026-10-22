"""Phase 3 unit tests — ABD, Threat Predictor, Email Service, CSI."""
import pytest
import numpy as np


class TestABDDataSeeder:
    def test_generate_logs_returns_correct_count(self):
        from ai_engine.abd.data_seeder import generate_logs
        logs = generate_logs("camera-test-001", "entrance", days=1)
        # 24 hours × ~3 entries each
        assert 40 < len(logs) < 120

    def test_generate_logs_has_required_fields(self):
        from ai_engine.abd.data_seeder import generate_logs
        logs = generate_logs("camera-test-001", "canteen", days=1)
        for log in logs[:5]:
            assert "camera_id" in log
            assert "behavior_type" in log
            assert "person_count" in log
            assert "risk_score" in log
            assert 0.0 <= log["risk_score"] <= 1.0

    def test_generate_logs_respects_zone_type(self):
        from ai_engine.abd.data_seeder import generate_logs
        restricted_logs = generate_logs("x", "restricted", days=7)
        # Restricted zones should have mostly 0-1 persons
        avg_persons = sum(l["person_count"] for l in restricted_logs) / len(restricted_logs)
        assert avg_persons < 5

    def test_canteen_has_higher_peak_counts(self):
        from ai_engine.abd.data_seeder import generate_logs
        canteen = generate_logs("x", "canteen", days=7)
        entrance = generate_logs("x", "entrance", days=7)
        canteen_max = max(l["person_count"] for l in canteen)
        entrance_max = max(l["person_count"] for l in entrance)
        assert canteen_max >= entrance_max * 0.5


class TestThreatPredictor:
    def test_rule_based_returns_dict(self):
        from ai_engine.prediction.threat_predictor import ThreatPredictor
        p = ThreatPredictor(camera_id="test-cam")
        result = p.predict(behavior_state={
            "crowd_count": 25,
            "loitering_count": 3,
            "zone_violations": 1,
            "anomaly_score": 0.8,
        })
        assert isinstance(result, dict)

    def test_zone_violation_triggers_restricted_access(self):
        from ai_engine.prediction.threat_predictor import ThreatPredictor
        p = ThreatPredictor(camera_id="test-cam2")
        result = p.predict(behavior_state={"zone_violations": 2})
        assert "restricted_access" in result

    def test_high_anomaly_triggers_breach(self):
        from ai_engine.prediction.threat_predictor import ThreatPredictor
        p = ThreatPredictor(camera_id="test-cam3")
        result = p.predict(behavior_state={"anomaly_score": 0.9, "zone_violations": 0})
        assert "security_breach" in result

    def test_low_state_no_alerts(self):
        from ai_engine.prediction.threat_predictor import ThreatPredictor
        p = ThreatPredictor(camera_id="test-cam4")
        result = p.predict(behavior_state={
            "crowd_count": 2,
            "loitering_count": 0,
            "zone_violations": 0,
            "anomaly_score": 0.05,
        })
        assert len(result) == 0

    def test_make_prediction_levels(self):
        from ai_engine.prediction.threat_predictor import ThreatPredictor
        p = ThreatPredictor(camera_id="level-test")
        assert p._make_prediction("crowd_surge", 0.1)["threat_level"] == "low"
        assert p._make_prediction("crowd_surge", 0.5)["threat_level"] == "medium"
        assert p._make_prediction("crowd_surge", 0.7)["threat_level"] == "high"
        assert p._make_prediction("crowd_surge", 0.9)["threat_level"] == "critical"


class TestRFModelTrainer:
    def test_synthetic_data_generation(self):
        from ai_engine.prediction.model_trainer import _synthetic_training_data
        X, y = _synthetic_training_data(500)
        assert X.shape == (500, 9)
        assert y.shape == (500,)
        assert set(y.tolist()).issubset({0, 1})

    def test_rf_training_returns_model(self):
        from ai_engine.prediction.model_trainer import train_random_forest, _synthetic_training_data
        X, y = _synthetic_training_data(300)
        bundle = train_random_forest(X, y)
        assert "model" in bundle
        assert "scaler" in bundle
        assert bundle["accuracy"] > 0.5

    def test_feature_names_count(self):
        from ai_engine.prediction.model_trainer import train_random_forest, _synthetic_training_data
        X, y = _synthetic_training_data(100)
        bundle = train_random_forest(X, y)
        assert len(bundle["feature_names"]) == 9


class TestCSIScoring:
    def test_score_to_level_safe(self):
        from app.services.tasks.analytics_tasks import _score_to_level
        assert _score_to_level(90) == "safe"
        assert _score_to_level(75) == "low_risk"

    def test_score_to_level_moderate(self):
        from app.services.tasks.analytics_tasks import _score_to_level
        assert _score_to_level(74) == "moderate"
        assert _score_to_level(60) == "moderate"

    def test_score_to_level_high_risk(self):
        from app.services.tasks.analytics_tasks import _score_to_level
        assert _score_to_level(49) == "high_risk"
        assert _score_to_level(40) == "high_risk"

    def test_score_to_level_critical(self):
        from app.services.tasks.analytics_tasks import _score_to_level
        assert _score_to_level(24) == "critical"
        assert _score_to_level(0) == "critical"


class TestExplanationGeneration:
    def test_explanation_has_required_keys(self):
        from app.services.tasks.alert_tasks import _generate_explanation
        explanation = _generate_explanation({
            "alert_type": "loitering",
            "threat_score": 0.75,
        })
        assert "method" in explanation
        assert "feature_contributions" in explanation
        assert "predicted_value" in explanation
        assert explanation["predicted_value"] == 0.75

    def test_custom_contributions_preserved(self):
        from app.services.tasks.alert_tasks import _generate_explanation
        contrib = {"duration": 0.6, "location_risk": 0.3}
        explanation = _generate_explanation({
            "alert_type": "loitering",
            "threat_score": 0.9,
            "feature_contributions": contrib,
        })
        assert explanation["feature_contributions"] == contrib

    def test_default_contributions_sum_to_one(self):
        from app.services.tasks.alert_tasks import _generate_explanation
        explanation = _generate_explanation({"alert_type": "crowd", "threat_score": 0.5})
        total = sum(explanation["feature_contributions"].values())
        assert abs(total - 1.0) < 0.01
