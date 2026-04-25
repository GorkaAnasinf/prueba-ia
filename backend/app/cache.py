import hashlib
import redis as redis_lib
from .config import settings

_CACHEABLE = ("research", "analyst")
_TTL = 3600


def _r():
    return redis_lib.from_url(settings.redis_url, decode_responses=True)


def cache_get(query: str, agent: str) -> str | None:
    if agent not in _CACHEABLE:
        return None
    try:
        key = f"cache:{agent}:{hashlib.md5(query.encode()).hexdigest()}"
        return _r().get(key)
    except Exception:
        return None


def cache_set(query: str, agent: str, content: str):
    if agent not in _CACHEABLE:
        return
    try:
        key = f"cache:{agent}:{hashlib.md5(query.encode()).hexdigest()}"
        _r().setex(key, _TTL, content)
    except Exception:
        pass
