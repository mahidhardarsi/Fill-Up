"""Spatial station corridor indexing and candidate filtering using KD-Tree."""

import math
from collections.abc import Sequence
from typing import Protocol

import numpy as np
from scipy.spatial import cKDTree

from planner.geometry import (
    EARTH_RADIUS_MILES,
    compute_cumulative_distances,
    densify_polyline,
    haversine_distance_miles,
    latlon_to_cartesian,
)
from planner.types import CandidateStation, RoutePath


class StationIndex(Protocol):
    """Protocol for finding candidate stations along a route corridor."""

    def candidates(self, route: RoutePath, corridor_miles: float = 5.0) -> list[CandidateStation]:
        """Return candidate stations within corridor_miles of the route, with mile_marker set."""
        ...


class SpatialStationIndex:
    """In-memory spatial index for fuel stations using scipy.spatial.cKDTree.

    Converts station coordinates to 3D Cartesian coordinates on the Earth sphere
    to enable fast, singularity-free corridor distance queries.
    """

    def __init__(self, stations: Sequence[CandidateStation] | None = None) -> None:
        self._stations: tuple[CandidateStation, ...] = tuple(stations) if stations else ()
        self._tree: cKDTree | None = None

        if self._stations:
            coords = np.array(
                [
                    latlon_to_cartesian(s.location.lat, s.location.lon, EARTH_RADIUS_MILES)
                    for s in self._stations
                ],
                dtype=np.float64,
            )
            self._tree = cKDTree(coords)

    @property
    def station_count(self) -> int:
        """Total number of indexed stations."""
        return len(self._stations)

    def candidates(self, route: RoutePath, corridor_miles: float = 5.0) -> list[CandidateStation]:
        """Return candidate stations within corridor_miles of the route, with mile_marker set.

        The polyline is densified so that sampling points are spaced <= 1.5 miles.
        Each station within the corridor is matched to the nearest polyline point,
        and assigned that point's cumulative road mile marker.
        """
        if not self._stations or self._tree is None or not route.points:
            return []

        if corridor_miles <= 0:
            raise ValueError(f"corridor_miles must be positive, got {corridor_miles}")

        # 1. Densify route polyline to guarantee dense corridor sampling
        densified_points = densify_polyline(route.points, max_step_miles=1.5)
        raw_cumulative = compute_cumulative_distances(densified_points)

        # 2. Scale cumulative distances to match route.distance_miles if provided
        if route.distance_miles > 0 and raw_cumulative[-1] > 0:
            scale = route.distance_miles / raw_cumulative[-1]
            cumulative_miles = [dist * scale for dist in raw_cumulative]
        else:
            cumulative_miles = raw_cumulative

        # 3. Query cKDTree using 3D Euclidean chord radius
        # Chord distance c = 2 * R * sin(d / (2 * R))
        half_angle = corridor_miles / (2.0 * EARTH_RADIUS_MILES)
        chord_radius = 2.0 * EARTH_RADIUS_MILES * math.sin(half_angle)

        query_coords = np.array(
            [latlon_to_cartesian(p.lat, p.lon, EARTH_RADIUS_MILES) for p in densified_points],
            dtype=np.float64,
        )

        matched_lists = self._tree.query_ball_point(query_coords, r=chord_radius)

        # 4. Map each unique station to its closest polyline point and mile marker
        best_matches: dict[int, tuple[float, float]] = {}

        for point_idx, station_indices in enumerate(matched_lists):
            poly_point = densified_points[point_idx]
            point_mile = cumulative_miles[point_idx]

            for s_idx in station_indices:
                station = self._stations[s_idx]
                exact_dist = haversine_distance_miles(poly_point, station.location)

                if exact_dist <= corridor_miles:
                    if s_idx not in best_matches or exact_dist < best_matches[s_idx][0]:
                        best_matches[s_idx] = (exact_dist, point_mile)

        # 5. Build candidate stations with projected mile markers and sort by mile marker
        results: list[CandidateStation] = []
        for s_idx, (_dist, mile_marker) in best_matches.items():
            st = self._stations[s_idx]
            results.append(
                CandidateStation(
                    station_id=st.station_id,
                    name=st.name,
                    address=st.address,
                    city=st.city,
                    state=st.state,
                    location=st.location,
                    price_per_gallon=st.price_per_gallon,
                    mile_marker=round(mile_marker, 2),
                )
            )

        results.sort(key=lambda s: (s.mile_marker, s.price_per_gallon))
        return results
