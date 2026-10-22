from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth, cameras, alerts, detections, csi,
    predictions, incidents, analytics, websocket, stream, admin,
    heatmap, settings, classroom
)

api_router = APIRouter()

api_router.include_router(auth.router,        prefix="/auth",        tags=["Authentication"])
api_router.include_router(cameras.router,     prefix="/cameras",     tags=["Cameras"])
api_router.include_router(alerts.router,      prefix="/alerts",      tags=["Alerts"])
api_router.include_router(detections.router,  prefix="/detections",  tags=["Detections"])
api_router.include_router(csi.router,         prefix="/csi",         tags=["Campus Safety Index"])
api_router.include_router(predictions.router, prefix="/predictions", tags=["Predictions"])
api_router.include_router(incidents.router,   prefix="/incidents",   tags=["Incidents"])
api_router.include_router(analytics.router,   prefix="/analytics",   tags=["Analytics"])
api_router.include_router(stream.router,      prefix="/streams",     tags=["Stream Control"])
api_router.include_router(heatmap.router,     prefix="/heatmap",     tags=["Heatmap"])
api_router.include_router(settings.router,    prefix="/settings",    tags=["Settings"])
api_router.include_router(admin.router,       prefix="/admin",       tags=["Admin"])
api_router.include_router(websocket.router,   prefix="/ws",          tags=["WebSocket"])
api_router.include_router(classroom.router,   prefix="/classroom",   tags=["Classroom Monitoring"])
