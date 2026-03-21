"""CSV export for CM2016 recording data."""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from cm2016.session import SlotRecord

# CSV column headers matching the data table
CSV_HEADERS = [
    "Slot",
    "Time",
    "Program",
    "Actual",
    "Voltage (V)",
    "Current (A)",
    "CCAP (mAh)",
    "DCAP (mAh)",
    "Chemistry",
]


def export_csv(records: list[SlotRecord], path: Path) -> int:
    """Export slot records to a CSV file.

    Args:
        records: List of SlotRecord objects to export.
        path: Output file path.

    Returns:
        Number of rows written (excluding header).
    """
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)

        for record in records:
            writer.writerow(
                [
                    record.slot_index + 1,
                    record.runtime_formatted,
                    record.program,
                    record.status,
                    f"{record.voltage:.3f}",
                    f"{record.current:.3f}",
                    f"{record.charge_capacity:.2f}",
                    f"{record.discharge_capacity:.2f}",
                    record.chemistry,
                ]
            )

    return len(records)
