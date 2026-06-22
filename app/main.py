from fastapi import FastAPI

from app.core.config import RATE_LIMIT_ALGORITHM
from app.middlewares.rate_limiter import FixedWindowRateLimiterMiddleware
from app.middlewares.sliding_window_rate_limiter import SlidingWindowLogRateLimiterMiddleware

app = FastAPI(title="Performance Layer API")

if RATE_LIMIT_ALGORITHM == "sliding_window_log":
    app.add_middleware(SlidingWindowLogRateLimiterMiddleware)
else:
    app.add_middleware(FixedWindowRateLimiterMiddleware)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"message": "Performance Layer API"}