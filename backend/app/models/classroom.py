import uuid
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Float, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.database import Base


class ClassroomConfig(Base):
    __tablename__ = "classroom_configs"

    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), primary_key=True)
    expected_students: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    teaching_zone: Mapped[list | None] = mapped_column(JSONB)
    sleeping_secs_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=15.0)
    talking_secs_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=8.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ClassroomMetric(Base):
    __tablename__ = "classroom_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), primary_key=True)
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    present_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sleeping_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    talking_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attentive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    faculty_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    faculty_engagement_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    attention_index: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    details: Mapped[dict] = mapped_column(JSONB, default={})
