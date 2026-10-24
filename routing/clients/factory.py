"""Routing client factory and fallback orchestration."""

import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache

from planner.types import LatLon, RoutePath
from routing.clients.base import RoutingClient
from routing.clients.ors import OpenRouteServiceClient
from routing.clients.osrm import OSRMClient
from routing.errors import ProviderError, ProviderRateLimited

logger = logging.getLogger(__name__)


class CachedRoutingClient:
    """Caching wrapper around a RoutingClient to ensure 0 external calls on cache hit."""

    def __init__(self, inner_client: RoutingClient, cache_ttl: int | None = None) -> None:
        self.inner_client = inner_client
        self.cache_ttl = cache_ttl or getattr(settings, "ROUTE_CACHE_TTL", 86400 * 7)
        self._local_cache: dict[str, RoutePath] = {}

    def _cache_key(self, start: LatLon, finish: LatLon) -> str:
        # Precision rounded to 4 decimals (~11 meters)
        return (
            f"route:{round(start.lat, 4)}:{round(start.lon, 4)}:"
            f"{round(finish.lat, 4)}:{round(finish.lon, 4)}"
        )

    def route(self, start: LatLon, finish: LatLon) -> RoutePath:
        """Fetch route from cache if present; otherwise delegate and store."""
        key = self._cache_key(start, finish)

        # 1. Check local in-memory cache
        if key in self._local_cache:
            return self._local_cache[key]

        # 2. Check Django cache backend
        try:
            cached_data: dict[str, Any] | None = cache.get(key)
            if cached_data is not None:
                points = tuple(LatLon(lat=p[0], lon=p[1]) for p in cached_data["points"])
                route_path = RoutePath(
                    points=points, distance_miles=float(cached_data["distance_miles"])
                )
                self._local_cache[key] = route_path
                return route_path
        except Exception as exc:
            logger.debug("Failed reading route from Django cache: %s", exc)

        # 3. Call inner client
        route_path = self.inner_client.route(start, finish)

        # 4. Save to caches
        self._local_cache[key] = route_path
        try:
            serialized = {
                "points": [(p.lat, p.lon) for p in route_path.points],
                "distance_miles": route_path.distance_miles,
            }
            cache.set(key, serialized, timeout=self.cache_ttl)
        except Exception as exc:
            logger.debug("Failed saving route to Django cache: %s", exc)

        return route_path


class FallbackRoutingClient:
    """Routing client that tries primary provider (e.g. ORS) and falls back to secondary (e.g. OSRM)."""

    def __init__(
        self,
        primary: RoutingClient | None = None,
        fallback: RoutingClient | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback or OSRMClient()

    def route(self, start: LatLon, finish: LatLon) -> RoutePath:
        """Route using primary client if available, with automatic fallback on provider failure."""
        if self.primary is not None:
            try:
                return self.primary.route(start, finish)
            except (ProviderRateLimited, ProviderError) as exc:
                logger.warning(
                    "Primary routing provider failed (%s); falling back to secondary",
                    exc,
                )

        return self.fallback.route(start, finish)


def get_routing_client(
    api_key: str | None = None,
    use_cache: bool = True,
) -> RoutingClient:
    """Factory creating the production routing client configured from settings."""
    if api_key is None:
        api_key = getattr(settings, "ORS_API_KEY", "")

    primary: RoutingClient | None = None
    if api_key:
        primary = OpenRouteServiceClient(api_key=api_key)

    fallback: RoutingClient = OSRMClient()
    client: RoutingClient = FallbackRoutingClient(primary=primary, fallback=fallback)

    if use_cache:
        client = CachedRoutingClient(client)

    return client
