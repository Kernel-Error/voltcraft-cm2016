"""Tests for Excel export callback fix (Issue #5).

Verifies that the GTK async callback correctly unpacks the
(records, slot_name) tuple passed as user_data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cm2016.session import SlotRecord

try:
    import gi

    gi.require_version("Adw", "1")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gio, GLib, Gtk  # noqa: F401

    from cm2016.app import MainWindow

    GTK_AVAILABLE = True
except (ImportError, ValueError):
    GTK_AVAILABLE = False


def _make_test_records() -> list[SlotRecord]:
    """Create sample records for testing."""
    base = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
    return [
        SlotRecord(
            timestamp=base,
            slot_index=0,
            program="Charge",
            status="Charge",
            chemistry="NiMH",
            runtime_minutes=10,
            runtime_formatted="0:10",
            voltage=1.32,
            current=0.5,
            charge_capacity=100.0,
            discharge_capacity=0.0,
        )
    ]


@pytest.mark.skipif(not GTK_AVAILABLE, reason="GTK 4 not available")
class TestExcelCallbackUnpack:
    """Issue #5: Excel export passes multiple user_data args to GTK async callback."""

    def test_callback_unpacks_tuple(self) -> None:
        """_on_excel_save_done should accept a (records, slot_name) tuple."""
        records = _make_test_records()
        slot_name = "Slot 1"
        user_data = (records, slot_name)

        # Create a mock dialog that returns a file path
        mock_dialog = MagicMock()
        mock_gfile = MagicMock()
        mock_gfile.get_path.return_value = "/tmp/test_export.xlsx"
        mock_dialog.save_finish.return_value = mock_gfile
        mock_result = MagicMock()

        # We need a MainWindow instance — mock enough to call the method
        # Create a minimal mock that has _on_excel_save_done as the real method
        with patch("cm2016.app.export_excel", return_value=1) as mock_export:
            mock_self = MagicMock()
            mock_self._on_excel_save_done = MainWindow._on_excel_save_done.__get__(
                mock_self, MainWindow
            )

            mock_self._on_excel_save_done(mock_dialog, mock_result, user_data)

            mock_export.assert_called_once_with(
                records, Path("/tmp/test_export.xlsx"), slot_name="Slot 1"
            )

    def test_callback_handles_cancel(self) -> None:
        """Callback should handle user cancellation gracefully."""
        mock_dialog = MagicMock()
        mock_dialog.save_finish.side_effect = GLib.Error("Dismissed by user")
        mock_result = MagicMock()

        mock_self = MagicMock()
        mock_self._on_excel_save_done = MainWindow._on_excel_save_done.__get__(
            mock_self, MainWindow
        )

        # Should not raise
        mock_self._on_excel_save_done(mock_dialog, mock_result, (_make_test_records(), "Slot 1"))
