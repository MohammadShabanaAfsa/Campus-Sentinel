import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import settings
from app.core.celery_app import celery_app
# Celery's "current app" resolution is thread-local. This process dispatches tasks
# (analyze_behavior, create_and_dispatch_alert, ...) from background agent threads,
# not just the main thread, so set_default() registers the Redis-backed app
# process-wide — otherwise those threads silently fall back to Celery's
# unconfigured default app (AMQP on localhost) and every .delay() call fails.
celery_app.set_default()
from app.api.v1.router import api_router
from app.db.database import engine
from app.db.redis_client import get_redis, close_redis
from app.utils.exceptions import http_exception_handler, unhandled_exception_handler


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Initialize Redis connection
    await get_redis()
    logger.info("Redis connected")

    # Additive migration also covers existing native installations on restart.
    from app.services.vehicle_counts import ensure_vehicle_schema
    await ensure_vehicle_schema()

    # Seed a default camera (Phone Camera / IP Webcam) if none exist yet,
    # so the stream manager and dashboard have something to show.
    await _seed_default_camera()

    # Start Redis pub/sub listener for WebSocket broadcasting
    asyncio.create_task(_redis_pubsub_listener())

    # Start multi-agent system in background threads
    import threading
    def _start_agents():
        from agents.response_agent.agent import start_all_agents
        start_all_agents()
    threading.Thread(target=_start_agents, daemon=True, name="agent-init").start()

    # Start all active camera streams — one StreamManager instance per camera
    def _start_streams():
        import time
        time.sleep(3)  # Allow DB to stabilize
        from ai_engine.vision.stream_manager import start_all_active_cameras
        start_all_active_cameras()
    threading.Thread(target=_start_streams, daemon=True, name="stream-init").start()

    logger.info("Background systems starting...")

    yield

    # Shutdown
    from ai_engine.vision.stream_manager import stop_all_camera_streams
    stop_all_camera_streams()
    await close_redis()
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Powered Predictive Smart Campus Surveillance System",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ─── Middleware ───────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS if settings.ENVIRONMENT == "production" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Rate limiting (Redis-backed sliding window)
from app.middleware.rate_limiter import RateLimiterMiddleware
app.add_middleware(RateLimiterMiddleware, redis_url=settings.REDIS_URL)

# ─── Exception handlers ───────────────────────────────────────────────────────
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ─── Prometheus metrics ───────────────────────────────────────────────────────
if settings.PROMETHEUS_ENABLED:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ─── Routes ──────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


async def _seed_default_camera():
    """Ensure the two default cameras exist: a webcam-fed entrance camera and
    a phone-fed classroom camera, each with its own distinct source."""
    from sqlalchemy import select, func
    from app.db.database import AsyncSessionLocal
    from app.models.camera import Camera

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(func.count()).select_from(Camera))
        if result.scalar_one() > 0:
            return

        db.add(Camera(
            name="General Entrance",
            location_name="Main Entrance",
            rtsp_url=str(settings.CAMERA_FALLBACK_INDEX),
            stream_url=str(settings.CAMERA_FALLBACK_INDEX),
            zone_type="general",
            is_active=True,
            status="online",
        ))
        if settings.IP_CAMERA_URL:
            db.add(Camera(
                name="Classroom",
                location_name="Android IP Webcam",
                rtsp_url=settings.IP_CAMERA_URL,
                stream_url=settings.IP_CAMERA_URL,
                zone_type="classroom",
                is_active=True,
                status="online",
            ))
        await db.commit()
        logger.info(
            f"Seeded default cameras: 'General Entrance' -> webcam "
            f"{settings.CAMERA_FALLBACK_INDEX}; classroom seed configured={bool(settings.IP_CAMERA_URL)}"
        )


async def _redis_pubsub_listener():
    """Resubscribe after transient Redis loss without duplicating listeners."""
    from app.services.websocket_manager import ws_manager
    import json
    delay = 1
    while True:
        pubsub = None
        try:
            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe("alerts_channel", "csi_updates", "camera_events", "classroom_updates")
            logger.info("Redis pub/sub listener started")
            await ws_manager.broadcast({'type':'realtime_resync'})
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    await ws_manager.broadcast(data)
                    delay = 1
                except (ValueError, TypeError):
                    logger.warning("Invalid realtime payload ignored")
            raise ConnectionError("Redis subscription ended")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning(f"Redis listener reconnecting: {type(error).__name__}")
        finally:
            if pubsub is not None:
                try:
                    await pubsub.aclose()
                except Exception:
                    pass
        await asyncio.sleep(delay)
        delay = min(30, delay * 2)
