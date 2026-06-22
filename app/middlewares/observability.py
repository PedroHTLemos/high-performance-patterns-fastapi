"""
Cache observability middleware.

Adds a consistent `X-Cache` response header (HIT / MISS / N/A) to every
response, based on a `cache_status` value set by the route handler on
`request.state`.

Usage in a route handler:
    request.state.cache_status = "HIT"   # or "MISS"

If a route never touches the cache, the header defaults to "N/A".
"""

"""
Cache observability middleware.

Adds a consistent `X-Cache` response header (HIT / MISS / N/A) to every
response, based on a `cache_status` value set by the route handler on
`request.state`.

Usage in a route handler:
    request.state.cache_status = "HIT"   # or "MISS"

If a route never touches the cache, the header defaults to "N/A".

NOTE: implemented as pure ASGI middleware (not Starlette's
BaseHTTPMiddleware). Under concurrent load, BaseHTTPMiddleware has a
known history of leaking per-request state across requests handled
in parallel (the dispatch/call_next pairing isn't perfectly isolated
in some versions). A raw ASGI middleware closes over each individual
`scope`/`send`, so there is no shared mutable state between concurrent
requests.
"""

from starlette.types import ASGIApp, Receive, Scope, Send


class CacheObservabilityMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Per-request, request-scoped container. We stash it directly on
        # the scope's "state" dict (FastAPI/Starlette populate
        # `request.state` from `scope["state"]`), so route handlers can
        # keep writing `request.state.cache_status = "HIT"` unchanged.
        scope.setdefault("state", {})
        scope["state"]["cache_status"] = "N/A"

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                cache_status = scope["state"].get("cache_status", "N/A")
                headers = message.setdefault("headers", [])
                headers.append((b"x-cache", cache_status.encode("latin-1")))
            await send(message)

        await self.app(scope, receive, send_wrapper)