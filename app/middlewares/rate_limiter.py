import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.redis_client import redis_client
from app.core.config import RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECONDS


class FixedWindowRateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Fixed Window Rate Limiter.

    Para cada IP, mantemos um contador associado à janela de tempo atual
    (ex: janelas de 60s, calculadas como int(timestamp / window_seconds)).
    Problema conhecido: pode permitir picos de até 2x o limite na borda
    entre duas janelas (ex: 10 reqs no fim da janela 1 + 10 reqs no início
    da janela 2 = 20 reqs em poucos segundos). Resolveremos isso com
    Sliding Window Log no próximo passo.
    """

    async def dispatch(self, request: Request, call_next):
        # Endpoints de infraestrutura não são limitados
        if request.url.path in ("/health", "/docs", "/openapi.json"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        current_window = int(time.time() / RATE_LIMIT_WINDOW_SECONDS)
        key = f"ratelimit:fixed:{client_ip}:{current_window}"

        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, RATE_LIMIT_WINDOW_SECONDS)

        if count > RATE_LIMIT_MAX_REQUESTS:
            ttl = await redis_client.ttl(key)
            retry_after = ttl if ttl > 0 else RATE_LIMIT_WINDOW_SECONDS
            return JSONResponse(
                status_code=429,
                content={"detail": "Too Many Requests"},
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_MAX_REQUESTS)
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, RATE_LIMIT_MAX_REQUESTS - count)
        )
        return response