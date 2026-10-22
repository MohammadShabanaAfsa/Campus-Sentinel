import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Float, Integer, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.database import Base


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location_name: Mapped[str] = mapped_column(String(255), nullable=False)
    rtsp_url: Mapped[str] = mapped_column(Text, nullable=False)
    stream_url: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    zone_type: Mapped[str] = mapped_column(String(100), default="general")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_recording: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolution: Mapped[str] = mapped_column(String(20), default="1920x1080")
    fps: Mapped[int] = mapped_column(Integer, default=25)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="offline")
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config: Mapped[dict] = mapped_column(JSONB, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    restricted_zones: Mapped[list["RestrictedZone"]] = relationship("RestrictedZone", back_populates="camera")

    @property
    def last_error(self) -> str | None:
        return (self.config or {}).get("last_error")


class RestrictedZone(Base):
    __tablename__ = "restricted_zones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    zone_points: Mapped[list] = mapped_column(JSONB, nullable=False)
    alert_level: Mapped[str] = mapped_column(String(20), default="high")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    camera: Mapped["Camera"] = relationship("Camera", back_populates="restricted_zones")
