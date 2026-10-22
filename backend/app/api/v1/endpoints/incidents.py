import uuid
from typing import List, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from app.db.database import get_db
from app.models.incident import Incident
from app.models.user import User
from app.api.v1.endpoints.auth import get_current_user
from pydantic import BaseModel


class IncidentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    incident_type: str
    severity: Literal["low", "medium", "high", "critical"]
    camera_id: Optional[uuid.UUID] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class IncidentResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str]
    incident_type: str
    severity: str
    status: str
    camera_id: Optional[uuid.UUID]
    latitude: Optional[float]
    longitude: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


from app.services.safety_index import publish_campus_safety_index

router = APIRouter()


@router.get("/", response_model=List[IncidentResponse])
async def list_incidents(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    query = select(Incident).order_by(Incident.created_at.desc()).limit(100)
    if status_filter:
        query = query.where(Incident.status == status_filter)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=IncidentResponse, status_code=201)
async def create_incident(
    data: IncidentCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    incident = Incident(**data.model_dump())
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    await publish_campus_safety_index(db)
    return incident


@router.patch("/{incident_id}/resolve", response_model=IncidentResponse)
async def resolve_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident.status = "resolved"
    incident.resolved_by = current_user.id
    incident.resolved_at = datetime.utcnow()
    await db.commit()
    await db.refresh(incident)
    await publish_campus_safety_index(db)
    return incident


class IncidentUpdate(BaseModel):
    severity: Optional[Literal["low", "medium", "high", "critical"]] = None
    status: Optional[Literal["open", "investigating", "resolved", "closed"]] = None


@router.patch("/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: uuid.UUID,
    data: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    incident = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if data.severity:
        incident.severity = data.severity
    if data.status:
        incident.status = data.status
        resolved = data.status in {"resolved", "closed"}
        incident.resolved_at = datetime.utcnow() if resolved else None
        incident.resolved_by = current_user.id if resolved else None
    await db.commit()
    await db.refresh(incident)
    await publish_campus_safety_index(db)
    return incident


@router.delete("/{incident_id}", status_code=204)
async def delete_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    incident = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    await db.delete(incident)
    await db.commit()
    await publish_campus_safety_index(db)
