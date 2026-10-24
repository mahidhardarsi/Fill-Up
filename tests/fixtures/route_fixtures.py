"""Test fixtures with recorded and synthetic routing, geocoding, and station responses."""

from decimal import Decimal
from typing import Any

from planner.types import CandidateStation, LatLon, RoutePath

# Standard US Cities
LA_COORDS = LatLon(lat=34.0522, lon=-118.2437)
NYC_COORDS = LatLon(lat=40.7128, lon=-74.0060)
CHICAGO_COORDS = LatLon(lat=41.8781, lon=-87.6298)
DALLAS_COORDS = LatLon(lat=32.7767, lon=-96.7970)
ATLANTA_COORDS = LatLon(lat=33.7490, lon=-84.3880)
PHILLY_COORDS = LatLon(lat=39.9526, lon=-75.1652)

# Non-contiguous / US Territories
ANCHORAGE_COORDS = LatLon(lat=61.2181, lon=-149.9003)
HONOLULU_COORDS = LatLon(lat=21.3069, lon=-157.8583)
SAN_JUAN_COORDS = LatLon(lat=18.4655, lon=-66.1057)

# International (Outside USA)
TORONTO_COORDS = LatLon(lat=43.6532, lon=-79.3832)
CALGARY_COORDS = LatLon(lat=51.0447, lon=-114.0719)
MEXICO_CITY_COORDS = LatLon(lat=19.4326, lon=-99.1332)
LONDON_COORDS = LatLon(lat=51.5074, lon=-0.1278)
TOKYO_COORDS = LatLon(lat=35.6762, lon=139.6503)

# Sample Synthetic Route: Philadelphia to New York (~95 miles)
PHILLY_TO_NYC_ROUTE = RoutePath(
    points=(
        LatLon(lat=39.9526, lon=-75.1652),
        LatLon(lat=40.1000, lon=-74.9000),
        LatLon(lat=40.3000, lon=-74.6000),
        LatLon(lat=40.5000, lon=-74.3000),
        LatLon(lat=40.7128, lon=-74.0060),
    ),
    distance_miles=95.0,
)


def make_ors_geojson_response(
    distance_meters: float = 152887.68,  # ~95 miles
    coordinates: list[list[float]] | None = None,
) -> dict[str, Any]:
    """Generate a synthetic OpenRouteService GeoJSON directions response."""
    coords = (
        coordinates
        if coordinates is not None
        else [
            [-75.1652, 39.9526],
            [-74.9000, 40.1000],
            [-74.6000, 40.3000],
            [-74.3000, 40.5000],
            [-74.0060, 40.7128],
        ]
    )
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords,
                },
                "properties": {
                    "summary": {
                        "distance": distance_meters,
                        "duration": 5800.0,
                    }
                },
            }
        ],
    }


def make_osrm_json_response(
    distance_meters: float = 152887.68,
    coordinates: list[list[float]] | None = None,
) -> dict[str, Any]:
    """Generate a synthetic OSRM directions response."""
    coords = (
        coordinates
        if coordinates is not None
        else [
            [-75.1652, 39.9526],
            [-74.9000, 40.1000],
            [-74.6000, 40.3000],
            [-74.3000, 40.5000],
            [-74.0060, 40.7128],
        ]
    )
    return {
        "code": "Ok",
        "routes": [
            {
                "distance": distance_meters,
                "duration": 5800.0,
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords,
                },
            }
        ],
        "waypoints": [
            {"location": [-75.1652, 39.9526], "name": "Philadelphia"},
            {"location": [-74.0060, 40.7128], "name": "New York"},
        ],
    }


def make_nominatim_response(
    lat: float = 34.0522,
    lon: float = -118.2437,
    display_name: str = "Los Angeles, Los Angeles County, California, USA",
    country_code: str = "us",
) -> list[dict[str, Any]]:
    """Generate a synthetic Nominatim geocoder response."""
    return [
        {
            "place_id": 123456,
            "licence": "Data © OpenStreetMap contributors",
            "lat": str(lat),
            "lon": str(lon),
            "display_name": display_name,
            "address": {"country_code": country_code},
        }
    ]


def make_ors_geocode_response(lat: float = 34.0522, lon: float = -118.2437) -> dict[str, Any]:
    """Generate a synthetic OpenRouteService geocoder response."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat],
                },
                "properties": {
                    "label": "Los Angeles, CA, USA",
                    "country": "United States",
                },
            }
        ],
    }


def make_sample_stations() -> list[CandidateStation]:
    """Generate sample candidate stations positioned near the Philly to NYC route."""
    return [
        # Exactly on route near mile 20
        CandidateStation(
            station_id="101",
            name="STATION NEAR PHILLY",
            address="100 Route 1",
            city="Langhorne",
            state="PA",
            location=LatLon(lat=40.1010, lon=-74.8980),
            price_per_gallon=Decimal("3.45"),
            mile_marker=0.0,
        ),
        # 2 miles off route near mile 50
        CandidateStation(
            station_id="102",
            name="STATION CENTRAL NJ",
            address="200 Route 1",
            city="Princeton",
            state="NJ",
            location=LatLon(lat=40.3200, lon=-74.6200),
            price_per_gallon=Decimal("3.15"),
            mile_marker=0.0,
        ),
        # 4.5 miles off route near mile 75
        CandidateStation(
            station_id="103",
            name="STATION EDISON",
            address="300 Turnpike",
            city="Edison",
            state="NJ",
            location=LatLon(lat=40.5400, lon=-74.3400),
            price_per_gallon=Decimal("3.85"),
            mile_marker=0.0,
        ),
        # ~10.5 miles off route (outside 5-mile corridor)
        CandidateStation(
            station_id="104",
            name="STATION FAR OFF",
            address="500 Ocean Ave",
            city="Asbury Park",
            state="NJ",
            location=LatLon(lat=40.3000, lon=-74.4000),
            price_per_gallon=Decimal("2.99"),
            mile_marker=0.0,
        ),
        # Far away in Ohio
        CandidateStation(
            station_id="105",
            name="STATION OHIO",
            address="100 Buckeye Way",
            city="Columbus",
            state="OH",
            location=LatLon(lat=39.9612, lon=-82.9988),
            price_per_gallon=Decimal("3.05"),
            mile_marker=0.0,
        ),
    ]
