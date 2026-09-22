"""
Threat Prediction Engine using LSTM + Random Forest ensemble.
Forecasts threat types within a configurable time window.
"""
import numpy as np
import json
import time
from typing import List, Dict, Optional
from datetime import datetime
from loguru import logger


THREAT_TYPES = ["potential_fight", "crowd_surge", "security_breach", "restricted_access"]


class ThreatPredictor:
    _instances: Dict[str, "ThreatPredictor"] = {}

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self._feature_buffer: List[List[float]] = []
        self._rf_model = None
        self._lstm_model = None
        self._load_models()

    @classmethod
    def get_instance(cls, camera_id: str) -> "ThreatPredictor":
        if camera_id not in cls._instances:
            cls._instances[camera_id] = cls(camera_id=camera_id)
        return cls._instances[camera_id]

    def _load_models(self):
        """Load pre-trained models from disk (global or per-camera)."""
        import os, pickle
        # Prefer camera-specific, fall back to global trained model
        paths_to_try = [
            f"/app/models/prediction/rf_{self.camera_id}.pkl",
            "/app/models/prediction/threat_predictor_rf.pkl",
        ]
        for rf_path in paths_to_try:
            if os.path.exists(rf_path):
                with open(rf_path, "rb") as f:
                    bundle = pickle.load(f)
                self._rf_model = bundle.get("model") if isinstance(bundle, dict) else bundle
                self._rf_scaler = bundle.get("scaler") if isinstance(bundle, dict) else None
                logger.info(f"RF model loaded: {rf_path}")
                return
        logger.debug(f"No RF model found for {self.camera_id} — using rule-based fallback")

    def predict(self, feature_vec: Optional[List[float]] = None,
               behavior_state: Optional[Dict] = None) -> Dict[str, Dict]:
        """
        Predict threats from current behavior state or pre-built feature vector.
        Returns dict keyed by threat_type.
        """
        if feature_vec is None and behavior_state is not None:
            feature_vec = self._extract_features(behavior_state)
        elif feature_vec is None:
            feature_vec = [0.0] * 8

        if behavior_state is None:
            behavior_state = {}

        self._feature_buffer.append(feature_vec)
        if len(self._feature_buffer) > 100:
            self._feature_buffer = self._feature_buffer[-100:]

        raw_predictions: List[Dict] = []
        if self._rf_model is not None:
            raw_predictions = self._rf_predict(feature_vec)
        else:
            raw_predictions = self._rule_based_predict(behavior_state)

        # Return as dict for easy Redis serialisation
        return {p["threat_type"]: p for p in raw_predictions}

    def _extract_features(self, state: Dict) -> List[float]:
        now = datetime.utcnow()
        return [
            state.get("crowd_count", 0),
            state.get("loitering_count", 0),
            state.get("zone_violations", 0),
            state.get("anomaly_score", 0.0),
            state.get("avg_speed", 0.0),
            state.get("formation_density", 0.0),
            now.hour,
            now.weekday(),
        ]

    def _rf_predict(self, feature_vec: List[float]) -> List[Dict]:
        X = np.array([feature_vec])
        if hasattr(self, "_rf_scaler") and self._rf_scaler is not None:
            X = self._rf_scaler.transform(X)
        probs = self._rf_model.predict_proba(X)[0]
        classes = self._rf_model.classes_

        results = []
        for cls_name, prob in zip(classes, probs):
            if prob > 0.3:
                results.append(self._make_prediction(cls_name, float(prob)))
        return results

    def _rule_based_predict(self, state: Dict) -> List[Dict]:
        """Heuristic prediction fallback when no trained model exists."""
        results = []
        crowd = state.get("crowd_count", 0)
        loitering = state.get("loitering_count", 0)
        violations = state.get("zone_violations", 0)
        anomaly = state.get("anomaly_score", 0.0)

        if crowd > 15 and state.get("formation_density", 0) > 0.5:
            prob = min(0.9, crowd / 30 + 0.3)
            results.append(self._make_prediction("potential_fight", prob))

        if crowd > 20:
            prob = min(0.9, crowd / 40 + 0.4)
            results.append(self._make_prediction("crowd_surge", prob))

        if violations > 0:
            results.append(self._make_prediction("restricted_access", 0.85))

        if anomaly > 0.7:
            results.append(self._make_prediction("security_breach", anomaly))

        return results

    def _make_prediction(self, threat_type: str, probability: float) -> Dict:
        level_map = {
            (0.0, 0.3): "low",
            (0.3, 0.6): "medium",
            (0.6, 0.8): "high",
            (0.8, 1.1): "critical",
        }
        level = "low"
        for (lo, hi), lv in level_map.items():
            if lo <= probability < hi:
                level = lv

        actions = {
            "potential_fight": "Dispatch security personnel to the area immediately.",
            "crowd_surge": "Activate crowd control measures and open additional exits.",
            "security_breach": "Alert security team and review access logs.",
            "restricted_access": "Verify identity of individuals in restricted zone.",
        }

        return {
            "threat_type": threat_type,
            "probability": round(probability, 3),
            "threat_level": level,
            "predicted_window_secs": 300,
            "recommended_action": actions.get(threat_type, "Review situation."),
            "model_version": "1.0.0-rule" if self._rf_model is None else "1.0.0-rf",
        }
