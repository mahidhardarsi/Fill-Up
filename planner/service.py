"""Fuel planning service coordinating route candidates and optimizer.

This module acts as the service layer glue between routing corridor candidate discovery
and the pure greedy fuel stop optimizer. It has zero framework/Django dependencies.
"""

from collections.abc import Sequence

from planner.corridor import StationIndex
from planner.optimizer import plan_fuel_stops
from planner.types import CandidateStation, FuelPlan, RoutePath

__all__ = ["FuelPlanningService", "plan_route_fuel", "plan_route_with_index"]


def plan_route_fuel(
    route: RoutePath,
    candidate_stations: Sequence[CandidateStation],
    *,
    range_miles: float = 500.0,
    mpg: float = 10.0,
    initial_range_miles: float = 500.0,
    reserve_miles: float = 0.0,
) -> FuelPlan:
    """Plan optimal fuel stops along a calculated route using pre-filtered candidate stations.

    Args:
        route: Calculated driving route with polyline points and distance.
        candidate_stations: Candidate stations located in the corridor with mile_marker set.
        range_miles: Full tank maximum range in miles (default: 500.0).
        mpg: Fuel economy miles per gallon (default: 10.0).
        initial_range_miles: Starting range on fuel in tank at origin (default: 500.0).
        reserve_miles: Safety reserve miles (default: 0.0).

    Returns:
        FuelPlan containing optimal FuelStops, total cost, gallons, and consumption metrics.
    """
    return plan_fuel_stops(
        stations=candidate_stations,
        total_distance_miles=route.distance_miles,
        range_miles=range_miles,
        mpg=mpg,
        initial_range_miles=initial_range_miles,
        reserve_miles=reserve_miles,
    )


def plan_route_with_index(
    route: RoutePath,
    station_index: StationIndex,
    *,
    corridor_miles: float = 5.0,
    range_miles: float = 500.0,
    mpg: float = 10.0,
    initial_range_miles: float = 500.0,
    reserve_miles: float = 0.0,
) -> FuelPlan:
    """Query candidates from a StationIndex and plan optimal fuel stops.

    Args:
        route: Calculated driving route.
        station_index: Spatial index implementing StationIndex protocol.
        corridor_miles: Search radius perpendicular to route polyline (default: 5.0).
        range_miles: Full tank range in miles.
        mpg: Fuel efficiency miles per gallon.
        initial_range_miles: Starting tank fuel in miles.
        reserve_miles: Safety reserve miles.

    Returns:
        FuelPlan containing optimal stops and costs.
    """
    candidates = station_index.candidates(route, corridor_miles=corridor_miles)
    return plan_route_fuel(
        route=route,
        candidate_stations=candidates,
        range_miles=range_miles,
        mpg=mpg,
        initial_range_miles=initial_range_miles,
        reserve_miles=reserve_miles,
    )


class FuelPlanningService:
    """Service orchestrating spatial corridor discovery and fuel stop optimization."""

    def __init__(self, station_index: StationIndex | None = None) -> None:
        self.station_index = station_index

    def plan(
        self,
        route: RoutePath,
        stations: Sequence[CandidateStation] | None = None,
        *,
        corridor_miles: float = 5.0,
        range_miles: float = 500.0,
        mpg: float = 10.0,
        initial_range_miles: float = 500.0,
        reserve_miles: float = 0.0,
    ) -> FuelPlan:
        """Plan optimal fuel stops for a route.

        If stations is None, uses self.station_index to discover candidates within corridor_miles.
        """
        if stations is not None:
            return plan_route_fuel(
                route=route,
                candidate_stations=stations,
                range_miles=range_miles,
                mpg=mpg,
                initial_range_miles=initial_range_miles,
                reserve_miles=reserve_miles,
            )

        if self.station_index is None:
            raise ValueError(
                "Either stations must be provided or FuelPlanningService initialized with StationIndex"
            )

        return plan_route_with_index(
            route=route,
            station_index=self.station_index,
            corridor_miles=corridor_miles,
            range_miles=range_miles,
            mpg=mpg,
            initial_range_miles=initial_range_miles,
            reserve_miles=reserve_miles,
        )
