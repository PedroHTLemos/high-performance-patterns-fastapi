API_KEYS = {
    "free-key-123": {"tier": "free"},
    "premium-key-456": {"tier": "premium"},
}

TIER_LIMITS = {
    "free": {"max_requests": 10, "window_seconds": 60},
    "premium": {"max_requests": 100, "window_seconds": 60},
    "anonymous": {"max_requests": 5, "window_seconds": 60},
}


def resolve_identity(api_key: str | None) -> dict:
    """
    Retorna a identidade do cliente (tier + identificador) baseado na API Key.
    Sem chave válida -> tier 'anonymous' (mais restritivo).
    """
    if api_key and api_key in API_KEYS:
        tier = API_KEYS[api_key]["tier"]
        return {"id": api_key, "tier": tier}
    return {"id": "anonymous", "tier": "anonymous"}