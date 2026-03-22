"""Cairo-based chart widgets for CM2016 voltage and current graphs.

Renders line charts with time on the X-axis and voltage/current on the
Y-axis. Charging segments are drawn in green, discharging in red, and
missing data points (gaps) as gray dots.
"""

from __future__ import annotations

import math
from enum import IntEnum
from typing import TYPE_CHECKING, ClassVar

import gi

gi.require_version("Gtk", "4.0")
import cairo as _cairo
from gi.repository import Gtk

from cm2016.i18n import _

if TYPE_CHECKING:
    from cm2016.session import SlotRecord

# Chart colors
COLOR_CHARGE = (0.30, 0.60, 0.02)  # Green (#4e9a06)
COLOR_DISCHARGE = (0.80, 0.00, 0.00)  # Red (#cc0000)
COLOR_GAP = (0.50, 0.50, 0.50)  # Gray
COLOR_GRID = (0.40, 0.40, 0.40)  # Grid lines
COLOR_AXIS = (0.70, 0.70, 0.70)  # Axis labels
COLOR_BG = (0.12, 0.12, 0.14)  # Background
COLOR_FINAL_V = (1.00, 1.00, 0.30)  # Yellow for final voltage annotation

# Chart margins (pixels)
MARGIN_LEFT = 60
MARGIN_RIGHT = 15
MARGIN_TOP = 30
MARGIN_BOTTOM = 35


class ChartStyle(IntEnum):
    """Available chart rendering styles."""

    LINES = 0
    BAR = 1


class ChartWidget(Gtk.DrawingArea):
    """Single chart drawing area for voltage or current vs time.

    The chart auto-scales to the data range with padding. Time axis
    shows elapsed time in HH:MM format.
    """

    def __init__(self, title: str, y_label: str, y_format: str = "{:.3f}") -> None:
        super().__init__()
        self._title = title
        self._y_label = y_label
        self._y_format = y_format
        self._records: list[SlotRecord] = []
        self._style = ChartStyle.LINES

        # Viewport: None = auto-fit to data
        self._view_t_min: float | None = None
        self._view_t_max: float | None = None
        self._view_v_min: float | None = None
        self._view_v_max: float | None = None
        self._zoom_stack: list[tuple[float, float, float, float]] = []

        # Drag-zoom state
        self._drag_start: tuple[float, float] | None = None
        self._drag_end: tuple[float, float] | None = None

        # Last computed plot geometry (for coordinate mapping)
        self._plot_geom: tuple[int, int, int, int] = (0, 0, 1, 1)
        self._data_range: tuple[float, float, float, float] = (0, 1, 0, 1)

        self.set_draw_func(self._draw)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_focusable(True)

        # --- Gesture controllers ---
        # Drag for rectangle zoom
        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.add_controller(drag)

        # Right-click for context menu / tooltip
        click = Gtk.GestureClick(button=3)
        click.connect("released", self._on_right_click)
        self.add_controller(click)

        # Scroll wheel zoom
        scroll = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.VERTICAL,
        )
        scroll.connect("scroll", self._on_scroll)
        self.add_controller(scroll)

        # Keyboard navigation
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key)

        # Context menu
        from gi.repository import Gio

        menu = Gio.Menu()
        menu.append(_("Zoom In"), "chart.zoom-in")
        menu.append(_("Reset Zoom"), "chart.reset-zoom")

        action_group = Gio.SimpleActionGroup()
        zoom_in_action = Gio.SimpleAction(name="zoom-in")
        zoom_in_action.connect("activate", lambda *_: self._zoom_in_center())
        action_group.add_action(zoom_in_action)
        reset_action = Gio.SimpleAction(name="reset-zoom")
        reset_action.connect("activate", lambda *_: self.reset_zoom())
        action_group.add_action(reset_action)
        self.insert_action_group("chart", action_group)

        self._context_menu = Gtk.PopoverMenu(menu_model=menu)
        self._context_menu.set_parent(self)

        # Tooltip popover
        self._tooltip = Gtk.Popover()
        self._tooltip.set_parent(self)
        self._tooltip.set_autohide(True)
        tooltip_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        tooltip_box.set_margin_start(8)
        tooltip_box.set_margin_end(8)
        tooltip_box.set_margin_top(4)
        tooltip_box.set_margin_bottom(4)
        self._tooltip_labels: dict[str, Gtk.Label] = {}
        for field in ("mode", "voltage", "current", "time"):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            name_lbl = Gtk.Label()
            name_lbl.add_css_class("dim-label")
            val_lbl = Gtk.Label()
            row.append(name_lbl)
            row.append(val_lbl)
            tooltip_box.append(row)
            self._tooltip_labels[f"{field}_name"] = name_lbl
            self._tooltip_labels[f"{field}_val"] = val_lbl
        self._tooltip_labels["mode_name"].set_text(_("Actual Mode:"))
        self._tooltip_labels["voltage_name"].set_text(_("Voltage:"))
        self._tooltip_labels["current_name"].set_text(_("Current:"))
        self._tooltip_labels["time_name"].set_text(_("Time:"))
        self._tooltip.set_child(tooltip_box)

    def set_style(self, style: ChartStyle) -> None:
        """Set the chart rendering style."""
        self._style = style
        self.queue_draw()

    def set_data(self, records: list[SlotRecord]) -> None:
        """Set the data to display and trigger a redraw."""
        self._records = records
        self.queue_draw()

    def clear(self) -> None:
        """Clear all data."""
        self._records = []
        self.reset_zoom()

    def reset_zoom(self) -> None:
        """Reset viewport to auto-fit all data."""
        self._view_t_min = None
        self._view_t_max = None
        self._view_v_min = None
        self._view_v_max = None
        self._zoom_stack.clear()
        self.queue_draw()

    def zoom_undo(self) -> None:
        """Undo the last zoom step."""
        if self._zoom_stack:
            t0, t1, v0, v1 = self._zoom_stack.pop()
            self._view_t_min = t0
            self._view_t_max = t1
            self._view_v_min = v0
            self._view_v_max = v1
            self.queue_draw()
        else:
            self.reset_zoom()

    @property
    def is_zoomed(self) -> bool:
        """Whether the chart is currently zoomed in."""
        return self._view_t_min is not None

    def _draw(self, _area: Gtk.DrawingArea, cr: _cairo.Context, width: int, height: int) -> None:
        """Draw the chart on the Cairo context."""
        # Background
        cr.set_source_rgb(*COLOR_BG)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        plot_x = MARGIN_LEFT
        plot_y = MARGIN_TOP
        plot_w = width - MARGIN_LEFT - MARGIN_RIGHT
        plot_h = height - MARGIN_TOP - MARGIN_BOTTOM

        if plot_w < 20 or plot_h < 20:
            return

        # Draw title
        cr.set_source_rgb(*COLOR_AXIS)
        cr.select_font_face("Sans", _cairo.FONT_SLANT_NORMAL, _cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(12)
        title_ext = cr.text_extents(self._title)
        cr.move_to(plot_x + (plot_w - title_ext.width) / 2, 18)
        cr.show_text(self._title)

        if not self._records:
            cr.set_source_rgb(*COLOR_AXIS)
            cr.select_font_face("Sans", _cairo.FONT_SLANT_NORMAL, _cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(11)
            no_data = _("No data")
            ext = cr.text_extents(no_data)
            cr.move_to(plot_x + (plot_w - ext.width) / 2, plot_y + plot_h / 2)
            cr.show_text(no_data)
            return

        # Compute data ranges using elapsed seconds from first record
        t0 = self._records[0].timestamp
        times = [(r.timestamp - t0).total_seconds() for r in self._records]
        values = self._get_values()

        t_min, t_max = min(times), max(times)
        if t_max - t_min < 1.0:
            t_min -= 1
            t_max += 1

        v_min, v_max = min(values), max(values)
        if v_min == v_max:
            v_min -= 0.1
            v_max += 0.1

        # Y-axis range depends on chart style
        if self._style == ChartStyle.BAR:
            # Bar charts start at 0 so bar height represents absolute value
            v_min = 0
            v_max *= 1.05  # 5% headroom
        else:
            # Line charts: tight range with 5% padding
            v_range = v_max - v_min
            v_min -= v_range * 0.05
            v_max += v_range * 0.05
            if v_min < 0:
                v_min = 0

        # Apply viewport override (zoom)
        if self._view_t_min is not None:
            t_min = self._view_t_min
            t_max = self._view_t_max if self._view_t_max is not None else t_max
            v_min = self._view_v_min if self._view_v_min is not None else v_min
            v_max = self._view_v_max if self._view_v_max is not None else v_max

        # Safety clamp: ensure ranges are never zero after viewport override
        if t_max <= t_min:
            mid = (t_min + t_max) / 2
            t_min = mid - 1.0
            t_max = mid + 1.0
        if v_max <= v_min:
            mid = (v_min + v_max) / 2
            v_min = mid - 0.1
            v_max = mid + 0.1

        # Store geometry for coordinate mapping
        self._plot_geom = (plot_x, plot_y, plot_w, plot_h)
        self._data_range = (t_min, t_max, v_min, v_max)

        # Draw grid and axes
        self._draw_grid(cr, plot_x, plot_y, plot_w, plot_h, t_min, t_max, v_min, v_max)

        # Clip drawing to plot area
        cr.save()
        cr.rectangle(plot_x, plot_y, plot_w, plot_h)
        cr.clip()

        # Draw data using selected style
        args = (cr, plot_x, plot_y, plot_w, plot_h, t_min, t_max, v_min, v_max, values)
        if self._style == ChartStyle.BAR:
            self._draw_bars(*args)
        else:
            self._draw_lines(*args)

        cr.restore()  # Remove clip

        # Drag selection rectangle
        if self._drag_start and self._drag_end:
            x0, y0 = self._drag_start
            x1, y1 = self._drag_end
            rx = min(x0, x1)
            ry = min(y0, y1)
            rw = abs(x1 - x0)
            rh = abs(y1 - y0)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.2)
            cr.rectangle(rx, ry, rw, rh)
            cr.fill()
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.6)
            cr.set_line_width(1)
            cr.rectangle(rx, ry, rw, rh)
            cr.stroke()

        # Final voltage annotation
        self._draw_final_voltage(
            cr, plot_x, plot_y, plot_w, plot_h, t_min, t_max, v_min, v_max, values
        )

    def _get_values(self) -> list[float]:
        """Override in subclass to return the Y-axis values."""
        return [0.0] * len(self._records)

    def _draw_grid(
        self,
        cr: _cairo.Context,
        px: int,
        py: int,
        pw: int,
        ph: int,
        t_min: float,
        t_max: float,
        v_min: float,
        v_max: float,
    ) -> None:
        """Draw grid lines, axis labels, and ticks."""
        cr.set_line_width(0.5)
        cr.select_font_face("Sans", _cairo.FONT_SLANT_NORMAL, _cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(9)

        # Y-axis grid lines and labels
        y_ticks = _nice_ticks(v_min, v_max, 5)
        for val in y_ticks:
            y = py + ph - (val - v_min) / (v_max - v_min) * ph
            if y < py or y > py + ph:
                continue

            cr.set_source_rgb(*COLOR_GRID)
            cr.set_dash([2, 4])
            cr.move_to(px, y)
            cr.line_to(px + pw, y)
            cr.stroke()
            cr.set_dash([])

            label = self._y_format.format(val)
            cr.set_source_rgb(*COLOR_AXIS)
            ext = cr.text_extents(label)
            cr.move_to(px - ext.width - 5, y + ext.height / 2)
            cr.show_text(label)

        # X-axis grid lines and labels (elapsed time)
        x_ticks = _nice_ticks(t_min, t_max, 6)
        for val in x_ticks:
            x = px + (val - t_min) / (t_max - t_min) * pw
            if x < px or x > px + pw:
                continue

            cr.set_source_rgb(*COLOR_GRID)
            cr.set_dash([2, 4])
            cr.move_to(x, py)
            cr.line_to(x, py + ph)
            cr.stroke()
            cr.set_dash([])

            label = _format_elapsed(val)
            cr.set_source_rgb(*COLOR_AXIS)
            ext = cr.text_extents(label)
            cr.move_to(x - ext.width / 2, py + ph + ext.height + 5)
            cr.show_text(label)

        # Y-axis label
        cr.save()
        cr.set_source_rgb(*COLOR_AXIS)
        cr.set_font_size(10)
        ext = cr.text_extents(self._y_label)
        cr.move_to(12, py + (ph + ext.width) / 2)
        cr.rotate(-math.pi / 2)
        cr.show_text(self._y_label)
        cr.restore()

        # X-axis label
        time_label = _("Time")
        cr.set_source_rgb(*COLOR_AXIS)
        cr.set_font_size(10)
        ext = cr.text_extents(time_label)
        cr.move_to(px + (pw - ext.width) / 2, py + ph + 30)
        cr.show_text(time_label)

        # Plot area border
        cr.set_source_rgb(*COLOR_GRID)
        cr.set_line_width(1)
        cr.rectangle(px, py, pw, ph)
        cr.stroke()

    def _draw_lines(
        self,
        cr: _cairo.Context,
        px: int,
        py: int,
        pw: int,
        ph: int,
        t_min: float,
        t_max: float,
        v_min: float,
        v_max: float,
        values: list[float],
    ) -> None:
        """Draw data points with charge/discharge color coding."""
        cr.set_line_width(1.5)

        t_range = t_max - t_min
        v_range = v_max - v_min
        t0 = self._records[0].timestamp

        prev_x: float | None = None
        prev_y: float | None = None
        prev_seconds: float = 0.0

        for i, record in enumerate(self._records):
            elapsed = (record.timestamp - t0).total_seconds()
            x = px + (elapsed - t_min) / t_range * pw
            y = py + ph - (values[i] - v_min) / v_range * ph

            status = record.status

            # Pick color based on status
            if status in ("Charge", "Trickle"):
                color = COLOR_CHARGE
            elif status == "Discharge":
                color = COLOR_DISCHARGE
            else:
                color = COLOR_GAP

            if prev_x is not None and prev_y is not None:
                # Check for time gap (>30 seconds between points = gap)
                time_diff = elapsed - prev_seconds

                if time_diff > 30:
                    # Draw gap dot
                    cr.set_source_rgb(*COLOR_GAP)
                    cr.arc(x, y, 2, 0, 2 * math.pi)
                    cr.fill()
                else:
                    # Draw line segment
                    cr.set_source_rgb(*color)
                    cr.move_to(prev_x, prev_y)
                    cr.line_to(x, y)
                    cr.stroke()
            else:
                # First point — draw a dot
                cr.set_source_rgb(*color)
                cr.arc(x, y, 2, 0, 2 * math.pi)
                cr.fill()

            prev_x = x
            prev_y = y
            prev_seconds = elapsed

    def _draw_bars(
        self,
        cr: _cairo.Context,
        px: int,
        py: int,
        pw: int,
        ph: int,
        t_min: float,
        t_max: float,
        v_min: float,
        v_max: float,
        values: list[float],
    ) -> None:
        """Draw vertical bar chart with charge/discharge color coding."""
        if not self._records:
            return

        t_range = t_max - t_min
        v_range = v_max - v_min
        t0 = self._records[0].timestamp

        n = len(self._records)
        bar_width = max(pw / max(n, 1) * 0.8, 1)

        for i, record in enumerate(self._records):
            elapsed = (record.timestamp - t0).total_seconds()
            x = px + (elapsed - t_min) / t_range * pw
            y = py + ph - (values[i] - v_min) / v_range * ph
            bar_h = py + ph - y

            status = record.status
            if status in ("Charge", "Trickle"):
                color = COLOR_CHARGE
            elif status == "Discharge":
                color = COLOR_DISCHARGE
            else:
                color = COLOR_GAP

            cr.set_source_rgb(*color)
            cr.rectangle(x - bar_width / 2, y, bar_width, bar_h)
            cr.fill()

    def _draw_final_voltage(
        self,
        cr: _cairo.Context,
        px: int,
        py: int,
        pw: int,
        ph: int,
        t_min: float,
        t_max: float,
        v_min: float,
        v_max: float,
        values: list[float],
    ) -> None:
        """Draw final voltage annotation when a slot program has completed."""
        if not self._records or not values:
            return

        last = self._records[-1]
        # Check if program finished: slot inactive and was previously active
        if last.status in ("Ready", "Idle") and len(self._records) > 1:
            prev = self._records[-2]
            if prev.status not in ("Ready", "Idle", "Empty"):
                # Draw annotation at the last data point
                t0 = self._records[0].timestamp
                elapsed = (last.timestamp - t0).total_seconds()
                x = px + (elapsed - t_min) / (t_max - t_min) * pw
                y = py + ph - (values[-1] - v_min) / (v_max - v_min) * ph

                label = self._y_format.format(values[-1])
                cr.set_source_rgb(*COLOR_FINAL_V)
                cr.select_font_face("Sans", _cairo.FONT_SLANT_NORMAL, _cairo.FONT_WEIGHT_BOLD)
                cr.set_font_size(10)
                ext = cr.text_extents(label)
                cr.move_to(x - ext.width - 5, y - 5)
                cr.show_text(label)

                # Small marker
                cr.arc(x, y, 3, 0, 2 * math.pi)
                cr.fill()

    # --- Coordinate mapping ---

    def _pixel_to_data(self, px_x: float, px_y: float) -> tuple[float, float]:
        """Convert pixel coordinates to data coordinates."""
        plot_x, plot_y, plot_w, plot_h = self._plot_geom
        t_min, t_max, v_min, v_max = self._data_range
        t = t_min + (px_x - plot_x) / max(plot_w, 1) * (t_max - t_min)
        v = v_max - (px_y - plot_y) / max(plot_h, 1) * (v_max - v_min)
        return t, v

    def _find_nearest_record(self, px_x: float, px_y: float) -> SlotRecord | None:
        """Find the record nearest to the given pixel coordinates."""
        if not self._records:
            return None

        plot_x, _, plot_w, _ = self._plot_geom
        t_min, t_max, _, _ = self._data_range
        t_range = t_max - t_min
        t0 = self._records[0].timestamp

        best_dist = float("inf")
        best_record: SlotRecord | None = None

        for record in self._records:
            elapsed = (record.timestamp - t0).total_seconds()
            rx = plot_x + (elapsed - t_min) / max(t_range, 1) * plot_w
            dist = abs(rx - px_x)
            if dist < best_dist:
                best_dist = dist
                best_record = record

        # Only match if within 20 pixels
        if best_dist > 20:
            return None
        return best_record

    # --- Drag zoom ---

    def _on_drag_begin(self, _gesture: Gtk.GestureDrag, x: float, y: float) -> None:
        self._drag_start = (x, y)
        self._drag_end = None

    def _on_drag_update(self, _gesture: Gtk.GestureDrag, dx: float, dy: float) -> None:
        if self._drag_start:
            self._drag_end = (self._drag_start[0] + dx, self._drag_start[1] + dy)
            self.queue_draw()

    def _on_drag_end(self, _gesture: Gtk.GestureDrag, dx: float, dy: float) -> None:
        if not self._drag_start:
            return

        x0, y0 = self._drag_start
        x1, y1 = x0 + dx, y0 + dy

        # Minimum drag size to count as a zoom (not a click)
        if abs(dx) > 5 and abs(dy) > 5:
            self._push_zoom()
            t0, v0 = self._pixel_to_data(min(x0, x1), min(y0, y1))
            t1, v1 = self._pixel_to_data(max(x0, x1), max(y0, y1))
            self._view_t_min = t0
            self._view_t_max = t1
            self._view_v_min = v1  # Note: v is inverted (top=max)
            self._view_v_max = v0

        self._drag_start = None
        self._drag_end = None
        self.queue_draw()

    # --- Right-click: context menu or tooltip ---

    def _on_right_click(self, _gesture: Gtk.GestureClick, _n: int, x: float, y: float) -> None:
        from gi.repository import Gdk

        record = self._find_nearest_record(x, y)
        if record:
            self._show_tooltip(record, x, y)
        else:
            rect = Gdk.Rectangle()
            rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
            self._context_menu.set_pointing_to(rect)
            self._context_menu.popup()

    def _show_tooltip(self, record: SlotRecord, x: float, y: float) -> None:
        from gi.repository import Gdk

        self._tooltip_labels["mode_val"].set_text(record.status)
        self._tooltip_labels["voltage_val"].set_text(f"{record.voltage:.3f} V")
        self._tooltip_labels["current_val"].set_text(f"{record.current:.3f} A")
        self._tooltip_labels["time_val"].set_text(record.runtime_formatted)

        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self._tooltip.set_pointing_to(rect)
        self._tooltip.popup()

    # --- Scroll wheel zoom ---

    def _on_scroll(self, _controller: Gtk.EventControllerScroll, _dx: float, dy: float) -> bool:
        if dy < 0:
            self._zoom_at_cursor(0.8)  # Zoom in
        elif dy > 0:
            self._zoom_at_cursor(1.25)  # Zoom out
        return True

    def _zoom_at_cursor(self, factor: float) -> None:
        """Zoom centered on the current viewport center."""
        t_min, t_max, v_min, v_max = self._data_range
        t_center = (t_min + t_max) / 2
        v_center = (v_min + v_max) / 2
        t_half = (t_max - t_min) / 2 * factor
        v_half = (v_max - v_min) / 2 * factor

        # Prevent degenerate zoom from collapsing the viewport
        if t_half < 1e-6:
            t_half = 1.0
        if v_half < 1e-9:
            v_half = 0.1

        self._push_zoom()
        self._view_t_min = t_center - t_half
        self._view_t_max = t_center + t_half
        self._view_v_min = v_center - v_half
        self._view_v_max = v_center + v_half
        self.queue_draw()

    def _zoom_in_center(self) -> None:
        """Zoom in 2x centered on viewport."""
        self._zoom_at_cursor(0.5)

    # --- Keyboard navigation ---

    def _on_key_pressed(
        self, _ctrl: Gtk.EventControllerKey, keyval: int, _code: int, _state: int
    ) -> bool:
        from gi.repository import Gdk

        t_min, t_max, v_min, v_max = self._data_range
        t_span = t_max - t_min
        step = t_span * 0.1
        big_step = t_span * 0.5

        if keyval == Gdk.KEY_Home:
            self.reset_zoom()
            return True
        if keyval == Gdk.KEY_Delete:
            # Jump to start of data
            if self._records:
                self._pan_to_start()
            return True
        if keyval == Gdk.KEY_End:
            if self._records:
                self._pan_to_end()
            return True
        if keyval == Gdk.KEY_BackSpace:
            self.zoom_undo()
            return True
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Right):
            dt = -step if keyval == Gdk.KEY_Left else step
            self._pan(dt, 0)
            return True
        if keyval in (Gdk.KEY_Up, Gdk.KEY_Down):
            dv_step = (v_max - v_min) * 0.1
            dv = dv_step if keyval == Gdk.KEY_Up else -dv_step
            self._pan(0, dv)
            return True
        if keyval == Gdk.KEY_Page_Up:
            self._pan(big_step, 0)
            return True
        if keyval == Gdk.KEY_Page_Down:
            self._pan(-big_step, 0)
            return True
        return False

    def _pan(self, dt: float, dv: float) -> None:
        """Pan the viewport by dt seconds and dv units."""
        t_min, t_max, v_min, v_max = self._data_range
        if not self.is_zoomed:
            self._view_t_min = t_min
            self._view_t_max = t_max
            self._view_v_min = v_min
            self._view_v_max = v_max
        self._view_t_min = (self._view_t_min if self._view_t_min is not None else t_min) + dt
        self._view_t_max = (self._view_t_max if self._view_t_max is not None else t_max) + dt
        self._view_v_min = (self._view_v_min if self._view_v_min is not None else v_min) + dv
        self._view_v_max = (self._view_v_max if self._view_v_max is not None else v_max) + dv
        self.queue_draw()

    def _pan_to_start(self) -> None:
        """Pan so the viewport starts at the first data point."""
        t_min, t_max, _, _ = self._data_range
        span = (self._view_t_max if self._view_t_max is not None else t_max) - (
            self._view_t_min if self._view_t_min is not None else t_min
        )
        self._view_t_min = 0
        self._view_t_max = span
        self.queue_draw()

    def _pan_to_end(self) -> None:
        """Pan so the viewport ends at the last data point."""
        if not self._records:
            return
        t0 = self._records[0].timestamp
        end = (self._records[-1].timestamp - t0).total_seconds()
        t_min, t_max, _, _ = self._data_range
        span = (self._view_t_max if self._view_t_max is not None else t_max) - (
            self._view_t_min if self._view_t_min is not None else t_min
        )
        self._view_t_min = end - span
        self._view_t_max = end
        self.queue_draw()

    def _push_zoom(self) -> None:
        """Save the current viewport to the zoom stack."""
        t_min, t_max, v_min, v_max = self._data_range
        self._zoom_stack.append(
            (
                self._view_t_min if self._view_t_min is not None else t_min,
                self._view_t_max if self._view_t_max is not None else t_max,
                self._view_v_min if self._view_v_min is not None else v_min,
                self._view_v_max if self._view_v_max is not None else v_max,
            )
        )


class VoltageChart(ChartWidget):
    """Chart showing voltage over time."""

    def __init__(self) -> None:
        super().__init__(
            title=_("Voltage"),
            y_label=_("Voltage [V]"),
            y_format="{:.3f}",
        )

    def _get_values(self) -> list[float]:
        return [r.voltage for r in self._records]


class CurrentChart(ChartWidget):
    """Chart showing current over time."""

    def __init__(self) -> None:
        super().__init__(
            title=_("Current"),
            y_label=_("Current [A]"),
            y_format="{:.3f}",
        )

    def _get_values(self) -> list[float]:
        return [r.current for r in self._records]


class ChartPair(Gtk.Box):
    """Voltage + current charts with a time window toolbar.

    Default view shows the last 5 minutes. The user can adjust the
    visible window with +/- buttons or a slider.
    """

    # Available time window presets in minutes
    WINDOW_PRESETS: ClassVar[list[int]] = [1, 2, 5, 10, 20, 30, 60, 120, 0]  # 0 = "All"
    DEFAULT_WINDOW = 5  # minutes

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._all_records: list[SlotRecord] = []
        self._window_minutes = self.DEFAULT_WINDOW

        # Time window toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        toolbar.set_margin_start(8)
        toolbar.set_margin_end(8)
        toolbar.set_margin_top(4)
        toolbar.set_margin_bottom(2)

        zoom_out_btn = Gtk.Button(label="+")
        zoom_out_btn.set_tooltip_text(_("Show more time"))
        zoom_out_btn.connect("clicked", self._on_zoom_out)
        toolbar.append(zoom_out_btn)

        self._window_label = Gtk.Label()
        self._window_label.set_hexpand(True)
        toolbar.append(self._window_label)

        zoom_in_btn = Gtk.Button(label="\u2212")  # Minus sign
        zoom_in_btn.set_tooltip_text(_("Show less time"))
        zoom_in_btn.connect("clicked", self._on_zoom_in)
        toolbar.append(zoom_in_btn)

        self.append(toolbar)

        # Chart style toolbar
        from cm2016.widgets.chart_toolbar import ChartToolbar

        self._style_toolbar = ChartToolbar()
        self._style_toolbar.on_style_changed = self._on_style_changed
        self.append(self._style_toolbar)

        # Charts
        self._voltage_chart = VoltageChart()
        self._current_chart = CurrentChart()

        self._voltage_chart.set_size_request(-1, 150)
        self._current_chart.set_size_request(-1, 150)

        self.append(self._voltage_chart)
        self.append(self._current_chart)

        self._update_window_label()

    def set_data(self, records: list[SlotRecord]) -> None:
        """Update both charts with new data, applying the time window."""
        self._all_records = records
        self._apply_window()

    def clear(self) -> None:
        """Clear both charts."""
        self._all_records = []
        self._voltage_chart.clear()
        self._current_chart.clear()

    def _on_style_changed(self, style: ChartStyle) -> None:
        self._voltage_chart.set_style(style)
        self._current_chart.set_style(style)

    def _apply_window(self) -> None:
        """Filter records to the time window and update charts."""
        if not self._all_records or self._window_minutes == 0:
            # 0 = show all
            filtered = self._all_records
        else:
            # Show last N minutes based on actual recording timestamps
            from datetime import timedelta

            latest = self._all_records[-1].timestamp
            cutoff = latest - timedelta(minutes=self._window_minutes)
            filtered = [r for r in self._all_records if r.timestamp >= cutoff]

        self._voltage_chart.set_data(filtered)
        self._current_chart.set_data(filtered)

    def _on_zoom_out(self, _button: Gtk.Button) -> None:
        """Show more time (wider window)."""
        idx = self._current_preset_index()
        if idx < len(self.WINDOW_PRESETS) - 1:
            self._window_minutes = self.WINDOW_PRESETS[idx + 1]
            self._update_window_label()
            self._apply_window()

    def _on_zoom_in(self, _button: Gtk.Button) -> None:
        """Show less time (narrower window)."""
        idx = self._current_preset_index()
        if idx > 0:
            self._window_minutes = self.WINDOW_PRESETS[idx - 1]
            self._update_window_label()
            self._apply_window()

    def _current_preset_index(self) -> int:
        """Find the current window in the presets list."""
        try:
            return self.WINDOW_PRESETS.index(self._window_minutes)
        except ValueError:
            # Find nearest preset
            for i, preset in enumerate(self.WINDOW_PRESETS):
                if preset >= self._window_minutes:
                    return i
            return len(self.WINDOW_PRESETS) - 1

    def _update_window_label(self) -> None:
        if self._window_minutes == 0:
            self._window_label.set_text(_("Time window: All"))
        elif self._window_minutes >= 60:
            hours = self._window_minutes // 60
            self._window_label.set_text(_("Time window: {h}h").format(h=hours))
        else:
            self._window_label.set_text(_("Time window: {m} min").format(m=self._window_minutes))


def _nice_ticks(lo: float, hi: float, target_count: int) -> list[float]:
    """Generate nicely rounded tick values for an axis range.

    Returns approximately ``target_count`` evenly spaced values that are
    round numbers (multiples of 1, 2, 5, 10, etc.).
    """
    if hi <= lo:
        return [lo]

    raw_step = (hi - lo) / max(target_count, 1)

    # Round step to a "nice" number
    magnitude = 10 ** math.floor(math.log10(max(raw_step, 1e-10)))
    residual = raw_step / magnitude

    if residual <= 1.5:
        nice_step = 1 * magnitude
    elif residual <= 3:
        nice_step = 2 * magnitude
    elif residual <= 7:
        nice_step = 5 * magnitude
    else:
        nice_step = 10 * magnitude

    # Avoid zero step
    if nice_step <= 0:
        return [lo, hi]

    start = math.ceil(lo / nice_step) * nice_step
    ticks = []
    val = start
    while val <= hi:
        ticks.append(round(val, 10))
        val += nice_step

    return ticks


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as a readable time label.

    < 60s:    "30s"
    < 3600s:  "5:30" (M:SS)
    >= 3600s: "1:05:30" (H:MM:SS)
    """
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    minutes = total // 60
    secs = total % 60
    if minutes < 60:
        return f"{minutes}:{secs:02d}"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}:{mins:02d}:{secs:02d}"
