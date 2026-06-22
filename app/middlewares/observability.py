"""
Cache observability middleware.

Adds a consistent `X-Cache` response header (HIT / MISS / N/A) to every
response, based on a `cache_status` value set by the route handler on
`request.state`.

Usage in a route handler:
    request.state.cache_status = "HIT"   # or "MISS"

If a route never touches the cache, the header defaults to "N/A".
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class CacheObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Default before the route runs; route handlers overwrite this
        # by setting request.state.cache_status = "HIT" / "MISS".
        request.state.cache_status = "N/A"

        response = await call_next(request)

        cache_status = getattr(request.state, "cache_status", "N/A")
        response.headers["X-Cache"] = cache_status

        return response