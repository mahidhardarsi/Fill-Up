"""Free-text geocoding protocol, US boundary validation, and cached geocoder implementation."""

import hashlib
import logging
import re
import time
from typing import Any, Protocol

import requests
from django.conf import settings
from django.core.cache import cache

from planner.types import LatLon
from routing.errors import LocationNotFound, OutsideUSA, ProviderError, ProviderRateLimited

logger = logging.getLogger(__name__)

# Geographic bounding boxes for the United States
# Contiguous United States (Lower 48 + DC)
CONUS_MIN_LAT = 24.396308
CONUS_MAX_LAT = 49.384358
CONUS_MIN_LON = -125.0
CONUS_MAX_LON = -66.93457

# Alaska
ALASKA_MIN_LAT = 51.2
ALASKA_MAX_LAT = 71.4
ALASKA_MIN_LON = -179.1
ALASKA_MAX_LON = -129.9

# Hawaii
HAWAII_MIN_LAT = 18.9
HAWAII_MAX_LAT = 28.5
HAWAII_MIN_LON = -178.4
HAWAII_MAX_LON = -154.8

# Puerto Rico
PR_MIN_LAT = 17.8
PR_MAX_LAT = 18.6
PR_MIN_LON = -67.3
PR_MAX_LON = -65.2

DEFAULT_TIMEOUT_SECONDS = 5.0


def is_in_us(lat: float, lon: float) -> bool:
    """Check if coordinates fall within the United States bounding boxes (Lower 48, AK, HI, PR)."""
    # Contiguous US check
    if CONUS_MIN_LAT <= lat <= CONUS_MAX_LAT and CONUS_MIN_LON <= lon <= CONUS_MAX_LON:
        return True
    # Alaska check
    if ALASKA_MIN_LAT <= lat <= ALASKA_MAX_LAT and ALASKA_MIN_LON <= lon <= ALASKA_MAX_LON:
        return True
    # Hawaii check
    if HAWAII_MIN_LAT <= lat <= HAWAII_MAX_LAT and HAWAII_MIN_LON <= lon <= HAWAII_MAX_LON:
        return True
    # Puerto Rico check
    if PR_MIN_LAT <= lat <= PR_MAX_LAT and PR_MIN_LON <= lon <= PR_MAX_LON:
        return True
    return False


class Geocoder(Protocol):
    """Protocol for geocoding queries within the USA."""

    def geocode_us(self, query: str) -> LatLon:
        """Resolve a query string to US coordinates.

        Raises:
            LocationNotFound: if query cannot be resolved.
            OutsideUSA: if resolved coordinates are outside the US.
        """
        ...


class USGeocoder:
    """Production-grade geocoder with in-memory & Django caching, 5s timeout, and US bounds checking."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
        cache_ttl: int | None = None,
    ) -> None:
        if api_key is None:
            api_key = getattr(settings, "ORS_API_KEY", "")
        self.api_key = api_key
        self.timeout = timeout
        self.session = session or requests.Session()
        self.cache_ttl = cache_ttl or getattr(settings, "GEOCODING_CACHE_TTL", 86400 * 30)
        self._local_cache: dict[str, LatLon] = {}

    def _normalize_query(self, query: str) -> str:
        return " ".join(query.strip().lower().split())

    def _cache_key(self, normalized_query: str) -> str:
        # Generate safe cache key for memcached/redis (no whitespace or special chars)
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", normalized_query)[:40]
        hash_digest = hashlib.md5(normalized_query.encode("utf-8")).hexdigest()[:12]
        return f"geocode_us:{slug}:{hash_digest}"

    def geocode_us(self, query: str) -> LatLon:
        """Resolve a free-text location query to US LatLon coordinates."""
        if not query or not query.strip():
            raise LocationNotFound(query)

        normalized = self._normalize_query(query)
        cache_key = self._cache_key(normalized)

        # 1. Check local in-memory cache (0 external calls)
        if normalized in self._local_cache:
            return self._local_cache[normalized]

        # 2. Check Django cache backend (0 external calls)
        try:
            cached_coords: tuple[float, float] | None = cache.get(cache_key)
            if cached_coords is not None:
                latlon = LatLon(lat=cached_coords[0], lon=cached_coords[1])
                self._local_cache[normalized] = latlon
                return latlon
        except Exception as exc:
            logger.debug("Failed reading geocode from Django cache: %s", exc)

        # 3. Call external geocoding provider
        coords = self._resolve_online(query)

        # 4. Validate USA boundary
        if not is_in_us(coords.lat, coords.lon):
            raise OutsideUSA(lat=coords.lat, lon=coords.lon, location_name=query)

        # 5. Populate caches
        self._local_cache[normalized] = coords
        try:
            cache.set(cache_key, (coords.lat, coords.lon), timeout=self.cache_ttl)
        except Exception as exc:
            logger.debug("Failed writing geocode to Django cache: %s", exc)

        return coords

    def _resolve_online(self, query: str) -> LatLon:
        """Query external geocoding providers with retry and timeout."""
        # Try OpenRouteService Geocode if key configured
        if self.api_key:
            try:
                return self._geocode_ors(query)
            except (ProviderError, ProviderRateLimited) as exc:
                logger.warning("ORS geocoding failed (%s); falling back to Nominatim", exc)

        # Fallback to Nominatim
        return self._geocode_nominatim(query)

    def _geocode_ors(self, query: str) -> LatLon:
        url = "https://api.openrouteservice.org/geocode/search"
        params: dict[str, str | int] = {
            "api_key": self.api_key,
            "text": query,
            "boundary.country": "USA",
            "size": 1,
        }
        headers = {"Accept": "application/json"}

        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
                if resp.status_code == 429:
                    raise ProviderRateLimited("openrouteservice_geocode")
                if resp.status_code >= 500:
                    if attempt < max_attempts - 1:
                        time.sleep(0.5 * (2**attempt))
                        continue
                    raise ProviderError(
                        "openrouteservice_geocode",
                        f"Server error {resp.status_code}",
                        status_code=resp.status_code,
                    )
                if resp.status_code != 200:
                    raise ProviderError(
                        "openrouteservice_geocode",
                        f"HTTP {resp.status_code}: {resp.text[:200]}",
                        status_code=resp.status_code,
                    )

                data: dict[str, Any] = resp.json()
                features = data.get("features", [])
                if not features:
                    raise LocationNotFound(query)

                props = features[0].get("properties", {})
                country = str(props.get("country", "")).lower()
                if country and country not in ("united states", "usa", "us"):
                    coords = features[0].get("geometry", {}).get("coordinates", [0.0, 0.0])
                    raise OutsideUSA(
                        lat=float(coords[1]), lon=float(coords[0]), location_name=query
                    )

                coords = features[0].get("geometry", {}).get("coordinates", [])
                if len(coords) < 2:
                    raise LocationNotFound(query)

                return LatLon(lat=float(coords[1]), lon=float(coords[0]))

            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt < max_attempts - 1:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise ProviderError("openrouteservice_geocode", f"Network error: {exc}") from exc

        raise LocationNotFound(query)

    def _geocode_nominatim(self, query: str) -> LatLon:
        url = "https://nominatim.openstreetmap.org/search"
        params: dict[str, str | int] = {
            "q": query,
            "format": "json",
            "countrycodes": "us",
            "limit": 1,
        }
        headers = {
            "Accept": "application/json",
            "User-Agent": "FuelRoutePlanner/1.0",
        }

        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
                if resp.status_code == 429:
                    raise ProviderRateLimited("nominatim")
                if resp.status_code >= 500:
                    if attempt < max_attempts - 1:
                        time.sleep(0.5 * (2**attempt))
                        continue
                    raise ProviderError(
                        "nominatim",
                        f"Server error {resp.status_code}",
                        status_code=resp.status_code,
                    )
                if resp.status_code != 200:
                    raise ProviderError(
                        "nominatim",
                        f"HTTP {resp.status_code}: {resp.text[:200]}",
                        status_code=resp.status_code,
                    )

                data: list[dict[str, Any]] = resp.json()
                if not data or not isinstance(data, list):
                    raise LocationNotFound(query)

                top_result = data[0]
                lat = float(top_result["lat"])
                lon = float(top_result["lon"])

                # Check country indicators in result if provided
                display_name = str(top_result.get("display_name", "")).lower()
                address = top_result.get("address", {})
                country_code = str(address.get("country_code", "")).lower()

                if country_code and country_code not in ("us", "usa", "pr", "vi", "gu", "as", "mp"):
                    raise OutsideUSA(lat=lat, lon=lon, location_name=query)

                non_us_indicators = (
                    "canada",
                    "mexico",
                    "united kingdom",
                    "germany",
                    "france",
                    "japan",
                )
                if (
                    any(ind in display_name for ind in non_us_indicators)
                    and "united states" not in display_name
                ):
                    raise OutsideUSA(lat=lat, lon=lon, location_name=query)

                return LatLon(lat=lat, lon=lon)

            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt < max_attempts - 1:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise ProviderError("nominatim", f"Network error: {exc}") from exc

        raise LocationNotFound(query)
