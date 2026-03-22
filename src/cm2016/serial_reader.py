"""Serial communication with the Voltcraft CM 2016.

Reads 127-byte frames from the device over USB serial (CP210x).
Runs a background daemon thread for non-blocking I/O and delivers
parsed frames via callbacks.

The device transmits frames every ~2 seconds. If no valid frame is
received within the timeout period, the reader signals a lost connection.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING
from typing import Protocol as TypingProtocol

if TYPE_CHECKING:
    from collections.abc import Callable

import serial
import serial.tools.list_ports

from cm2016.protocol import (
    DEVICE_ID,
    DEVICE_ID_LENGTH,
    FRAME_LENGTH,
    Frame,
    FrameError,
    parse_frame,
)

logger = logging.getLogger(__name__)

# Disconnect timeout (seconds). Must exceed the ~2 s frame interval by a
# comfortable margin to avoid false disconnects from USB/OS jitter.
DISCONNECT_TIMEOUT = 5.0

# Serial port settings for the CM2016.
BAUD_RATE = 19200
DATA_BITS = serial.EIGHTBITS
STOP_BITS = serial.STOPBITS_ONE
PARITY = serial.PARITY_NONE

# Read timeout for serial port (seconds). Short enough to check the
# stop event frequently, long enough to avoid busy-waiting.
SERIAL_READ_TIMEOUT = 0.5


class FrameCallback(TypingProtocol):
    """Protocol for frame delivery callbacks."""

    def __call__(self, frame: Frame) -> None: ...


class ConnectionLostCallback(TypingProtocol):
    """Protocol for connection lost callbacks."""

    def __call__(self) -> None: ...


# Silicon Labs CP210x USB vendor/product IDs used by the CM2016.
CP210X_VID = 0x10C4
CP210X_PID = 0xEA60


def scan_ports() -> list[str]:
    """List available serial ports that could be a CM2016.

    Returns port device paths (e.g., ``/dev/ttyUSB0``), sorted alphabetically.
    Filters for USB serial ports only.
    """
    ports = []
    for port_info in serial.tools.list_ports.comports():
        # Include USB serial ports (ttyUSB* on Linux)
        if port_info.device and (
            "ttyUSB" in port_info.device
            or "ttyACM" in port_info.device
            or port_info.vid is not None  # Any USB device with vendor ID
        ):
            ports.append(port_info.device)
    ports.sort()
    return ports


def scan_ports_detailed() -> list[tuple[str, str]]:
    """List available serial ports with descriptions.

    Returns list of (device_path, description) tuples.
    """
    ports = []
    for port_info in serial.tools.list_ports.comports():
        if port_info.device and (
            "ttyUSB" in port_info.device
            or "ttyACM" in port_info.device
            or port_info.vid is not None
        ):
            desc = port_info.description or port_info.device
            ports.append((port_info.device, desc))
    ports.sort(key=lambda x: x[0])
    return ports


def detect_cm2016_port() -> str | None:
    """Auto-detect a CM2016 device by its USB vendor/product ID.

    The CM2016 uses a Silicon Labs CP210x USB-to-UART bridge
    (VID=0x10C4, PID=0xEA60). If exactly one matching port is found,
    returns its device path. If multiple are found, returns None
    (user must choose manually).

    Returns:
        Device path (e.g., ``/dev/ttyUSB1``) or None.
    """
    candidates = []
    for port_info in serial.tools.list_ports.comports():
        if port_info.vid == CP210X_VID and port_info.pid == CP210X_PID:
            candidates.append(port_info.device)

    if len(candidates) == 1:
        logger.info("Auto-detected CM2016 on %s", candidates[0])
        return str(candidates[0])

    if len(candidates) > 1:
        logger.info(
            "Multiple CP210x ports found (%s), manual selection needed",
            ", ".join(candidates),
        )
    return None


class SerialReader:
    """Reads CM2016 frames from a serial port in a background thread.

    Usage::

        reader = SerialReader()
        reader.on_frame = my_frame_handler
        reader.on_connection_lost = my_disconnect_handler
        reader.connect("/dev/ttyUSB0")
        # ...later...
        reader.disconnect()

    The ``on_frame`` callback is called from the reader thread. If you
    need to update a GTK UI, use ``GLib.idle_add()`` to dispatch to
    the main loop::

        def my_frame_handler(frame: Frame) -> None:
            GLib.idle_add(update_ui, frame)
    """

    def __init__(self, disconnect_timeout: float = DISCONNECT_TIMEOUT) -> None:
        self._port: serial.Serial | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._disconnect_timeout = disconnect_timeout

        self.on_frame: Callable[[Frame], None] | None = None
        self.on_connection_lost: Callable[[], None] | None = None

    @property
    def is_connected(self) -> bool:
        """Whether the serial port is currently open."""
        return self._port is not None and self._port.is_open

    @property
    def port_name(self) -> str | None:
        """Name of the currently connected port, or None."""
        if self._port is not None and self._port.is_open:
            return str(self._port.port)
        return None

    def connect(self, port: str) -> None:
        """Open the serial port and start the reader thread.

        Args:
            port: Device path, e.g. ``/dev/ttyUSB0``.

        Raises:
            serial.SerialException: If the port cannot be opened.
        """
        if self.is_connected:
            self.disconnect()

        self._port = serial.Serial(
            port=port,
            baudrate=BAUD_RATE,
            bytesize=DATA_BITS,
            stopbits=STOP_BITS,
            parity=PARITY,
            timeout=SERIAL_READ_TIMEOUT,
        )

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._read_loop,
            name="cm2016-serial-reader",
            daemon=True,
        )
        self._thread.start()
        logger.info("Connected to %s", port)

    def disconnect(self) -> None:
        """Stop the reader thread and close the serial port."""
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

        if self._port is not None and self._port.is_open:
            self._port.close()
            logger.info("Disconnected from %s", self._port.port)

        self._port = None

    def _read_loop(self) -> None:
        """Background thread: sync to frame headers and parse frames."""
        assert self._port is not None

        last_frame_time = time.monotonic()

        while not self._stop_event.is_set():
            try:
                frame_data = self._sync_and_read_frame()
            except serial.SerialException:
                logger.warning("Serial port error, connection lost")
                self._signal_connection_lost()
                return
            except OSError:
                logger.warning("OS error reading serial port")
                self._signal_connection_lost()
                return

            if frame_data is not None:
                last_frame_time = time.monotonic()
                try:
                    frame = parse_frame(frame_data)
                except FrameError:
                    logger.debug("Failed to parse frame, skipping")
                    continue

                if self.on_frame is not None:
                    self.on_frame(frame)
            else:
                # No frame received; check timeout
                elapsed = time.monotonic() - last_frame_time
                if elapsed > self._disconnect_timeout:
                    logger.info("No frame received for %.1fs, connection lost", elapsed)
                    self._signal_connection_lost()
                    return

    def _sync_and_read_frame(self) -> bytes | None:
        """Read bytes until the "CM2016 " header is found, then read the rest.

        Returns:
            127 bytes of frame data, or None if no complete frame was read
            (e.g., due to timeout).
        """
        assert self._port is not None

        # Read one byte at a time to find the sync marker.
        # Accumulate bytes in a buffer; when the last 7 bytes match
        # DEVICE_ID, we've found the start of a frame.
        sync_buffer = bytearray()

        while not self._stop_event.is_set():
            byte = self._port.read(1)
            if not byte:
                # Read timeout, no data available
                return None

            sync_buffer.append(byte[0])

            if (
                len(sync_buffer) >= DEVICE_ID_LENGTH
                and bytes(sync_buffer[-DEVICE_ID_LENGTH:]) == DEVICE_ID
            ):
                # Found the header marker. Read the remaining bytes.
                remaining = FRAME_LENGTH - DEVICE_ID_LENGTH
                rest = self._port.read(remaining)
                if len(rest) < remaining:
                    # Incomplete frame (timeout during read)
                    return None
                return bytes(DEVICE_ID + rest)

            # Prevent unbounded buffer growth while scanning for sync
            if len(sync_buffer) > 1024:
                sync_buffer = sync_buffer[-DEVICE_ID_LENGTH:]

        return None

    def _signal_connection_lost(self) -> None:
        """Notify the callback that the connection was lost."""
        if self.on_connection_lost is not None:
            self.on_connection_lost()
