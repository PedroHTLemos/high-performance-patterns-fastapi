import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.redis_client import redis_client
from app.core.api_keys import resolve_identity, TIER_LIMITS


class SlidingWindowLogRateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Sliding Window Log Rate Limiter, com limite variável por tier
    (resolvido via header X-API-Key). Sem chave válida, cai no tier
    'anonymous' (mais restritivo).
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/health", "/docs", "/openapi.json"):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")
        identity = resolve_identity(api_key)
        tier = identity["tier"]
        limits = TIER_LIMITS[tier]
        max_requests = limits["max_requests"]
        window_seconds = limits["window_seconds"]

        # Anônimos ainda são distinguidos por IP (senão compartilhariam o mesmo balde)
        client_ip = request.client.host if request.client else "unknown"
        identifier = identity["id"] if tier != "anonymous" else f"anonymous:{client_ip}"

        key = f"ratelimit:sliding:{identifier}"
        now = time.time()
        window_start = now - window_seconds

        await redis_client.zremrangebyscore(key, 0, window_start)
        current_count = await redis_client.zcard(key)

        if current_count >= max_requests:
            oldest = await redis_client.zrange(key, 0, 0, withscores=True)
            if oldest:
                oldest_ts = oldest[0][1]
                retry_after = max(1, int(oldest_ts + window_seconds - now))
            else:
                retry_after = window_seconds
            return JSONResponse(
                status_code=429,
                content={"detail": "Too Many Requests", "tier": tier},
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now}:{uuid.uuid4().hex}"
        await redis_client.zadd(key, {member: now})
        await redis_client.expire(key, window_seconds)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(max(0, max_requests - current_count - 1))
        response.headers["X-RateLimit-Tier"] = tier
        return response