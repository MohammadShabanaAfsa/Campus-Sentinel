"""
Heatmap data endpoint — returns detection density as a grid for Leaflet.heat.
Supports time-windowed queries and per-class filtering.
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime, timedelta
from app.db.database import get_db
from app.models.user import User
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


@router.get("/detections")
async def detection_heatmap(
    hours: int = Query(6, ge=1, le=168),
    object_class: Optional[str] = Query(None),
    camera_id: Optional[uuid.UUID] = Query(None),
    grid_size: float = Query(0.0001, description="Lat/lng cell size for aggregation"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Returns heatmap points: [[lat, lng, intensity], ...]
    Joins detections to camera lat/lng, adds spatial jitter per track_id for density.
    """
    since = datetime.utcnow() - timedelta(hours=hours)

    filters = ["d.detected_at >= :since", "c.latitude IS NOT NULL", "c.longitude IS NOT NULL"]
    params: dict = {"since": since}

    if object_class:
        filters.append("d.object_class = :object_class")
        params["object_class"] = object_class
    if camera_id:
        filters.append("d.camera_id = :camera_id")
        params["camera_id"] = str(camera_id)

    where_clause = " AND ".join(filters)

    # detections stores bbox_x/y/w/h in raw pixel coordinates, not a
    # normalized center — derive a 0-1 normalized position from the pixel
    # bbox center divided by that camera's configured resolution (e.g.
    # "1920x1080"), so detections spread out around the camera's map pin
    # instead of stacking on a single point.
    result = await db.execute(text(f"""
        WITH norm AS (
            SELECT
                d.camera_id,
                c.latitude,
                c.longitude,
                COALESCE(
                    (d.bbox_x + d.bbox_w / 2.0) / NULLIF(split_part(c.resolution, 'x', 1)::float, 0),
                    0.5
                ) AS norm_cx,
                COALESCE(
                    (d.bbox_y + d.bbox_h / 2.0) / NULLIF(split_part(c.resolution, 'x', 2)::float, 0),
                    0.5
                ) AS norm_cy
            FROM detections d
            JOIN cameras c ON d.camera_id = c.id
            WHERE {where_clause}
        )
        SELECT
            latitude  + (AVG(norm_cx) - 0.5) * 0.002  AS lat,
            longitude + (AVG(norm_cy) - 0.5) * 0.002  AS lng,
            COUNT(*)::float                           AS intensity
        FROM norm
        GROUP BY camera_id, latitude, longitude,
                 ROUND(norm_cx::numeric, 1),
                 ROUND(norm_cy::numeric, 1)
        ORDER BY intensity DESC
        LIMIT 5000
    """), params)

    rows = result.fetchall()
    if not rows:
        return {"points": [], "max_intensity": 0}

    max_intensity = max(r.intensity for r in rows)
    points = [
        [round(r.lat, 6), round(r.lng, 6), round(r.intensity / max_intensity, 3)]
        for r in rows
        if r.lat is not None and r.lng is not None
    ]
    return {"points": points, "max_intensity": max_intensity, "count": len(points)}


@router.get("/behavior")
async def behavior_heatmap(
    hours: int = Query(24, ge=1, le=168),
    behavior_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Returns heatmap of behavior log events weighted by risk_score.
    """
    since = datetime.utcnow() - timedelta(hours=hours)

    filters = ["b.logged_at >= :since", "c.latitude IS NOT NULL"]
    params: dict = {"since": since}

    if behavior_type:
        filters.append("b.behavior_type = :behavior_type")
        params["behavior_type"] = behavior_type

    where_clause = " AND ".join(filters)

    result = await db.execute(text(f"""
        SELECT
            c.latitude  AS lat,
            c.longitude AS lng,
            SUM(b.risk_score)::float AS intensity
        FROM behavior_logs b
        JOIN cameras c ON b.camera_id = c.id
        WHERE {where_clause}
        GROUP BY c.id, c.latitude, c.longitude
        ORDER BY intensity DESC
    """), params)

    rows = result.fetchall()
    if not rows:
        return {"points": [], "max_intensity": 0}

    max_intensity = max(r.intensity for r in rows) or 1.0
    points = [
        [round(r.lat, 6), round(r.lng, 6), round(r.intensity / max_intensity, 3)]
        for r in rows
        if r.lat is not None
    ]
    return {"points": points, "max_intensity": max_intensity}
