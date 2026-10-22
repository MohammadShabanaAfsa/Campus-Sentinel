import uuid
from datetime import datetime
from sqlalchemy import BigInteger, String, Float, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.database import Base


class BehaviorLog(Base):
    __tablename__ = "behavior_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), primary_key=True)
    behavior_type: Mapped[str] = mapped_column(String(100), nullable=False)
    track_id: Mapped[int | None] = mapped_column(Integer)
    person_count: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duration_secs: Mapped[float] = mapped_column(Float, default=0.0)
    location_x: Mapped[float | None] = mapped_column(Float)
    location_y: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSONB, default={})
