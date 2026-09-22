"""
Class Attention Index (CAI) — a single 0-100 composite score for a
classroom, combining attendance, student attentiveness, and faculty
engagement. Mirrors the Campus Safety Index pattern in
app.services.tasks.analytics_tasks._compute_csi_for_camera.
"""
from typing import Dict

WEIGHTS = {"attendance": 0.25, "attentive": 0.50, "faculty": 0.25}


def compute_attention_index(
    present_count: int,
    expected_count: int,
    sleeping_count: int,
    talking_count: int,
    faculty_engagement_score: float,
    faculty_present: bool,
) -> Dict:
    attendance_ratio = min(1.0, present_count / max(1, expected_count))
    distracted = min(present_count, sleeping_count + talking_count)
    attentive_count = max(0, present_count - distracted)
    attentive_ratio = (attentive_count / present_count) if present_count > 0 else 1.0
    # Neutral (0.5) when no faculty could be identified, rather than penalizing
    # the room for a detection gap.
    faculty_component = (faculty_engagement_score / 100.0) if faculty_present else 0.5

    index = 100 * (
        WEIGHTS["attendance"] * attendance_ratio
        + WEIGHTS["attentive"] * attentive_ratio
        + WEIGHTS["faculty"] * faculty_component
    )
    index = round(index, 1)

    return {
        "attention_index": index,
        "attentive_count": attentive_count,
        "level": _level(index),
        "factors": {
            "attendance_ratio": round(attendance_ratio, 3),
            "attentive_ratio": round(attentive_ratio, 3),
            "faculty_component": round(faculty_component, 3),
        },
    }


def _level(score: float) -> str:
    if score >= 80:
        return "excellent"
    if score >= 60:
        return "good"
    if score >= 40:
        return "fair"
    return "poor"
