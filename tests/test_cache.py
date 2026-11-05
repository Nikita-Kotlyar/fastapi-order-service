from __future__ import annotations

import os
import time

import pytest

from app.cache import Cache


def test_memory_cache_roundtrip_and_ttl() -> None:
    cache = Cache(ttl=1)
    cache.set("orderhub:test", {"a": 1})
    assert cache.get("orderhub:test") == {"a": 1}
    time.sleep(1.1)
    assert cache.get("orderhub:test") is None


def test_memory_cache_invalidate() -> None:
    cache = Cache(ttl=60)
    cache.set("orderhub:a", 1)
    cache.set("orderhub:b", 2)
    cache.invalidate()
    assert cache.get("orderhub:a") is None
    assert cache.get("orderhub:b") is None


def test_redis_client_roundtrip() -> None:
    fakeredis = pytest.importorskip("fakeredis")
    client = fakeredis.FakeRedis(decode_responses=True)
    cache = Cache(redis_client=client, ttl=60)
    cache.set("orderhub:test", {"a": 1})
    assert cache.get("orderhub:test") == {"a": 1}
    cache.invalidate()
    assert cache.get("orderhub:test") is None


@pytest.mark.redis
def test_real_redis_roundtrip() -> None:
    url = os.environ.get("ORDERHUB_TEST_REDIS_URL")
    if not url:
        pytest.skip("ORDERHUB_TEST_REDIS_URL is not set")
    redis = pytest.importorskip("redis")
    client = redis.Redis.from_url(url, decode_responses=True)
    client.ping()
    cache = Cache(redis_client=client, ttl=60)
    cache.set("orderhub:test:real", {"ok": True})
    assert cache.get("orderhub:test:real") == {"ok": True}
    cache.invalidate()
    assert cache.get("orderhub:test:real") is None
