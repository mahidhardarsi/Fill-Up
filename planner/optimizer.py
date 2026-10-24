"""Fuel stop optimizer interface and stubs."""

from collections.abc import Sequence

from planner.types import CandidateStation, FuelPlan, InfeasibleRouteError

__all__ = ["InfeasibleRouteError", "plan_fuel_stops"]


def plan_fuel_stops(
    stations: Sequence[CandidateStation],
    total_distance_miles: float,
    *,
    range_miles: float = 500.0,
    mpg: float = 10.0,
    initial_range_miles: float = 500.0,
    reserve_miles: float = 0.0,
) -> FuelPlan:
    """Select the optimal fuel stops minimizing total fuel cost while respecting range constraints.

    Args:
        stations: Candidate stations located in the corridor, ordered by mile_marker.
        total_distance_miles: Total driving distance of the route.
        range_miles: Maximum distance the vehicle can travel on a full tank (default: 500.0).
        mpg: Miles per gallon fuel efficiency (default: 10.0).
        initial_range_miles: Distance vehicle can travel on fuel currently in tank at start (default: 500.0).
        reserve_miles: Safety reserve miles that should never be consumed (default: 0.0).

    Returns:
        FuelPlan containing ordered FuelStops, total cost, gallons purchased, and gallons consumed.

    Raises:
        InfeasibleRouteError: If any gap along the route exceeds reachable range.
    """
    raise NotImplementedError("Optimizer not yet implemented")
