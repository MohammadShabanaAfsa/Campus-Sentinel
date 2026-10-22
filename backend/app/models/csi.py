import uuid
from datetime import datetime
from sqlalchemy import BigInteger, String, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.database import Base


class CSIScore(Base):
    __tablename__ = "csi_scores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), primary_key=True)
    camera_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"))
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    crowd_score: Mapped[float] = mapped_column(Float, default=100.0)
    loitering_score: Mapped[float] = mapped_column(Float, default=100.0)
    access_score: Mapped[float] = mapped_column(Float, default=100.0)
    anomaly_score: Mapped[float] = mapped_column(Float, default=100.0)
    historical_score: Mapped[float] = mapped_column(Float, default=100.0)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="safe")
    contributing_factors: Mapped[dict] = mapped_column(JSONB, default={})
