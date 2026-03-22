"""Tests for chart_widget fixes (Issues #2 and #3).

Tests the falsy-zero viewport bug and division-by-zero protection
without requiring a running GTK display.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from cm2016.session import SlotRecord

# We need to import chart_widget which requires GTK — skip if unavailable
try:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk  # noqa: F401

    from cm2016.widgets.chart_widget import ChartWidget

    GTK_AVAILABLE = True
except (ImportError, ValueError):
    GTK_AVAILABLE = False


def _make_records(
    count: int = 10,
    voltage: float = 1.32,
    current: float = 0.5,
    interval_seconds: float = 2.0,
    constant_voltage: bool = False,
) -> list[SlotRecord]:
    """Create a list of SlotRecords for testing."""
    base = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
    records = []
    for i in range(count):
        v = voltage if constant_voltage else voltage + i * 0.01
        records.append(
            SlotRecord(
                timestamp=base + timedelta(seconds=i * interval_seconds),
                slot_index=0,
                program="Charge",
                status="Charge",
                chemistry="NiMH",
                runtime_minutes=i,
                runtime_formatted=f"0:{i:02d}",
                voltage=v,
                current=current,
                charge_capacity=100.0 + i * 10,
                discharge_capacity=0.0,
            )
        )
    return records


@pytest.mark.skipif(not GTK_AVAILABLE, reason="GTK 4 not available")
class TestFalsyZeroViewport:
    """Issue #2: or-pattern treats 0.0 as unset."""

    def test_viewport_zero_t_min_preserved(self) -> None:
        """A viewport with t_min=0.0 should not fall back to auto-computed value."""
        widget = ChartWidget(title="Test", y_label="V")
        widget._records = _make_records(5)
        # Set viewport with t_min at 0.0
        widget._view_t_min = 0.0
        widget._view_t_max = 5.0
        widget._view_v_min = 0.0
        widget._view_v_max = 2.0

        # Simulate the draw path: call _draw with a mock context
        cr = MagicMock()
        cr.text_extents.return_value = MagicMock(width=10, height=10)
        widget._draw(widget, cr, 800, 400)

        # data_range should reflect our viewport, not auto-computed
        t_min, t_max, v_min, v_max = widget._data_range
        assert t_min == 0.0
        assert t_max == 5.0
        assert v_min == 0.0
        assert v_max == 2.0

    def test_push_zoom_preserves_zero_boundaries(self) -> None:
        """_push_zoom should save 0.0 boundaries faithfully."""
        widget = ChartWidget(title="Test", y_label="V")
        widget._data_range = (0.0, 10.0, 0.0, 2.0)
        widget._view_t_min = 0.0
        widget._view_t_max = 5.0
        widget._view_v_min = 0.0
        widget._view_v_max = 1.0

        widget._push_zoom()

        assert len(widget._zoom_stack) == 1
        saved = widget._zoom_stack[0]
        assert saved == (0.0, 5.0, 0.0, 1.0)

    def test_pan_from_zero_viewport(self) -> None:
        """Panning from a viewport starting at 0.0 should work correctly."""
        widget = ChartWidget(title="Test", y_label="V")
        widget._data_range = (0.0, 10.0, 0.0, 2.0)
        widget._view_t_min = 0.0
        widget._view_t_max = 5.0
        widget._view_v_min = 0.0
        widget._view_v_max = 1.0

        widget._pan(2.0, 0.0)

        assert widget._view_t_min == 2.0
        assert widget._view_t_max == 7.0

    def test_pan_to_start_with_zero_viewport(self) -> None:
        """_pan_to_start with viewport starting at 0.0 computes span correctly."""
        widget = ChartWidget(title="Test", y_label="V")
        widget._data_range = (0.0, 100.0, 0.0, 2.0)
        widget._view_t_min = 0.0
        widget._view_t_max = 20.0

        widget._records = _make_records(5)
        widget._pan_to_start()

        # Span should be 20.0 (20 - 0), not using the fallback
        assert widget._view_t_min == 0
        assert widget._view_t_max == 20.0

    def test_pan_to_end_with_zero_viewport(self) -> None:
        """_pan_to_end with viewport starting at 0.0 computes span correctly."""
        widget = ChartWidget(title="Test", y_label="V")
        records = _make_records(5, interval_seconds=10.0)
        widget._records = records
        widget._data_range = (0.0, 40.0, 0.0, 2.0)
        widget._view_t_min = 0.0
        widget._view_t_max = 20.0

        widget._pan_to_end()

        # End is at 40s, span is 20s, so t_min should be 20
        assert widget._view_t_max == 40.0
        assert widget._view_t_min == 20.0


@pytest.mark.skipif(not GTK_AVAILABLE, reason="GTK 4 not available")
class TestDivisionByZero:
    """Issue #3: division by zero with single datapoint or degenerate zoom."""

    def test_single_datapoint_no_crash(self) -> None:
        """A single data point should render without ZeroDivisionError."""
        widget = ChartWidget(title="Test", y_label="V")
        widget._records = _make_records(1)

        cr = MagicMock()
        cr.text_extents.return_value = MagicMock(width=10, height=10)

        # Should not raise
        widget._draw(widget, cr, 800, 400)

        t_min, t_max, v_min, v_max = widget._data_range
        assert t_max > t_min
        assert v_max > v_min

    def test_constant_voltage_no_crash(self) -> None:
        """All identical voltages should render without ZeroDivisionError."""
        widget = ChartWidget(title="Test", y_label="V")
        widget._records = _make_records(5, constant_voltage=True)

        cr = MagicMock()
        cr.text_extents.return_value = MagicMock(width=10, height=10)

        widget._draw(widget, cr, 800, 400)

        _, _, v_min, v_max = widget._data_range
        assert v_max > v_min

    def test_degenerate_zoom_viewport(self) -> None:
        """Viewport with t_min == t_max should be clamped, not crash."""
        widget = ChartWidget(title="Test", y_label="V")
        widget._records = _make_records(5)
        widget._view_t_min = 5.0
        widget._view_t_max = 5.0  # Degenerate: zero width
        widget._view_v_min = 1.0
        widget._view_v_max = 1.0  # Degenerate: zero height

        cr = MagicMock()
        cr.text_extents.return_value = MagicMock(width=10, height=10)

        widget._draw(widget, cr, 800, 400)

        t_min, t_max, v_min, v_max = widget._data_range
        assert t_max > t_min
        assert v_max > v_min

    def test_zoom_at_cursor_zero_span(self) -> None:
        """_zoom_at_cursor when data range has zero span should not store zero half."""
        widget = ChartWidget(title="Test", y_label="V")
        # Force a degenerate data range
        widget._data_range = (5.0, 5.0, 1.0, 1.0)

        widget._zoom_at_cursor(0.5)

        # Viewport should have non-zero span
        assert widget._view_t_max > widget._view_t_min
        assert widget._view_v_max > widget._view_v_min
