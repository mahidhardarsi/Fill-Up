"""Unit tests for spherical geometry and polyline utilities."""

import math

import pytest

from planner.geometry import (
    EARTH_RADIUS_MILES,
    compute_cumulative_distances,
    densify_polyline,
    haversine_distance_miles,
    interpolate_latlon,
    latlon_to_cartesian,
)
from planner.types import LatLon
from tests.fixtures.route_fixtures import LA_COORDS, NYC_COORDS, PHILLY_COORDS


class TestHaversineDistance:
    """Tests for haversine_distance_miles."""

    def test_identical_points_return_zero(self) -> None:
        p = LatLon(lat=40.7128, lon=-74.0060)
        assert haversine_distance_miles(p, p) == 0.0

    def test_symmetry(self) -> None:
        dist_forward = haversine_distance_miles(NYC_COORDS, LA_COORDS)
        dist_reverse = haversine_distance_miles(LA_COORDS, NYC_COORDS)
        assert math.isclose(dist_forward, dist_reverse, rel_tol=1e-9)

    def test_nyc_to_la_known_distance(self) -> None:
        # Great circle distance between NYC and LA is ~2,446 to 2,455 miles
        distance = haversine_distance_miles(NYC_COORDS, LA_COORDS)
        assert 2440.0 < distance < 2460.0

    def test_philly_to_nyc_distance(self) -> None:
        distance = haversine_distance_miles(PHILLY_COORDS, NYC_COORDS)
        assert 75.0 < distance < 85.0

    def test_equator_longitude_degree_distance(self) -> None:
        # 1 degree of longitude at equator is ~ 69.17 miles
        p1 = LatLon(lat=0.0, lon=0.0)
        p2 = LatLon(lat=0.0, lon=1.0)
        expected = (2 * math.pi * EARTH_RADIUS_MILES) / 360.0
        assert math.isclose(haversine_distance_miles(p1, p2), expected, rel_tol=1e-5)


class TestInterpolateLatLon:
    """Tests for interpolate_latlon."""

    def test_endpoints(self) -> None:
        p1 = LatLon(lat=30.0, lon=-90.0)
        p2 = LatLon(lat=35.0, lon=-85.0)

        assert interpolate_latlon(p1, p2, 0.0) == p1
        assert interpolate_latlon(p1, p2, 1.0) == p2
        assert interpolate_latlon(p1, p2, -0.1) == p1
        assert interpolate_latlon(p1, p2, 1.2) == p2

    def test_midpoint_distance_balance(self) -> None:
        p1 = LatLon(lat=30.0, lon=-90.0)
        p2 = LatLon(lat=40.0, lon=-80.0)
        total_dist = haversine_distance_miles(p1, p2)

        mid = interpolate_latlon(p1, p2, 0.5)
        dist_first_half = haversine_distance_miles(p1, mid)
        dist_second_half = haversine_distance_miles(mid, p2)

        assert math.isclose(dist_first_half, dist_second_half, rel_tol=1e-3)
        assert math.isclose(dist_first_half + dist_second_half, total_dist, rel_tol=1e-3)

    def test_identical_points_interpolation(self) -> None:
        p = LatLon(lat=32.0, lon=-96.0)
        res = interpolate_latlon(p, p, 0.5)
        assert math.isclose(res.lat, p.lat, abs_tol=1e-6)
        assert math.isclose(res.lon, p.lon, abs_tol=1e-6)


class TestDensifyPolyline:
    """Tests for densify_polyline."""

    def test_empty_or_single_point(self) -> None:
        assert densify_polyline([]) == []
        single = [LatLon(lat=35.0, lon=-100.0)]
        assert densify_polyline(single) == single

    def test_already_dense_polyline(self) -> None:
        # Points very close (~0.1 miles apart)
        p1 = LatLon(lat=35.0, lon=-100.0)
        p2 = LatLon(lat=35.001, lon=-100.001)
        res = densify_polyline([p1, p2], max_step_miles=2.0)
        assert len(res) == 2
        assert res[0] == p1
        assert res[1] == p2

    def test_densifies_long_segment(self) -> None:
        # Distance ~70 miles
        p1 = LatLon(lat=35.0, lon=-100.0)
        p2 = LatLon(lat=36.0, lon=-100.0)
        densified = densify_polyline([p1, p2], max_step_miles=1.5)

        assert len(densified) > 40
        assert densified[0] == p1
        assert densified[-1] == p2

        # Verify all adjacent step distances are <= 1.5 miles
        for i in range(len(densified) - 1):
            step_dist = haversine_distance_miles(densified[i], densified[i + 1])
            assert step_dist <= 1.5 + 1e-4

    def test_invalid_max_step_raises(self) -> None:
        with pytest.raises(ValueError, match="max_step_miles must be positive"):
            densify_polyline([LA_COORDS, NYC_COORDS], max_step_miles=0.0)


class TestComputeCumulativeDistances:
    """Tests for compute_cumulative_distances."""

    def test_empty_and_single_point(self) -> None:
        assert compute_cumulative_distances([]) == []
        assert compute_cumulative_distances([LA_COORDS]) == [0.0]

    def test_three_points(self) -> None:
        p1 = LatLon(lat=30.0, lon=-90.0)
        p2 = LatLon(lat=31.0, lon=-90.0)
        p3 = LatLon(lat=32.0, lon=-90.0)

        cum = compute_cumulative_distances([p1, p2, p3])
        assert len(cum) == 3
        assert cum[0] == 0.0

        d1 = haversine_distance_miles(p1, p2)
        d2 = haversine_distance_miles(p2, p3)
        assert math.isclose(cum[1], d1, rel_tol=1e-5)
        assert math.isclose(cum[2], d1 + d2, rel_tol=1e-5)


class TestCartesianConversion:
    """Tests for latlon_to_cartesian."""

    def test_equator_prime_meridian(self) -> None:
        x, y, z = latlon_to_cartesian(0.0, 0.0, radius=100.0)
        assert math.isclose(x, 100.0, abs_tol=1e-6)
        assert math.isclose(y, 0.0, abs_tol=1e-6)
        assert math.isclose(z, 0.0, abs_tol=1e-6)

    def test_north_pole(self) -> None:
        x, y, z = latlon_to_cartesian(90.0, 0.0, radius=100.0)
        assert math.isclose(x, 0.0, abs_tol=1e-6)
        assert math.isclose(y, 0.0, abs_tol=1e-6)
        assert math.isclose(z, 100.0, abs_tol=1e-6)

    def test_norm_always_equals_radius(self) -> None:
        radius = EARTH_RADIUS_MILES
        for lat in [-75.0, -30.0, 0.0, 45.0, 80.0]:
            for lon in [-150.0, -60.0, 0.0, 90.0, 170.0]:
                x, y, z = latlon_to_cartesian(lat, lon, radius=radius)
                norm = math.sqrt(x * x + y * y + z * z)
                assert math.isclose(norm, radius, rel_tol=1e-6)
