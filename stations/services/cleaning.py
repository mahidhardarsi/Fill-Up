"""CSV cleaning and deduplication service for fuel station records."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TextIO

# Valid 50 US States + District of Columbia (DC)
US_STATES: frozenset[str] = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "DC",
    }
)

# Canadian provinces and territories to filter out
CANADIAN_PROVINCES: frozenset[str] = frozenset(
    {
        "AB",
        "BC",
        "MB",
        "NB",
        "NL",
        "NS",
        "NT",
        "NU",
        "ON",
        "PE",
        "QC",
        "SK",
        "YT",
    }
)

# Flexible column aliases for raw CSV ingestion
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "station_id": ("opis truckstop id", "station_id", "station id", "opis_truckstop_id", "id"),
    "name": ("truckstop name", "station_name", "station name", "truckstop_name", "name"),
    "address": ("address", "street_address", "street address", "street"),
    "city": ("city",),
    "state": ("state", "province", "st"),
    "price": ("retail price", "retail_price", "price", "price_per_gallon"),
}


@dataclass(frozen=True, slots=True)
class CleanedStationRecord:
    """Cleaned, validated, and deduplicated station record ready for geocoding/storage."""

    station_id: str
    name: str
    address: str
    city: str
    state: str
    price_per_gallon: Decimal


@dataclass(frozen=True, slots=True)
class CleaningSummary:
    """Detailed summary metrics for the CSV ingestion and deduplication stage."""

    raw_rows_count: int
    non_usa_dropped: int
    duplicates_dropped: int
    invalid_price_dropped: int
    valid_cleaned_count: int

    @property
    def total_dropped(self) -> int:
        """Total count of records dropped during cleaning."""
        return self.non_usa_dropped + self.duplicates_dropped + self.invalid_price_dropped


def _clean_text(value: str | None) -> str:
    """Strip whitespace and collapse multiple whitespace characters into a single space."""
    if not value:
        return ""
    stripped = value.strip().strip("\"'").strip()
    return " ".join(stripped.split())


def _parse_price(value: str | None) -> Decimal | None:
    """Parse raw price string into a positive Decimal, or return None if invalid."""
    if not value:
        return None
    cleaned = _clean_text(value).lstrip("$").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        price = Decimal(cleaned)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not price.is_finite() or price <= Decimal("0"):
        return None
    return price


def _resolve_column_mapping(fieldnames: list[str]) -> dict[str, str]:
    """Map expected fields to actual CSV header names using alias lookup."""
    normalized_fields = {fn.strip().lower(): fn for fn in fieldnames if fn}
    mapping: dict[str, str] = {}

    for target_key, aliases in _COLUMN_ALIASES.items():
        matched_header: str | None = None
        for alias in aliases:
            if alias in normalized_fields:
                matched_header = normalized_fields[alias]
                break
        if matched_header is None:
            raise ValueError(
                f"Missing required CSV column for '{target_key}'. Available headers: {fieldnames}"
            )
        mapping[target_key] = matched_header

    return mapping


def clean_stations_stream(
    stream: Iterable[str],
) -> tuple[list[CleanedStationRecord], CleaningSummary]:
    """Clean and deduplicate station records from an iterable/stream of CSV lines.

    Rules applied:
    1. Drop non-USA rows (Canadian provinces and any non 50 US states + DC).
    2. Validate retail price: must parse to a strictly positive, finite Decimal.
    3. Clean all text fields (strip leading/trailing whitespace, collapse internal spaces).
    4. Deterministic deduplication on OPIS Truckstop ID:
       Retains the record with the lowest retail price.
       If prices are equal, retains the first-encountered record.
       Preserves first-appearance order of station IDs.

    Args:
        stream: An iterable yielding CSV formatted lines (e.g. TextIO or file object).

    Returns:
        tuple containing:
            - list of cleaned and deduplicated CleanedStationRecord instances
            - CleaningSummary with row counts and dropped metrics
    """
    reader = csv.DictReader(stream, skipinitialspace=True)
    if reader.fieldnames is None:
        raise ValueError("CSV input is empty or missing headers.")

    mapping = _resolve_column_mapping(list(reader.fieldnames))

    raw_rows_count = 0
    non_usa_dropped = 0
    invalid_price_dropped = 0
    duplicates_dropped = 0

    best_records: dict[str, CleanedStationRecord] = {}

    col_id = mapping["station_id"]
    col_name = mapping["name"]
    col_addr = mapping["address"]
    col_city = mapping["city"]
    col_state = mapping["state"]
    col_price = mapping["price"]

    for row_idx, row in enumerate(reader, start=1):
        raw_rows_count += 1

        # Rule 1: Drop non-USA locations (keep only 50 US states + DC)
        raw_state = row.get(col_state)
        state_cleaned = _clean_text(raw_state).upper()
        if state_cleaned not in US_STATES:
            non_usa_dropped += 1
            continue

        # Rule 3: Retail price must be a positive, finite Decimal
        raw_price = row.get(col_price)
        price = _parse_price(raw_price)
        if price is None:
            invalid_price_dropped += 1
            continue

        # Rule 4: Clean text fields
        station_id = _clean_text(row.get(col_id))
        if not station_id:
            raise ValueError(f"Row {row_idx}: OPIS Truckstop ID cannot be empty.")

        name = _clean_text(row.get(col_name))
        address = _clean_text(row.get(col_addr))
        city = _clean_text(row.get(col_city))

        record = CleanedStationRecord(
            station_id=station_id,
            name=name,
            address=address,
            city=city,
            state=state_cleaned,
            price_per_gallon=price,
        )

        # Rule 2: Deterministic deduplication on station_id
        if station_id not in best_records:
            best_records[station_id] = record
        else:
            duplicates_dropped += 1
            current_best = best_records[station_id]
            # Retain record with strictly lowest retail price; if equal, keep existing (first)
            if record.price_per_gallon < current_best.price_per_gallon:
                best_records[station_id] = record

    summary = CleaningSummary(
        raw_rows_count=raw_rows_count,
        non_usa_dropped=non_usa_dropped,
        duplicates_dropped=duplicates_dropped,
        invalid_price_dropped=invalid_price_dropped,
        valid_cleaned_count=len(best_records),
    )

    return list(best_records.values()), summary


def clean_raw_stations_csv(
    csv_path: str | Path | TextIO,
) -> tuple[list[CleanedStationRecord], CleaningSummary]:
    """Clean and deduplicate station records from a CSV path, file object, or CSV string.

    Args:
        csv_path: File path as str or Path, an open TextIO stream, or inline CSV string.

    Returns:
        tuple containing (cleaned_records, cleaning_summary)
    """
    if isinstance(csv_path, str):
        if not csv_path.strip():
            raise ValueError("CSV input path or string cannot be empty.")
        if "\n" in csv_path:
            return clean_stations_stream(io.StringIO(csv_path))
        path = Path(csv_path)
        with path.open(mode="r", encoding="utf-8-sig") as f:
            return clean_stations_stream(f)

    if isinstance(csv_path, Path):
        with csv_path.open(mode="r", encoding="utf-8-sig") as f:
            return clean_stations_stream(f)

    return clean_stations_stream(csv_path)
