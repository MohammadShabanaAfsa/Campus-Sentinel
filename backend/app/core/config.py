from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional, Literal
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # ─── App ─────────────────────────────────────────────────────────
    APP_NAME: str = "Campus Sentinel"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # ─── Server ──────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4

    # ─── Security ────────────────────────────────────────────────────
    SECRET_KEY: str = "REPLACE_WITH_RANDOM_SECRET_BEFORE_USE"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALLOWED_HOSTS: List[str] = ["*"]

    # ─── Database ────────────────────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "campus_sentinel"
    POSTGRES_USER: str = "cs_admin"
    POSTGRES_PASSWORD: str = "REPLACE_WITH_DATABASE_PASSWORD"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ─── Redis ───────────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def CELERY_BROKER_URL(self) -> str:
        return self.REDIS_URL

    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return self.REDIS_URL

    # ─── AI Engine ───────────────────────────────────────────────────
    YOLO_MODEL_PATH: str = "models/weights/yolov8n.pt"
    YOLO_CONFIDENCE_THRESHOLD: float = 0.5
    YOLO_DEVICE: str = "cpu"  # "cuda" for GPU
    FRAME_SKIP: int = 3        # Process every Nth frame
    MAX_CAMERAS: int = 16

    # ─── Camera Source ───────────────────────────────────────────────
    # Primary source for all camera streams (Android IP Webcam app).
    # Falls back to the local webcam (device index below) if unreachable.
    IP_CAMERA_URL: str = ""  # First-time seed only; existing cameras use the database.
    CAMERA_FALLBACK_INDEX: int = 0
    CAMERA_RECONNECT_DELAY_SECS: float = 5.0
    QR_IDENTIFICATION_ENABLED: bool = True
    STUDENT_QR_WORKBOOK: str = "student_face_list.xlsx"
    QR_SCAN_INTERVAL_SECS: float = 1.0
    QR_IDENTITY_TIMEOUT_SECS: float = 30.0  # Legacy compatibility only; no visibility timeout.
    QR_TRACK_GRACE_SECS: float = 3.0  # Identity lives with the track, not QR visibility.
    QR_ASSOC_MAX_DISTANCE_FRACTION: float = 0.08
    QR_ASSOC_AMBIGUITY_MARGIN_FRACTION: float = 0.03
    QR_ASSOCIATION_MARGIN_PX: float = 40.0
    QR_DEBUG_LOGGING: bool = False
    QR_DEBUG_OVERLAY: bool = False
    QR_SCAN_TIMEOUT_SECS: float = 2.0

    # ─── Behavioral Analytics ────────────────────────────────────────
    LOITERING_THRESHOLD_SECS: int = 300   # 5 minutes
    LOITERING_MOVEMENT_RADIUS: float = 0.05
    LOITERING_TRACK_GRACE_SECS: float = 3.0
    LOITERING_DEBUG_THRESHOLD_SECS: float = 10.0  # Used only with ACTIVITY_DEBUG=true.
    CROWD_DENSITY_THRESHOLD: int = 5      # active persons per camera
    CROWD_SURGE_WINDOW_SECS: float = 30.0
    CROWD_SURGE_GROWTH_THRESHOLD: float = 0.50
    CROWD_SURGE_BASELINE_SECS: float = 5.0
    CROWD_SURGE_CONFIRM_SECS: float = 3.0
    CROWD_SURGE_MIN_SAMPLES: int = 3
    CROWD_EPISODE_CLEAR_SECS: float = 3.0
    CROWD_MAX_SAMPLE_GAP_SECS: float = 5.0
    RUNNING_SPEED_THRESHOLD: float = 3.0  # m/s equivalent
    ACTIVITY_ANALYSIS_INTERVAL_SECS: float = 0.75
    ACTIVITY_TRACK_GRACE_SECS: float = 3.0
    SLEEPING_LANDMARK_GRACE_SECS: float = 3.0
    SLEEP_EAR_THRESHOLD: float = 0.20
    GENERAL_SLEEP_EAR_THRESHOLD: Optional[float] = None
    BEHAVIOR_ANALYSIS_INTERVAL_SECS: float = 0.75
    RUNNING_SPEED_THRESHOLD_PX_SEC: float = 120.0
    RUNNING_MIN_CONSECUTIVE_SAMPLES: int = 3
    RUNNING_MIN_DURATION_SECS: float = 1.5
    RUNNING_MIN_DISPLACEMENT_PX: float = 80.0
    ACCELERATION_MIN_BASE_SPEED_PX_SEC: float = 25.0
    ACCELERATION_MIN_DELTA_PX_SEC: float = 80.0
    ACCELERATION_RATIO: float = 3.0
    EATING_TEST_MIN_CYCLES: int = 1
    EATING_DEBUG: bool = False
    TALKING_MAR_STD_THRESHOLD: float = 0.035
    GENERAL_TALKING_MAR_STD_THRESHOLD: Optional[float] = None
    YOLO_PHONE_CONFIDENCE_THRESHOLD: float = 0.25
    PHONE_ROI_INFERENCE_ENABLED: bool = True
    PHONE_ROI_MAX_PERSONS: int = 2
    PHONE_ROI_MAX_INPUT_SIZE: int = 960
    ACTIVITY_POSE_CROP_PADDING: float = 0.20
    ACTIVITY_DEBUG: bool = False
    RESTRICTED_ZONE_DEBUG: bool = False  # Log one active track, never draw diagnostics.
    RESTRICTED_ZONE_MIN_OVERLAP_RATIO: float = Field(default=0.05,gt=0,le=1)
    RESTRICTED_ZONE_FOOT_TOLERANCE: float = Field(default=0.05,ge=0,le=0.10)
    RESTRICTED_ZONE_REFERENCE_POINT: Literal['FOOT_POINT','LOWER_BODY_POINT'] = 'FOOT_POINT'
    FALL_ANGLE_THRESHOLD: float = 60.0
    FALL_PERSISTENCE_SECS: float = 4.0
    FALL_RECOVERY_SECS: float = 2.0
    FIGHT_PERSISTENCE_SECS: float = 4.0
    FIGHT_CLEAR_SECS: float = 3.0
    FIGHT_PROXIMITY_RADIUS: float = .15
    FIGHT_RELATIVE_SPEED: float = .10
    FIGHT_ARM_SPEED: float = .70
    ABANDONED_BAG_SECS: float = 45.0
    ABANDONED_BAG_TEST_SECS: float = 5.0
    BAG_OWNER_RADIUS: float = .18
    BAG_STATIONARY_RADIUS: float = .02
    AFTER_HOURS_CONFIRM_SECS: float = 2.0
    EXIT_BLOCKAGE_SECS: float = 10.0
    ENABLE_ACTIVITY_ANALYSIS_ON_GENERAL: bool = True
    PHONE_USE_MIN_DURATION_SECS: float = 2.0
    PHONE_USE_MIN_HITS: int = 3
    PHONE_USE_CLEAR_TIMEOUT_SECS: float = 1.5
    PHONE_PERSON_ASSOCIATION_MARGIN: float = 20.0
    PHONE_HAND_DISTANCE_THRESHOLD: float = 0.45
    EATING_MIN_EVENTS: int = 3
    EATING_LIMB_CROP_PADDING: float = 0.35
    EATING_WRIST_VISIBILITY_THRESHOLD: float = 0.50
    EATING_LANDMARK_GRACE_SECS: float = 1.5
    EATING_MAX_LANDMARK_GRACE_SECS: float = 3.0
    PHONE_EATING_DEBUG: bool = False
    EATING_WINDOW_SECS: float = 20.0
    EATING_CLEAR_TIMEOUT_SECS: float = 6.0
    EATING_MOUTH_DISTANCE_THRESHOLD: float = 0.70
    EATING_AWAY_DISTANCE_THRESHOLD: float = 0.85
    EATING_MIN_NEAR_SECS: float = 0.25
    EATING_MAX_NEAR_SECS: float = 3.0
    EATING_MIN_EVENT_INTERVAL_SECS: float = 1.0

    # ─── Alert Settings ──────────────────────────────────────────────
    ALERT_COOLDOWN_SECS: int = 60   # Min time between same-type alerts per camera
    THREAT_ALERT_THRESHOLD: float = 0.5   # Min predicted probability to create an alert

    # ─── Email (FastAPI-Mail) ────────────────────────────────────────
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = "alerts@campus-sentinel.local"
    MAIL_PORT: int = 587
    MAIL_SERVER: str = "smtp.gmail.com"
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False
    ALERT_EMAIL_TO: List[str] = []

    # ─── Frontend ────────────────────────────────────────────────────
    FRONTEND_URL: str = "http://localhost:3000"

    # ─── Monitoring ──────────────────────────────────────────────────
    PROMETHEUS_ENABLED: bool = True

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
