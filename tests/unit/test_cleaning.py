"""Unit tests for the fuel station CSV cleaning and deduplication module."""

from decimal import Decimal
from pathlib import Path

import pytest

from stations.services.cleaning import (
    CANADIAN_PROVINCES,
    US_STATES,
    CleanedStationRecord,
    CleaningSummary,
    clean_raw_stations_csv,
    clean_stations_stream,
)

SAMPLE_CSV_HEADER = "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"


class TestRule1NonUsaFiltering:
    """Tests for Rule 1: Filtering non-USA records (Canadian provinces & unknown codes)."""

    def test_drops_canadian_provinces(self) -> None:
        csv_data = SAMPLE_CSV_HEADER + (
            "101,CANADIAN STOP 1,123 HWY 1,Calgary,AB,10,3.99\n"
            "102,CANADIAN STOP 2,456 HWY 2,Vancouver,BC,11,4.15\n"
            "103,CANADIAN STOP 3,789 HWY 3,Toronto,ON,12,4.25\n"
            "104,US STOP,100 MAIN ST,Dallas,TX,13,2.99\n"
        )
        records, summary = clean_raw_stations_csv(csv_data)

        assert summary.raw_rows_count == 4
        assert summary.non_usa_dropped == 3
        assert summary.valid_cleaned_count == 1
        assert len(records) == 1
        assert records[0].station_id == "104"
        assert records[0].state == "TX"

    def test_drops_all_known_canadian_provinces(self) -> None:
        rows = [
            f"{i},STOP {prov},ADDR,CITY,{prov},1,3.50\n"
            for i, prov in enumerate(CANADIAN_PROVINCES, start=1)
        ]
        csv_data = SAMPLE_CSV_HEADER + "".join(rows)
        records, summary = clean_raw_stations_csv(csv_data)

        assert summary.raw_rows_count == len(CANADIAN_PROVINCES)
        assert summary.non_usa_dropped == len(CANADIAN_PROVINCES)
        assert summary.valid_cleaned_count == 0
        assert len(records) == 0

    def test_accepts_all_50_us_states_and_dc(self) -> None:
        rows = [
            f"{i},STOP {st},ADDR,CITY,{st},1,3.50\n"
            for i, st in enumerate(sorted(US_STATES), start=1)
        ]
        csv_data = SAMPLE_CSV_HEADER + "".join(rows)
        records, summary = clean_raw_stations_csv(csv_data)

        assert summary.raw_rows_count == 51
        assert summary.non_usa_dropped == 0
        assert summary.valid_cleaned_count == 51
        assert len(records) == 51

    def test_drops_unknown_or_empty_state_codes(self) -> None:
        csv_data = SAMPLE_CSV_HEADER + (
            "201,MEXICO STOP,ADDR,CITY,MX,1,3.50\n"
            "202,UNKNOWN STOP,ADDR,CITY,ZZ,2,3.50\n"
            "203,EMPTY STOP,ADDR,CITY,,3,3.50\n"
            "204,VALID US STOP,ADDR,CITY,NY,4,3.50\n"
        )
        records, summary = clean_raw_stations_csv(csv_data)

        assert summary.raw_rows_count == 4
        assert summary.non_usa_dropped == 3
        assert summary.valid_cleaned_count == 1
        assert records[0].station_id == "204"


class TestRule2Deduplication:
    """Tests for Rule 2: Deterministic deduplication on OPIS Truckstop ID."""

    def test_retains_lowest_price_when_lower_price_appears_later(self) -> None:
        csv_data = SAMPLE_CSV_HEADER + (
            "500,EXPENSIVE FIRST,ADDR 1,Austin,TX,1,4.299\n"
            "500,CHEAP LATER,ADDR 2,Austin,TX,2,3.199\n"
            "500,MID PRICE LATEST,ADDR 3,Austin,TX,3,3.899\n"
        )
        records, summary = clean_raw_stations_csv(csv_data)

        assert summary.raw_rows_count == 3
        assert summary.duplicates_dropped == 2
        assert summary.valid_cleaned_count == 1
        assert len(records) == 1

        retained = records[0]
        assert retained.station_id == "500"
        assert retained.name == "CHEAP LATER"
        assert retained.price_per_gallon == Decimal("3.199")

    def test_retains_lowest_price_when_lower_price_appears_first(self) -> None:
        csv_data = SAMPLE_CSV_HEADER + (
            "600,CHEAP FIRST,ADDR 1,Denver,CO,1,2.999\n"
            "600,EXPENSIVE LATER,ADDR 2,Denver,CO,2,3.999\n"
        )
        records, summary = clean_raw_stations_csv(csv_data)

        assert summary.duplicates_dropped == 1
        assert summary.valid_cleaned_count == 1
        assert records[0].name == "CHEAP FIRST"
        assert records[0].price_per_gallon == Decimal("2.999")

    def test_retains_first_when_duplicate_prices_are_identical(self) -> None:
        csv_data = SAMPLE_CSV_HEADER + (
            "700,FIRST OCCURRENCE,ADDR 1,Phoenix,AZ,1,3.500\n"
            "700,SECOND OCCURRENCE,ADDR 2,Phoenix,AZ,2,3.500\n"
            "700,THIRD OCCURRENCE,ADDR 3,Phoenix,AZ,3,3.500\n"
        )
        records, summary = clean_raw_stations_csv(csv_data)

        assert summary.duplicates_dropped == 2
        assert summary.valid_cleaned_count == 1
        assert records[0].name == "FIRST OCCURRENCE"
        assert records[0].address == "ADDR 1"

    def test_preserves_first_appearance_order_of_station_ids(self) -> None:
        csv_data = SAMPLE_CSV_HEADER + (
            "10,STATION 10,ADDR,City,TX,1,3.50\n"
            "20,STATION 20,ADDR,City,TX,2,3.60\n"
            "30,STATION 30,ADDR,City,TX,3,3.70\n"
            "20,STATION 20 CHEAPER,ADDR,City,TX,4,3.10\n"
            "10,STATION 10 CHEAPER,ADDR,City,TX,5,3.00\n"
        )
        records, summary = clean_raw_stations_csv(csv_data)

        assert summary.raw_rows_count == 5
        assert summary.duplicates_dropped == 2
        assert summary.valid_cleaned_count == 3
        # First appearance order: 10, then 20, then 30
        assert [r.station_id for r in records] == ["10", "20", "30"]
        assert records[0].price_per_gallon == Decimal("3.00")
        assert records[1].price_per_gallon == Decimal("3.10")
        assert records[2].price_per_gallon == Decimal("3.70")


class TestRule3PriceValidation:
    """Tests for Rule 3: Retail price must be positive Decimal."""

    def test_drops_zero_and_negative_prices(self) -> None:
        csv_data = SAMPLE_CSV_HEADER + (
            "1,ZERO PRICE,ADDR,City,CA,1,0.00\n"
            "2,NEGATIVE PRICE,ADDR,City,CA,2,-3.50\n"
            "3,VALID PRICE,ADDR,City,CA,3,3.25\n"
        )
        records, summary = clean_raw_stations_csv(csv_data)

        assert summary.raw_rows_count == 3
        assert summary.invalid_price_dropped == 2
        assert summary.valid_cleaned_count == 1
        assert records[0].station_id == "3"

    def test_drops_non_numeric_and_special_floats(self) -> None:
        csv_data = SAMPLE_CSV_HEADER + (
            "11,STRING PRICE,ADDR,City,FL,1,FREE\n"
            "12,EMPTY PRICE,ADDR,City,FL,2,\n"
            "13,NAN PRICE,ADDR,City,FL,3,NaN\n"
            "14,INF PRICE,ADDR,City,FL,4,Infinity\n"
            "15,DOLLAR ONLY,ADDR,City,FL,5,$\n"
            "16,VALID PRICE,ADDR,City,FL,6,3.99\n"
        )
        records, summary = clean_raw_stations_csv(csv_data)

        assert summary.raw_rows_count == 6
        assert summary.invalid_price_dropped == 5
        assert summary.valid_cleaned_count == 1
        assert records[0].station_id == "16"

    def test_parses_formatted_currency_and_commas(self) -> None:
        csv_data = SAMPLE_CSV_HEADER + (
            '21,DOLLAR SIGN,ADDR,City,GA,1,"$3.499"\n'
            '22,SPACED DOLLAR,ADDR,City,GA,2," $ 3.899 "\n'
            '23,COMMA THOUSANDS,ADDR,City,GA,3,"1,003.50"\n'
        )
        records, summary = clean_raw_stations_csv(csv_data)

        assert summary.invalid_price_dropped == 0
        assert summary.valid_cleaned_count == 3
        assert records[0].price_per_gallon == Decimal("3.499")
        assert records[1].price_per_gallon == Decimal("3.899")
        assert records[2].price_per_gallon == Decimal("1003.50")


class TestRule4TextCleaning:
    """Tests for Rule 4: Cleaning text fields (whitespace, multi-space collapse, uppercase state)."""

    def test_cleans_excessive_whitespace(self) -> None:
        csv_data = SAMPLE_CSV_HEADER + (
            '  88  ,  PILOT   TRAVEL   CENTER  ,  " I-95,   EXIT   10 "  ,  " New   Castle   "  ,  " de "  ,1,  3.459  \n'
        )
        records, summary = clean_raw_stations_csv(csv_data)

        assert summary.valid_cleaned_count == 1
        rec = records[0]
        assert rec.station_id == "88"
        assert rec.name == "PILOT TRAVEL CENTER"
        assert rec.address == "I-95, EXIT 10"
        assert rec.city == "New Castle"
        assert rec.state == "DE"
        assert rec.price_per_gallon == Decimal("3.459")


class TestSummaryInvariantsAndExceptions:
    """Tests for CleaningSummary invariants, aliases, and error handling."""

    def test_summary_invariants_hold(self) -> None:
        record = CleanedStationRecord(
            station_id="1",
            name="TEST",
            address="123 MAIN",
            city="CITY",
            state="TX",
            price_per_gallon=Decimal("3.00"),
        )
        assert record.station_id == "1"

        summary_direct = CleaningSummary(
            raw_rows_count=10,
            non_usa_dropped=2,
            duplicates_dropped=3,
            invalid_price_dropped=1,
            valid_cleaned_count=4,
        )
        assert summary_direct.total_dropped == 6

        csv_data = SAMPLE_CSV_HEADER + (
            "1,US VALID,ADDR,City,TX,1,3.00\n"
            "1,US DUP,ADDR,City,TX,2,3.50\n"
            "2,CANADIAN,ADDR,City,ON,3,3.00\n"
            "3,INVALID PRICE,ADDR,City,TX,4,-1.00\n"
        )
        _, summary = clean_raw_stations_csv(csv_data)

        assert summary.raw_rows_count == 4
        assert summary.non_usa_dropped == 1
        assert summary.duplicates_dropped == 1
        assert summary.invalid_price_dropped == 1
        assert summary.valid_cleaned_count == 1
        assert summary.total_dropped == 3
        assert (
            summary.raw_rows_count
            == summary.non_usa_dropped
            + summary.duplicates_dropped
            + summary.invalid_price_dropped
            + summary.valid_cleaned_count
        )

    def test_flexible_header_aliases(self) -> None:
        alias_header = "station_id,name,address,city,state,price\n"
        csv_data = alias_header + "99,TEST STOP,100 HIGHWAY,AUSTIN,tx,3.19\n"
        records, summary = clean_raw_stations_csv(csv_data)

        assert summary.valid_cleaned_count == 1
        assert records[0].station_id == "99"
        assert records[0].name == "TEST STOP"
        assert records[0].price_per_gallon == Decimal("3.19")

    def test_raises_on_missing_column(self) -> None:
        bad_header = "station_id,name,address,city\n"  # missing state and price
        csv_data = bad_header + "1,NAME,ADDR,CITY\n"
        with pytest.raises(ValueError, match="Missing required CSV column"):
            clean_raw_stations_csv(csv_data)

    def test_raises_on_empty_input(self) -> None:
        with pytest.raises(ValueError, match="CSV input path or string cannot be empty"):
            clean_raw_stations_csv("   ")

    def test_raises_on_empty_station_id(self) -> None:
        csv_data = SAMPLE_CSV_HEADER + "  ,NAME,ADDR,City,TX,1,3.00\n"
        with pytest.raises(ValueError, match="OPIS Truckstop ID cannot be empty"):
            clean_raw_stations_csv(csv_data)

    def test_file_stream_and_path_inputs(self, tmp_path: Path) -> None:
        content = SAMPLE_CSV_HEADER + "1,NAME,ADDR,City,TX,1,3.15\n"
        file_path = tmp_path / "stations.csv"
        file_path.write_text(content, encoding="utf-8")

        # Test Path object
        records1, _ = clean_raw_stations_csv(file_path)
        assert len(records1) == 1

        # Test str path
        records2, _ = clean_raw_stations_csv(str(file_path))
        assert len(records2) == 1

        # Test open TextIO stream passed to clean_stations_stream
        with file_path.open("r", encoding="utf-8") as f:
            records3, _ = clean_stations_stream(f)
            assert len(records3) == 1

        # Test open TextIO stream passed to clean_raw_stations_csv
        with file_path.open("r", encoding="utf-8") as f:
            records4, _ = clean_raw_stations_csv(f)
            assert len(records4) == 1

    def test_raises_on_empty_stream(self) -> None:
        with pytest.raises(ValueError, match="CSV input is empty or missing headers"):
            clean_stations_stream([])


class TestRealDatasetIngestion:
    """End-to-end verification against the assessment dataset."""

    REAL_CSV_PATH = Path("data/raw/fuel-prices-for-be-assessment.csv")

    def test_real_dataset_metrics(self) -> None:
        if not self.REAL_CSV_PATH.is_file():
            pytest.skip(f"Baseline raw CSV not found at {self.REAL_CSV_PATH}")

        records, summary = clean_raw_stations_csv(self.REAL_CSV_PATH)

        # Baseline ground truth from raw dataset analysis
        assert summary.raw_rows_count == 8151
        assert summary.non_usa_dropped == 620
        assert summary.invalid_price_dropped == 0
        assert summary.duplicates_dropped == 905
        assert summary.valid_cleaned_count == 6626
        assert len(records) == 6626

        # Invariant check
        assert (
            summary.raw_rows_count
            == summary.non_usa_dropped
            + summary.duplicates_dropped
            + summary.invalid_price_dropped
            + summary.valid_cleaned_count
        )

        # Assert no duplicates exist in output
        seen_ids = set()
        for r in records:
            assert r.station_id not in seen_ids
            seen_ids.add(r.station_id)
            assert r.state in US_STATES
            assert r.price_per_gallon > Decimal("0")
            assert len(r.name) > 0
            assert len(r.address) > 0
            assert len(r.city) > 0
