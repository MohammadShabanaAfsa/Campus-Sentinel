import uuid
from datetime import datetime
from sqlalchemy import BigInteger, String, Float, Integer, Boolean, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), primary_key=True)
    camera_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"))
    threat_type: Mapped[str] = mapped_column(String(100), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    threat_level: Mapped[str] = mapped_column(String(20), nullable=False)
    predicted_window_secs: Mapped[int] = mapped_column(Integer, default=300)
    recommended_action: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String(50))
    feature_importance: Mapped[dict] = mapped_column(JSONB, default={})
    was_accurate: Mapped[bool | None] = mapped_column(Boolean)
