"""Unit tests for routing clients (ORS, OSRM, Fallback, Cache) and Geocoder."""

from unittest.mock import MagicMock, patch

import pytest
import requests
from django.conf import settings
from django.core.cache import cache

from planner.types import RoutePath
from routing.clients.factory import (
    CachedRoutingClient,
    FallbackRoutingClient,
    get_routing_client,
)
from routing.clients.ors import OpenRouteServiceClient
from routing.clients.osrm import OSRMClient
from routing.errors import (
    LocationNotFound,
    OutsideUSA,
    ProviderError,
    ProviderRateLimited,
)
from routing.geocode import USGeocoder, is_in_us
from tests.fixtures.route_fixtures import (
    ANCHORAGE_COORDS,
    CALGARY_COORDS,
    HONOLULU_COORDS,
    LA_COORDS,
    LONDON_COORDS,
    MEXICO_CITY_COORDS,
    NYC_COORDS,
    PHILLY_COORDS,
    SAN_JUAN_COORDS,
    TOKYO_COORDS,
    make_nominatim_response,
    make_ors_geocode_response,
    make_ors_geojson_response,
    make_osrm_json_response,
)


class TestOpenRouteServiceClient:
    """Unit tests for OpenRouteServiceClient."""

    def test_default_api_key_from_settings(self) -> None:
        with patch.object(settings, "ORS_API_KEY", "settings-api-key"):
            client = OpenRouteServiceClient(api_key=None)
            assert client.api_key == "settings-api-key"

    def test_missing_api_key_raises_provider_error(self) -> None:
        client = OpenRouteServiceClient(api_key="")
        with pytest.raises(ProviderError, match="No API key configured"):
            client.route(PHILLY_COORDS, NYC_COORDS)

    def test_successful_geojson_response_parsing(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = make_ors_geojson_response(
            distance_meters=160934.4,  # Exactly 100 miles
            coordinates=[[-75.1652, 39.9526], [-74.0060, 40.7128]],
        )
        session.post.return_value = mock_resp

        client = OpenRouteServiceClient(api_key="test-api-key", session=session)
        route_path = client.route(PHILLY_COORDS, NYC_COORDS)

        assert isinstance(route_path, RoutePath)
        assert len(route_path.points) == 2
        assert route_path.points[0] == PHILLY_COORDS
        assert route_path.points[1] == NYC_COORDS
        assert pytest.approx(route_path.distance_miles, rel=1e-4) == 100.0
        assert session.post.call_count == 1

    def test_rate_limited_429_immediately_raises(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        session.post.return_value = mock_resp

        client = OpenRouteServiceClient(api_key="test-api-key", session=session)
        with pytest.raises(ProviderRateLimited) as exc_info:
            client.route(PHILLY_COORDS, NYC_COORDS)

        assert exc_info.value.status_code == 429
        assert exc_info.value.provider == "openrouteservice"
        assert session.post.call_count == 1

    def test_retry_on_500_server_error(self) -> None:
        session = MagicMock()
        mock_fail = MagicMock()
        mock_fail.status_code = 502
        mock_fail.text = "Bad Gateway"

        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = make_ors_geojson_response(distance_meters=10000.0)

        session.post.side_effect = [mock_fail, mock_ok]

        with patch("time.sleep"):
            client = OpenRouteServiceClient(api_key="test-api-key", session=session)
            route_path = client.route(PHILLY_COORDS, NYC_COORDS)

        assert session.post.call_count == 2
        assert route_path.distance_miles > 0

    def test_server_error_500_exhausted_retries_raises(self) -> None:
        session = MagicMock()
        mock_fail = MagicMock()
        mock_fail.status_code = 500
        mock_fail.text = "Internal Server Error"
        session.post.return_value = mock_fail

        with patch("time.sleep"):
            client = OpenRouteServiceClient(api_key="test-api-key", session=session)
            with pytest.raises(ProviderError, match="Server error 500"):
                client.route(PHILLY_COORDS, NYC_COORDS)

        assert session.post.call_count == 2

    def test_http_400_bad_request_raises(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request Parameters"
        session.post.return_value = mock_resp

        client = OpenRouteServiceClient(api_key="test-api-key", session=session)
        with pytest.raises(ProviderError, match="HTTP 400"):
            client.route(PHILLY_COORDS, NYC_COORDS)

    def test_exhausted_retries_network_error_raises(self) -> None:
        session = MagicMock()
        session.post.side_effect = requests.Timeout("Connection timed out")

        with patch("time.sleep"):
            client = OpenRouteServiceClient(api_key="test-api-key", session=session)
            with pytest.raises(ProviderError, match="Network error after retry"):
                client.route(PHILLY_COORDS, NYC_COORDS)

        assert session.post.call_count == 2

    def test_parsing_fallback_json_routes_format(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "routes": [
                {
                    "summary": {"distance": 50000.0},
                    "geometry": {"coordinates": [[-75.1652, 39.9526], [-74.0060, 40.7128]]},
                }
            ]
        }
        session.post.return_value = mock_resp

        client = OpenRouteServiceClient(api_key="test-api-key", session=session)
        route_path = client.route(PHILLY_COORDS, NYC_COORDS)
        assert len(route_path.points) == 2

    def test_parsing_missing_features_or_routes_raises(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"other_key": 123}
        session.post.return_value = mock_resp

        client = OpenRouteServiceClient(api_key="test-api-key", session=session)
        with pytest.raises(ProviderError, match="Failed to parse"):
            client.route(PHILLY_COORDS, NYC_COORDS)

    def test_parsing_empty_coordinates_raises(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = make_ors_geojson_response(coordinates=[])
        session.post.return_value = mock_resp

        client = OpenRouteServiceClient(api_key="test-api-key", session=session)
        with pytest.raises(ProviderError, match="Failed to parse"):
            client.route(PHILLY_COORDS, NYC_COORDS)


class TestOSRMClient:
    """Unit tests for OSRMClient."""

    def test_successful_osrm_response_parsing(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = make_osrm_json_response(
            distance_meters=160934.4,  # 100 miles
            coordinates=[[-75.1652, 39.9526], [-74.0060, 40.7128]],
        )
        session.get.return_value = mock_resp

        client = OSRMClient(session=session)
        route_path = client.route(PHILLY_COORDS, NYC_COORDS)

        assert isinstance(route_path, RoutePath)
        assert len(route_path.points) == 2
        assert pytest.approx(route_path.distance_miles, rel=1e-4) == 100.0
        assert session.get.call_count == 1

    def test_osrm_non_ok_code_raises_provider_error(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "code": "NoRoute",
            "message": "Impossible route",
            "routes": [],
        }
        session.get.return_value = mock_resp

        client = OSRMClient(session=session)
        with pytest.raises(ProviderError, match="OSRM route returned code 'NoRoute'"):
            client.route(PHILLY_COORDS, NYC_COORDS)

    def test_osrm_rate_limited_429(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        session.get.return_value = mock_resp

        client = OSRMClient(session=session)
        with pytest.raises(ProviderRateLimited) as exc_info:
            client.route(PHILLY_COORDS, NYC_COORDS)

        assert exc_info.value.status_code == 429
        assert session.get.call_count == 1

    def test_osrm_server_error_500_exhausted_retries(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"
        session.get.return_value = mock_resp

        with patch("time.sleep"):
            client = OSRMClient(session=session)
            with pytest.raises(ProviderError, match="Server error 503"):
                client.route(PHILLY_COORDS, NYC_COORDS)

        assert session.get.call_count == 2

    def test_osrm_http_400_raises(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        session.get.return_value = mock_resp

        client = OSRMClient(session=session)
        with pytest.raises(ProviderError, match="HTTP 400"):
            client.route(PHILLY_COORDS, NYC_COORDS)

    def test_osrm_retry_on_timeout(self) -> None:
        session = MagicMock()
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = make_osrm_json_response(distance_meters=50000.0)

        session.get.side_effect = [requests.Timeout("Timeout"), mock_ok]

        with patch("time.sleep"):
            client = OSRMClient(session=session)
            route_path = client.route(PHILLY_COORDS, NYC_COORDS)

        assert session.get.call_count == 2
        assert route_path.distance_miles > 0

    def test_osrm_empty_routes_raises(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": "Ok", "routes": []}
        session.get.return_value = mock_resp

        client = OSRMClient(session=session)
        with pytest.raises(ProviderError, match="OSRM returned no routes"):
            client.route(PHILLY_COORDS, NYC_COORDS)

    def test_osrm_empty_coordinates_raises(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "code": "Ok",
            "routes": [
                {
                    "distance": 100.0,
                    "geometry": {"coordinates": []},
                }
            ],
        }
        session.get.return_value = mock_resp

        client = OSRMClient(session=session)
        with pytest.raises(ProviderError, match="empty coordinates"):
            client.route(PHILLY_COORDS, NYC_COORDS)


class TestFallbackAndCachedRoutingClient:
    """Unit tests for FallbackRoutingClient and CachedRoutingClient."""

    def test_fallback_activates_on_primary_rate_limited(self) -> None:
        primary = MagicMock()
        primary.route.side_effect = ProviderRateLimited("openrouteservice")

        fallback = MagicMock()
        fallback.route.return_value = RoutePath(
            points=(PHILLY_COORDS, NYC_COORDS), distance_miles=95.0
        )

        client = FallbackRoutingClient(primary=primary, fallback=fallback)
        result = client.route(PHILLY_COORDS, NYC_COORDS)

        assert primary.route.call_count == 1
        assert fallback.route.call_count == 1
        assert result.distance_miles == 95.0

    def test_fallback_activates_on_primary_provider_error(self) -> None:
        primary = MagicMock()
        primary.route.side_effect = ProviderError("openrouteservice", "Service Down", 503)

        fallback = MagicMock()
        fallback.route.return_value = RoutePath(
            points=(PHILLY_COORDS, NYC_COORDS), distance_miles=95.0
        )

        client = FallbackRoutingClient(primary=primary, fallback=fallback)
        result = client.route(PHILLY_COORDS, NYC_COORDS)

        assert primary.route.call_count == 1
        assert fallback.route.call_count == 1
        assert result.distance_miles == 95.0

    def test_fallback_without_primary_uses_fallback(self) -> None:
        fallback = MagicMock()
        fallback.route.return_value = RoutePath(
            points=(PHILLY_COORDS, NYC_COORDS), distance_miles=95.0
        )
        client = FallbackRoutingClient(primary=None, fallback=fallback)
        result = client.route(PHILLY_COORDS, NYC_COORDS)
        assert fallback.route.call_count == 1
        assert result.distance_miles == 95.0

    def test_cached_client_guarantees_zero_calls_on_cache_hit(self) -> None:
        inner = MagicMock()
        inner.route.return_value = RoutePath(
            points=(PHILLY_COORDS, NYC_COORDS), distance_miles=95.0
        )

        cached_client = CachedRoutingClient(inner)

        # First call: makes exactly 1 inner call
        res1 = cached_client.route(PHILLY_COORDS, NYC_COORDS)
        assert inner.route.call_count == 1
        assert res1.distance_miles == 95.0

        # Second call with identical coordinates: 0 inner calls
        res2 = cached_client.route(PHILLY_COORDS, NYC_COORDS)
        assert inner.route.call_count == 1  # Unchanged!
        assert res2.distance_miles == 95.0
        assert res2.points == res1.points

    def test_cached_client_django_cache_backend_hit(self) -> None:
        inner = MagicMock()
        cached_client = CachedRoutingClient(inner)
        key = cached_client._cache_key(PHILLY_COORDS, NYC_COORDS)

        # Prepopulate Django cache backend
        cache.set(
            key,
            {
                "points": [
                    (PHILLY_COORDS.lat, PHILLY_COORDS.lon),
                    (NYC_COORDS.lat, NYC_COORDS.lon),
                ],
                "distance_miles": 95.5,
            },
            timeout=300,
        )

        result = cached_client.route(PHILLY_COORDS, NYC_COORDS)
        assert inner.route.call_count == 0
        assert result.distance_miles == 95.5
        assert len(result.points) == 2

    def test_cached_client_handles_django_cache_exceptions_gracefully(self) -> None:
        inner = MagicMock()
        inner.route.return_value = RoutePath(
            points=(PHILLY_COORDS, NYC_COORDS), distance_miles=95.0
        )
        cached_client = CachedRoutingClient(inner)

        with patch.object(cache, "get", side_effect=RuntimeError("Cache connection lost")):
            with patch.object(cache, "set", side_effect=RuntimeError("Cache connection lost")):
                res = cached_client.route(PHILLY_COORDS, NYC_COORDS)
                assert res.distance_miles == 95.0
                assert inner.route.call_count == 1

    def test_factory_returns_configured_client(self) -> None:
        client = get_routing_client(api_key="test-key", use_cache=True)
        assert isinstance(client, CachedRoutingClient)
        assert isinstance(client.inner_client, FallbackRoutingClient)

    def test_factory_without_api_key_or_cache(self) -> None:
        client = get_routing_client(api_key="", use_cache=False)
        assert isinstance(client, FallbackRoutingClient)
        assert client.primary is None


class TestUSBoundaryAndGeocoder:
    """Unit tests for US boundary checks and USGeocoder."""

    def test_is_in_us_boundaries(self) -> None:
        # Contiguous US
        assert is_in_us(LA_COORDS.lat, LA_COORDS.lon) is True
        assert is_in_us(NYC_COORDS.lat, NYC_COORDS.lon) is True
        assert is_in_us(PHILLY_COORDS.lat, PHILLY_COORDS.lon) is True

        # Non-contiguous US & territories
        assert is_in_us(ANCHORAGE_COORDS.lat, ANCHORAGE_COORDS.lon) is True
        assert is_in_us(HONOLULU_COORDS.lat, HONOLULU_COORDS.lon) is True
        assert is_in_us(SAN_JUAN_COORDS.lat, SAN_JUAN_COORDS.lon) is True

        # Outside USA (latitude / longitude outside US bounds)
        assert is_in_us(CALGARY_COORDS.lat, CALGARY_COORDS.lon) is False
        assert is_in_us(MEXICO_CITY_COORDS.lat, MEXICO_CITY_COORDS.lon) is False
        assert is_in_us(LONDON_COORDS.lat, LONDON_COORDS.lon) is False
        assert is_in_us(TOKYO_COORDS.lat, TOKYO_COORDS.lon) is False

    def test_geocoder_default_api_key_from_settings(self) -> None:
        with patch.object(settings, "ORS_API_KEY", "settings-ors-key"):
            geocoder = USGeocoder(api_key=None)
            assert geocoder.api_key == "settings-ors-key"

    def test_geocoder_empty_input_raises_location_not_found(self) -> None:
        geocoder = USGeocoder(api_key="")
        with pytest.raises(LocationNotFound):
            geocoder.geocode_us("")

        with pytest.raises(LocationNotFound):
            geocoder.geocode_us("   ")

    def test_geocoder_resolves_valid_us_location(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = make_nominatim_response(lat=34.0522, lon=-118.2437)
        session.get.return_value = mock_resp

        geocoder = USGeocoder(api_key="", session=session)
        coords = geocoder.geocode_us("Los Angeles, CA")

        assert pytest.approx(coords.lat, rel=1e-4) == 34.0522
        assert pytest.approx(coords.lon, rel=1e-4) == -118.2437
        assert session.get.call_count == 1

        # Second call to same query: 0 network calls (cached)
        cached_coords = geocoder.geocode_us("los angeles, ca")
        assert cached_coords == coords
        assert session.get.call_count == 1

    def test_geocoder_django_cache_backend_hit(self) -> None:
        session = MagicMock()
        geocoder = USGeocoder(api_key="", session=session)
        norm = geocoder._normalize_query("Denver, CO")
        key = geocoder._cache_key(norm)

        # Prepopulate Django cache backend
        cache.set(key, (39.7392, -104.9903), timeout=300)

        coords = geocoder.geocode_us("Denver, CO")
        assert session.get.call_count == 0
        assert pytest.approx(coords.lat, rel=1e-4) == 39.7392

    def test_geocoder_handles_django_cache_exceptions_gracefully(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = make_nominatim_response(lat=39.7392, lon=-104.9903)
        session.get.return_value = mock_resp

        geocoder = USGeocoder(api_key="", session=session)

        with patch.object(cache, "get", side_effect=RuntimeError("Cache get failed")):
            with patch.object(cache, "set", side_effect=RuntimeError("Cache set failed")):
                coords = geocoder.geocode_us("Denver, CO")
                assert session.get.call_count == 1
                assert pytest.approx(coords.lat, rel=1e-4) == 39.7392

    def test_geocoder_raises_outside_usa_when_resolved_abroad(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Resolves to Toronto, Canada with non-US country code
        mock_resp.json.return_value = make_nominatim_response(
            lat=43.6532,
            lon=-79.3832,
            display_name="Toronto, Golden Horseshoe, Ontario, Canada",
            country_code="ca",
        )
        session.get.return_value = mock_resp

        geocoder = USGeocoder(api_key="", session=session)
        with pytest.raises(OutsideUSA) as exc_info:
            geocoder.geocode_us("Toronto, ON")

        assert exc_info.value.lat == 43.6532
        assert exc_info.value.lon == -79.3832

    def test_geocoder_raises_outside_usa_when_coordinates_outside_bounds(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Resolves to London coordinates
        mock_resp.json.return_value = make_nominatim_response(
            lat=51.5074,
            lon=-0.1278,
            display_name="London, England",
            country_code="gb",
        )
        session.get.return_value = mock_resp

        geocoder = USGeocoder(api_key="", session=session)
        with pytest.raises(OutsideUSA) as exc_info:
            geocoder.geocode_us("London, UK")

        assert exc_info.value.lat == 51.5074
        assert exc_info.value.lon == -0.1278

    def test_geocoder_unresolved_query_raises_location_not_found(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []  # No results found
        session.get.return_value = mock_resp

        geocoder = USGeocoder(api_key="", session=session)
        with pytest.raises(LocationNotFound, match="nowhere_land_xyz_123"):
            geocoder.geocode_us("nowhere_land_xyz_123")

    def test_geocoder_nominatim_non_list_raises_location_not_found(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": "Invalid format"}
        session.get.return_value = mock_resp

        geocoder = USGeocoder(api_key="", session=session)
        with pytest.raises(LocationNotFound):
            geocoder.geocode_us("some query")

    def test_geocoder_nominatim_500_retries_and_exhausts(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Nominatim service down"
        session.get.return_value = mock_resp

        with patch("time.sleep"):
            geocoder = USGeocoder(api_key="", session=session)
            with pytest.raises(ProviderError, match="Server error 503"):
                geocoder.geocode_us("Austin, TX")

        assert session.get.call_count == 2

    def test_geocoder_nominatim_400_raises_provider_error(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        session.get.return_value = mock_resp

        geocoder = USGeocoder(api_key="", session=session)
        with pytest.raises(ProviderError, match="HTTP 400"):
            geocoder.geocode_us("Austin, TX")

    def test_geocoder_nominatim_network_timeout_retries_and_raises(self) -> None:
        session = MagicMock()
        session.get.side_effect = requests.Timeout("Nominatim timeout")

        with patch("time.sleep"):
            geocoder = USGeocoder(api_key="", session=session)
            with pytest.raises(ProviderError, match="Network error"):
                geocoder.geocode_us("Austin, TX")

        assert session.get.call_count == 2

    def test_geocoder_ors_primary_success(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = make_ors_geocode_response(lat=30.2672, lon=-97.7431)
        session.get.return_value = mock_resp

        geocoder = USGeocoder(api_key="valid-ors-key", session=session)
        coords = geocoder.geocode_us("Austin, TX")

        assert pytest.approx(coords.lat, rel=1e-4) == 30.2672
        assert pytest.approx(coords.lon, rel=1e-4) == -97.7431
        assert session.get.call_count == 1

    def test_geocoder_ors_foreign_country_raises_outside_usa(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-0.1278, 51.5074]},
                    "properties": {"country": "United Kingdom"},
                }
            ],
        }
        session.get.return_value = mock_resp

        geocoder = USGeocoder(api_key="valid-ors-key", session=session)
        with pytest.raises(OutsideUSA):
            geocoder.geocode_us("London")

    def test_geocoder_ors_empty_features_raises_location_not_found(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"features": []}
        session.get.return_value = mock_resp

        # ORS geocode raises LocationNotFound, which falls back to Nominatim
        # Let Nominatim also return empty
        mock_nom = MagicMock()
        mock_nom.status_code = 200
        mock_nom.json.return_value = []
        session.get.side_effect = [mock_resp, mock_nom]

        geocoder = USGeocoder(api_key="valid-ors-key", session=session)
        with pytest.raises(LocationNotFound):
            geocoder.geocode_us("Invalid Query")

    def test_geocoder_ors_primary_with_nominatim_fallback(self) -> None:
        session = MagicMock()
        # First call to ORS geocode returns 429
        mock_ors_429 = MagicMock()
        mock_ors_429.status_code = 429

        # Fallback call to Nominatim succeeds 200
        mock_nom_ok = MagicMock()
        mock_nom_ok.status_code = 200
        mock_nom_ok.json.return_value = make_nominatim_response(lat=40.7128, lon=-74.0060)

        session.get.side_effect = [mock_ors_429, mock_nom_ok]

        geocoder = USGeocoder(api_key="ors-key", session=session)
        coords = geocoder.geocode_us("New York, NY")

        assert pytest.approx(coords.lat, rel=1e-4) == 40.7128
        assert pytest.approx(coords.lon, rel=1e-4) == -74.0060
        assert session.get.call_count == 2
