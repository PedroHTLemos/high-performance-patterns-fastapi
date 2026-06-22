from fastapi import FastAPI

from app.middlewares.rate_limiter import FixedWindowRateLimiterMiddleware

app = FastAPI(title="Performance Layer API")

app.add_middleware(FixedWindowRateLimiterMiddleware)


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"message": "Performance Layer API"}