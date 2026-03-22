"""Tests for cm2016.widgets.chart_widget — chart helpers and widget (Issue #13)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from cm2016.session import SlotRecord

try:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk  # noqa: F401

    from cm2016.widgets.chart_widget import (
        ChartStyle,
        ChartWidget,
        CurrentChart,
        VoltageChart,
        _format_elapsed,
        _nice_ticks,
    )

    GTK_AVAILABLE = True
except (ImportError, ValueError):
    GTK_AVAILABLE = False


def _make_records(count: int = 5, voltage: float = 1.32) -> list[SlotRecord]:
    base = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
    return [
        SlotRecord(
            timestamp=base + timedelta(seconds=i * 2),
            slot_index=0,
            program="Charge",
            status="Charge",
            chemistry="NiMH",
            runtime_minutes=i,
            runtime_formatted=f"0:{i:02d}",
            voltage=voltage + i * 0.01,
            current=0.5 + i * 0.01,
            charge_capacity=100.0 + i * 10,
            discharge_capacity=0.0,
        )
        for i in range(count)
    ]


# --- Pure helper function tests (GTK-free after import) ---


@pytest.mark.skipif(not GTK_AVAILABLE, reason="GTK 4 not available")
class TestNiceTicks:
    """Test the _nice_ticks axis tick generator."""

    def test_basic_range(self) -> None:
        ticks = _nice_ticks(0, 10, 5)
        assert len(ticks) > 0
        assert all(0 <= t <= 10 for t in ticks)

    def test_degenerate_range(self) -> None:
        ticks = _nice_ticks(5, 5, 5)
        assert ticks == [5]

    def test_small_float_range(self) -> None:
        ticks = _nice_ticks(1.32, 1.35, 5)
        assert len(ticks) >= 1
        assert all(1.32 <= t <= 1.35 for t in ticks)

    def test_returns_at_most_reasonable_count(self) -> None:
        ticks = _nice_ticks(0, 100, 5)
        assert len(ticks) <= 20


@pytest.mark.skipif(not GTK_AVAILABLE, reason="GTK 4 not available")
class TestFormatElapsed:
    """Test the _format_elapsed time formatter."""

    def test_seconds(self) -> None:
        assert _format_elapsed(30) == "30s"

    def test_zero(self) -> None:
        assert _format_elapsed(0) == "0s"

    def test_minutes(self) -> None:
        assert _format_elapsed(90) == "1:30"

    def test_exact_hour(self) -> None:
        assert _format_elapsed(3600) == "1:00:00"

    def test_hours_minutes_seconds(self) -> None:
        assert _format_elapsed(3690) == "1:01:30"


# --- Chart widget tests ---


@pytest.mark.skipif(not GTK_AVAILABLE, reason="GTK 4 not available")
class TestChartWidgetCore:
    """Test ChartWidget state management."""

    def test_empty_data_draws_no_data(self) -> None:
        widget = ChartWidget(title="Test", y_label="V")
        cr = MagicMock()
        cr.text_extents.return_value = MagicMock(width=10, height=10)
        widget._draw(widget, cr, 800, 400)
        # "No data" text should be shown
        texts = [c.args[0] for c in cr.show_text.call_args_list if c.args]
        assert any("data" in t.lower() or "Data" in t for t in texts)

    def test_clear_resets_state(self) -> None:
        widget = ChartWidget(title="Test", y_label="V")
        widget._records = _make_records(5)
        widget._view_t_min = 1.0
        widget.clear()
        assert widget._records == []
        assert widget._view_t_min is None

    def test_reset_zoom_clears_viewport(self) -> None:
        widget = ChartWidget(title="Test", y_label="V")
        widget._view_t_min = 0.0
        widget._view_t_max = 10.0
        widget._view_v_min = 0.0
        widget._view_v_max = 2.0
        widget._zoom_stack = [(0, 10, 0, 2)]
        widget.reset_zoom()
        assert widget._view_t_min is None
        assert widget._view_t_max is None
        assert widget._view_v_min is None
        assert widget._view_v_max is None
        assert widget._zoom_stack == []

    def test_is_zoomed_false_by_default(self) -> None:
        widget = ChartWidget(title="Test", y_label="V")
        assert widget.is_zoomed is False

    def test_is_zoomed_true_after_setting_viewport(self) -> None:
        widget = ChartWidget(title="Test", y_label="V")
        widget._view_t_min = 0.0  # 0.0 is still zoomed
        assert widget.is_zoomed is True

    def test_zoom_undo_pops_stack(self) -> None:
        widget = ChartWidget(title="Test", y_label="V")
        widget._zoom_stack = [(0, 10, 0, 2), (2, 8, 0.5, 1.5)]
        widget.zoom_undo()
        assert len(widget._zoom_stack) == 1
        assert widget._view_t_min == 2
        assert widget._view_t_max == 8

    def test_zoom_undo_empty_stack_resets(self) -> None:
        widget = ChartWidget(title="Test", y_label="V")
        widget._view_t_min = 5.0
        widget.zoom_undo()
        assert widget._view_t_min is None

    def test_set_style(self) -> None:
        widget = ChartWidget(title="Test", y_label="V")
        widget.set_style(ChartStyle.BAR)
        assert widget._style == ChartStyle.BAR


@pytest.mark.skipif(not GTK_AVAILABLE, reason="GTK 4 not available")
class TestChartSubclasses:
    """Test VoltageChart and CurrentChart value extraction."""

    def test_voltage_chart_values(self) -> None:
        chart = VoltageChart()
        records = _make_records(3)
        chart._records = records
        assert chart._get_values() == [r.voltage for r in records]

    def test_current_chart_values(self) -> None:
        chart = CurrentChart()
        records = _make_records(3)
        chart._records = records
        assert chart._get_values() == [r.current for r in records]


@pytest.mark.skipif(not GTK_AVAILABLE, reason="GTK 4 not available")
class TestFindNearestRecord:
    """Test _find_nearest_record coordinate mapping."""

    def test_returns_none_with_no_records(self) -> None:
        widget = ChartWidget(title="Test", y_label="V")
        assert widget._find_nearest_record(400, 200) is None

    def test_returns_none_when_far_away(self) -> None:
        widget = ChartWidget(title="Test", y_label="V")
        records = _make_records(1)
        widget._records = records
        # Set geometry so the single record maps to x=100
        widget._plot_geom = (60, 30, 700, 350)
        widget._data_range = (0, 10, 0, 2)
        # Query at x=500, which is far from x=60 (the record at t=0)
        result = widget._find_nearest_record(500, 200)
        assert result is None

    def test_returns_nearest_record(self) -> None:
        widget = ChartWidget(title="Test", y_label="V")
        records = _make_records(3)
        widget._records = records
        widget._plot_geom = (60, 30, 700, 350)
        widget._data_range = (0, 4, 1.0, 1.5)
        # Record at t=0 maps to x=60, query near there
        result = widget._find_nearest_record(62, 200)
        assert result is not None
        assert result.timestamp == records[0].timestamp
