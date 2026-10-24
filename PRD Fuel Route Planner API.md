# PRD: Fuel Route Planner API

**Owner:** Mahidhar  |  **Status:** Approved v2.0 (Antigravity Edition)  |  **Stack:** Django (latest stable), Python 3.12+, Django REST Framework  |  **Environment:** Antigravity 2.0 / Windows & Linux  |  **Delivery window:** 3 days from receipt

---

## 1. Overview

The **Fuel Route Planner API** accepts a start and a finish location within the United States and returns:

1. The optimal driving route, formatted as map-ready GeoJSON and viewable in both a web-based Leaflet HTML map and an inline Antigravity Generative UI preview widget.
2. An ordered list of recommended fuel stops along the route, selected algorithmically to minimize total fuel expenditure.
3. The total money spent on fuel across the entire journey.

The vehicle has a maximum range of **500 miles** on a full tank and achieves **10 miles per gallon (MPG)**, corresponding to a **50-gallon** fuel tank capacity. Fuel prices are sourced from the provided truckstop dataset. The system enforces strict external API call budgets, fast local computation, and clean architectural separation.

---

## 2. Problem Statement

Long-haul driving across the United States involves significant fuel price variance: across the supplied dataset, diesel prices vary by over \$3.70 per gallon between stations. For a 2,800-mile cross-country trip, stopping at optimal stations saves hundreds of dollars compared to random or unoptimized stops. Manually finding stations within reach and comparing prices along a multi-state route is intractable.

This API automates the process: given origin and destination, it calculates the route, queries candidates within a geographic corridor, applies a greedy optimization algorithm, and outputs the cost-minimal fuel stop plan in a single request.

---

## 3. Goals and Non-Goals

### Goals
- **G1. Route Generation**: Calculate driving routes between any two valid USA locations.
- **G2. Cost-Minimal Fuel Planning**: Select fuel stops that minimize overall cost while never exceeding the 500-mile vehicle range.
- **G3. Accurate Fuel Arithmetic**: Compute total gallons consumed and total fuel cost using exact `Decimal` arithmetic at 10 MPG.
- **G4. Dual-Surface Visualization**: Provide both an interactive Leaflet HTML map and an Antigravity Generative UI widget showing the route line, numbered stop markers, and fuel metrics.
- **G5. High Performance & Call Budget**: Achieve local computation $< 300\text{ ms}$ (p95), cache-hit responses $< 50\text{ ms}$, and at most 1 external routing call per request (at most 3 if free-text geocoding is required; 0 on cache hits).
- **G6. Production Engineering**: Strict typing (`mypy --strict`), comprehensive automated tests ($\ge 90\%$ coverage on core modules), property-based testing, and automated quality gates.

### Non-Goals
- Real-time or live fuel price scraping (the dataset is an offline static snapshot).
- Turn-by-turn navigation instructions.
- Detour fuel penalties (stations within the 5-mile corridor are assumed accessible with negligible detour cost).
- User authentication, billing, or saved trip profiles.
- Routes outside the contiguous United States, EV charging networks, traffic forecasting, or toll calculations.

---

## 4. Users and Use Cases

| User / Persona | Use Case |
| --- | --- |
| **Driver or Fleet Planner** | Inputs origin and destination; receives the cheapest fuel stop schedule, gallons to buy at each stop, and visual route map. |
| **Frontend / API Integrator** | Consumes JSON endpoints (`/api/v1/route/`) and renders GeoJSON features directly in client applications. |
| **Antigravity Pair Programmer / Reviewer** | Inspects system behavior, verifies quality gates, interacts with map artifacts in Antigravity chat, and audits performance benchmarks. |

---

## 5. Input Data: Analysis of Supplied Dataset

Analysis of `fuel-prices-for-be-assessment.csv` (8,151 rows):

| Property | Dataset Value | Engineering Implication |
| --- | --- | --- |
| **Row Count** | 8,151 rows, 7 columns (`OPIS Truckstop ID`, `Truckstop Name`, `Address`, `City`, `State`, `Rack ID`, `Retail Price`) | Memory-friendly; suitable for preloading into an in-memory spatial index (KD-Tree). |
| **Coordinates** | None (addresses formatted as highway exits, e.g., `I-44, EXIT 283 & US-69`) | Requires one-time offline geocoding before runtime matching. Zero runtime geocoding for stations. |
| **Duplicate IDs** | 1,413 duplicate IDs (597 IDs have conflicting prices) | Deterministic deduplication rule: preserve the record with the lowest retail price. |
| **Geographic Scope** | Includes non-US entries (Canadian provinces: AB, BC, MB, NB, NS, ON, QC, SK, YT) | Filtered out during CSV ingestion; only US stations are stored. |
| **Price Distribution** | Retail prices span \$2.69 to \$6.40 (mean ~\$3.50) | Validated with boundary assertions; parsed strictly into `Decimal`. |
| **Unique Locations** | ~6,434 unique (Address, City, State) tuples | Batch geocoded offline via US Census Geocoder + city centroid fallbacks. |

---

## 6. Default Assumptions

- **A1. Starting Fuel**: Vehicle departs origin with a **full tank (500 miles of range / 50 gallons)**. Only fuel purchased en route is charged to the trip cost.
- **A2. Final Arrival**: The planner buys only the exact quantity of fuel needed to reach the destination with zero waste.
- **A3. Fractional Fuel Purchases**: Stations permit continuous/fractional purchases up to tank capacity (50 gallons).
- **A4. Route Corridor**: A station is an eligible candidate if it lies within a **5-mile radius** of the route polyline.
- **A5. Constant Consumption**: Fuel economy is exactly 10 MPG regardless of terrain, payload, or speed.
- **A6. Duplicate Station Prices**: For repeated station IDs, the lowest price is preserved.
- **A7. Distance Metric**: Distances represent cumulative driving road miles along the routing provider's polyline.
- **A8. Safety Reserve**: Configurable reserve (default 0 miles; vehicle may run down to 0 at a planned stop).

---

## 7. Functional Requirements

### 7.1 Input Handling & Validation
- **FR1**: Accept `start` and `finish` as either free-text queries (e.g., `"Austin, TX"`) or explicit `{ "lat": float, "lon": float }` objects.
- **FR2**: Validate that coordinates and geocoded locations reside within the USA. Return HTTP 422 if outside the USA.
- **FR3**: Reject missing, empty, or identical start/finish inputs with HTTP 400.

### 7.2 Routing & Geocoding
- **FR4**: Request route polyline and distance using **exactly one call** to a routing provider (primary: OpenRouteService; fallback: OSRM).
- **FR5**: Free-text geocoding uses at most two provider calls (one for start, one for finish). Total external calls must never exceed 3 (1 with coordinates; 0 on cache hits).

### 7.3 Station Corridor Matching
- **FR6**: Station spatial matching executes **entirely locally** using the pre-computed `cKDTree` spatial index. No external calls permitted for station discovery.
- **FR7**: Identify all candidate stations within the 5-mile corridor and project each station onto the polyline to determine its **mile marker** (distance from route start).

### 7.4 Optimal Fuel Stop Selection
- **FR8**: Solve the fuel planning problem using a greedy strategy:
  - If a station with a lower price exists within reachable range, buy only enough fuel to reach that station.
  - If no cheaper station exists within reachable range, fill the tank to capacity (or enough to reach the destination if reachable), then advance to the cheapest available station within the expanded range.
- **FR9**: If the total route distance is $\le 500\text{ miles}$, return 0 fuel stops and \$0.00 fuel cost.
- **FR10**: If an unbridgeable station gap $> 500\text{ miles}$ occurs, raise `InfeasibleRouteError` and return HTTP 422 with the exact mile range of the gap.

### 7.5 Output & Visualization
- **FR11**: Response payload includes trip summary (total distance, gallons consumed, total fuel cost), an ordered stop list (name, address, city, state, coordinates, price per gallon, mile marker, gallons purchased, stop cost), and GeoJSON.
- **FR12**: Provide a dedicated HTML map view (`GET /api/v1/map/<request_id>/`) using Leaflet and OpenStreetMap tiles.
- **FR13**: Support inline Antigravity Generative UI visualization artifacts for interactive developer inspection inside the Antigravity chat.

---

## 8. API Specification

### 8.1 Plan Route Endpoint
`POST /api/v1/route/`

**Request Payload Examples:**
```json
{
  "start": "Los Angeles, CA",
  "finish": "New York, NY"
}
```
*Or using coordinate objects:*
```json
{
  "start": { "lat": 34.0522, "lon": -118.2437 },
  "finish": { "lat": 40.7128, "lon": -74.0060 }
}
```

**Response Payload (HTTP 200 OK):**
```json
{
  "request_id": "c7f1a8e0-4b21-4d33-9f8a-9812b1234567",
  "start": { "query": "Los Angeles, CA", "lat": 34.0522, "lon": -118.2437 },
  "finish": { "query": "New York, NY", "lat": 40.7128, "lon": -74.0060 },
  "distance_miles": 2790.4,
  "gallons_consumed": 279.04,
  "total_fuel_cost": 894.35,
  "currency": "USD",
  "stops": [
    {
      "order": 1,
      "name": "PILOT TRAVEL CENTER #123",
      "address": "I-40, EXIT 123",
      "city": "Flagstaff",
      "state": "AZ",
      "lat": 35.1983,
      "lon": -111.6513,
      "mile_marker": 462.1,
      "price_per_gallon": 3.09,
      "gallons_purchased": 46.21,
      "cost": 142.79
    }
  ],
  "route_geojson": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": {
          "type": "LineString",
          "coordinates": [[-118.2437, 34.0522], [-111.6513, 35.1983], [-74.0060, 40.7128]]
        },
        "properties": { "name": "Driving Route" }
      }
    ]
  },
  "map_url": "/api/v1/map/c7f1a8e0-4b21-4d33-9f8a-9812b1234567/",
  "meta": {
    "external_api_calls": 1,
    "cache_hit": false,
    "compute_ms": 112
  }
}
```

### 8.2 Interactive Map Endpoint
`GET /api/v1/map/<request_id>/`
Renders a responsive Leaflet.js HTML page displaying the route polyline, origin/destination markers, and numbered fuel stop pins with interactive popups showing price, gallons purchased, and stop cost.

### 8.3 Health Check Endpoint
`GET /api/v1/health/`
Returns `{"status": "healthy", "stations_loaded": 8151, "spatial_index_ready": true}`.

### 8.4 Error Handling
All error responses adhere to the uniform envelope:
```json
{
  "error": {
    "code": "LOCATION_OUTSIDE_USA",
    "message": "Start location resolved outside contiguous United States."
  }
}
```

| HTTP Status | Error Code | Trigger Condition |
| --- | --- | --- |
| **400 Bad Request** | `INVALID_INPUT` | Missing required parameters, invalid format, or identical start/finish |
| **422 Unprocessable** | `LOCATION_NOT_FOUND` | Free-text location could not be geocoded |
| **422 Unprocessable** | `OUTSIDE_USA` | Coordinates resolve outside the USA |
| **422 Unprocessable** | `INFEASIBLE_ROUTE` | Unbridgeable gap $> 500\text{ miles}$ without an available station |
| **429 Too Many Req** | `RATE_LIMITED` | DRF client throttling limit exceeded or provider rate limit encountered |
| **502 Bad Gateway** | `PROVIDER_ERROR` | Upstream routing/geocoding service unreachable or timed out |

---

## 9. Algorithmic Design: Fuel Stop Optimization

### 9.1 Formulation
Let the route be discretized into points with cumulative distances $d_0 = 0$ (origin) up to $d_{final} = D$ (destination). Stations $S = \{s_1, s_2, \dots, s_n\}$ along the corridor are ordered by mile marker $m_i \in [0, D]$, with unit fuel price $p_i$. The vehicle has fuel capacity $C = 50\text{ gal}$, fuel efficiency $\eta = 10\text{ MPG}$, and starting fuel range $R_0 = 500\text{ miles}$.

### 9.2 Greedy Execution
1. Sort candidate corridor stations strictly by increasing mile marker.
2. Initialize current location at mile 0 with full tank range (500 miles).
3. While current position $< D$:
   - Scan all reachable stations within current range.
   - **Case A (Cheaper station reachable)**: Find the nearest reachable station $s_{cheap}$ where $p_{cheap} < p_{curr}$. Purchase only enough fuel to reach $s_{cheap}$, and advance to $s_{cheap}$.
   - **Case B (Current station is cheapest in range)**:
     - If destination $D$ is within range, buy only fuel to reach $D$ and terminate.
     - Otherwise, purchase fuel to fill the tank to maximum capacity (500 miles of range). Advance to the station within range that offers the lowest fuel price.
4. If at any step no stations are reachable and the destination is not reachable, raise `InfeasibleRouteError(gap_start, gap_end)`.

### 9.3 Optimality & Verification
The greedy choice property guarantees optimal total cost for this problem structure. The implementation is verified through **property-based tests** cross-checking greedy results against an exhaustive dynamic programming reference across 500+ randomized station topologies.

---

## 10. System Design & Antigravity Architecture

```
                  +----------------------------------------------+
                  |         Antigravity Lead Orchestrator        |
                  |  - Planning, ADRs, Gates, Artifacts, Reports  |
                  +----------------------------------------------+
                                         |
         +-------------------------------+-------------------------------+
         |                               |                               |
+------------------+           +-------------------+           +-------------------+
|  Data Engineer   |           | Geo/Routing Eng.  |           |   Algorithm Eng.  |
| - CSV dedupe     |           | - ORS/OSRM client |           | - Greedy optimizer|
| - Offline geocode|           | - Polyline densify|           | - Decimal maths   |
| - Station loader |           | - KD-Tree index   |           | - Property tests  |
+------------------+           +-------------------+           +-------------------+
         |                               |                               |
         +-------------------------------+-------------------------------+
                                         |
         +-------------------------------+-------------------------------+
         |                                                               |
+------------------+                                           +-------------------+
|   API Engineer   |                                           |   Map Engineer    |
| - DRF endpoints  |                                           | - Leaflet HTML    |
| - Throttling     |                                           | - GeoJSON builder |
| - Error envelope |                                           | - Generative UI   |
+------------------+                                           +-------------------+
```

### 10.1 Components
- **Data Pipeline**: Clean, filter, and geocode the raw CSV once offline using the US Census Bureau batch API with city centroid fallback. Store processed data in `data/processed/stations_geocoded.json` and load via `python manage.py load_stations`.
- **Spatial Index**: `cKDTree` built from station coordinates at application startup. Enables sub-millisecond 5-mile corridor queries.
- **Routing Engine**: `RoutingClient` protocol with OpenRouteService primary and OSRM fallback. Strictly 1 routing call per uncached request.
- **Optimizer Engine**: Pure Python module (`planner/optimizer.py`) with zero Django or database dependencies.
- **Presentation Layer**: Django REST Framework API views, Leaflet map views, and Antigravity Generative UI widgets.

---

## 11. Non-Functional Requirements & Performance Budgets

| Requirement | Metric Target | Verification Strategy |
| --- | --- | --- |
| **Compute Latency** | Local compute $< 300\text{ ms}$ (p95) | Benchmarked across short, medium, and coast-to-coast routes in `tests/perf/` |
| **Cache-Hit Latency** | Response time $< 50\text{ ms}$ (p95) | Cached request integration tests |
| **Cold Request Latency** | Total response $< 2.0\text{ s}$ (p95) | End-to-end integration test with mocked provider network latency |
| **External Call Budget** | Exactly 1 for coordinates; $\le 3$ for text; 0 on cache hits | Monitored with strict call-counter assertions in tests |
| **Numeric Precision** | Zero float rounding errors | `Decimal` used exclusively for money, gallons, and unit prices |
| **Code Quality** | $\ge 90\%$ test coverage on core; `mypy --strict`; clean `ruff` | CI pipeline and Antigravity per-task quality gates |

---

## 12. Testing and Verification Strategy

1. **Unit Testing**:
   - Algorithmic edge cases: trip $< 500$ miles, single stop, cheaper station just outside range, equal prices, reserve miles, and unbridgeable gaps.
   - Polyline densification and KD-tree corridor spatial queries.
   - CSV deduplication, Canadian province filtering, and price boundary validation.
2. **Property-Based Testing**:
   - Compare greedy optimizer outputs against brute-force DP on $\ge 500$ randomized test cases.
3. **Mocked Integration Testing**:
   - Test endpoints with recorded fixtures for coast-to-coast (LA to NYC), regional (Dallas to Atlanta), and short (Philadelphia to NYC) trips. Assert exact external call counts.
4. **Antigravity Interactive Testing**:
   - Validate map rendering and stop placement via Antigravity Generative UI artifacts.

---

## 13. Phased 3-Day Delivery Plan

- **Day 1**: Scaffold Django project, implement CSV cleaning and offline geocoding command, load station database, build spatial index, implement pure greedy optimizer and property test suite.
- **Day 2**: Implement routing and geocoding clients with caching, connect corridor query to optimizer, implement DRF endpoints (`/api/v1/route/`, `/api/v1/health/`), and add Leaflet map template.
- **Day 3**: Complete integration tests with call-count assertions, profile performance against budgets, run security audits, author documentation (`README.md`, `PERF.md`, `STATUS.md`), and publish release tag `v1.0.0`.

---

## 14. Deliverables

1. Full Django source code repository matching the layout in `AGENTS.md`.
2. Cleaned and geocoded station dataset in `data/processed/`.
3. Comprehensive test suite achieving $\ge 90\%$ coverage on `planner/` and `routing/`.
4. Production configuration (`requirements.txt`, `.env.example`, `Dockerfile`, GitHub Actions CI).
5. Comprehensive `README.md` with setup guide, API examples, curl snippets, and architectural decisions.
6. Antigravity Artifacts: status logs, performance benchmarks, and interactive map preview.

---

## 15. Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Highway exit addresses fail exact geocoding | Medium | Census batch geocoder primary + city centroid fallback; transparent `geocode_quality` flag. |
| External routing provider rate limits | High | Aggressive in-memory/Redis caching; fallback OSRM support; coordinate inputs bypass geocoding. |
| Large route corridors slow spatial matching | Medium | Polyline densification at 1-mile steps + bounding box prefilter + `cKDTree` radial query. |
| Float precision drift in financial calculations | High | Mandatory `Decimal` throughout planner and API layers; rounded only at final serialization. |

---

## 16. Confirmed Design Decisions

1. **Starting Fuel**: Full tank (500 miles of range) provided free at start of journey.
2. **Duplicate Station Pricing**: Preserves the lowest price found among duplicate station IDs.
3. **Routing Provider**: OpenRouteService as primary provider, with OSRM demo as resilient fallback.
4. **Map Presentation**: Both REST API GeoJSON and rendered Leaflet HTML page provided.
5. **Corridor Radius**: 5 miles standard corridor width.

---

## 17. Additional Enhancements

- Detour road distance and time penalties incorporated into stop cost function.
- Multi-vehicle fleet profiles (configurable tank capacity, fuel efficiency, and fuel types).
- Station amenity filtering (truck parking, showers, weigh stations).
- Live fuel price sync hooks via periodic background tasks.
- Precomputed offline road graph for zero-external-call routing.
