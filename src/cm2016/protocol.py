"""CM2016 serial protocol parser.

Parses 127-byte frames transmitted by the Voltcraft Charge Manager CM 2016
every ~2 seconds over USB serial (CP210x, 19200 baud, 8N1).

Frame layout:
    Bytes 0-6:     Device ID "CM2016 " (ASCII)
    Bytes 7-16:    Header (firmware, chemistry, temperature, action counter)
    Bytes 17-34:   Slot 1 data (18 bytes)
    Bytes 35-52:   Slot 2 data (18 bytes)
    Bytes 53-70:   Slot 3 data (18 bytes)
    Bytes 71-88:   Slot 4 data (18 bytes)
    Bytes 89-106:  Slot A data (18 bytes, 9V block)
    Bytes 107-124: Slot B data (18 bytes, 9V block)
    Bytes 125-126: Checksum (algorithm unknown, not validated)

References:
    - https://github.com/sarnau/cm2016
    - https://github.com/michael-wahler/CM2016
    - https://www.leisenfels.com/howto-charge-manager-2016-data-format
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum

# Frame constants
FRAME_LENGTH = 127
DEVICE_ID = b"CM2016 "
DEVICE_ID_LENGTH = 7
HEADER_LENGTH = 10
SLOT_LENGTH = 18
SLOT_COUNT = 6
CHECKSUM_LENGTH = 2

# Slot data offsets within a frame (each 18 bytes)
SLOT_OFFSETS = (17, 35, 53, 71, 89, 107)

# Slot names for display
SLOT_NAMES = ("Slot 1", "Slot 2", "Slot 3", "Slot 4", "Slot A", "Slot B")

# Slots 4 and 5 (indices 4, 5) are 9V block slots with different scaling
NINE_VOLT_SLOT_INDICES = (4, 5)


class SlotProgram(IntEnum):
    """Charging program selected on the device."""

    NONE = 0
    CHARGE = 1
    DISCHARGE = 2
    CHECK = 3
    CYCLE = 4
    ALIVE = 5
    ERROR_6 = 6
    ERROR_9 = 9

    @property
    def label(self) -> str:
        """Human-readable label."""
        labels: dict[int, str] = {
            0: "---",
            1: "Charge",
            2: "Discharge",
            3: "Check",
            4: "Cycle",
            5: "Alive",
            6: "Error",
            9: "Error",
        }
        return labels.get(self.value, "Unknown")


class SlotStatus(IntEnum):
    """Derived status of a slot combining active flag, status byte, and step."""

    EMPTY = 0
    IDLE = 1
    CHARGING = 2
    DISCHARGING = 3
    READY = 4
    TRICKLE = 5
    ERROR = 6


class Chemistry(IntEnum):
    """Battery chemistry reported in the frame header."""

    NIMH = 0
    NIZN = 1

    @property
    def label(self) -> str:
        labels: dict[int, str] = {0: "NiMH", 1: "NiZn"}
        return labels.get(self.value, "Unknown")


@dataclass(frozen=True)
class FrameHeader:
    """Parsed header bytes 7-16 of a CM2016 frame.

    Note: Header fields use big-endian byte order, unlike slot data
    which uses little-endian.
    """

    firmware_major: int
    firmware_minor: int
    chemistry: Chemistry
    overtemp_flag: bool
    temp_start: int  # Signed, units unknown
    temp_actual: int  # Signed, units unknown
    action_counter: int


@dataclass(frozen=True)
class SlotData:
    """Parsed data for a single charging slot (18 bytes)."""

    active: bool
    program: SlotProgram
    step: int
    status_byte: int
    runtime_minutes: int
    voltage_mv: int
    current_raw: int
    charge_cap_raw: int
    discharge_cap_raw: int
    slot_index: int  # 0-5

    @property
    def status(self) -> SlotStatus:
        """Derive the slot status from active flag, status byte, and step."""
        if self.status_byte == 0x20:
            return SlotStatus.EMPTY
        if self.status_byte == 0x21:
            return SlotStatus.ERROR
        if not self.active:
            if self.status_byte in (0x07, 0x02):
                return SlotStatus.READY
            return SlotStatus.IDLE
        # Active
        if self.status_byte == 0x07:
            return SlotStatus.TRICKLE
        if self.step == 0:
            return SlotStatus.IDLE
        if self.step % 2 == 1:  # Odd steps = charging
            return SlotStatus.CHARGING
        return SlotStatus.DISCHARGING  # Even steps = discharging

    @property
    def status_label(self) -> str:
        """Human-readable status label."""
        labels: dict[SlotStatus, str] = {
            SlotStatus.EMPTY: "Empty",
            SlotStatus.IDLE: "Idle",
            SlotStatus.CHARGING: "Charge",
            SlotStatus.DISCHARGING: "Discharge",
            SlotStatus.READY: "Ready",
            SlotStatus.TRICKLE: "Trickle",
            SlotStatus.ERROR: "Error",
        }
        return labels.get(self.status, "Unknown")

    @property
    def is_9v_slot(self) -> bool:
        return self.slot_index in NINE_VOLT_SLOT_INDICES

    @property
    def voltage(self) -> float:
        """Voltage in V."""
        return self.voltage_mv / 1000.0

    @property
    def current(self) -> float:
        """Current in A. Slots A/B use finer scaling (÷10000 vs ÷1000)."""
        if self.is_9v_slot:
            return self.current_raw / 10000.0
        return self.current_raw / 1000.0

    @property
    def charge_capacity(self) -> float:
        """Charge capacity in mAh. Slots 1-4: ÷100, Slots A/B: ÷1000."""
        if self.is_9v_slot:
            return self.charge_cap_raw / 1000.0
        return self.charge_cap_raw / 100.0

    @property
    def discharge_capacity(self) -> float:
        """Discharge capacity in mAh. Same scaling as charge capacity."""
        if self.is_9v_slot:
            return self.discharge_cap_raw / 1000.0
        return self.discharge_cap_raw / 100.0

    @property
    def runtime_formatted(self) -> str:
        """Runtime as H:MM or D:HH:MM string."""
        total_minutes = self.runtime_minutes
        days = total_minutes // (24 * 60)
        remaining = total_minutes % (24 * 60)
        hours = remaining // 60
        minutes = remaining % 60
        if days > 0:
            return f"{days}:{hours:02d}:{minutes:02d}"
        return f"{hours}:{minutes:02d}"


@dataclass(frozen=True)
class Frame:
    """A complete parsed CM2016 frame (127 bytes)."""

    header: FrameHeader
    slots: tuple[SlotData, SlotData, SlotData, SlotData, SlotData, SlotData]
    checksum: int
    timestamp: datetime
    raw: bytes


class FrameError(ValueError):
    """Raised when frame data is invalid."""


def parse_header(data: bytes) -> FrameHeader:
    """Parse header bytes 7-16 (10 bytes).

    Header uses big-endian byte order for multi-byte fields.
    """
    if len(data) != HEADER_LENGTH:
        msg = f"Header must be {HEADER_LENGTH} bytes, got {len(data)}"
        raise FrameError(msg)

    firmware_major = data[0]
    firmware_minor = data[1]

    try:
        chemistry = Chemistry(data[2])
    except ValueError:
        chemistry = Chemistry.NIMH  # Default fallback

    overtemp_flag = bool(data[3])
    temp_start = struct.unpack(">h", data[4:6])[0]  # Big-endian signed
    temp_actual = struct.unpack(">h", data[6:8])[0]  # Big-endian signed
    action_counter = struct.unpack(">h", data[8:10])[0]  # Big-endian signed

    return FrameHeader(
        firmware_major=firmware_major,
        firmware_minor=firmware_minor,
        chemistry=chemistry,
        overtemp_flag=overtemp_flag,
        temp_start=temp_start,
        temp_actual=temp_actual,
        action_counter=action_counter,
    )


def parse_slot(data: bytes, slot_index: int) -> SlotData:
    """Parse 18 bytes of slot data.

    Slot fields use little-endian byte order.

    Args:
        data: 18 bytes of raw slot data.
        slot_index: 0-5 (0-3 = Slots 1-4, 4 = Slot A, 5 = Slot B).
    """
    if len(data) != SLOT_LENGTH:
        msg = f"Slot data must be {SLOT_LENGTH} bytes, got {len(data)}"
        raise FrameError(msg)

    active = bool(data[0])

    try:
        program = SlotProgram(data[1])
    except ValueError:
        program = SlotProgram.NONE

    step = data[2]
    status_byte = data[3]

    # 16-bit little-endian fields
    runtime_minutes = struct.unpack("<H", data[4:6])[0]
    voltage_mv = struct.unpack("<H", data[6:8])[0]
    current_raw = struct.unpack("<H", data[8:10])[0]

    # 32-bit little-endian charge capacity: bytes [10-13]
    charge_cap_raw = struct.unpack("<I", data[10:14])[0]

    # 32-bit little-endian discharge capacity: bytes [14-17]
    discharge_cap_raw = struct.unpack("<I", data[14:18])[0]

    return SlotData(
        active=active,
        program=program,
        step=step,
        status_byte=status_byte,
        runtime_minutes=runtime_minutes,
        voltage_mv=voltage_mv,
        current_raw=current_raw,
        charge_cap_raw=charge_cap_raw,
        discharge_cap_raw=discharge_cap_raw,
        slot_index=slot_index,
    )


def parse_frame(data: bytes) -> Frame:
    """Parse a complete 127-byte CM2016 frame.

    Args:
        data: Exactly 127 bytes of raw frame data.

    Returns:
        Parsed Frame object.

    Raises:
        FrameError: If data length is wrong or device ID doesn't match.
    """
    if len(data) != FRAME_LENGTH:
        msg = f"Frame must be {FRAME_LENGTH} bytes, got {len(data)}"
        raise FrameError(msg)

    device_id = data[:DEVICE_ID_LENGTH]
    if device_id != DEVICE_ID:
        msg = f"Invalid device ID: {device_id!r}, expected {DEVICE_ID!r}"
        raise FrameError(msg)

    header = parse_header(data[DEVICE_ID_LENGTH : DEVICE_ID_LENGTH + HEADER_LENGTH])

    slots = tuple(
        parse_slot(data[offset : offset + SLOT_LENGTH], index)
        for index, offset in enumerate(SLOT_OFFSETS)
    )

    checksum = struct.unpack("<H", data[125:127])[0]

    return Frame(
        header=header,
        slots=slots,  # type: ignore[arg-type]
        checksum=checksum,
        timestamp=datetime.now(tz=timezone.utc),
        raw=data,
    )
