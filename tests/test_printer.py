"""Tests for cm2016.export.printer — print report rendering (Issue #13)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from cm2016.session import SlotRecord

try:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk  # noqa: F401

    from cm2016.export.printer import _draw_print_chart, _on_draw_page, print_report

    GTK_AVAILABLE = True
except (ImportError, ValueError):
    GTK_AVAILABLE = False


def _make_records(
    count: int = 5,
    voltage: float = 1.32,
    status: str = "Charge",
    constant_voltage: bool = False,
) -> list[SlotRecord]:
    base = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
    return [
        SlotRecord(
            timestamp=base + timedelta(seconds=i * 2),
            slot_index=0,
            program="Charge",
            status=status,
            chemistry="NiMH",
            runtime_minutes=i,
            runtime_formatted=f"0:{i:02d}",
            voltage=voltage if constant_voltage else voltage + i * 0.01,
            current=0.5,
            charge_capacity=100.0 + i * 10,
            discharge_capacity=0.0,
        )
        for i in range(count)
    ]


@pytest.mark.skipif(not GTK_AVAILABLE, reason="GTK 4 not available")
class TestDrawPrintChart:
    """Test the _draw_print_chart helper."""

    def test_empty_records_returns_early(self) -> None:
        cr = MagicMock()
        _draw_print_chart(cr, 0, 0, 500, 300, [], [], "V", "{:.3f}")
        cr.stroke.assert_not_called()

    def test_single_record_no_crash(self) -> None:
        records = _make_records(1)
        values = [r.voltage for r in records]
        cr = MagicMock()
        cr.text_extents.return_value = MagicMock(width=10, height=10)
        _draw_print_chart(cr, 0, 0, 500, 300, records, values, "V", "{:.3f}")

    def test_multiple_records_draws_lines(self) -> None:
        records = _make_records(5)
        values = [r.voltage for r in records]
        cr = MagicMock()
        cr.text_extents.return_value = MagicMock(width=10, height=10)
        _draw_print_chart(cr, 0, 0, 500, 300, records, values, "V", "{:.3f}")
        assert cr.stroke.call_count > 0

    def test_charge_color_green(self) -> None:
        records = _make_records(3, status="Charge")
        values = [r.voltage for r in records]
        cr = MagicMock()
        cr.text_extents.return_value = MagicMock(width=10, height=10)
        _draw_print_chart(cr, 0, 0, 500, 300, records, values, "V", "{:.3f}")
        cr.set_source_rgb.assert_any_call(0.30, 0.60, 0.02)

    def test_discharge_color_red(self) -> None:
        records = _make_records(3, status="Discharge")
        values = [r.voltage for r in records]
        cr = MagicMock()
        cr.text_extents.return_value = MagicMock(width=10, height=10)
        _draw_print_chart(cr, 0, 0, 500, 300, records, values, "V", "{:.3f}")
        cr.set_source_rgb.assert_any_call(0.80, 0.00, 0.00)

    def test_constant_voltage_no_crash(self) -> None:
        records = _make_records(5, constant_voltage=True)
        values = [r.voltage for r in records]
        cr = MagicMock()
        cr.text_extents.return_value = MagicMock(width=10, height=10)
        _draw_print_chart(cr, 0, 0, 500, 300, records, values, "V", "{:.3f}")


@pytest.mark.skipif(not GTK_AVAILABLE, reason="GTK 4 not available")
class TestOnDrawPage:
    """Test the _on_draw_page callback."""

    def test_title_contains_slot_name(self) -> None:
        records = _make_records(3)
        cr = MagicMock()
        cr.text_extents.return_value = MagicMock(width=10, height=10)
        ctx = MagicMock()
        ctx.get_cairo_context.return_value = cr
        ctx.get_width.return_value = 800
        ctx.get_height.return_value = 600

        _on_draw_page(MagicMock(), ctx, 0, records, "Slot 1")

        # Check that show_text was called with a string containing "Slot 1"
        texts = [c.args[0] for c in cr.show_text.call_args_list if c.args]
        assert any("Slot 1" in t for t in texts)

    def test_draws_two_charts(self) -> None:
        records = _make_records(3)
        cr = MagicMock()
        cr.text_extents.return_value = MagicMock(width=10, height=10)
        ctx = MagicMock()
        ctx.get_cairo_context.return_value = cr
        ctx.get_width.return_value = 800
        ctx.get_height.return_value = 600

        with patch("cm2016.export.printer._draw_print_chart") as mock_draw:
            _on_draw_page(MagicMock(), ctx, 0, records, "Slot 1")
            assert mock_draw.call_count == 2


@pytest.mark.skipif(not GTK_AVAILABLE, reason="GTK 4 not available")
class TestPrintReport:
    """Test the print_report entry point."""

    def test_empty_records_noop(self) -> None:
        with patch("cm2016.export.printer.Gtk.PrintOperation") as mock_op:
            print_report(MagicMock(), [], "Slot 1")
            mock_op.assert_not_called()
