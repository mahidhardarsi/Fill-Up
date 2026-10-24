# ADR-001: Frozen Interface Contracts

## Status
Accepted

## Context
In accordance with AGENTS.md Section 8 and the PRD, the Fuel Route Planner API requires well-defined, frozen interface contracts before implementation starts. This allows parallel implementation of the algorithm, routing clients, geocoding, corridor querying, and API layers using stubs and synthetic fixtures without runtime dependencies.

## Decision
The core contracts are defined and frozen in Python dataclasses and protocols:

1. `planner/types.py`:
   - `LatLon(lat: float, lon: float)`
   - `RoutePath(points: tuple[LatLon, ...], distance_miles: float)`
   - `CandidateStation(station_id: str, name: str, address: str, city: str, state: str, location: LatLon, price_per_gallon: Decimal, mile_marker: float)`
   - `FuelStop(order: int, station: CandidateStation, gallons: Decimal, cost: Decimal)`
   - `FuelPlan(stops: tuple[FuelStop, ...], total_cost: Decimal, total_gallons_purchased: Decimal, gallons_consumed: Decimal)`
   - Exceptions: `InfeasibleRouteError(start_mile: float, end_mile: float, gap_miles: float)`

2. `planner/optimizer.py`:
   - `plan_fuel_stops(stations: Sequence[CandidateStation], total_distance_miles: float, *, range_miles: float = 500.0, mpg: float = 10.0, initial_range_miles: float = 500.0, reserve_miles: float = 0.0) -> FuelPlan`

3. `routing/clients/base.py`:
   - `RoutingClient(Protocol)`: `route(self, start: LatLon, finish: LatLon) -> RoutePath`

4. `routing/geocode.py`:
   - `Geocoder(Protocol)`: `geocode_us(self, query: str) -> LatLon`

5. `planner/corridor.py`:
   - `StationIndex(Protocol)`: `candidates(self, route: RoutePath, corridor_miles: float = 5.0) -> list[CandidateStation]`

6. `routing/errors.py`:
   - `RoutingError`, `LocationNotFound`, `OutsideUSA`, `ProviderError`, `ProviderRateLimited`

## Consequences
All agents must adhere to these exact types, method signatures, and exception types. Any change requires a new ADR approved by the orchestrator.

