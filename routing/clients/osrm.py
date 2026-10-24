"""OSRM routing client implementation."""

import logging
import time
from typing import Any

import requests

from planner.types import LatLon, RoutePath
from routing.errors import ProviderError, ProviderRateLimited

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_OSRM_BASE_URL = "https://router.project-osrm.org"
METERS_TO_MILES = 1.0 / 1609.344


class OSRMClient:
    """Client for OSRM public API route service."""

    def __init__(
        self,
        base_url: str = DEFAULT_OSRM_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

    def route(self, start: LatLon, finish: LatLon) -> RoutePath:
        """Calculate a driving route between start and finish coordinates via OSRM."""
        # OSRM coordinate order in URL: {lon1},{lat1};{lon2},{lat2}
        url = f"{self.base_url}/route/v1/driving/{start.lon},{start.lat};{finish.lon},{finish.lat}"
        params = {
            "overview": "full",
            "geometries": "geojson",
        }
        headers = {
            "Accept": "application/json",
            "User-Agent": "FuelRoutePlanner/1.0",
        }

        max_attempts = 2
        last_exception: Exception | None = None

        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )

                if response.status_code == 429:
                    raise ProviderRateLimited("osrm")

                if response.status_code >= 500:
                    if attempt < max_attempts - 1:
                        time.sleep(0.5 * (2**attempt))
                        continue
                    raise ProviderError(
                        "osrm",
                        f"Server error {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                    )

                if response.status_code != 200:
                    raise ProviderError(
                        "osrm",
                        f"HTTP {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                    )

                data: dict[str, Any] = response.json()
                return self._parse_osrm_response(data)

            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exception = exc
                if attempt < max_attempts - 1:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise ProviderError(
                    "osrm",
                    f"Network error after retry: {exc}",
                ) from exc

        raise ProviderError(
            "osrm",
            f"Failed to fetch route from OSRM: {last_exception}",
        )

    def _parse_osrm_response(self, data: dict[str, Any]) -> RoutePath:
        """Parse OSRM JSON response into a RoutePath dataclass."""
        try:
            code = data.get("code")
            if code != "Ok":
                msg = data.get("message", "Unknown error")
                raise ProviderError("osrm", f"OSRM route returned code '{code}': {msg}")

            routes = data.get("routes", [])
            if not routes:
                raise ProviderError("osrm", "OSRM returned no routes")

            first_route = routes[0]
            distance_meters = float(first_route.get("distance", 0.0))

            geometry = first_route.get("geometry", {})
            raw_coords = geometry.get("coordinates", [])

            if not raw_coords:
                raise ValueError("OSRM response contained empty coordinates list")

            points = tuple(LatLon(lat=float(coord[1]), lon=float(coord[0])) for coord in raw_coords)
            distance_miles = distance_meters * METERS_TO_MILES

            return RoutePath(points=points, distance_miles=distance_miles)

        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(
                "osrm",
                f"Failed to parse OSRM route response: {exc}",
            ) from exc
