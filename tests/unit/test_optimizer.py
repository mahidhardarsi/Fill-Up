"""Unit and property tests for the fuel stop optimizer and fuel planning service.

Includes exhaustive linear programming / dynamic programming comparator over >= 500 seeded
scenarios proving global optimality of the greedy strategy.
"""

import random
from collections.abc import Sequence
from decimal import Decimal

import numpy as np
import pytest
from scipy.optimize import linprog

from planner.optimizer import InfeasibleRouteError, plan_fuel_stops
from planner.service import FuelPlanningService, plan_route_fuel, plan_route_with_index
from planner.types import CandidateStation, LatLon, RoutePath


def make_station(
    station_id: str,
    mile_marker: float,
    price_per_gallon: str | Decimal,
    name: str = "Test Station",
    lat: float = 35.0,
    lon: float = -100.0,
) -> CandidateStation:
    """Helper to construct a test CandidateStation."""
    return CandidateStation(
        station_id=station_id,
        name=name,
        address=f"I-40 EXIT {station_id}",
        city="Test City",
        state="TX",
        location=LatLon(lat=lat, lon=lon),
        price_per_gallon=Decimal(str(price_per_gallon)),
        mile_marker=mile_marker,
    )


class DummyStationIndex:
    """Mock StationIndex for testing service integration."""

    def __init__(self, stations: Sequence[CandidateStation]) -> None:
        self._stations = list(stations)

    def candidates(self, route: RoutePath, corridor_miles: float = 5.0) -> list[CandidateStation]:
        return self._stations


# ==============================================================================
# 1. Edge Cases & Base Constraints
# ==============================================================================


class TestOptimizerBaseConstraints:
    """Tests basic input bounds, zero stops, and parameter validations."""

    def test_trip_zero_distance(self) -> None:
        plan = plan_fuel_stops([], 0.0)
        assert len(plan.stops) == 0
        assert plan.total_cost == Decimal("0.00")
        assert plan.total_gallons_purchased == Decimal("0.00")
        assert plan.gallons_consumed == Decimal("0.00")

    def test_trip_negative_distance(self) -> None:
        plan = plan_fuel_stops([], -10.0)
        assert len(plan.stops) == 0
        assert plan.total_cost == Decimal("0.00")
        assert plan.total_gallons_purchased == Decimal("0.00")
        assert plan.gallons_consumed == Decimal("0.00")

    def test_trip_under_500_miles_requires_zero_stops(self) -> None:
        stations = [
            make_station("s1", 100.0, "3.50"),
            make_station("s2", 250.0, "2.99"),
        ]
        plan = plan_fuel_stops(stations, 350.0)
        assert len(plan.stops) == 0
        assert plan.total_cost == Decimal("0.00")
        assert plan.total_gallons_purchased == Decimal("0.00")
        assert plan.gallons_consumed == Decimal("35.0")

    def test_trip_exactly_equal_initial_range_requires_zero_stops(self) -> None:
        stations = [make_station("s1", 250.0, "3.20")]
        plan = plan_fuel_stops(stations, 500.0, initial_range_miles=500.0)
        assert len(plan.stops) == 0
        assert plan.total_cost == Decimal("0.00")
        assert plan.total_gallons_purchased == Decimal("0.00")
        assert plan.gallons_consumed == Decimal("50.0")

    @pytest.mark.parametrize(
        ("mpg", "range_miles", "initial_range", "reserve", "expected_err"),
        [
            (-1.0, 500.0, 500.0, 0.0, "mpg must be strictly positive"),
            (0.0, 500.0, 500.0, 0.0, "mpg must be strictly positive"),
            (10.0, -100.0, 500.0, 0.0, "range_miles must be strictly positive"),
            (10.0, 0.0, 500.0, 0.0, "range_miles must be strictly positive"),
            (10.0, 500.0, -10.0, 0.0, "initial_range_miles cannot be negative"),
            (10.0, 500.0, 500.0, -5.0, "reserve_miles cannot be negative"),
            (10.0, 500.0, 500.0, 500.0, "reserve_miles must be strictly less than range_miles"),
            (10.0, 500.0, 500.0, 550.0, "reserve_miles must be strictly less than range_miles"),
        ],
    )
    def test_invalid_parameters_raise_value_error(
        self,
        mpg: float,
        range_miles: float,
        initial_range: float,
        reserve: float,
        expected_err: str,
    ) -> None:
        with pytest.raises(ValueError, match=expected_err):
            plan_fuel_stops(
                [],
                600.0,
                mpg=mpg,
                range_miles=range_miles,
                initial_range_miles=initial_range,
                reserve_miles=reserve,
            )

    def test_initial_range_less_than_reserve_raises_infeasible(self) -> None:
        # initial_range 40 < reserve 50 => cannot even depart safely
        with pytest.raises(InfeasibleRouteError) as exc_info:
            plan_fuel_stops([], 600.0, initial_range_miles=40.0, reserve_miles=50.0)
        assert exc_info.value.start_mile == 0.0
        assert exc_info.value.end_mile == 600.0
        assert exc_info.value.gap_miles == 600.0


# ==============================================================================
# 2. Infeasible Gap Detection Tests
# ==============================================================================


class TestInfeasibleRoutes:
    """Tests all cases of unbridgeable gaps along the route."""

    def test_no_stations_on_long_route(self) -> None:
        with pytest.raises(InfeasibleRouteError) as exc_info:
            plan_fuel_stops([], 800.0)
        assert exc_info.value.start_mile == 0.0
        assert exc_info.value.end_mile == 800.0
        assert exc_info.value.gap_miles == 800.0

    def test_gap_from_origin_to_first_station_exceeds_range(self) -> None:
        stations = [make_station("s1", 520.0, "3.50")]
        with pytest.raises(InfeasibleRouteError) as exc_info:
            plan_fuel_stops(stations, 800.0)
        assert exc_info.value.start_mile == 0.0
        assert exc_info.value.end_mile == 520.0
        assert exc_info.value.gap_miles == 520.0

    def test_gap_between_consecutive_stations_exceeds_range(self) -> None:
        stations = [
            make_station("s1", 300.0, "3.50"),
            make_station("s2", 820.0, "3.20"),  # gap = 520 > 500
        ]
        with pytest.raises(InfeasibleRouteError) as exc_info:
            plan_fuel_stops(stations, 1000.0)
        assert exc_info.value.start_mile == 300.0
        assert exc_info.value.end_mile == 820.0
        assert exc_info.value.gap_miles == 520.0

    def test_gap_from_last_station_to_destination_exceeds_range(self) -> None:
        stations = [make_station("s1", 400.0, "3.50")]
        with pytest.raises(InfeasibleRouteError) as exc_info:
            plan_fuel_stops(stations, 950.0)  # gap = 550 > 500
        assert exc_info.value.start_mile == 400.0
        assert exc_info.value.end_mile == 950.0
        assert exc_info.value.gap_miles == 550.0

    def test_safety_reserve_causes_infeasible_gap(self) -> None:
        # Range = 500, reserve = 50 => usable range = 450.
        # Gap = 480 is valid under 500, but exceeds 450.
        stations = [
            make_station("s1", 400.0, "3.50"),
            make_station("s2", 880.0, "3.20"),  # gap = 480 > 450
        ]
        with pytest.raises(InfeasibleRouteError) as exc_info:
            plan_fuel_stops(stations, 1200.0, range_miles=500.0, reserve_miles=50.0)
        assert exc_info.value.start_mile == 400.0
        assert exc_info.value.end_mile == 880.0
        assert exc_info.value.gap_miles == 480.0


# ==============================================================================
# 3. Optimization Scenarios & Purchase Rules
# ==============================================================================


class TestOptimizerScenarios:
    """Tests single stops, price comparisons, tie-breaking, and exact purchases."""

    def test_single_stop_optimal_purchase(self) -> None:
        # Distance = 800 miles. MPG = 10. Starting tank = 50 gal (500 miles free).
        # Total fuel needed for trip = 80 gal.
        # Station at mile 400 with price $3.00.
        # Vehicle arrives at mile 400 with 100 miles (10 gal) of free fuel remaining.
        # Distance to destination = 400 miles (40 gal).
        # Gallons to purchase = 40 - 10 = 30 gallons.
        # Total cost = 30 * $3.00 = $90.00.
        station = make_station("s1", 400.0, "3.00")
        plan = plan_fuel_stops([station], 800.0)

        assert len(plan.stops) == 1
        stop = plan.stops[0]
        assert stop.order == 1
        assert stop.station.station_id == "s1"
        assert stop.gallons == Decimal("30.0")
        assert stop.cost == Decimal("90.00")
        assert plan.total_cost == Decimal("90.00")
        assert plan.total_gallons_purchased == Decimal("30.0")
        assert plan.gallons_consumed == Decimal("80.0")

    def test_cheaper_station_within_reach_is_preferred(self) -> None:
        # Station 1: mile 200, $4.00. Station 2: mile 400, $2.50. Dest: 800.
        # Station 2 is in reach from origin on free fuel and cheaper.
        # Greedy skips station 1 entirely and buys at station 2.
        s1 = make_station("s1", 200.0, "4.00")
        s2 = make_station("s2", 400.0, "2.50")
        plan = plan_fuel_stops([s1, s2], 800.0)

        assert len(plan.stops) == 1
        assert plan.stops[0].station.station_id == "s2"
        # At mile 400, 100 miles fuel remaining. Destination 400 miles away.
        # Buys 300 miles / 10 mpg = 30 gal @ $2.50 = $75.00
        assert plan.stops[0].gallons == Decimal("30.0")
        assert plan.stops[0].cost == Decimal("75.00")
        assert plan.total_cost == Decimal("75.00")

    def test_cheaper_station_out_of_reach_requires_intermediate_fill(self) -> None:
        # Origin -> Station 1 (mile 100, $4.00) -> Station 2 (mile 550, $2.00) -> Dest 800.
        # From origin, station 2 (mile 550) is out of reach (> 500).
        # Vehicle must stop at station 1.
        # At station 1 (mile 100), station 2 (mile 550) is 450 miles away <= 500.
        # Station 2 is cheaper ($2.00 < $4.00).
        # At station 1, vehicle arrives with 400 miles of free fuel.
        # Needs 450 miles to reach station 2. Buys 50 miles (5 gal) @ $4.00 = $20.00.
        # At station 2 (mile 550), destination is 250 miles away. Arrives with 0 fuel.
        # Buys 250 miles (25 gal) @ $2.00 = $50.00.
        # Total cost = $70.00.
        s1 = make_station("s1", 100.0, "4.00")
        s2 = make_station("s2", 550.0, "2.00")
        plan = plan_fuel_stops([s1, s2], 800.0)

        assert len(plan.stops) == 2
        assert plan.stops[0].station.station_id == "s1"
        assert plan.stops[0].gallons == Decimal("5.0")
        assert plan.stops[0].cost == Decimal("20.00")

        assert plan.stops[1].station.station_id == "s2"
        assert plan.stops[1].gallons == Decimal("25.0")
        assert plan.stops[1].cost == Decimal("50.00")

        assert plan.total_cost == Decimal("70.00")
        assert plan.total_gallons_purchased == Decimal("30.0")
        assert plan.gallons_consumed == Decimal("80.0")

    def test_equal_prices_tie_break_farthest(self) -> None:
        # Station 1: mile 200, $3.00. Station 2: mile 400, $3.00. Dest: 700.
        # Both reachable from origin. Tie-break chooses farthest (mile 400).
        # At mile 400, dest is 300 miles away. Remaining fuel is 100 miles.
        # Buys 200 miles (20 gal) @ $3.00 = $60.00.
        s1 = make_station("s1", 200.0, "3.00")
        s2 = make_station("s2", 400.0, "3.00")
        plan = plan_fuel_stops([s1, s2], 700.0)

        assert len(plan.stops) == 1
        assert plan.stops[0].station.station_id == "s2"
        assert plan.stops[0].gallons == Decimal("20.0")
        assert plan.stops[0].cost == Decimal("60.00")

    def test_duplicate_mile_marker_picks_cheapest_record(self) -> None:
        # Two stations at mile 300: one at $4.00, one at $2.80. Dest: 700.
        s_expensive = make_station("s_exp", 300.0, "4.00")
        s_cheap = make_station("s_cheap", 300.0, "2.80")
        plan = plan_fuel_stops([s_expensive, s_cheap], 700.0)

        assert len(plan.stops) == 1
        assert plan.stops[0].station.station_id == "s_cheap"
        assert plan.stops[0].cost == Decimal("20.0") * Decimal("2.80")

    def test_filters_out_stations_outside_route(self) -> None:
        s_behind = make_station("s_behind", -50.0, "1.00")
        s_valid = make_station("s_valid", 300.0, "3.00")
        s_beyond = make_station("s_beyond", 900.0, "1.00")
        plan = plan_fuel_stops([s_behind, s_valid, s_beyond], 700.0)

        assert len(plan.stops) == 1
        assert plan.stops[0].station.station_id == "s_valid"

    def test_zero_waste_at_destination(self) -> None:
        # Initial fuel (50 gal) + fuel purchased must equal fuel consumed
        stations = [
            make_station("s1", 350.0, "3.20"),
            make_station("s2", 750.0, "3.10"),
            make_station("s3", 1100.0, "3.50"),
        ]
        total_dist = 1450.0
        plan = plan_fuel_stops(stations, total_dist)

        initial_gallons = Decimal("50.0")
        assert initial_gallons + plan.total_gallons_purchased == plan.gallons_consumed


# ==============================================================================
# 4. Service Layer Glue Tests
# ==============================================================================


class TestPlannerService:
    """Tests planner/service.py functions and FuelPlanningService class."""

    def test_plan_route_fuel_convenience_function(self) -> None:
        route = RoutePath(points=(LatLon(0.0, 0.0), LatLon(1.0, 1.0)), distance_miles=300.0)
        plan = plan_route_fuel(route, [])
        assert len(plan.stops) == 0
        assert plan.total_cost == Decimal("0.00")
        assert plan.gallons_consumed == Decimal("30.0")

    def test_plan_route_with_index(self) -> None:
        route = RoutePath(points=(LatLon(0.0, 0.0), LatLon(1.0, 1.0)), distance_miles=750.0)
        station = make_station("s1", 400.0, "3.00")
        index = DummyStationIndex([station])

        plan = plan_route_with_index(route, index)
        assert len(plan.stops) == 1
        assert plan.stops[0].station.station_id == "s1"
        assert plan.total_cost == Decimal("25.0") * Decimal("3.00")

    def test_fuel_planning_service_with_provided_stations(self) -> None:
        service = FuelPlanningService()
        route = RoutePath(points=(), distance_miles=800.0)
        stations = [make_station("s1", 400.0, "3.20")]

        plan = service.plan(route, stations=stations)
        assert len(plan.stops) == 1
        assert plan.stops[0].cost == Decimal("30.0") * Decimal("3.20")

    def test_fuel_planning_service_with_index(self) -> None:
        station = make_station("s1", 400.0, "3.20")
        index = DummyStationIndex([station])
        service = FuelPlanningService(station_index=index)
        route = RoutePath(points=(), distance_miles=800.0)

        plan = service.plan(route)
        assert len(plan.stops) == 1
        assert plan.stops[0].cost == Decimal("30.0") * Decimal("3.20")

    def test_fuel_planning_service_raises_when_no_index_and_no_stations(self) -> None:
        service = FuelPlanningService()
        route = RoutePath(points=(), distance_miles=800.0)

        with pytest.raises(ValueError, match="Either stations must be provided"):
            service.plan(route)


# ==============================================================================
# 5. Property-Based Verification (Exhaustive LP Reference >= 500 Scenarios)
# ==============================================================================


def solve_lp_reference(
    stations: Sequence[tuple[float, float]],
    total_distance: float,
    *,
    range_miles: float = 500.0,
    mpg: float = 10.0,
    initial_range: float = 500.0,
    reserve: float = 0.0,
) -> float | None:
    """Independent Linear Programming reference solver using HiGHS simplex.

    Formulates the exact continuous refueling problem as an LP:
      minimize sum(p_i / mpg * m_i)
      subject to prefix capacity bounds and prefix reachability bounds.
    """
    usable_range = range_miles - reserve
    usable_initial = initial_range - reserve

    valid_stations = [s for s in stations if 0 < s[0] < total_distance]
    valid_stations.sort(key=lambda s: s[0])

    # Deduplicate same mile markers
    deduped: list[tuple[float, float]] = []
    for s in valid_stations:
        if deduped and abs(deduped[-1][0] - s[0]) < 1e-7:
            if s[1] < deduped[-1][1]:
                deduped[-1] = s
        else:
            deduped.append(s)
    valid_stations = deduped

    if total_distance <= usable_initial:
        return 0.0

    if not valid_stations:
        return None

    if valid_stations[0][0] > usable_initial:
        return None

    for i in range(len(valid_stations) - 1):
        if valid_stations[i + 1][0] - valid_stations[i][0] > usable_range:
            return None

    if total_distance - valid_stations[-1][0] > usable_range:
        return None

    n = len(valid_stations)
    c = [s[1] / mpg for s in valid_stations]

    num_constraints = n + (n + 1)
    a_ub = np.zeros((num_constraints, n))
    b_ub = np.zeros(num_constraints)

    # Tank capacity bounds: sum_{i <= j} m_i <= range_miles - initial_range + x_j
    for j in range(n):
        a_ub[j, : j + 1] = 1.0
        b_ub[j] = range_miles - initial_range + valid_stations[j][0]

    # Reachability bounds: sum_{i <= j} m_i >= next_x - usable_initial
    for j in range(n):
        next_x = valid_stations[j + 1][0] if j + 1 < n else total_distance
        a_ub[n + j, : j + 1] = -1.0
        b_ub[n + j] = -(next_x - usable_initial)

    # Destination reachability
    a_ub[2 * n, :] = -1.0
    b_ub[2 * n] = -(total_distance - usable_initial)

    res = linprog(c, A_ub=a_ub, b_ub=b_ub, bounds=(0, None), method="highs")
    if res.success:
        return float(res.fun)
    return None


class TestPropertyOptimizerAgainstLP:
    """Property tests validating the greedy optimizer against Linear Programming on >= 500 topologies."""

    def test_greedy_matches_lp_across_500_seeded_scenarios(self) -> None:
        """Prove global optimality across 500 diverse, seeded random route topologies."""
        rng = random.Random(20261024)
        num_scenarios = 500
        tolerance = 1e-2  # 1 cent

        for scenario_idx in range(num_scenarios):
            total_dist = rng.uniform(400.0, 3200.0)
            range_miles = rng.choice([400.0, 500.0, 600.0])
            reserve_miles = rng.choice([0.0, 20.0, 50.0])
            mpg = rng.choice([8.0, 10.0, 12.5])
            initial_range = rng.choice([range_miles, range_miles - 50.0, 350.0])

            usable_range = range_miles - reserve_miles
            usable_initial = initial_range - reserve_miles

            # Generate random station positions ensuring coverage
            stations_raw: list[tuple[float, float]] = []
            curr = rng.uniform(20.0, min(300.0, usable_initial - 10.0))
            while curr < total_dist - 20.0:
                price = round(rng.uniform(2.40, 5.80), 2)
                stations_raw.append((curr, price))
                curr += rng.uniform(60.0, usable_range - 20.0)

            # Ensure final leg is bridgeable
            if stations_raw and total_dist - stations_raw[-1][0] > usable_range - 10.0:
                stations_raw.append((total_dist - 30.0, round(rng.uniform(2.40, 5.80), 2)))

            candidate_objs = [
                make_station(f"st_{i}", m, Decimal(str(p))) for i, (m, p) in enumerate(stations_raw)
            ]

            lp_cost = solve_lp_reference(
                stations_raw,
                total_dist,
                range_miles=range_miles,
                mpg=mpg,
                initial_range=initial_range,
                reserve=reserve_miles,
            )

            try:
                plan = plan_fuel_stops(
                    candidate_objs,
                    total_dist,
                    range_miles=range_miles,
                    mpg=mpg,
                    initial_range_miles=initial_range,
                    reserve_miles=reserve_miles,
                )
                greedy_cost = float(plan.total_cost)
            except InfeasibleRouteError:
                plan = None
                greedy_cost = None

            if lp_cost is None:
                assert greedy_cost is None, (
                    f"Scenario {scenario_idx}: LP failed but greedy returned {greedy_cost}"
                )
            else:
                assert greedy_cost is not None, (
                    f"Scenario {scenario_idx}: LP solved {lp_cost} but greedy raised Infeasible"
                )
                diff = abs(lp_cost - greedy_cost)
                assert diff <= tolerance, (
                    f"Scenario {scenario_idx} cost mismatch: LP={lp_cost:.4f}, Greedy={greedy_cost:.4f}, "
                    f"diff={diff:.4f}, total_dist={total_dist:.1f}"
                )
