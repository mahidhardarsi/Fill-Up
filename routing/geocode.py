"""Free-text geocoding protocol and interfaces."""

from typing import Protocol

from planner.types import LatLon


class Geocoder(Protocol):
    """Protocol for geocoding queries within the USA."""

    def geocode_us(self, query: str) -> LatLon:
        """Resolve a query string to US coordinates.

        Raises:
            LocationNotFound: if query cannot be resolved.
            OutsideUSA: if resolved coordinates are outside the US.
        """
        ...
