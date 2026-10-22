"""Custom application exceptions and global FastAPI exception handlers."""
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger


class CameraStreamError(Exception):
    """Raised when a camera stream cannot be opened or maintained."""
    def __init__(self, camera_id: str, detail: str = "Stream error"):
        self.camera_id = camera_id
        super().__init__(detail)


class AIModelError(Exception):
    """Raised when an AI model fails to load or run inference."""
    pass


class AlertDispatchError(Exception):
    """Raised when alert dispatch fails."""
    pass


async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(f"HTTP {exc.status_code}: {exc.detail} — {request.url}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "path": str(request.url)},
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "path": str(request.url)},
    )
