"""Base interface for routing clients."""

from typing import Protocol

from planner.types import LatLon, RoutePath


class RoutingClient(Protocol):
    """Protocol for external routing services."""

    def route(self, start: LatLon, finish: LatLon) -> RoutePath:
        """Calculate a driving route between start and finish coordinates.

        Must make exactly 1 external call to the routing service.
        """
        ...
