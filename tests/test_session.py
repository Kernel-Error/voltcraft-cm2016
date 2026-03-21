"""Tests for cm2016.session — in-memory data store."""

from __future__ import annotations

from cm2016.protocol import parse_frame
from cm2016.session import Session, SlotRecord
from tests.conftest import make_frame


class TestSlotRecord:
    """Test SlotRecord creation."""

    def test_from_slot_data(self) -> None:
        frame = parse_frame(
            make_frame(
                slot_overrides={
                    0: {
                        "active": 1,
                        "program": 1,
                        "step": 1,
                        "status": 0x00,
                        "runtime_minutes": 45,
                        "voltage_mv": 1320,
                        "current_raw": 500,
                        "charge_cap_raw": 75000,
                        "discharge_cap_raw": 0,
                    },
                }
            )
        )
        record = SlotRecord.from_slot_data(frame.slots[0], "NiMH")
        assert record.slot_index == 0
        assert record.program == "Charge"
        assert record.status == "Charge"
        assert record.chemistry == "NiMH"
        assert record.runtime_minutes == 45
        assert record.voltage == 1.32
        assert record.current == 0.5
        assert record.charge_capacity == 750.0
        assert record.discharge_capacity == 0.0

    def test_from_9v_slot(self) -> None:
        frame = parse_frame(
            make_frame(
                slot_overrides={
                    4: {
                        "active": 1,
                        "program": 1,
                        "step": 1,
                        "status": 0x00,
                        "voltage_mv": 8400,
                        "current_raw": 1500,
                        "charge_cap_raw": 5000,
                    },
                }
            )
        )
        record = SlotRecord.from_slot_data(frame.slots[4], "NiMH")
        assert record.voltage == 8.4
        assert record.current == 0.15  # 1500 / 10000
        assert record.charge_capacity == 5.0  # 5000 / 1000


class TestSession:
    """Test Session data store."""

    def test_empty_initially(self) -> None:
        session = Session()
        assert session.total_records == 0
        for i in range(6):
            assert session.get_slot_data(i) == []

    def test_append_record(self) -> None:
        session = Session()
        frame = parse_frame(
            make_frame(
                slot_overrides={
                    0: {"active": 1, "program": 1, "step": 1, "status": 0x00, "voltage_mv": 1320},
                }
            )
        )
        record = SlotRecord.from_slot_data(frame.slots[0], "NiMH")
        session.append(0, record)

        assert session.total_records == 1
        assert len(session.get_slot_data(0)) == 1
        assert session.get_slot_data(0)[0].voltage == 1.32

    def test_clear_slot(self) -> None:
        session = Session()
        frame = parse_frame(
            make_frame(
                slot_overrides={
                    0: {"active": 1, "program": 1, "step": 1, "status": 0x00},
                    1: {"active": 1, "program": 2, "step": 2, "status": 0x00},
                }
            )
        )
        session.append(0, SlotRecord.from_slot_data(frame.slots[0], "NiMH"))
        session.append(1, SlotRecord.from_slot_data(frame.slots[1], "NiMH"))

        session.clear_slot(0)
        assert len(session.get_slot_data(0)) == 0
        assert len(session.get_slot_data(1)) == 1

    def test_clear_all(self) -> None:
        session = Session()
        frame = parse_frame(
            make_frame(
                slot_overrides={
                    0: {"active": 1, "program": 1, "step": 1, "status": 0x00},
                    1: {"active": 1, "program": 2, "step": 2, "status": 0x00},
                }
            )
        )
        session.append(0, SlotRecord.from_slot_data(frame.slots[0], "NiMH"))
        session.append(1, SlotRecord.from_slot_data(frame.slots[1], "NiMH"))

        session.clear()
        assert session.total_records == 0

    def test_get_all_data(self) -> None:
        session = Session()
        data = session.get_all_data()
        assert len(data) == 6


class TestSessionProcessFrame:
    """Test frame processing and auto-clear."""

    def test_records_non_empty_slots(self) -> None:
        session = Session()
        frame = parse_frame(
            make_frame(
                slot_overrides={
                    0: {"active": 1, "program": 1, "step": 1, "status": 0x00, "voltage_mv": 1320},
                    # Slots 1-5 are empty (default status=0x20)
                }
            )
        )
        session.process_frame(frame)

        assert len(session.get_slot_data(0)) == 1
        assert session.get_slot_data(0)[0].voltage == 1.32
        # Empty slots should have no records
        for i in range(1, 6):
            assert len(session.get_slot_data(i)) == 0

    def test_skips_empty_slots(self) -> None:
        session = Session()
        frame = parse_frame(make_frame())  # All empty
        session.process_frame(frame)
        assert session.total_records == 0

    def test_auto_clear_on_battery_removal(self) -> None:
        session = Session()

        # First frame: slot 0 is active
        frame1 = parse_frame(
            make_frame(
                slot_overrides={
                    0: {"active": 1, "program": 1, "step": 1, "status": 0x00, "voltage_mv": 1320},
                }
            )
        )
        session.process_frame(frame1)
        assert len(session.get_slot_data(0)) == 1

        # Second frame: slot 0 is now empty (battery removed)
        frame2 = parse_frame(make_frame())  # All empty
        session.process_frame(frame2)

        # Data should be auto-cleared
        assert len(session.get_slot_data(0)) == 0

    def test_no_auto_clear_if_was_already_empty(self) -> None:
        session = Session()

        # Both frames: all empty
        frame1 = parse_frame(make_frame())
        session.process_frame(frame1)
        frame2 = parse_frame(make_frame())
        session.process_frame(frame2)

        # No clear should have happened (nothing to clear)
        assert session.total_records == 0

    def test_auto_clear_does_not_affect_other_slots(self) -> None:
        session = Session()

        # Frame 1: slots 0 and 1 active
        frame1 = parse_frame(
            make_frame(
                slot_overrides={
                    0: {"active": 1, "program": 1, "step": 1, "status": 0x00},
                    1: {"active": 1, "program": 2, "step": 2, "status": 0x00},
                }
            )
        )
        session.process_frame(frame1)
        assert len(session.get_slot_data(0)) == 1
        assert len(session.get_slot_data(1)) == 1

        # Frame 2: slot 0 removed, slot 1 still active
        frame2 = parse_frame(
            make_frame(
                slot_overrides={
                    1: {"active": 1, "program": 2, "step": 2, "status": 0x00},
                }
            )
        )
        session.process_frame(frame2)

        # Slot 0 cleared, slot 1 has 2 records
        assert len(session.get_slot_data(0)) == 0
        assert len(session.get_slot_data(1)) == 2


class TestSessionCallbacks:
    """Test session event callbacks."""

    def test_on_record_added(self) -> None:
        session = Session()
        added: list[tuple[int, SlotRecord]] = []
        session.on_record_added = lambda i, r: added.append((i, r))

        frame = parse_frame(
            make_frame(
                slot_overrides={
                    0: {"active": 1, "program": 1, "step": 1, "status": 0x00},
                }
            )
        )
        record = SlotRecord.from_slot_data(frame.slots[0], "NiMH")
        session.append(0, record)

        assert len(added) == 1
        assert added[0][0] == 0

    def test_on_slot_cleared(self) -> None:
        session = Session()
        cleared: list[int] = []
        session.on_slot_cleared = lambda i: cleared.append(i)

        session.clear_slot(2)
        assert cleared == [2]

    def test_on_all_cleared(self) -> None:
        session = Session()
        called = [False]
        session.on_all_cleared = lambda: called.__setitem__(0, True)

        session.clear()
        assert called[0] is True
