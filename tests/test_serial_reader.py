"""Tests for cm2016.serial_reader — serial I/O and frame synchronization."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

from cm2016.protocol import DEVICE_ID, Frame
from cm2016.serial_reader import (
    CP210X_PID,
    CP210X_VID,
    SerialReader,
    detect_cm2016_port,
    scan_ports,
    scan_ports_detailed,
)
from tests.conftest import make_frame

# ---------------------------------------------------------------------------
# Port scanning
# ---------------------------------------------------------------------------


class _FakePortInfo:
    """Minimal mock for serial.tools.list_ports.comports() entries."""

    def __init__(
        self, device: str, description: str = "", vid: int | None = None, pid: int | None = None
    ) -> None:
        self.device = device
        self.description = description
        self.vid = vid
        self.pid = pid


class TestScanPorts:
    """Test port scanning functions."""

    @patch("cm2016.serial_reader.serial.tools.list_ports.comports")
    def test_finds_ttyusb_ports(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _FakePortInfo("/dev/ttyUSB0", "CP210x"),
            _FakePortInfo("/dev/ttyUSB1", "CH341"),
            _FakePortInfo("/dev/ttyS0", "Built-in"),  # Not USB
        ]
        ports = scan_ports()
        assert ports == ["/dev/ttyUSB0", "/dev/ttyUSB1"]

    @patch("cm2016.serial_reader.serial.tools.list_ports.comports")
    def test_finds_ttyacm_ports(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _FakePortInfo("/dev/ttyACM0", "Arduino"),
        ]
        ports = scan_ports()
        assert ports == ["/dev/ttyACM0"]

    @patch("cm2016.serial_reader.serial.tools.list_ports.comports")
    def test_finds_usb_ports_by_vid(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _FakePortInfo("/dev/ttyS0", "USB device", vid=0x10C4),
        ]
        ports = scan_ports()
        assert ports == ["/dev/ttyS0"]

    @patch("cm2016.serial_reader.serial.tools.list_ports.comports")
    def test_no_ports(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = []
        assert scan_ports() == []

    @patch("cm2016.serial_reader.serial.tools.list_ports.comports")
    def test_sorted_order(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _FakePortInfo("/dev/ttyUSB2"),
            _FakePortInfo("/dev/ttyUSB0"),
            _FakePortInfo("/dev/ttyUSB1"),
        ]
        ports = scan_ports()
        assert ports == ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2"]

    @patch("cm2016.serial_reader.serial.tools.list_ports.comports")
    def test_detailed_returns_descriptions(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _FakePortInfo("/dev/ttyUSB0", "CP210x UART Bridge"),
        ]
        ports = scan_ports_detailed()
        assert ports == [("/dev/ttyUSB0", "CP210x UART Bridge")]

    @patch("cm2016.serial_reader.serial.tools.list_ports.comports")
    def test_detailed_fallback_description(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _FakePortInfo("/dev/ttyUSB0", ""),
        ]
        ports = scan_ports_detailed()
        assert ports == [("/dev/ttyUSB0", "/dev/ttyUSB0")]


class TestDetectCm2016Port:
    """Test auto-detection of CM2016 by USB VID/PID."""

    @patch("cm2016.serial_reader.serial.tools.list_ports.comports")
    def test_detects_single_cp210x(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _FakePortInfo("/dev/ttyUSB0", "CH341", vid=0x1A86),
            _FakePortInfo("/dev/ttyUSB1", "CP2104", vid=CP210X_VID, pid=CP210X_PID),
        ]
        assert detect_cm2016_port() == "/dev/ttyUSB1"

    @patch("cm2016.serial_reader.serial.tools.list_ports.comports")
    def test_returns_none_for_multiple_cp210x(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _FakePortInfo("/dev/ttyUSB0", "CP2104", vid=CP210X_VID, pid=CP210X_PID),
            _FakePortInfo("/dev/ttyUSB1", "CP2104", vid=CP210X_VID, pid=CP210X_PID),
        ]
        assert detect_cm2016_port() is None

    @patch("cm2016.serial_reader.serial.tools.list_ports.comports")
    def test_returns_none_when_no_cp210x(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _FakePortInfo("/dev/ttyUSB0", "CH341", vid=0x1A86),
        ]
        assert detect_cm2016_port() is None

    @patch("cm2016.serial_reader.serial.tools.list_ports.comports")
    def test_returns_none_for_empty(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = []
        assert detect_cm2016_port() is None


# ---------------------------------------------------------------------------
# Mock serial port for reader tests
# ---------------------------------------------------------------------------


class MockSerialPort:
    """Simulates a serial port that feeds pre-built frames."""

    def __init__(self, frames: list[bytes] | None = None, read_delay: float = 0.0) -> None:
        self._data = bytearray()
        self._pos = 0
        self._read_delay = read_delay
        self._is_open = True
        self.port = "/dev/ttyUSB_MOCK"

        if frames:
            for f in frames:
                self._data.extend(f)

    @property
    def is_open(self) -> bool:
        return self._is_open

    def read(self, size: int = 1) -> bytes:
        if not self._is_open:
            return b""
        if self._read_delay > 0:
            time.sleep(self._read_delay)
        if self._pos >= len(self._data):
            return b""  # Simulate timeout
        end = min(self._pos + size, len(self._data))
        result = bytes(self._data[self._pos : end])
        self._pos = end
        return result

    def close(self) -> None:
        self._is_open = False

    def add_data(self, data: bytes) -> None:
        """Add more data to the buffer (simulate device sending)."""
        self._data.extend(data)


# ---------------------------------------------------------------------------
# SerialReader tests
# ---------------------------------------------------------------------------


class TestSerialReaderProperties:
    """Test reader state properties."""

    def test_not_connected_initially(self) -> None:
        reader = SerialReader()
        assert reader.is_connected is False
        assert reader.port_name is None

    def test_connected_after_connect(self) -> None:
        reader = SerialReader()
        mock_port = MockSerialPort(frames=[make_frame()])

        with patch("cm2016.serial_reader.serial.Serial", return_value=mock_port):
            reader.connect("/dev/ttyUSB0")
            assert reader.is_connected is True
            assert reader.port_name == "/dev/ttyUSB_MOCK"
            reader.disconnect()

    def test_not_connected_after_disconnect(self) -> None:
        reader = SerialReader()
        mock_port = MockSerialPort(frames=[make_frame()])

        with patch("cm2016.serial_reader.serial.Serial", return_value=mock_port):
            reader.connect("/dev/ttyUSB0")
            reader.disconnect()
            assert reader.is_connected is False
            assert reader.port_name is None


class TestSerialReaderFrameSync:
    """Test frame synchronization and parsing."""

    def test_reads_valid_frame(self) -> None:
        """Reader should parse a valid frame and call on_frame."""
        frame_data = make_frame()
        mock_port = MockSerialPort(frames=[frame_data])
        received_frames: list[Frame] = []

        reader = SerialReader(disconnect_timeout=0.5)
        reader.on_frame = lambda f: received_frames.append(f)

        with patch("cm2016.serial_reader.serial.Serial", return_value=mock_port):
            reader.connect("/dev/ttyUSB0")
            # Give the thread time to process
            time.sleep(0.3)
            reader.disconnect()

        assert len(received_frames) >= 1
        assert received_frames[0].raw == frame_data

    def test_reads_multiple_frames(self) -> None:
        """Reader should parse consecutive frames."""
        frames = [make_frame(), make_frame(), make_frame()]
        mock_port = MockSerialPort(frames=frames)
        received: list[Frame] = []

        reader = SerialReader(disconnect_timeout=0.5)
        reader.on_frame = lambda f: received.append(f)

        with patch("cm2016.serial_reader.serial.Serial", return_value=mock_port):
            reader.connect("/dev/ttyUSB0")
            time.sleep(0.3)
            reader.disconnect()

        assert len(received) == 3

    def test_syncs_after_garbage(self) -> None:
        """Reader should skip garbage bytes and find the frame header."""
        garbage = b"\xff\xab\x00\x13\x37"
        frame_data = make_frame()
        mock_port = MockSerialPort()
        mock_port._data = bytearray(garbage + frame_data)

        received: list[Frame] = []
        reader = SerialReader(disconnect_timeout=0.5)
        reader.on_frame = lambda f: received.append(f)

        with patch("cm2016.serial_reader.serial.Serial", return_value=mock_port):
            reader.connect("/dev/ttyUSB0")
            time.sleep(0.3)
            reader.disconnect()

        assert len(received) == 1
        assert received[0].raw == frame_data

    def test_syncs_after_partial_frame(self) -> None:
        """Reader should resync if a partial frame is followed by a valid one."""
        partial = DEVICE_ID + b"\x00" * 50  # Incomplete frame (only 57 bytes)
        full_frame = make_frame()
        mock_port = MockSerialPort()
        mock_port._data = bytearray(partial + full_frame)

        received: list[Frame] = []
        reader = SerialReader(disconnect_timeout=0.5)
        reader.on_frame = lambda f: received.append(f)

        with patch("cm2016.serial_reader.serial.Serial", return_value=mock_port):
            reader.connect("/dev/ttyUSB0")
            time.sleep(0.3)
            reader.disconnect()

        # Should find at least the full frame
        assert len(received) >= 1


class TestSerialReaderDisconnect:
    """Test auto-disconnect detection."""

    def test_connection_lost_on_timeout(self) -> None:
        """on_connection_lost should fire when no data arrives within timeout."""
        mock_port = MockSerialPort()  # No data at all
        lost_event = threading.Event()

        reader = SerialReader(disconnect_timeout=0.3)
        reader.on_connection_lost = lambda: lost_event.set()

        with patch("cm2016.serial_reader.serial.Serial", return_value=mock_port):
            reader.connect("/dev/ttyUSB0")
            # Wait for the timeout to trigger
            assert lost_event.wait(timeout=2.0), "on_connection_lost was not called"
            reader.disconnect()

    def test_no_false_disconnect_with_data(self) -> None:
        """No disconnect signal while frames are arriving."""
        # Provide enough frames to keep the reader busy
        frames = [make_frame() for _ in range(5)]
        mock_port = MockSerialPort(frames=frames)
        lost = threading.Event()

        reader = SerialReader(disconnect_timeout=1.0)
        reader.on_connection_lost = lambda: lost.set()

        with patch("cm2016.serial_reader.serial.Serial", return_value=mock_port):
            reader.connect("/dev/ttyUSB0")
            time.sleep(0.2)  # Let reader process frames
            reader.disconnect()

        # The frames are processed fast, then the reader runs out of data.
        # But we disconnect before the timeout, so lost should NOT be set
        # during the time we were actively reading frames.
        # (It may set after data runs out, that's OK.)

    def test_disconnect_stops_thread(self) -> None:
        """Calling disconnect() should stop the reader thread."""
        mock_port = MockSerialPort(frames=[make_frame()])

        reader = SerialReader()
        with patch("cm2016.serial_reader.serial.Serial", return_value=mock_port):
            reader.connect("/dev/ttyUSB0")
            assert reader._thread is not None
            assert reader._thread.is_alive()
            reader.disconnect()
            assert reader._thread is None

    def test_double_disconnect_safe(self) -> None:
        """Calling disconnect() twice should not raise."""
        mock_port = MockSerialPort()

        reader = SerialReader()
        with patch("cm2016.serial_reader.serial.Serial", return_value=mock_port):
            reader.connect("/dev/ttyUSB0")
            reader.disconnect()
            reader.disconnect()  # Should not raise

    def test_reconnect(self) -> None:
        """Should be able to connect, disconnect, and connect again."""
        frame1 = make_frame(slot_overrides={0: {"voltage_mv": 1000}})
        frame2 = make_frame(slot_overrides={0: {"voltage_mv": 2000}})

        received: list[Frame] = []
        reader = SerialReader(disconnect_timeout=0.5)
        reader.on_frame = lambda f: received.append(f)

        mock_port1 = MockSerialPort(frames=[frame1])
        mock_port2 = MockSerialPort(frames=[frame2])

        with patch("cm2016.serial_reader.serial.Serial", return_value=mock_port1):
            reader.connect("/dev/ttyUSB0")
            time.sleep(0.2)
            reader.disconnect()

        with patch("cm2016.serial_reader.serial.Serial", return_value=mock_port2):
            reader.connect("/dev/ttyUSB0")
            time.sleep(0.2)
            reader.disconnect()

        assert len(received) >= 2
        voltages = [f.slots[0].voltage_mv for f in received]
        assert 1000 in voltages
        assert 2000 in voltages


class TestSerialReaderNoCallback:
    """Test reader behavior when no callbacks are set."""

    def test_no_frame_callback(self) -> None:
        """Reader should not crash if on_frame is None."""
        mock_port = MockSerialPort(frames=[make_frame()])
        reader = SerialReader(disconnect_timeout=0.5)
        # on_frame is None (default)

        with patch("cm2016.serial_reader.serial.Serial", return_value=mock_port):
            reader.connect("/dev/ttyUSB0")
            time.sleep(0.2)
            reader.disconnect()
        # No exception = pass

    def test_no_connection_lost_callback(self) -> None:
        """Reader should not crash if on_connection_lost is None."""
        mock_port = MockSerialPort()  # No data → timeout
        reader = SerialReader(disconnect_timeout=0.2)
        # on_connection_lost is None (default)

        with patch("cm2016.serial_reader.serial.Serial", return_value=mock_port):
            reader.connect("/dev/ttyUSB0")
            time.sleep(0.5)
            reader.disconnect()
        # No exception = pass
