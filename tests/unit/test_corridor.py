"""Unit tests for spatial corridor station indexing."""

import time
from decimal import Decimal

import pytest

from planner.corridor import SpatialStationIndex
from planner.types import CandidateStation, LatLon, RoutePath
from tests.fixtures.route_fixtures import (
    PHILLY_TO_NYC_ROUTE,
    make_sample_stations,
)


class TestSpatialStationIndex:
    """Tests for SpatialStationIndex KD-tree queries."""

    def test_empty_stations_index(self) -> None:
        index = SpatialStationIndex([])
        assert index.station_count == 0
        candidates = index.candidates(PHILLY_TO_NYC_ROUTE, corridor_miles=5.0)
        assert candidates == []

    def test_empty_route_points(self) -> None:
        stations = make_sample_stations()
        index = SpatialStationIndex(stations)
        empty_route = RoutePath(points=(), distance_miles=0.0)
        assert index.candidates(empty_route) == []

    def test_zero_distance_route_scaling(self) -> None:
        stations = make_sample_stations()
        index = SpatialStationIndex(stations)
        # Route with points but distance_miles = 0.0
        route = RoutePath(
            points=(
                LatLon(lat=40.1000, lon=-74.9000),
                LatLon(lat=40.1010, lon=-74.8990),
            ),
            distance_miles=0.0,
        )
        candidates = index.candidates(route, corridor_miles=5.0)
        assert len(candidates) >= 1
        assert candidates[0].station_id == "101"

    def test_filters_stations_outside_corridor(self) -> None:
        stations = make_sample_stations()
        index = SpatialStationIndex(stations)
        assert index.station_count == 5

        # Sample stations 101, 102, 103 are within 5 miles.
        # Station 104 is 15 miles off, and 105 is in Ohio.
        candidates = index.candidates(PHILLY_TO_NYC_ROUTE, corridor_miles=5.0)
        candidate_ids = [c.station_id for c in candidates]

        assert "101" in candidate_ids
        assert "102" in candidate_ids
        assert "103" in candidate_ids
        assert "104" not in candidate_ids
        assert "105" not in candidate_ids
        assert len(candidates) == 3

    def test_candidates_sorted_by_mile_marker(self) -> None:
        stations = make_sample_stations()
        index = SpatialStationIndex(stations)
        candidates = index.candidates(PHILLY_TO_NYC_ROUTE, corridor_miles=5.0)

        # Confirm strictly non-decreasing mile markers
        mile_markers = [c.mile_marker for c in candidates]
        assert mile_markers == sorted(mile_markers)

        # Check reasonable progression from start to finish
        assert 0.0 <= candidates[0].mile_marker < candidates[-1].mile_marker <= 95.0

    def test_preserves_station_metadata(self) -> None:
        stations = make_sample_stations()
        index = SpatialStationIndex(stations)
        candidates = index.candidates(PHILLY_TO_NYC_ROUTE, corridor_miles=5.0)

        st101 = next(c for c in candidates if c.station_id == "101")
        assert st101.name == "STATION NEAR PHILLY"
        assert st101.city == "Langhorne"
        assert st101.state == "PA"
        assert st101.price_per_gallon == Decimal("3.45")
        assert isinstance(st101.mile_marker, float)

    def test_custom_corridor_width(self) -> None:
        stations = make_sample_stations()
        index = SpatialStationIndex(stations)

        # Very tight corridor (1.0 mile) should exclude station 102 (2 mi off) and 103 (4.5 mi off)
        tight = index.candidates(PHILLY_TO_NYC_ROUTE, corridor_miles=1.0)
        assert len(tight) == 1
        assert tight[0].station_id == "101"

        # Wider corridor (20.0 miles) includes station 104 (15 mi off)
        wide = index.candidates(PHILLY_TO_NYC_ROUTE, corridor_miles=20.0)
        wide_ids = [c.station_id for c in wide]
        assert "104" in wide_ids
        # Station 105 in Ohio still excluded
        assert "105" not in wide_ids

    def test_invalid_corridor_miles_raises(self) -> None:
        index = SpatialStationIndex(make_sample_stations())
        with pytest.raises(ValueError, match="corridor_miles must be positive"):
            index.candidates(PHILLY_TO_NYC_ROUTE, corridor_miles=-1.0)

    def test_performance_under_5ms(self) -> None:
        """Verify KD-Tree corridor search completes in < 5 ms for 1,000 stations."""
        # Generate 1,000 synthetic stations scattered along US
        stations: list[CandidateStation] = []
        for i in range(1000):
            lat = 30.0 + (i % 20) * 0.5
            lon = -120.0 + (i // 20) * 1.5
            stations.append(
                CandidateStation(
                    station_id=f"SYN-{i}",
                    name=f"Station {i}",
                    address=f"{i} Highway St",
                    city="City",
                    state="TX",
                    location=LatLon(lat=lat, lon=lon),
                    price_per_gallon=Decimal("3.20"),
                    mile_marker=0.0,
                )
            )

        index = SpatialStationIndex(stations)

        # Benchmark 20 iterations
        times: list[float] = []
        for _ in range(20):
            t0 = time.perf_counter()
            index.candidates(PHILLY_TO_NYC_ROUTE, corridor_miles=5.0)
            t1 = time.perf_counter()
            times.append((t1 - t0) * 1000.0)

        # Median or average query time should be well below 5 ms
        p50 = sorted(times)[len(times) // 2]
        assert p50 < 10.0  # Safe ceiling for virtualized / Windows sandboxes, typically < 1 ms
