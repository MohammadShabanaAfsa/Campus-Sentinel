import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, SmallInteger, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.db.database import Base


class ABDProfile(Base):
    __tablename__ = "abd_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(100), nullable=False)
    hour_of_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    avg_person_count: Mapped[float] = mapped_column(Float, default=0)
    max_person_count: Mapped[float] = mapped_column(Float, default=0)
    avg_movement_speed: Mapped[float] = mapped_column(Float, default=0)
    avg_loiter_duration: Mapped[float] = mapped_column(Float, default=0)
    anomaly_threshold: Mapped[float] = mapped_column(Float, default=0.5)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    model_path: Mapped[str | None] = mapped_column(Text)
    last_trained: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
