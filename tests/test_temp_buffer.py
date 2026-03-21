"""Tests for cm2016.persistence.temp_buffer — crash recovery."""

from __future__ import annotations

from unittest.mock import patch

from cm2016.persistence.temp_buffer import (
    TempBuffer,
    delete_recovery,
    has_recovery_data,
    load_recovery,
)
from cm2016.protocol import parse_frame
from cm2016.session import Session, SlotRecord
from tests.conftest import make_frame


def _session_with_data() -> Session:
    session = Session()
    frame = parse_frame(
        make_frame(
            slot_overrides={
                0: {
                    "active": 1,
                    "program": 1,
                    "step": 1,
                    "status": 0x00,
                    "voltage_mv": 1320,
                },
            }
        )
    )
    session.append(0, SlotRecord.from_slot_data(frame.slots[0], "NiMH"))
    return session


class TestTempBuffer:
    """Test periodic temp file flushing."""

    def test_flush_creates_file(self, tmp_path: object) -> None:
        session = _session_with_data()
        with patch("cm2016.persistence.temp_buffer._get_temp_dir", return_value=tmp_path):
            buf = TempBuffer(session)
            buf.flush()
            assert has_recovery_data()

    def test_cleanup_removes_file(self, tmp_path: object) -> None:
        session = _session_with_data()
        with patch("cm2016.persistence.temp_buffer._get_temp_dir", return_value=tmp_path):
            buf = TempBuffer(session)
            buf.flush()
            assert has_recovery_data()
            buf.cleanup()
            assert not has_recovery_data()

    def test_periodic_flush(self, tmp_path: object) -> None:
        session = _session_with_data()
        with (
            patch("cm2016.persistence.temp_buffer._get_temp_dir", return_value=tmp_path),
            patch("cm2016.persistence.temp_buffer.FLUSH_INTERVAL", 3),
        ):
            buf = TempBuffer(session)
            buf.on_frame_received()  # 1
            buf.on_frame_received()  # 2
            assert not has_recovery_data()
            buf.on_frame_received()  # 3 → flush
            assert has_recovery_data()


class TestRecovery:
    """Test recovery load/delete."""

    def test_load_recovery(self, tmp_path: object) -> None:
        session = _session_with_data()
        with patch("cm2016.persistence.temp_buffer._get_temp_dir", return_value=tmp_path):
            buf = TempBuffer(session)
            buf.flush()

            recovered = load_recovery()
            assert recovered is not None
            assert recovered.total_records == 1

    def test_no_recovery_data(self, tmp_path: object) -> None:
        with patch("cm2016.persistence.temp_buffer._get_temp_dir", return_value=tmp_path):
            assert not has_recovery_data()
            assert load_recovery() is None

    def test_delete_recovery(self, tmp_path: object) -> None:
        session = _session_with_data()
        with patch("cm2016.persistence.temp_buffer._get_temp_dir", return_value=tmp_path):
            buf = TempBuffer(session)
            buf.flush()
            assert has_recovery_data()
            delete_recovery()
            assert not has_recovery_data()
