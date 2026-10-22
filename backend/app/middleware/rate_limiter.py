"""
Redis-based sliding-window rate limiter middleware.
Limits requests per IP per time window. WebSocket and health check paths are exempt.
"""
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from loguru import logger

EXEMPT_PREFIXES = ("/api/v1/ws/", "/health", "/metrics")
DEFAULT_LIMIT = 200       # requests per window
DEFAULT_WINDOW = 60       # seconds
AUTH_LIMIT = 10           # stricter for login endpoint
AUTH_WINDOW = 60


class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_url: str):
        super().__init__(app)
        self._redis_url = redis_url
        self._redis = None

    def _get_redis(self):
        if self._redis is None:
            import redis as _redis
            self._redis = _redis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Exempt paths
        for prefix in EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Determine limits
        is_auth = path.startswith("/api/v1/auth/login")
        limit  = AUTH_LIMIT  if is_auth else DEFAULT_LIMIT
        window = AUTH_WINDOW if is_auth else DEFAULT_WINDOW

        # Resolve client IP (respects X-Forwarded-For from Nginx)
        forwarded_for = request.headers.get("X-Forwarded-For")
        ip = forwarded_for.split(",")[0].strip() if forwarded_for else request.client.host

        key = f"rate:{ip}:{path if is_auth else 'global'}"

        try:
            r = self._get_redis()
            pipe = r.pipeline()
            now = time.time()
            window_start = now - window

            pipe.zremrangebyscore(key, "-inf", window_start)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window)
            results = pipe.execute()
            count = results[2]

            if count > limit:
                logger.warning(f"Rate limit exceeded: {ip} → {path} ({count}/{limit})")
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Too many requests. Please slow down.",
                        "retry_after": window,
                    },
                    headers={"Retry-After": str(window), "X-RateLimit-Limit": str(limit)},
                )
        except Exception as e:
            # Never block requests due to rate limiter errors
            logger.warning(f"Rate limiter error (allowing request): {e}")

        response = await call_next(request)
        return response
