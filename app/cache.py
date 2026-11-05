from __future__ import annotations

import json
import threading
import time
from typing import Any

from app.config import settings


class Cache:
    """Small cache facade: Redis when configured, in-process TTL otherwise."""

    def __init__(
        self,
        redis_url: str | None = None,
        redis_client: Any | None = None,
        ttl: int | None = None,
    ) -> None:
        self._memory: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl or settings.cache_ttl_seconds
        self._hits = 0
        self._misses = 0
        self._redis = redis_client
        url = redis_url or settings.redis_url
        if self._redis is None and url:
            try:
                import redis

                self._redis = redis.Redis.from_url(url, decode_responses=True)
                self._redis.ping()
            except Exception:  # pragma: no cover - optional dependency/runtime
                self._redis = None

    def get(self, key: str) -> Any | None:
        if self._redis is not None:
            raw = self._redis.get(key)
        else:
            with self._lock:
                item = self._memory.get(key)
                if item is None:
                    return None
                expires_at, raw = item
                if expires_at < time.monotonic():
                    self._memory.pop(key, None)
                    return None
        if raw is None:
            self._misses += 1
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            self._misses += 1
            return None
        self._hits += 1
        return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        raw = json.dumps(value, ensure_ascii=False, default=str)
        ttl = ttl or self._ttl
        if self._redis is not None:
            self._redis.set(key, raw, ex=ttl)
            return
        with self._lock:
            self._memory[key] = (time.monotonic() + ttl, raw)

    def invalidate(self) -> None:
        if self._redis is not None:
            for key in self._redis.scan_iter("orderhub:*"):
                self._redis.delete(key)
            return
        with self._lock:
            self._memory.clear()

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    def ping(self) -> bool:
        if self._redis is not None:
            try:
                return bool(self._redis.ping())
            except Exception:  # pragma: no cover - network/runtime failure
                return False
        return True

    def stats(self) -> dict[str, int | str]:
        return {"backend": self.backend, "hits": self._hits, "misses": self._misses}


cache = Cache()
