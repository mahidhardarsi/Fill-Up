"""Routing and geocoding exceptions."""


class RoutingError(Exception):
    """Base exception for routing and geocoding errors."""


class LocationNotFound(RoutingError):
    """Raised when a geocoding query cannot be resolved."""

    def __init__(self, query: str) -> None:
        self.query = query
        super().__init__(f"Location could not be found: '{query}'")


class OutsideUSA(RoutingError):
    """Raised when coordinates or query resolve outside the United States."""

    def __init__(
        self, lat: float, lon: float, location_name: str | None = None
    ) -> None:
        self.lat = lat
        self.lon = lon
        self.location_name = location_name
        msg = f"Location ({lat}, {lon}) is outside the USA"
        if location_name:
            msg += f" ('{location_name}')"
        super().__init__(msg)


class ProviderError(RoutingError):
    """Raised when an external routing or geocoding provider fails or times out."""

    def __init__(
        self, provider: str, message: str, status_code: int | None = None
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"Routing provider '{provider}' failed: {message}")


class ProviderRateLimited(ProviderError):
    """Raised when a provider returns a 429 rate limit error."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            provider=provider, message="Rate limit exceeded", status_code=429
        )
