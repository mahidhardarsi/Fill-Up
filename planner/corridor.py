"""Corridor candidate station filtering protocol."""

from typing import Protocol

from planner.types import CandidateStation, RoutePath


class StationIndex(Protocol):
    """Protocol for finding candidate stations along a route corridor."""

    def candidates(
        self, route: RoutePath, corridor_miles: float = 5.0
    ) -> list[CandidateStation]:
        """Return candidate stations within corridor_miles of the route, with mile_marker set."""
        ...
