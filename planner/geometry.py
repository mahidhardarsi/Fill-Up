"""High-speed spherical geometry and polyline utilities."""

import math
from collections.abc import Sequence

from planner.types import LatLon

# Mean Earth radius in miles (WGS-84 authalic radius: ~6371.0088 km / 1.609344)
EARTH_RADIUS_MILES: float = 3958.7613


def haversine_distance_miles(p1: LatLon, p2: LatLon) -> float:
    """Compute the great-circle distance between two LatLon points in miles using Haversine formula."""
    if p1.lat == p2.lat and p1.lon == p2.lon:
        return 0.0

    lat1 = math.radians(p1.lat)
    lon1 = math.radians(p1.lon)
    lat2 = math.radians(p2.lat)
    lon2 = math.radians(p2.lon)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return EARTH_RADIUS_MILES * c


def interpolate_latlon(p1: LatLon, p2: LatLon, fraction: float) -> LatLon:
    """Interpolate a point along the great circle between p1 and p2 at fraction [0.0, 1.0]."""
    if fraction <= 0.0:
        return p1
    if fraction >= 1.0:
        return p2

    lat1 = math.radians(p1.lat)
    lon1 = math.radians(p1.lon)
    lat2 = math.radians(p2.lat)
    lon2 = math.radians(p2.lon)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    a = min(1.0, max(0.0, a))
    delta = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    if delta < 1e-12:
        return p1

    sin_delta = math.sin(delta)
    factor_a = math.sin((1.0 - fraction) * delta) / sin_delta
    factor_b = math.sin(fraction * delta) / sin_delta

    x = factor_a * math.cos(lat1) * math.cos(lon1) + factor_b * math.cos(lat2) * math.cos(lon2)
    y = factor_a * math.cos(lat1) * math.sin(lon1) + factor_b * math.cos(lat2) * math.sin(lon2)
    z = factor_a * math.sin(lat1) + factor_b * math.sin(lat2)

    lat = math.atan2(z, math.sqrt(x * x + y * y))
    lon = math.atan2(y, x)

    return LatLon(lat=math.degrees(lat), lon=math.degrees(lon))


def densify_polyline(points: Sequence[LatLon], max_step_miles: float = 1.5) -> list[LatLon]:
    """Densify a polyline so adjacent points are separated by at most max_step_miles."""
    if len(points) <= 1:
        return list(points)
    if max_step_miles <= 0:
        raise ValueError(f"max_step_miles must be positive, got {max_step_miles}")

    densified: list[LatLon] = [points[0]]

    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        dist = haversine_distance_miles(p1, p2)

        if dist > max_step_miles:
            num_steps = int(math.ceil(dist / max_step_miles))
            for step in range(1, num_steps):
                fraction = step / num_steps
                densified.append(interpolate_latlon(p1, p2, fraction))

        densified.append(p2)

    return densified


def compute_cumulative_distances(points: Sequence[LatLon]) -> list[float]:
    """Compute cumulative great-circle distance in miles from the first point to each point."""
    if not points:
        return []

    cumulative = [0.0]
    total = 0.0

    for i in range(len(points) - 1):
        total += haversine_distance_miles(points[i], points[i + 1])
        cumulative.append(total)

    return cumulative


def latlon_to_cartesian(
    lat: float, lon: float, radius: float = EARTH_RADIUS_MILES
) -> tuple[float, float, float]:
    """Convert spherical latitude/longitude (degrees) to 3D Cartesian (x, y, z) coordinates."""
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    x = radius * math.cos(lat_r) * math.cos(lon_r)
    y = radius * math.cos(lat_r) * math.sin(lon_r)
    z = radius * math.sin(lat_r)
    return (x, y, z)
