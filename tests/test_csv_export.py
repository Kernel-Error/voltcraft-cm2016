"""Tests for cm2016.export.csv_export — CSV export."""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

from cm2016.export.csv_export import CSV_HEADERS, export_csv
from cm2016.protocol import parse_frame
from cm2016.session import SlotRecord
from tests.conftest import make_frame

if TYPE_CHECKING:
    from pathlib import Path


def _make_records(count: int = 3) -> list[SlotRecord]:
    """Create a list of test records."""
    frame = parse_frame(
        make_frame(
            slot_overrides={
                0: {
                    "active": 1,
                    "program": 1,
                    "step": 1,
                    "status": 0x00,
                    "runtime_minutes": 10,
                    "voltage_mv": 1320,
                    "current_raw": 500,
                    "charge_cap_raw": 75000,
                    "discharge_cap_raw": 0,
                },
            }
        )
    )
    return [SlotRecord.from_slot_data(frame.slots[0], "NiMH") for _ in range(count)]


class TestExportCsv:
    """Test CSV export function."""

    def test_exports_correct_headers(self, tmp_path: Path) -> None:
        records = _make_records(1)
        path = tmp_path / "test.csv"
        export_csv(records, path)

        with path.open(encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)
        assert headers == CSV_HEADERS

    def test_exports_correct_row_count(self, tmp_path: Path) -> None:
        records = _make_records(5)
        path = tmp_path / "test.csv"
        count = export_csv(records, path)

        assert count == 5
        with path.open(encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 6  # 1 header + 5 data

    def test_exports_correct_values(self, tmp_path: Path) -> None:
        records = _make_records(1)
        path = tmp_path / "test.csv"
        export_csv(records, path)

        with path.open(encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            row = next(reader)

        assert row[0] == "1"  # Slot (index 0 + 1)
        assert row[2] == "Charge"  # Program
        assert row[4] == "1.320"  # Voltage
        assert row[5] == "0.500"  # Current
        assert row[6] == "750.00"  # CCAP
        assert row[7] == "0.00"  # DCAP
        assert row[8] == "NiMH"  # Chemistry

    def test_empty_records(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.csv"
        count = export_csv([], path)

        assert count == 0
        with path.open(encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 1  # Header only

    def test_utf8_encoding(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        export_csv(_make_records(1), path)

        content = path.read_text(encoding="utf-8")
        assert "Slot" in content

    def test_returns_row_count(self, tmp_path: Path) -> None:
        path = tmp_path / "test.csv"
        assert export_csv(_make_records(3), path) == 3
        assert export_csv([], path) == 0
