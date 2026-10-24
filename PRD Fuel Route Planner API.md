# PRD: Fuel Route Planner API

**Owner:** Mahidhar  |  **Status:** Draft v1.0  |  **Stack:** Django (latest stable), Python 3.12+  |  **Delivery window:** 3 days from receipt of the exercise

## 1. Overview

The Fuel Route Planner API accepts a start and a finish location inside the USA and returns:

1. The driving route, as a map-ready GeoJSON object and a viewable HTML map.
2. An ordered list of recommended fuel stops along the route, chosen to minimise total fuel cost.
3. The total money spent on fuel for the trip.

The vehicle has a maximum range of 500 miles on a full tank and achieves 10 miles per gallon (so a full tank is 50 gallons). Fuel prices come from the supplied CSV file. The API must be fast and must make very few calls to the external map/routing service.

## 2. Problem Statement

A driver planning a long USA trip wants to know where to stop for fuel and what it will cost. Fuel prices vary by about $3.70 per gallon across the dataset, so stopping at the right stations saves real money. Choosing stops by hand across a multi-state route is impractical. The API automates this: route, optimal stops, and total cost in one request.

## 3. Goals and Non-Goals

### Goals

- G1. Return a route between any two USA locations.
- G2. Select fuel stops that minimise total fuel cost while never exceeding the 500-mile range.
- G3. Return total fuel cost, using 10 MPG.
- G4. Return a map (GeoJSON plus a rendered HTML map) showing the route and stops.
- G5. Respond quickly: local computation under 300 ms, and at most 1 routing call per request (3 including geocoding, as a worst case).
- G6. Be production-shaped: validated input, clear errors, tests, README, reproducible setup.

### Non-Goals

- Real-time or live fuel prices (the CSV is a static snapshot).
- Turn-by-turn navigation.
- Detours: stations are assumed reachable from the route at negligible cost.
- User accounts, authentication, billing, or saved trips.
- Non-USA routes, EV charging, multiple vehicle profiles, traffic or tolls.

## 4. Users and Use Cases

| User | Use case |
| --- | --- |
| Driver or trip planner (via a client app) | Enter origin and destination and see the cheapest fuel plan on a map. |
| Frontend or integrator developer | Call a JSON API and render the returned GeoJSON. |
| Reviewer or evaluator | Run the project, hit the endpoint, check correctness, speed, and call count. |

## 5. Input Data: Findings from the Supplied CSV

The file `fuel-prices-for-be-assessment.csv` was inspected. These findings drive several requirements below.

| Finding | Detail | Implication |
| --- | --- | --- |
| Size | 8,151 rows, 7 columns: OPIS Truckstop ID, Truckstop Name, Address, City, State, Rack ID, Retail Price | Small enough to hold fully in memory. |
| No coordinates | Addresses look like `I-44, EXIT 283 & US-69`. There is no latitude or longitude. | Stations must be geocoded offline before they can be matched to a route. |
| Duplicate station IDs | 1,413 rows repeat an ID (678 distinct IDs affected). For 597 of those IDs, the repeated rows carry different prices. | Need a deterministic dedupe rule. |
| Non-USA rows | State codes include Canadian provinces and territories (AB, BC, MB, NB, NS, ON, QC, SK, YT). | Filter these out. |
| Price range | Retail price per gallon from about $2.69 to $6.40 (mean about $3.50). | Outliers near the top should be sanity-checked. |
| Unique locations | About 6,434 distinct address, city, state combinations. | This is the geocoding workload. |

## 6. Assumptions

These are explicit so the behaviour is predictable and reviewable. Items marked **(confirm)** should be confirmed with the exercise author if possible; otherwise the stated default is used and documented in the README.

- A1. Vehicle starts with a **full tank (500 miles of range)**. Only fuel purchased en route is charged. **(confirm)**
- A2. The vehicle may arrive with a small reserve; the planner buys only what is needed to reach the destination at the final stop.
- A3. Price is per gallon at the listed station; the vehicle can buy any fractional quantity up to tank capacity (50 gallons).
- A4. A station is a valid candidate if it lies within a corridor of **5 miles** of the route (configurable). Detour distance and fuel are ignored.
- A5. Fuel consumption is a constant 10 MPG regardless of terrain, speed, or load.
- A6. For duplicate station IDs, the **lowest price** is kept. This is the cost-optimal reading of the data. **(confirm)**
- A7. Distances are driving distances along the route returned by the routing provider, in miles.
- A8. An optional safety reserve (default 0 miles) can be configured so the planner never plans to run the tank to zero.

## 7. Functional Requirements

### 7.1 Input handling

- FR1. Accept `start` and `finish` as free-text locations (for example "Dallas, TX") **or** as `{lat, lon}` objects. Coordinates skip the geocoding call.
- FR2. Validate that both points resolve to locations inside the USA; otherwise return a 422 error.
- FR3. Reject missing, empty, or identical start and finish with a 400 error.

### 7.2 Routing

- FR4. Obtain the route with **one call** to a free routing API (primary: OpenRouteService; fallback: OSRM). The response supplies the full route geometry and total distance.
- FR5. Geocoding of free-text inputs may use the same provider (up to two additional calls). Total external calls per request must not exceed 3, and exactly 1 when coordinates are supplied or results are cached.

### 7.3 Station matching

- FR6. All station lookups run **locally** against preloaded, geocoded data. No external call is made to find stations.
- FR7. Find all stations within the corridor of the route and compute each station's **mile marker** (distance along the route at its nearest point).

### 7.4 Fuel stop optimisation

- FR8. Select the set of stops and purchase quantities that minimise total cost subject to: range of 500 miles, tank capacity of 50 gallons, and ending at the destination.
- FR9. If the whole trip is within range of the starting tank, return zero stops and a cost of $0, noting this in the response.
- FR10. If no feasible plan exists (a gap larger than 500 miles with no station), return a clear 422 error that states the offending mile range.

### 7.5 Output

- FR11. Return total distance, total gallons consumed, total fuel cost, and the list of stops (name, address, city, state, coordinates, price per gallon, mile marker, gallons purchased, cost).
- FR12. Return the route and stops as a GeoJSON FeatureCollection.
- FR13. Provide an HTML map view (Leaflet with OpenStreetMap tiles) showing the route line and numbered stop markers with popups.

## 8. API Specification

### 8.1 Plan a trip

`POST /api/v1/route/`

**Request**

```json
{
  "start": "Los Angeles, CA",
  "finish": "New York, NY"
}
```

Alternatively `{ "start": {"lat": 34.05, "lon": -118.24}, "finish": {"lat": 40.71, "lon": -74.00} }`.

**Response 200**

```json
{
  "request_id": "c7f1...",
  "start": {"query": "Los Angeles, CA", "lat": 34.05, "lon": -118.24},
  "finish": {"query": "New York, NY", "lat": 40.71, "lon": -74.00},
  "distance_miles": 2790.4,
  "gallons_consumed": 279.0,
  "total_fuel_cost": 905.12,
  "currency": "USD",
  "stops": [
    {
      "order": 1,
      "name": "EXAMPLE TRAVEL CENTER",
      "address": "I-40, EXIT 123",
      "city": "Example",
      "state": "AZ",
      "lat": 35.1,
      "lon": -111.6,
      "mile_marker": 410.2,
      "price_per_gallon": 3.05,
      "gallons_purchased": 41.0,
      "cost": 125.05
    }
  ],
  "route_geojson": { "type": "FeatureCollection", "features": [] },
  "map_url": "/api/v1/map/c7f1.../",
  "meta": {
    "external_api_calls": 1,
    "cache_hit": false,
    "compute_ms": 84
  }
}
```

Values above are illustrative only.

### 8.2 View the map

`GET /api/v1/map/<request_id>/` returns an HTML page rendering the stored result. The result is held in cache for a configurable time (default 24 hours).

### 8.3 Health

`GET /api/v1/health/` returns service status and the number of stations loaded.

### 8.4 Errors

| Status | Condition |
| --- | --- |
| 400 | Missing or malformed input, identical start and finish |
| 422 | Location not found or outside the USA; no feasible fuel plan (gap over 500 miles) |
| 502 | Routing or geocoding provider failed or timed out |
| 429 | Provider rate limit reached |

All errors use the shape `{"error": {"code": "...", "message": "..."}}`.

## 9. Core Algorithm: Fuel Stop Selection

This is the classic gas station problem, solved greedily on the stations found along the route.

1. Build the candidate list: stations in the corridor, sorted by mile marker. Add the start (mile 0, with the initial tank) and the destination (mile D) as virtual nodes.
2. At the current position, with current fuel in range terms, look at all stations reachable within a full tank (500 miles) ahead.
3. **If a cheaper station exists within range:** buy only enough fuel to reach the nearest such cheaper station, and drive there.
4. **If no cheaper station exists within range:** fill the tank to capacity at the current station (if the destination is not reachable otherwise), then drive to the cheapest station within the new range. If the destination is within range, buy only the fuel needed to arrive.
5. Repeat until the destination is reached.
6. Total cost is the sum over stops of gallons purchased multiplied by the price at that stop. Gallons purchased equal miles to cover divided by 10.

Why greedy works here: with a fixed tank capacity and no detour cost, buying just enough to reach a cheaper station and filling up fully only when the current station is the cheapest in range is provably optimal. The implementation is covered by tests that cross-check it against a brute-force dynamic program on small randomised cases.

Complexity is O(n log n) for sorting plus O(n) for the scan, where n is the number of corridor stations (typically a few hundred).

## 10. System Design

### 10.1 Components

| Component | Responsibility |
| --- | --- |
| Data prep command (`manage.py load_stations`) | One-time: clean CSV, dedupe, drop non-USA, geocode, store in the database. |
| `Station` model | id, name, address, city, state, lat, lon, price, geocode\_quality. |
| Station index | In-memory numpy arrays plus a `cKDTree` built at startup for fast spatial queries. |
| Routing client | Wraps the routing provider; timeouts, retries, error mapping. |
| Geocoding client | Free-text to coordinates, with caching. |
| Planner service | Corridor search, mile-marker computation, stop selection, cost calculation. |
| API layer | Django REST Framework views and serializers for validation. |
| Map renderer | Builds GeoJSON and the Leaflet HTML page. |
| Cache | Redis for geocodes, routes, and results. |

### 10.2 Request flow

1. Validate input.
2. Look up the cache for the (start, finish) pair. On a hit, skip to step 6.
3. Geocode free-text inputs if needed (0 to 2 calls, each cached).
4. Call the routing API once and obtain the geometry and distance.
5. Run the planner locally: corridor query, mile markers, stop selection, cost.
6. Build the response and GeoJSON, store the result under a `request_id`, and return it.

### 10.3 Offline station geocoding

Stations have no coordinates, so geocoding is a one-time batch job and never happens during a request.

- **Primary:** US Census Geocoder batch endpoint (free; a batch accepts up to 10,000 records, enough for the roughly 6,400 unique addresses).
- **Fallback:** city and state centroid from a free USA places dataset, for addresses that do not resolve (highway exit descriptions often will not).
- Each station stores a `geocode_quality` flag (`address` or `city_centroid`) so the accuracy is transparent.
- Because the corridor is 5 miles wide and city centroids can be off by a few miles, the README documents this tradeoff.

### 10.4 Spatial matching

- Densify the route polyline to a point roughly every 1 to 2 miles and compute cumulative distance along it.
- Query the KD-tree (on projected or scaled coordinates) with the corridor radius to find candidate stations.
- Assign each candidate to its nearest route point to obtain its mile marker.
- A bounding-box prefilter avoids testing stations far from the route.

### 10.5 External API budget

| Scenario | Geocode calls | Route calls | Total |
| --- | --- | --- | --- |
| Coordinates supplied | 0 | 1 | 1 |
| Free-text, cold cache | 2 | 1 | 3 |
| Repeated request (cache hit) | 0 | 0 | 0 |

The provider choice (OpenRouteService with a free key, OSRM demo as a fallback) should be confirmed against current free-tier limits at build time.

## 11. Non-Functional Requirements

| Area | Requirement |
| --- | --- |
| Performance | Local compute (excluding external calls) under 300 ms at p95; cache-hit responses under 50 ms; total response under 2 s at p95 on a cold request. |
| External calls | At most 3 per request; 1 when coordinates are given. |
| Reliability | Provider timeouts of 5 s with one retry; clean 502 on failure. |
| Correctness | Never plan a leg longer than 500 miles; cost arithmetic uses `Decimal` and rounds to cents at output. |
| Security | API keys read from environment variables, never committed; input validation; sensible DRF throttling. |
| Observability | Structured logging with `request_id`, call counts, and timings. |
| Portability | Runs with `pip install -r requirements.txt`, SQLite by default; optional Docker. |

## 12. Testing and Acceptance

### Test plan

- **Unit:** stop-selection algorithm (edge cases: trip under 500 miles, single stop, cheaper station just beyond range, gap over 500 miles, all stations equal price); mile-marker computation; cost arithmetic; CSV cleaning and dedupe.
- **Property check:** greedy planner compared against a brute-force optimiser on small random instances.
- **Integration:** endpoint tests with the routing client mocked (fixtures for a short, a medium, and a coast-to-coast route), asserting external call counts.
- **Manual:** one real run for each of several city pairs, verifying the map renders and stops sit near the route.

### Acceptance criteria

1. `POST /api/v1/route/` with a valid USA start and finish returns 200 with stops, total cost, and GeoJSON.
2. No leg between consecutive stops (or start and first stop, or last stop and finish) exceeds 500 miles.
3. Total cost equals the sum of per-stop costs, and total gallons purchased match the distance covered beyond the starting tank, at 10 MPG.
4. Coordinates-in requests make exactly 1 external call; free-text requests make at most 3; repeat requests make 0.
5. Non-USA or unresolvable locations return a clear 4xx error.
6. The HTML map shows the full route and numbered stop markers.
7. All tests pass, and the README lets a new reader run the project in under 10 minutes.

## 13. Delivery Plan (3 Days)

| Day | Scope | Exit criteria |
| --- | --- | --- |
| 1 | Project scaffold, CSV cleaning and dedupe, offline geocoding command, `Station` model and loader, KD-tree index. | Database loaded with geocoded US stations; quality stats reported. |
| 2 | Routing client, corridor search, mile markers, stop-selection algorithm, cost calculation, unit tests. | Planner returns correct stops and cost on fixture routes. |
| 3 | API endpoint and validation, GeoJSON and Leaflet map, caching, error handling, integration tests, README, demo recording. | Acceptance criteria 1 to 7 met; package ready to send. |

## 14. Deliverables

- Django project source in a repository.
- `requirements.txt`, `.env.example`, and optional Dockerfile.
- README: setup, data preparation, API usage, assumptions, and known limitations.
- Example requests and responses (curl or a Postman collection).
- Test suite.
- Short demo video or screenshots of the map.

## 15. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Poor geocoding quality for highway-exit addresses | High | Medium | Batch geocoder first, city-centroid fallback, `geocode_quality` flag, document the tradeoff. |
| Free routing API rate limits or downtime | Medium | High | Cache aggressively, support OSRM fallback, accept coordinates directly. |
| Geocoding job takes longer than planned | Medium | High | Start Day 1 with it; the city-centroid fallback guarantees full coverage quickly. |
| Sparse stations leave a gap over 500 miles on some routes | Low | Medium | Clear 422 error naming the gap; widen the corridor on retry as an option. |
| Ambiguous starting-fuel assumption | Medium | Medium | Document the default; make it a single configuration flag. |
| Ambiguous duplicate pricing | Medium | Low | Keep lowest price, document it, keep the rule isolated in the loader. |
| Corridor ignores real detour cost | High | Low | State the limitation; optional future work to include detour distance. |

## 16. Open Questions

1. Should the starting tank be assumed full and free, or should the first fill-up be costed? (Default: full, not charged.)
2. For duplicate station IDs with different prices, is the lowest price the intended choice, or the most recent? The file has no timestamp.
3. Is there a preferred free routing provider, or is the choice left entirely to the implementer?
4. Is a rendered map page required, or is GeoJSON sufficient? (Default: provide both.)
5. Is a maximum acceptable detour from the route expected? (Default: 5-mile corridor, detour cost ignored.)

## 17. additional Enhancements you can try

- Include detour distance and time in the stop cost.
- Support multiple vehicle profiles (range, MPG, tank size).
- Station-level amenities and brand filters.
- Price freshness handling and scheduled data refresh.
- Precomputed route graph for offline routing with zero external calls.
