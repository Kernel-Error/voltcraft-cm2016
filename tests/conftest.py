"""Shared test fixtures for CM2016 tests.

Provides sample frame data and factory functions for building
test frames without requiring real hardware.
"""

from __future__ import annotations

import struct

import pytest

from cm2016.protocol import (
    DEVICE_ID,
    FRAME_LENGTH,
    SLOT_LENGTH,
)


def _build_slot(
    *,
    active: int = 0,
    program: int = 0,
    step: int = 0,
    status: int = 0x20,
    runtime_minutes: int = 0,
    voltage_mv: int = 0,
    current_raw: int = 0,
    charge_cap_raw: int = 0,
    discharge_cap_raw: int = 0,
) -> bytes:
    """Build an 18-byte slot data block with the given field values."""
    data = bytearray(SLOT_LENGTH)
    data[0] = active
    data[1] = program
    data[2] = step
    data[3] = status

    struct.pack_into("<H", data, 4, runtime_minutes)
    struct.pack_into("<H", data, 6, voltage_mv)
    struct.pack_into("<H", data, 8, current_raw)

    # 32-bit LE charge capacity: bytes [10-13]
    struct.pack_into("<I", data, 10, charge_cap_raw)

    # 32-bit LE discharge capacity: bytes [14-17]
    struct.pack_into("<I", data, 14, discharge_cap_raw)

    return bytes(data)


def _build_header(
    *,
    firmware_major: int = 2,
    firmware_minor: int = 10,
    chemistry: int = 0,
    overtemp: int = 0,
    temp_start: int = 25,
    temp_actual: int = 30,
    action_counter: int = 1,
) -> bytes:
    """Build a 10-byte header block."""
    data = bytearray(10)
    data[0] = firmware_major
    data[1] = firmware_minor
    data[2] = chemistry
    data[3] = overtemp
    struct.pack_into(">h", data, 4, temp_start)  # Big-endian signed
    struct.pack_into(">h", data, 6, temp_actual)
    struct.pack_into(">h", data, 8, action_counter)
    return bytes(data)


def make_frame(
    *,
    header_kwargs: dict | None = None,
    slot_overrides: dict[int, dict] | None = None,
) -> bytes:
    """Build a complete 127-byte CM2016 frame.

    Args:
        header_kwargs: Override header field values.
        slot_overrides: Dict mapping slot index (0-5) to field overrides
            for that slot's _build_slot() call.

    Returns:
        127 bytes of frame data with a dummy checksum.
    """
    hdr_kw = header_kwargs or {}
    slot_ov = slot_overrides or {}

    frame = bytearray()
    frame.extend(DEVICE_ID)
    frame.extend(_build_header(**hdr_kw))

    for i in range(6):
        kw = slot_ov.get(i, {})
        frame.extend(_build_slot(**kw))

    # Dummy checksum (2 bytes)
    frame.extend(b"\x00\x00")

    assert len(frame) == FRAME_LENGTH
    return bytes(frame)


# A sample frame with realistic data:
# - Slot 0: actively charging, 1.320V, 500mA, 45 minutes, 750 mAh charged
# - Slot 1: actively discharging, 1.100V, 200mA, 120 minutes, 200 mAh discharged
# - Slot 2: finished/ready, 1.450V, 0mA, 300 minutes, 2000 mAh charged
# - Slot 3: empty
# - Slot 4 (A): actively charging (9V slot), 8.400V, 150mA raw, 60 minutes
# - Slot 5 (B): empty
SAMPLE_FRAME = make_frame(
    header_kwargs={
        "firmware_major": 2,
        "firmware_minor": 10,
        "chemistry": 0,
        "temp_start": 22,
        "temp_actual": 28,
        "action_counter": 42,
    },
    slot_overrides={
        0: {
            "active": 1,
            "program": 1,  # Charge
            "step": 1,  # Odd = charging
            "status": 0x07,
            "runtime_minutes": 45,
            "voltage_mv": 1320,
            "current_raw": 500,
            "charge_cap_raw": 75000,  # 75000 / 100 = 750.0 mAh
            "discharge_cap_raw": 0,
        },
        1: {
            "active": 1,
            "program": 2,  # Discharge
            "step": 2,  # Even = discharging
            "status": 0x07,
            "runtime_minutes": 120,
            "voltage_mv": 1100,
            "current_raw": 200,
            "charge_cap_raw": 0,
            "discharge_cap_raw": 20000,  # 20000 / 100 = 200.0 mAh
        },
        2: {
            "active": 0,
            "program": 1,  # Charge
            "step": 0,
            "status": 0x07,  # Inactive + 0x07 = Ready
            "runtime_minutes": 300,
            "voltage_mv": 1450,
            "current_raw": 0,
            "charge_cap_raw": 200000,  # 200000 / 100 = 2000.0 mAh
            "discharge_cap_raw": 0,
        },
        # Slot 3: empty (defaults)
        4: {
            "active": 1,
            "program": 1,  # Charge
            "step": 1,  # Charging
            "status": 0x07,
            "runtime_minutes": 60,
            "voltage_mv": 8400,
            "current_raw": 1500,  # 1500 / 10000 = 0.15 A for 9V slot
            "charge_cap_raw": 5000,  # 5000 / 1000 = 5.0 mAh for 9V slot
            "discharge_cap_raw": 0,
        },
        # Slot 5 (B): empty (defaults)
    },
)


@pytest.fixture()
def sample_frame() -> bytes:
    """A realistic 127-byte CM2016 frame for testing."""
    return SAMPLE_FRAME


@pytest.fixture()
def empty_frame() -> bytes:
    """A frame with all slots empty."""
    return make_frame()
