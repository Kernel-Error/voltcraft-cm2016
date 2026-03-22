"""Tests for disconnect timeout constant (Issue #10)."""

from __future__ import annotations

from cm2016.serial_reader import DISCONNECT_TIMEOUT


def test_disconnect_timeout_exceeds_frame_interval() -> None:
    """Timeout must be well above the ~2s frame interval to avoid false disconnects."""
    assert DISCONNECT_TIMEOUT >= 4.0, (
        f"DISCONNECT_TIMEOUT ({DISCONNECT_TIMEOUT}s) is too close to the "
        "~2s frame interval and will cause false disconnects"
    )
