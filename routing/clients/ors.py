"""OpenRouteService routing client implementation."""

import logging
import time
from typing import Any

import requests
from django.conf import settings

from planner.types import LatLon, RoutePath
from routing.errors import ProviderError, ProviderRateLimited

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 5.0
METERS_TO_MILES = 1.0 / 1609.344


class OpenRouteServiceClient:
    """Client for OpenRouteService v2 directions driving-car API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openrouteservice.org",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        if api_key is None:
            api_key = getattr(settings, "ORS_API_KEY", "")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

    def route(self, start: LatLon, finish: LatLon) -> RoutePath:
        """Calculate a driving route between start and finish coordinates via OpenRouteService."""
        if not self.api_key:
            raise ProviderError("openrouteservice", "No API key configured for OpenRouteService")

        url = f"{self.base_url}/v2/directions/driving-car/geojson"
        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json, application/geo+json",
        }
        payload = {
            "coordinates": [
                [start.lon, start.lat],
                [finish.lon, finish.lat],
            ]
        }

        # Max 1 retry on network error or HTTP 5xx
        max_attempts = 2
        last_exception: Exception | None = None

        for attempt in range(max_attempts):
            try:
                response = self.session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )

                if response.status_code == 429:
                    raise ProviderRateLimited("openrouteservice")

                if response.status_code >= 500:
                    if attempt < max_attempts - 1:
                        time.sleep(0.5 * (2**attempt))
                        continue
                    raise ProviderError(
                        "openrouteservice",
                        f"Server error {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                    )

                if response.status_code != 200:
                    raise ProviderError(
                        "openrouteservice",
                        f"HTTP {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                    )

                data: dict[str, Any] = response.json()
                return self._parse_ors_response(data)

            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exception = exc
                if attempt < max_attempts - 1:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise ProviderError(
                    "openrouteservice",
                    f"Network error after retry: {exc}",
                ) from exc

        raise ProviderError(
            "openrouteservice",
            f"Failed to fetch route: {last_exception}",
        )

    def _parse_ors_response(self, data: dict[str, Any]) -> RoutePath:
        """Parse OpenRouteService GeoJSON response into a RoutePath dataclass."""
        try:
            # Handle GeoJSON FeatureCollection
            features = data.get("features", [])
            if features:
                feature = features[0]
                geometry = feature.get("geometry", {})
                raw_coords = geometry.get("coordinates", [])
                summary = feature.get("properties", {}).get("summary", {})
                distance_meters = float(summary.get("distance", 0.0))
            elif "routes" in data:
                # Handle standard JSON format if returned
                route = data["routes"][0]
                distance_meters = float(route.get("summary", {}).get("distance", 0.0))
                geom = route.get("geometry", {})
                if isinstance(geom, dict):
                    raw_coords = geom.get("coordinates", [])
                else:
                    raw_coords = []
            else:
                raise KeyError("No features or routes found in response")

            if not raw_coords:
                raise ValueError("ORS response contained empty coordinates list")

            points = tuple(LatLon(lat=float(coord[1]), lon=float(coord[0])) for coord in raw_coords)
            distance_miles = distance_meters * METERS_TO_MILES

            return RoutePath(points=points, distance_miles=distance_miles)

        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(
                "openrouteservice",
                f"Failed to parse OpenRouteService route response: {exc}",
            ) from exc
