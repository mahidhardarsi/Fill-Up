# ADR-002: Default Product and Technical Assumptions

## Status
Accepted

## Context
PRD Section 6 and Section 16 outline several assumptions and open questions that determine user-facing behavior, cost calculations, deduplication, and provider selection. To ensure deterministic and reproducible implementation, defaults must be established and recorded.

## Decision

1. **Starting Fuel (A1 & Open Question 1):**
   The vehicle starts with a full tank of fuel (500 miles of range, 50 gallons). Fuel initially in the tank is free/already paid for; only fuel purchased en route is charged and included in `total_fuel_cost`. If the total trip distance is <= 500 miles, 0 stops are required and `total_fuel_cost` is $0.00.

2. **Fuel Consumption & Sizing (A2, A3, A5):**
   - Fixed fuel consumption of 10.0 MPG.
   - Tank capacity of 50.0 gallons (range = 500.0 miles).
   - Fuel purchases can be fractional amounts.
   - At the final fuel stop, only the exact gallons needed to reach the destination are purchased (vehicle arrives at destination with zero unnecessary fuel purchased).

3. **Corridor Width & Detour (A4 & Open Question 5):**
   - Corridor width is 5.0 miles from the route polyline.
   - Detour distance and time to the station are assumed negligible / 0 cost as specified by the PRD.

4. **Duplicate Station ID Pricing (A6 & Open Question 2):**
   - When a station ID appears multiple times in the CSV, the **lowest price** is retained.
   - Canadian provinces/territories (AB, BC, MB, NB, NS, ON, QC, SK, YT) and non-US records are filtered out.

5. **Routing & Geocoding Providers (Open Question 3):**
   - Routing: Primary is OpenRouteService (ORS) API if key is supplied; fallback is OSRM public API (`https://router.project-osrm.org`).
   - Geocoding: Free US geocoding (OpenRouteService Pelias / Nominatim / Photon) with strict USA bounding and caching.
   - Station geocoding is performed completely offline and never at request time.

6. **Outputs (Open Question 4):**
   - Both a GeoJSON FeatureCollection and an interactive Leaflet HTML map view (`GET /api/v1/map/<request_id>/`) are supported and provided.

7. **Safety Reserve (A8):**
   - Configurable reserve parameter (default: 0.0 miles), allowing safety margins if requested.

8. **Money & Arithmetic Standards:**
   - All monetary amounts and fuel gallons use Python's `Decimal` type to prevent float imprecision. Rounding to 2 decimal places (half-up) occurs only at serialization.

