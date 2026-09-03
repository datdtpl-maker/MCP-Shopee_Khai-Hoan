"""Bounded-TTL cache for immutable MCP tool discovery metadata.

The cache only stores the result of ``list_tools``. Tool execution and all
Shopee/Notion data remain uncached. Explicit invalidation is used whenever the
FastMCP registry changes, while TTL provides a safe upper bound for stale
metadata in long-lived processes.
"""

from __future__ import annotations

import time
from typing import Awaitable, Callable, Generic, Optional, TypeVar

T = TypeVar("T")


class DiscoveryCache(Generic[T]):
    def __init__(self, ttl_seconds: float = 60.0, clock: Callable[[], float] = time.monotonic):
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be >= 0")
        self.ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._value: Optional[T] = None
        self._expires_at = 0.0

    async def get(self, loader: Callable[[], Awaitable[T]]) -> T:
        now = self._clock()
        if self._value is not None and now < self._expires_at:
            return self._value
        value = await loader()
        self._value = value
        self._expires_at = now + self.ttl_seconds
        return value

    def invalidate(self) -> None:
        self._value = None
        self._expires_at = 0.0

    @property
    def is_valid(self) -> bool:
        return self._value is not None and self._clock() < self._expires_at


class CachedFastMCPMixin:
    """Mixin implementing cached, read-only tool discovery for FastMCP."""

    def _init_discovery_cache(self, ttl_seconds: float = 60.0) -> None:
        self._discovery_cache = DiscoveryCache(ttl_seconds)

    async def list_tools(self):
        async def load():
            return await super(CachedFastMCPMixin, self).list_tools()

        return await self._discovery_cache.get(load)

    def add_tool(self, *args, **kwargs):
        result = super().add_tool(*args, **kwargs)
        self._discovery_cache.invalidate()
        return result

    def remove_tool(self, name: str):
        result = super().remove_tool(name)
        self._discovery_cache.invalidate()
        return result
