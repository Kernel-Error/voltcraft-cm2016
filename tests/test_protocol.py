"""Tests for cm2016.protocol — frame and slot parsing."""

from __future__ import annotations

import struct

import pytest

from cm2016.protocol import (
    FRAME_LENGTH,
    Chemistry,
    Frame,
    FrameError,
    SlotProgram,
    SlotStatus,
    parse_frame,
    parse_header,
    parse_slot,
)
from tests.conftest import _build_header, _build_slot, make_frame

# ---------------------------------------------------------------------------
# Frame validation
# ---------------------------------------------------------------------------


class TestParseFrameValidation:
    """Test frame-level validation."""

    def test_wrong_length_short(self) -> None:
        with pytest.raises(FrameError, match="127 bytes"):
            parse_frame(b"\x00" * 100)

    def test_wrong_length_long(self) -> None:
        with pytest.raises(FrameError, match="127 bytes"):
            parse_frame(b"\x00" * 200)

    def test_empty_data(self) -> None:
        with pytest.raises(FrameError, match="127 bytes"):
            parse_frame(b"")

    def test_wrong_device_id(self) -> None:
        data = bytearray(FRAME_LENGTH)
        data[:7] = b"FOOBAR "
        with pytest.raises(FrameError, match="Invalid device ID"):
            parse_frame(bytes(data))

    def test_valid_frame_parses(self, sample_frame: bytes) -> None:
        frame = parse_frame(sample_frame)
        assert isinstance(frame, Frame)
        assert len(frame.slots) == 6
        assert frame.raw == sample_frame


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------


class TestParseHeader:
    """Test header (bytes 7-16) parsing."""

    def test_firmware_version(self, sample_frame: bytes) -> None:
        frame = parse_frame(sample_frame)
        assert frame.header.firmware_major == 2
        assert frame.header.firmware_minor == 10

    def test_chemistry_nimh(self, sample_frame: bytes) -> None:
        frame = parse_frame(sample_frame)
        assert frame.header.chemistry == Chemistry.NIMH
        assert frame.header.chemistry.label == "NiMH"

    def test_chemistry_nizn(self) -> None:
        data = make_frame(header_kwargs={"chemistry": 1})
        frame = parse_frame(data)
        assert frame.header.chemistry == Chemistry.NIZN
        assert frame.header.chemistry.label == "NiZn"

    def test_overtemp_flag(self) -> None:
        data = make_frame(header_kwargs={"overtemp": 1})
        frame = parse_frame(data)
        assert frame.header.overtemp_flag is True

    def test_no_overtemp(self, sample_frame: bytes) -> None:
        frame = parse_frame(sample_frame)
        assert frame.header.overtemp_flag is False

    def test_temperatures(self, sample_frame: bytes) -> None:
        frame = parse_frame(sample_frame)
        assert frame.header.temp_start == 22
        assert frame.header.temp_actual == 28

    def test_negative_temperature(self) -> None:
        data = make_frame(header_kwargs={"temp_start": -5, "temp_actual": -10})
        frame = parse_frame(data)
        assert frame.header.temp_start == -5
        assert frame.header.temp_actual == -10

    def test_action_counter(self, sample_frame: bytes) -> None:
        frame = parse_frame(sample_frame)
        assert frame.header.action_counter == 42

    def test_header_wrong_length(self) -> None:
        with pytest.raises(FrameError, match="10 bytes"):
            parse_header(b"\x00" * 5)

    def test_unknown_chemistry_defaults_to_nimh(self) -> None:
        hdr = _build_header(chemistry=99)
        header = parse_header(hdr)
        assert header.chemistry == Chemistry.NIMH


# ---------------------------------------------------------------------------
# Slot parsing — field extraction
# ---------------------------------------------------------------------------


class TestParseSlot:
    """Test individual slot field parsing."""

    def test_slot_wrong_length(self) -> None:
        with pytest.raises(FrameError, match="18 bytes"):
            parse_slot(b"\x00" * 10, slot_index=0)

    def test_active_flag(self) -> None:
        slot = parse_slot(_build_slot(active=1), slot_index=0)
        assert slot.active is True

        slot = parse_slot(_build_slot(active=0), slot_index=0)
        assert slot.active is False

    def test_program_charge(self) -> None:
        slot = parse_slot(_build_slot(program=1), slot_index=0)
        assert slot.program == SlotProgram.CHARGE
        assert slot.program.label == "Charge"

    def test_program_discharge(self) -> None:
        slot = parse_slot(_build_slot(program=2), slot_index=0)
        assert slot.program == SlotProgram.DISCHARGE
        assert slot.program.label == "Discharge"

    def test_program_check(self) -> None:
        slot = parse_slot(_build_slot(program=3), slot_index=0)
        assert slot.program == SlotProgram.CHECK

    def test_program_cycle(self) -> None:
        slot = parse_slot(_build_slot(program=4), slot_index=0)
        assert slot.program == SlotProgram.CYCLE

    def test_program_alive(self) -> None:
        slot = parse_slot(_build_slot(program=5), slot_index=0)
        assert slot.program == SlotProgram.ALIVE

    def test_program_error_6(self) -> None:
        slot = parse_slot(_build_slot(program=6), slot_index=0)
        assert slot.program == SlotProgram.ERROR_6
        assert slot.program.label == "Error"

    def test_program_error_9(self) -> None:
        slot = parse_slot(_build_slot(program=9), slot_index=0)
        assert slot.program == SlotProgram.ERROR_9

    def test_program_unknown_defaults_to_none(self) -> None:
        slot = parse_slot(_build_slot(program=99), slot_index=0)
        assert slot.program == SlotProgram.NONE

    def test_runtime_minutes(self) -> None:
        slot = parse_slot(_build_slot(runtime_minutes=300), slot_index=0)
        assert slot.runtime_minutes == 300

    def test_runtime_max_16bit(self) -> None:
        slot = parse_slot(_build_slot(runtime_minutes=65535), slot_index=0)
        assert slot.runtime_minutes == 65535

    def test_voltage_mv(self) -> None:
        slot = parse_slot(_build_slot(voltage_mv=1320), slot_index=0)
        assert slot.voltage_mv == 1320
        assert slot.voltage == pytest.approx(1.32)

    def test_current_slot_1_4(self) -> None:
        """Slots 1-4 (index 0-3): current_raw / 1000 = A."""
        slot = parse_slot(_build_slot(current_raw=500), slot_index=0)
        assert slot.current == pytest.approx(0.5)

    def test_current_slot_a(self) -> None:
        """Slot A (index 4): current_raw / 10000 = A."""
        slot = parse_slot(_build_slot(current_raw=1500), slot_index=4)
        assert slot.current == pytest.approx(0.15)

    def test_current_slot_b(self) -> None:
        """Slot B (index 5): current_raw / 10000 = A."""
        slot = parse_slot(_build_slot(current_raw=2000), slot_index=5)
        assert slot.current == pytest.approx(0.2)

    def test_charge_capacity_slot_1_4(self) -> None:
        """Slots 1-4: charge_cap_raw / 100 = mAh."""
        slot = parse_slot(_build_slot(charge_cap_raw=75000), slot_index=0)
        assert slot.charge_capacity == pytest.approx(750.0)

    def test_charge_capacity_slot_a(self) -> None:
        """Slot A: charge_cap_raw / 1000 = mAh."""
        slot = parse_slot(_build_slot(charge_cap_raw=5000), slot_index=4)
        assert slot.charge_capacity == pytest.approx(5.0)

    def test_discharge_capacity_slot_1_4(self) -> None:
        """Slots 1-4: discharge_cap_raw / 100 = mAh."""
        slot = parse_slot(_build_slot(discharge_cap_raw=20000), slot_index=1)
        assert slot.discharge_capacity == pytest.approx(200.0)

    def test_discharge_capacity_slot_b(self) -> None:
        """Slot B: discharge_cap_raw / 1000 = mAh."""
        slot = parse_slot(_build_slot(discharge_cap_raw=3000), slot_index=5)
        assert slot.discharge_capacity == pytest.approx(3.0)

    def test_is_9v_slot(self) -> None:
        for i in range(4):
            slot = parse_slot(_build_slot(), slot_index=i)
            assert slot.is_9v_slot is False
        for i in (4, 5):
            slot = parse_slot(_build_slot(), slot_index=i)
            assert slot.is_9v_slot is True


# ---------------------------------------------------------------------------
# 32-bit capacity parsing (C-CAP and D-CAP)
# ---------------------------------------------------------------------------


class TestCapacityParsing:
    """Verify C-CAP (bytes 10-13) and D-CAP (bytes 14-17) as 32-bit LE."""

    def test_ccap_32bit(self) -> None:
        raw = bytearray(18)
        struct.pack_into("<I", raw, 10, 0x12345678)
        slot = parse_slot(bytes(raw), slot_index=0)
        assert slot.charge_cap_raw == 0x12345678

    def test_dcap_32bit(self) -> None:
        raw = bytearray(18)
        struct.pack_into("<I", raw, 14, 0x00004A6B)
        slot = parse_slot(bytes(raw), slot_index=0)
        assert slot.discharge_cap_raw == 0x00004A6B

    def test_ccap_dcap_independent(self) -> None:
        """C-CAP and D-CAP occupy separate 4-byte fields, no overlap."""
        raw = bytearray(18)
        struct.pack_into("<I", raw, 10, 12345)
        struct.pack_into("<I", raw, 14, 67890)
        slot = parse_slot(bytes(raw), slot_index=0)
        assert slot.charge_cap_raw == 12345
        assert slot.discharge_cap_raw == 67890

    def test_dcap_zero(self) -> None:
        slot = parse_slot(_build_slot(discharge_cap_raw=0), slot_index=0)
        assert slot.discharge_cap_raw == 0

    def test_dcap_large_value(self) -> None:
        slot = parse_slot(_build_slot(discharge_cap_raw=0xFFFFFFFF), slot_index=0)
        assert slot.discharge_cap_raw == 0xFFFFFFFF

    def test_realistic_discharge(self) -> None:
        """19051 raw / 100 = 190.51 mAh — realistic for AA NiMH discharge."""
        slot = parse_slot(_build_slot(discharge_cap_raw=19051), slot_index=0)
        assert slot.discharge_capacity == pytest.approx(190.51)


# ---------------------------------------------------------------------------
# Capacity scaling
# ---------------------------------------------------------------------------


class TestCapacityValues:
    """Test capacity field values via _build_slot roundtrip."""

    def test_ccap_small(self) -> None:
        slot = parse_slot(_build_slot(charge_cap_raw=0xFF), slot_index=0)
        assert slot.charge_cap_raw == 255

    def test_ccap_medium(self) -> None:
        slot = parse_slot(_build_slot(charge_cap_raw=0xBBAA), slot_index=0)
        assert slot.charge_cap_raw == 0xBBAA

    def test_ccap_large(self) -> None:
        slot = parse_slot(_build_slot(charge_cap_raw=0xCCBBAA), slot_index=0)
        assert slot.charge_cap_raw == 0xCCBBAA

    def test_ccap_32bit_max(self) -> None:
        slot = parse_slot(_build_slot(charge_cap_raw=0xFFFFFFFF), slot_index=0)
        assert slot.charge_cap_raw == 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Slot status derivation
# ---------------------------------------------------------------------------


class TestSlotStatus:
    """Test the derived status property."""

    def test_empty(self) -> None:
        slot = parse_slot(_build_slot(status=0x20), slot_index=0)
        assert slot.status == SlotStatus.EMPTY
        assert slot.status_label == "Empty"

    def test_error(self) -> None:
        slot = parse_slot(_build_slot(status=0x21, active=1), slot_index=0)
        assert slot.status == SlotStatus.ERROR
        assert slot.status_label == "Error"

    def test_ready_inactive_0x07(self) -> None:
        slot = parse_slot(_build_slot(active=0, status=0x07), slot_index=0)
        assert slot.status == SlotStatus.READY

    def test_ready_inactive_0x02(self) -> None:
        slot = parse_slot(_build_slot(active=0, status=0x02), slot_index=0)
        assert slot.status == SlotStatus.READY

    def test_trickle_active_step_zero_0x07(self) -> None:
        slot = parse_slot(_build_slot(active=1, status=0x07, step=0), slot_index=0)
        assert slot.status == SlotStatus.TRICKLE

    def test_charging_wins_over_status_0x07(self) -> None:
        slot = parse_slot(_build_slot(active=1, status=0x07, step=1), slot_index=0)
        assert slot.status == SlotStatus.CHARGING

    def test_discharging_wins_over_status_0x07(self) -> None:
        slot = parse_slot(_build_slot(active=1, status=0x07, step=2), slot_index=0)
        assert slot.status == SlotStatus.DISCHARGING

    def test_charging_odd_step(self) -> None:
        for step in (1, 3, 5, 7):
            slot = parse_slot(_build_slot(active=1, status=0x00, step=step), slot_index=0)
            assert slot.status == SlotStatus.CHARGING, f"step={step}"

    def test_discharging_even_step(self) -> None:
        for step in (2, 4, 6):
            slot = parse_slot(_build_slot(active=1, status=0x00, step=step), slot_index=0)
            assert slot.status == SlotStatus.DISCHARGING, f"step={step}"

    def test_idle_active_step_zero(self) -> None:
        slot = parse_slot(_build_slot(active=1, status=0x00, step=0), slot_index=0)
        assert slot.status == SlotStatus.IDLE

    def test_idle_inactive_unknown_status(self) -> None:
        slot = parse_slot(_build_slot(active=0, status=0x00), slot_index=0)
        assert slot.status == SlotStatus.IDLE


# ---------------------------------------------------------------------------
# Runtime formatting
# ---------------------------------------------------------------------------


class TestRuntimeFormatted:
    """Test runtime_formatted property."""

    def test_zero_minutes(self) -> None:
        slot = parse_slot(_build_slot(runtime_minutes=0), slot_index=0)
        assert slot.runtime_formatted == "0:00"

    def test_simple_minutes(self) -> None:
        slot = parse_slot(_build_slot(runtime_minutes=45), slot_index=0)
        assert slot.runtime_formatted == "0:45"

    def test_hours_and_minutes(self) -> None:
        slot = parse_slot(_build_slot(runtime_minutes=125), slot_index=0)
        assert slot.runtime_formatted == "2:05"

    def test_days(self) -> None:
        # 1 day + 2 hours + 30 minutes = 1590 minutes
        slot = parse_slot(_build_slot(runtime_minutes=1590), slot_index=0)
        assert slot.runtime_formatted == "1:02:30"

    def test_exactly_one_hour(self) -> None:
        slot = parse_slot(_build_slot(runtime_minutes=60), slot_index=0)
        assert slot.runtime_formatted == "1:00"


# ---------------------------------------------------------------------------
# Full frame parsing with sample data
# ---------------------------------------------------------------------------


class TestSampleFrame:
    """Integration tests using the SAMPLE_FRAME fixture."""

    def test_slot0_charging(self, sample_frame: bytes) -> None:
        frame = parse_frame(sample_frame)
        s = frame.slots[0]
        assert s.active is True
        assert s.program == SlotProgram.CHARGE
        assert s.status == SlotStatus.CHARGING  # step=1 (odd) takes priority
        assert s.voltage == pytest.approx(1.32)
        assert s.current == pytest.approx(0.5)
        assert s.charge_capacity == pytest.approx(750.0)
        assert s.runtime_minutes == 45

    def test_slot1_discharging(self, sample_frame: bytes) -> None:
        frame = parse_frame(sample_frame)
        s = frame.slots[1]
        assert s.active is True
        assert s.program == SlotProgram.DISCHARGE
        assert s.status == SlotStatus.DISCHARGING  # step=2 (even) takes priority
        assert s.voltage == pytest.approx(1.1)
        assert s.current == pytest.approx(0.2)
        assert s.discharge_capacity == pytest.approx(200.0)
        assert s.runtime_minutes == 120

    def test_slot2_ready(self, sample_frame: bytes) -> None:
        frame = parse_frame(sample_frame)
        s = frame.slots[2]
        assert s.active is False
        assert s.status == SlotStatus.READY
        assert s.voltage == pytest.approx(1.45)
        assert s.charge_capacity == pytest.approx(2000.0)

    def test_slot3_empty(self, sample_frame: bytes) -> None:
        frame = parse_frame(sample_frame)
        s = frame.slots[3]
        assert s.active is False
        assert s.status == SlotStatus.EMPTY

    def test_slot4_9v_charging(self, sample_frame: bytes) -> None:
        frame = parse_frame(sample_frame)
        s = frame.slots[4]
        assert s.is_9v_slot is True
        assert s.active is True
        assert s.voltage == pytest.approx(8.4)
        assert s.current == pytest.approx(0.15)
        assert s.charge_capacity == pytest.approx(5.0)

    def test_slot5_empty(self, sample_frame: bytes) -> None:
        frame = parse_frame(sample_frame)
        s = frame.slots[5]
        assert s.is_9v_slot is True
        assert s.status == SlotStatus.EMPTY

    def test_checksum_field(self, sample_frame: bytes) -> None:
        frame = parse_frame(sample_frame)
        # Checksum is the last 2 bytes, we set them to 0x0000
        assert frame.checksum == 0

    def test_timestamp_is_set(self, sample_frame: bytes) -> None:
        frame = parse_frame(sample_frame)
        assert frame.timestamp is not None


# ---------------------------------------------------------------------------
# SlotProgram labels
# ---------------------------------------------------------------------------


class TestSlotProgramLabels:
    """Test SlotProgram.label property."""

    def test_all_labels(self) -> None:
        assert SlotProgram.NONE.label == "---"
        assert SlotProgram.CHARGE.label == "Charge"
        assert SlotProgram.DISCHARGE.label == "Discharge"
        assert SlotProgram.CHECK.label == "Check"
        assert SlotProgram.CYCLE.label == "Cycle"
        assert SlotProgram.ALIVE.label == "Alive"
        assert SlotProgram.ERROR_6.label == "Error"
        assert SlotProgram.ERROR_9.label == "Error"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and boundary values."""

    def test_all_zeros_frame(self, empty_frame: bytes) -> None:
        """Frame with all slots empty should parse without errors."""
        frame = parse_frame(empty_frame)
        for slot in frame.slots:
            assert slot.status == SlotStatus.EMPTY
            assert slot.voltage == 0.0
            assert slot.current == 0.0

    def test_max_voltage(self) -> None:
        """Maximum 16-bit voltage (65535 mV = 65.535 V)."""
        slot = parse_slot(_build_slot(voltage_mv=65535), slot_index=0)
        assert slot.voltage == pytest.approx(65.535)

    def test_max_runtime(self) -> None:
        """Maximum 16-bit runtime (65535 minutes ≈ 45 days)."""
        slot = parse_slot(_build_slot(runtime_minutes=65535), slot_index=0)
        assert slot.runtime_minutes == 65535
        # 65535 min = 45 days, 12 hours, 15 minutes
        assert slot.runtime_formatted == "45:12:15"

    def test_frame_preserves_raw_data(self, sample_frame: bytes) -> None:
        frame = parse_frame(sample_frame)
        assert frame.raw == sample_frame
        assert len(frame.raw) == FRAME_LENGTH
