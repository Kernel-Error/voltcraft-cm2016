"""Print support for CM2016 measurement reports.

Renders a DIN A4/A3 landscape report with slot summary header,
data overview, and voltage/current charts using Cairo.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
import cairo as _cairo
from gi.repository import Gtk

from cm2016.i18n import _

if TYPE_CHECKING:
    from cm2016.session import SlotRecord

logger = __import__("logging").getLogger(__name__)

# Page margins in points (72 dpi)
MARGIN = 36  # 0.5 inch


def print_report(
    parent: Gtk.Window,
    records: list[SlotRecord],
    slot_name: str,
) -> None:
    """Launch the print dialog for a measurement report.

    Args:
        parent: Parent window for the dialog.
        records: Data records to print.
        slot_name: Name of the slot (e.g., "Slot 1").
    """
    if not records:
        return

    op = Gtk.PrintOperation()
    op.set_n_pages(1)
    op.set_job_name(f"CM2016 - {slot_name}")

    # Default to landscape A4
    page_setup = Gtk.PageSetup()
    page_setup.set_orientation(Gtk.PageOrientation.LANDSCAPE)
    op.set_default_page_setup(page_setup)

    op.connect("draw-page", _on_draw_page, records, slot_name)
    op.run(Gtk.PrintOperationAction.PRINT_DIALOG, parent)


def _on_draw_page(
    _op: Gtk.PrintOperation,
    context: Gtk.PrintContext,
    _page_nr: int,
    records: list[SlotRecord],
    slot_name: str,
) -> None:
    """Draw the report page."""
    cr = context.get_cairo_context()
    page_w = context.get_width()
    page_h = context.get_height()

    x = MARGIN
    y = MARGIN
    w = page_w - 2 * MARGIN
    h = page_h - 2 * MARGIN

    # --- Title ---
    cr.set_source_rgb(0, 0, 0)
    cr.select_font_face("Sans", _cairo.FONT_SLANT_NORMAL, _cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(14)

    last = records[-1]
    title = (
        f"CM2016 - {slot_name} | "
        f"{_('Time')}: {last.runtime_formatted} | "
        f"C-CAP: {last.charge_capacity:.2f} mAh | "
        f"D-CAP: {last.discharge_capacity:.2f} mAh"
    )
    cr.move_to(x, y + 14)
    cr.show_text(title)
    y += 28

    # --- Separator ---
    cr.set_line_width(0.5)
    cr.move_to(x, y)
    cr.line_to(x + w, y)
    cr.stroke()
    y += 8

    # --- Charts ---
    chart_h = (h - 36) / 2  # Two charts, split vertically

    _draw_print_chart(
        cr,
        x,
        y,
        w,
        chart_h - 10,
        records,
        [r.voltage for r in records],
        _("Voltage [V]"),
        "{:.3f}",
    )
    y += chart_h

    _draw_print_chart(
        cr,
        x,
        y,
        w,
        chart_h - 10,
        records,
        [r.current for r in records],
        _("Current [A]"),
        "{:.3f}",
    )


def _draw_print_chart(
    cr: _cairo.Context,  # type: ignore[name-defined]
    px: float,
    py: float,
    pw: float,
    ph: float,
    records: list[SlotRecord],
    values: list[float],
    y_label: str,
    y_format: str,
) -> None:
    """Draw a single chart on the print context."""
    if not records or not values:
        return

    chart_left = px + 50
    chart_top = py + 10
    chart_w = pw - 60
    chart_h = ph - 30

    if chart_w < 20 or chart_h < 20:
        return

    # Compute ranges
    t0 = records[0].timestamp
    times = [(r.timestamp - t0).total_seconds() for r in records]
    t_min, t_max = min(times), max(times)
    if t_max - t_min < 1:
        t_max = t_min + 1
    v_min, v_max = min(values), max(values)
    if v_min == v_max:
        v_min -= 0.1
        v_max += 0.1
    v_range_val = v_max - v_min
    v_min -= v_range_val * 0.05
    v_max += v_range_val * 0.05
    if v_min < 0:
        v_min = 0

    t_range = t_max - t_min
    v_range = v_max - v_min

    # Axes
    cr.set_source_rgb(0, 0, 0)
    cr.set_line_width(0.5)
    cr.rectangle(chart_left, chart_top, chart_w, chart_h)
    cr.stroke()

    # Y label
    cr.select_font_face("Sans", _cairo.FONT_SLANT_NORMAL, _cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(8)
    cr.save()
    ext = cr.text_extents(y_label)
    cr.move_to(px + 8, chart_top + (chart_h + ext.width) / 2)
    cr.rotate(-math.pi / 2)
    cr.show_text(y_label)
    cr.restore()

    # Y ticks
    for i in range(6):
        val = v_min + (v_max - v_min) * i / 5
        y = chart_top + chart_h - (val - v_min) / v_range * chart_h
        label = y_format.format(val)
        ext = cr.text_extents(label)
        cr.move_to(chart_left - ext.width - 3, y + ext.height / 2)
        cr.show_text(label)

    # Draw data
    cr.set_line_width(0.8)
    prev_x: float | None = None
    prev_y: float | None = None

    for i, record in enumerate(records):
        elapsed = times[i]
        dx = chart_left + (elapsed - t_min) / t_range * chart_w
        dy = chart_top + chart_h - (values[i] - v_min) / v_range * chart_h

        if record.status in ("Charge", "Trickle"):
            cr.set_source_rgb(0.30, 0.60, 0.02)
        elif record.status == "Discharge":
            cr.set_source_rgb(0.80, 0.00, 0.00)
        else:
            cr.set_source_rgb(0.50, 0.50, 0.50)

        if prev_x is not None and prev_y is not None:
            cr.move_to(prev_x, prev_y)
            cr.line_to(dx, dy)
            cr.stroke()

        prev_x = dx
        prev_y = dy
