"""Fuel stop optimizer for cost-minimal fuel stop planning.

This module provides a pure Python greedy gas station optimization algorithm.
It has zero framework dependencies (no Django, no requests, no database).
All financial and fuel amounts are strictly calculated using Python's Decimal type.
"""

from collections.abc import Sequence
from decimal import Decimal

from planner.types import CandidateStation, FuelPlan, FuelStop, InfeasibleRouteError

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
        stations: Candidate stations located along the corridor.
        total_distance_miles: Total driving distance of the route in miles.
        range_miles: Maximum distance vehicle can travel on a full tank (default: 500.0).
        mpg: Miles per gallon fuel efficiency (default: 10.0).
        initial_range_miles: Distance vehicle can travel on fuel currently in tank (default: 500.0).
        reserve_miles: Safety reserve miles that should never be consumed (default: 0.0).

    Returns:
        FuelPlan containing ordered FuelStops, total cost, gallons purchased, and gallons consumed.

    Raises:
        InfeasibleRouteError: If any gap along the route exceeds vehicle reachable range.
        ValueError: If input parameters violate physical constraints (e.g., negative mpg).
    """
    if mpg <= 0.0:
        raise ValueError("mpg must be strictly positive")
    if range_miles <= 0.0:
        raise ValueError("range_miles must be strictly positive")
    if initial_range_miles < 0.0:
        raise ValueError("initial_range_miles cannot be negative")
    if reserve_miles < 0.0:
        raise ValueError("reserve_miles cannot be negative")
    if reserve_miles >= range_miles:
        raise ValueError("reserve_miles must be strictly less than range_miles")

    usable_range = range_miles - reserve_miles
    usable_initial = initial_range_miles - reserve_miles

    if usable_initial < 0.0:
        raise InfeasibleRouteError(0.0, total_distance_miles, total_distance_miles)

    # Convert mpg to Decimal once for exact fuel quantity arithmetic
    dec_mpg = Decimal(str(round(mpg, 6)))

    # Zero distance or trip already completed
    if total_distance_miles <= 0.0:
        return FuelPlan(
            stops=(),
            total_cost=Decimal("0.00"),
            total_gallons_purchased=Decimal("0.00"),
            gallons_consumed=Decimal("0.00"),
        )

    # Trip reachable on existing starting fuel without any stops
    if total_distance_miles <= usable_initial:
        gallons_consumed = Decimal(str(round(total_distance_miles, 6))) / dec_mpg
        return FuelPlan(
            stops=(),
            total_cost=Decimal("0.00"),
            total_gallons_purchased=Decimal("0.00"),
            gallons_consumed=gallons_consumed,
        )

    # Filter candidate stations to those strictly along the route between origin and destination
    candidates = [s for s in stations if 0.0 < s.mile_marker < total_distance_miles]
    candidates.sort(key=lambda s: s.mile_marker)

    # Deduplicate stations at identical mile markers, retaining the lowest price
    valid_stations: list[CandidateStation] = []
    for s in candidates:
        if valid_stations and abs(valid_stations[-1].mile_marker - s.mile_marker) < 1e-7:
            if s.price_per_gallon < valid_stations[-1].price_per_gallon:
                valid_stations[-1] = s
        else:
            valid_stations.append(s)

    # If no valid stations exist on a route exceeding initial range, the trip is infeasible
    if not valid_stations:
        raise InfeasibleRouteError(0.0, total_distance_miles, total_distance_miles)

    # Validate reachability of first station from origin
    if valid_stations[0].mile_marker > usable_initial + 1e-7:
        gap = valid_stations[0].mile_marker
        raise InfeasibleRouteError(0.0, valid_stations[0].mile_marker, gap)

    # Validate gaps between consecutive candidate stations
    for i in range(len(valid_stations) - 1):
        gap = valid_stations[i + 1].mile_marker - valid_stations[i].mile_marker
        if gap > usable_range + 1e-7:
            raise InfeasibleRouteError(
                valid_stations[i].mile_marker,
                valid_stations[i + 1].mile_marker,
                gap,
            )

    # Validate reachability from last candidate station to destination
    final_gap = total_distance_miles - valid_stations[-1].mile_marker
    if final_gap > usable_range + 1e-7:
        raise InfeasibleRouteError(
            valid_stations[-1].mile_marker,
            total_distance_miles,
            final_gap,
        )

    # Greedy fuel stop optimization
    stops: list[FuelStop] = []
    curr_pos = 0.0
    curr_fuel = usable_initial
    curr_station_idx = -1

    while curr_pos < total_distance_miles:
        if curr_station_idx == -1:
            # At origin: select the cheapest reachable station, tie-breaking by farthest distance
            reachable_indices = [
                j
                for j, s in enumerate(valid_stations)
                if s.mile_marker - curr_pos <= curr_fuel + 1e-7
            ]
            best_j = min(
                reachable_indices,
                key=lambda j: (valid_stations[j].price_per_gallon, -valid_stations[j].mile_marker),
            )
            dist = valid_stations[best_j].mile_marker - curr_pos
            curr_fuel -= dist
            curr_pos = valid_stations[best_j].mile_marker
            curr_station_idx = best_j
        else:
            curr_station = valid_stations[curr_station_idx]
            p_curr = curr_station.price_per_gallon
            max_reach = curr_pos + usable_range

            reachable_indices = [
                j
                for j in range(curr_station_idx + 1, len(valid_stations))
                if valid_stations[j].mile_marker <= max_reach + 1e-7
            ]

            cheaper_indices = [
                j for j in reachable_indices if valid_stations[j].price_per_gallon < p_curr
            ]

            if cheaper_indices:
                # Case A: Cheaper station reachable. Buy only enough fuel to reach nearest cheaper station
                next_j = cheaper_indices[0]
                dist = valid_stations[next_j].mile_marker - curr_pos
                miles_to_buy = dist - curr_fuel
                gallons = Decimal(str(round(miles_to_buy, 6))) / dec_mpg
                cost = gallons * p_curr
                stops.append(
                    FuelStop(
                        order=len(stops) + 1,
                        station=curr_station,
                        gallons=gallons,
                        cost=cost,
                    )
                )
                curr_fuel = 0.0
                curr_pos = valid_stations[next_j].mile_marker
                curr_station_idx = next_j
            else:
                # Case B: Current station is the cheapest in reachable range
                if total_distance_miles <= max_reach + 1e-7:
                    # Destination is reachable: buy only exact fuel needed to reach destination
                    dist = total_distance_miles - curr_pos
                    if curr_fuel < dist:
                        miles_to_buy = dist - curr_fuel
                        gallons = Decimal(str(round(miles_to_buy, 6))) / dec_mpg
                        cost = gallons * p_curr
                        stops.append(
                            FuelStop(
                                order=len(stops) + 1,
                                station=curr_station,
                                gallons=gallons,
                                cost=cost,
                            )
                        )
                    # Arrive at destination with zero surplus fuel
                    break
                else:
                    # Destination not reachable: fill tank to maximum capacity
                    miles_to_buy = usable_range - curr_fuel
                    if miles_to_buy > 1e-7:
                        gallons = Decimal(str(round(miles_to_buy, 6))) / dec_mpg
                        cost = gallons * p_curr
                        stops.append(
                            FuelStop(
                                order=len(stops) + 1,
                                station=curr_station,
                                gallons=gallons,
                                cost=cost,
                            )
                        )
                    curr_fuel = usable_range

                    # Advance to cheapest station in range, tie-breaking by farthest distance
                    next_j = min(
                        reachable_indices,
                        key=lambda j: (
                            valid_stations[j].price_per_gallon,
                            -valid_stations[j].mile_marker,
                        ),
                    )
                    dist = valid_stations[next_j].mile_marker - curr_pos
                    curr_fuel -= dist
                    curr_pos = valid_stations[next_j].mile_marker
                    curr_station_idx = next_j

    total_cost = sum((s.cost for s in stops), Decimal("0.00"))
    total_gallons_purchased = sum((s.gallons for s in stops), Decimal("0.00"))
    gallons_consumed = Decimal(str(round(total_distance_miles, 6))) / dec_mpg

    return FuelPlan(
        stops=tuple(stops),
        total_cost=total_cost,
        total_gallons_purchased=total_gallons_purchased,
        gallons_consumed=gallons_consumed,
    )
