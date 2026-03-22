"""Tests for thread-safety of cm2016.session.Session (Issue #1)."""

from __future__ import annotations

import threading

from cm2016.protocol import parse_frame
from cm2016.session import Session, SlotRecord
from tests.conftest import make_frame


def _make_record(slot_index: int = 0, voltage_mv: int = 1320) -> SlotRecord:
    """Create a SlotRecord for testing."""
    frame = parse_frame(
        make_frame(
            slot_overrides={
                slot_index: {
                    "active": 1,
                    "program": 1,
                    "step": 1,
                    "status": 0x00,
                    "voltage_mv": voltage_mv,
                },
            }
        )
    )
    return SlotRecord.from_slot_data(frame.slots[slot_index], "NiMH")


class TestSessionThreadSafety:
    """Verify Session lock prevents data corruption under concurrent access."""

    def test_concurrent_append_and_read(self) -> None:
        """Append from one thread while reading from another."""
        session = Session()
        errors: list[Exception] = []
        count = 500

        def writer() -> None:
            try:
                for i in range(count):
                    record = _make_record(voltage_mv=1000 + i)
                    session.append(0, record)
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(count):
                    _ = session.get_slot_data(0)
                    _ = session.total_records
                    _ = session.get_all_data()
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
        assert session.total_records == count

    def test_concurrent_append_multiple_slots(self) -> None:
        """Multiple threads appending to different slots simultaneously."""
        session = Session()
        errors: list[Exception] = []
        per_slot = 200

        def append_to_slot(slot_idx: int) -> None:
            try:
                for i in range(per_slot):
                    record = _make_record(slot_index=slot_idx, voltage_mv=1000 + i)
                    session.append(slot_idx, record)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=append_to_slot, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert session.total_records == per_slot * 4
        for i in range(4):
            assert len(session.get_slot_data(i)) == per_slot

    def test_concurrent_append_and_clear(self) -> None:
        """Clear while another thread appends — no crash."""
        session = Session()
        errors: list[Exception] = []

        def writer() -> None:
            try:
                for i in range(300):
                    record = _make_record(voltage_mv=1000 + i)
                    session.append(0, record)
            except Exception as exc:
                errors.append(exc)

        def clearer() -> None:
            try:
                for _ in range(50):
                    session.clear()
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=clearer)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors

    def test_get_slot_data_returns_copy(self) -> None:
        """get_slot_data returns a copy, not a reference to internal list."""
        session = Session()
        record = _make_record()
        session.append(0, record)

        data = session.get_slot_data(0)
        data.clear()  # Mutating the returned list

        assert session.total_records == 1
        assert len(session.get_slot_data(0)) == 1

    def test_get_all_data_returns_copy(self) -> None:
        """get_all_data returns a copy of all lists."""
        session = Session()
        record = _make_record()
        session.append(0, record)

        data = session.get_all_data()
        data[0].clear()

        assert session.total_records == 1

    def test_callback_fired_outside_lock(self) -> None:
        """Callbacks should not deadlock (fired outside the lock)."""
        session = Session()
        callback_records: list[SlotRecord] = []

        def on_added(slot_idx: int, record: SlotRecord) -> None:
            # This accesses session from within the callback;
            # would deadlock if callback fired under a non-reentrant lock
            _ = session.total_records
            callback_records.append(record)

        session.on_record_added = on_added
        record = _make_record()
        session.append(0, record)

        assert len(callback_records) == 1
