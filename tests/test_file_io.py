"""Tests for cm2016.persistence.file_io — save/load sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cm2016.persistence.file_io import load_session, save_session
from cm2016.protocol import parse_frame
from cm2016.session import Session, SlotRecord
from tests.conftest import make_frame

if TYPE_CHECKING:
    from pathlib import Path


def _populate_session() -> Session:
    """Create a session with test data in slots 0 and 1."""
    session = Session()
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
                },
                1: {
                    "active": 1,
                    "program": 2,
                    "step": 2,
                    "status": 0x00,
                    "runtime_minutes": 20,
                    "voltage_mv": 1100,
                    "current_raw": 200,
                    "discharge_cap_raw": 30000,
                },
            }
        )
    )
    session.append(0, SlotRecord.from_slot_data(frame.slots[0], "NiMH"))
    session.append(0, SlotRecord.from_slot_data(frame.slots[0], "NiMH"))
    session.append(1, SlotRecord.from_slot_data(frame.slots[1], "NiMH"))
    return session


class TestSaveLoad:
    """Test save/load roundtrip."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        session = _populate_session()
        path = tmp_path / "test.cm2016"
        save_session(session, path)

        loaded = load_session(path)
        assert loaded.total_records == 3
        assert len(loaded.get_slot_data(0)) == 2
        assert len(loaded.get_slot_data(1)) == 1

    def test_preserves_values(self, tmp_path: Path) -> None:
        session = _populate_session()
        path = tmp_path / "test.cm2016"
        save_session(session, path)
        loaded = load_session(path)

        orig = session.get_slot_data(0)[0]
        loaded_rec = loaded.get_slot_data(0)[0]
        assert loaded_rec.voltage == orig.voltage
        assert loaded_rec.current == orig.current
        assert loaded_rec.charge_capacity == orig.charge_capacity
        assert loaded_rec.program == orig.program
        assert loaded_rec.chemistry == orig.chemistry

    def test_returns_record_count(self, tmp_path: Path) -> None:
        session = _populate_session()
        path = tmp_path / "test.cm2016"
        count = save_session(session, path)
        assert count == 3

    def test_empty_session(self, tmp_path: Path) -> None:
        session = Session()
        path = tmp_path / "empty.cm2016"
        count = save_session(session, path)
        assert count == 0

        loaded = load_session(path)
        assert loaded.total_records == 0

    def test_invalid_version(self, tmp_path: Path) -> None:
        import json

        path = tmp_path / "bad.cm2016"
        path.write_text(json.dumps({"version": 999, "slots": {}}))

        import pytest

        with pytest.raises(ValueError, match="version"):
            load_session(path)
