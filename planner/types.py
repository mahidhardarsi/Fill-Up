from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class LatLon:
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class RoutePath:
    points: tuple[LatLon, ...]  # full-resolution polyline
    distance_miles: float


@dataclass(frozen=True, slots=True)
class CandidateStation:
    station_id: str
    name: str
    address: str
    city: str
    state: str
    location: LatLon
    price_per_gallon: Decimal
    mile_marker: float  # distance along the route


@dataclass(frozen=True, slots=True)
class FuelStop:
    order: int
    station: CandidateStation
    gallons: Decimal
    cost: Decimal


@dataclass(frozen=True, slots=True)
class FuelPlan:
    stops: tuple[FuelStop, ...]
    total_cost: Decimal
    total_gallons_purchased: Decimal
    gallons_consumed: Decimal


class InfeasibleRouteError(Exception):
    """Raised when a gap along the route exceeds vehicle range."""

    def __init__(self, start_mile: float, end_mile: float, gap_miles: float) -> None:
        self.start_mile = start_mile
        self.end_mile = end_mile
        self.gap_miles = gap_miles
        super().__init__(
            f"No fuel station reachable between mile {start_mile:.1f} and mile {end_mile:.1f} "
            f"(gap of {gap_miles:.1f} miles exceeds vehicle range)"
        )
