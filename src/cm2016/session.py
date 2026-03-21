"""In-memory data store for CM2016 recording sessions.

Stores per-slot time series of measurement records. Supports auto-clear
when a battery is removed (slot transitions from active to empty).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from cm2016.protocol import Frame, SlotData, SlotStatus

logger = logging.getLogger(__name__)

SLOT_COUNT = 6


@dataclass(frozen=True)
class SlotRecord:
    """A single measurement data point for one slot at one point in time."""

    timestamp: datetime
    slot_index: int
    program: str
    status: str
    chemistry: str
    runtime_minutes: int
    runtime_formatted: str
    voltage: float  # V
    current: float  # A
    charge_capacity: float  # mAh
    discharge_capacity: float  # mAh

    @classmethod
    def from_slot_data(cls, slot: SlotData, chemistry: str) -> SlotRecord:
        """Create a record from parsed slot data."""
        return cls(
            timestamp=datetime.now(tz=timezone.utc),
            slot_index=slot.slot_index,
            program=slot.program.label,
            status=slot.status_label,
            chemistry=chemistry,
            runtime_minutes=slot.runtime_minutes,
            runtime_formatted=slot.runtime_formatted,
            voltage=slot.voltage,
            current=slot.current,
            charge_capacity=slot.charge_capacity,
            discharge_capacity=slot.discharge_capacity,
        )


class Session:
    """Stores recorded data for all 6 slots.

    Attributes:
        on_record_added: Callback fired when a new record is appended.
            Signature: ``(slot_index: int, record: SlotRecord) -> None``
        on_slot_cleared: Callback fired when a slot's data is cleared.
            Signature: ``(slot_index: int) -> None``
        on_all_cleared: Callback fired when all data is cleared.
            Signature: ``() -> None``
    """

    def __init__(self) -> None:
        self._data: dict[int, list[SlotRecord]] = {i: [] for i in range(SLOT_COUNT)}
        self._previous_status: dict[int, SlotStatus] = {}

        self.on_record_added: Callable[[int, SlotRecord], None] | None = None
        self.on_slot_cleared: Callable[[int], None] | None = None
        self.on_all_cleared: Callable[[], None] | None = None

    def get_slot_data(self, slot_index: int) -> list[SlotRecord]:
        """Get all recorded data for a slot.

        Args:
            slot_index: 0-5

        Returns:
            List of records (may be empty). Do not modify directly.
        """
        return self._data[slot_index]

    def get_all_data(self) -> dict[int, list[SlotRecord]]:
        """Get all recorded data for all slots."""
        return self._data

    @property
    def total_records(self) -> int:
        """Total number of records across all slots."""
        return sum(len(records) for records in self._data.values())

    def append(self, slot_index: int, record: SlotRecord) -> None:
        """Append a measurement record to a slot.

        Args:
            slot_index: 0-5
            record: The measurement data point.
        """
        self._data[slot_index].append(record)
        if self.on_record_added is not None:
            self.on_record_added(slot_index, record)

    def clear_slot(self, slot_index: int) -> None:
        """Clear all recorded data for a single slot."""
        self._data[slot_index] = []
        self._previous_status.pop(slot_index, None)
        logger.debug("Cleared data for slot %d", slot_index)
        if self.on_slot_cleared is not None:
            self.on_slot_cleared(slot_index)

    def clear(self) -> None:
        """Clear all recorded data for all slots."""
        for i in range(SLOT_COUNT):
            self._data[i] = []
        self._previous_status.clear()
        logger.debug("Cleared all session data")
        if self.on_all_cleared is not None:
            self.on_all_cleared()

    def process_frame(self, frame: Frame) -> None:
        """Process a frame: check for battery removal and append records.

        For each active slot, creates a SlotRecord and appends it.
        If a slot transitions from non-empty to empty, its data is auto-cleared.

        Args:
            frame: A parsed CM2016 frame.
        """
        chemistry = frame.header.chemistry.label

        for slot in frame.slots:
            current_status = slot.status
            previous_status = self._previous_status.get(slot.slot_index)

            # Auto-clear: slot was not empty before, now it is (battery removed)
            if (
                previous_status is not None
                and previous_status != SlotStatus.EMPTY
                and current_status == SlotStatus.EMPTY
                and self._data[slot.slot_index]
            ):
                logger.info(
                    "Battery removed from slot %d, clearing data",
                    slot.slot_index,
                )
                self.clear_slot(slot.slot_index)

            self._previous_status[slot.slot_index] = current_status

            # Only record data for non-empty slots
            if current_status != SlotStatus.EMPTY:
                record = SlotRecord.from_slot_data(slot, chemistry)
                self.append(slot.slot_index, record)
