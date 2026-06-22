import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.redis_client import redis_client
from app.core.config import RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECONDS


class SlidingWindowLogRateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Sliding Window Log Rate Limiter.

    Para cada IP, mantemos um ZSET com um membro por requisição (score = timestamp).
    A cada chamada: removemos entradas fora da janela (ZREMRANGEBYSCORE), contamos
    quantas restaram (ZCARD), e só então decidimos se adicionamos a nova entrada.
    Mais preciso que Fixed Window (sem picos na borda), mas usa mais memória
    (um membro por requisição em vez de um contador único).
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/health", "/docs", "/openapi.json"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:sliding:{client_ip}"
        now = time.time()
        window_start = now - RATE_LIMIT_WINDOW_SECONDS

        # Remove entradas fora da janela
        await redis_client.zremrangebyscore(key, 0, window_start)

        # Conta quantas requisições restaram dentro da janela
        current_count = await redis_client.zcard(key)

        if current_count >= RATE_LIMIT_MAX_REQUESTS:
            # Pega o timestamp mais antigo ainda válido pra calcular o retry-after
            oldest = await redis_client.zrange(key, 0, 0, withscores=True)
            if oldest:
                oldest_ts = oldest[0][1]
                retry_after = max(1, int(oldest_ts + RATE_LIMIT_WINDOW_SECONDS - now))
            else:
                retry_after = RATE_LIMIT_WINDOW_SECONDS
            return JSONResponse(
                status_code=429,
                content={"detail": "Too Many Requests"},
                headers={"Retry-After": str(retry_after)},
            )

        # Member único por requisição (uuid) pra evitar colisão de score igual
        member = f"{now}:{uuid.uuid4().hex}"
        await redis_client.zadd(key, {member: now})
        await redis_client.expire(key, RATE_LIMIT_WINDOW_SECONDS)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_MAX_REQUESTS)
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, RATE_LIMIT_MAX_REQUESTS - current_count - 1)
        )
        return response