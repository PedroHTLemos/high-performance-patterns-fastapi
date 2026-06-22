import httpx

GITHUB_API_BASE = "https://api.github.com"


async def fetch_github_user(username: str) -> dict | None:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{GITHUB_API_BASE}/users/{username}",
            headers={"Accept": "application/vnd.github+json"},
            timeout=10.0,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()