import json
import time
from fastapi import APIRouter, HTTPException

from app.core.redis_client import redis_client
from app.core.github_client import fetch_github_user
from app.core.config import CACHE_TTL_SECONDS

router = APIRouter(prefix="/github", tags=["github"])


@router.get("/users/{username}")
async def get_github_user(username: str):
    cache_key = f"cache:github:user:{username}"

    start = time.perf_counter()
    cached = await redis_client.get(cache_key)

    if cached:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        data = json.loads(cached)
        return {
            "source": "cache",
            "latency_ms": elapsed_ms,
            "data": data,
        }

    user_data = await fetch_github_user(username)
    if user_data is None:
        raise HTTPException(status_code=404, detail="GitHub user not found")

    await redis_client.set(cache_key, json.dumps(user_data), ex=CACHE_TTL_SECONDS)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return {
        "source": "origin",
        "latency_ms": elapsed_ms,
        "data": user_data,
    }

@router.delete("/users/{username}/cache")
async def purge_github_user_cache(username: str):
    cache_key = f"cache:github:user:{username}"

    deleted = await redis_client.delete(cache_key)

    if deleted == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No cached entry found for user '{username}'",
        )

    return {
        "message": f"Cache purged for user '{username}'",
        "purged": True,
    }