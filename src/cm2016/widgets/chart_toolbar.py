"""Chart style selector for CM2016."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from cm2016.i18n import _
from cm2016.widgets.chart_widget import ChartStyle

if TYPE_CHECKING:
    from collections.abc import Callable


class ChartToolbar(Gtk.Box):
    """Toolbar with chart style selector (Lines / Bar)."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.set_margin_top(2)
        self.set_margin_bottom(2)

        self.on_style_changed: Callable[[ChartStyle], None] | None = None

        # Style radio buttons
        style_label = Gtk.Label(label=_("Style:"))
        self.append(style_label)

        self._btn_lines = Gtk.ToggleButton(label=_("Lines"))
        self._btn_bar = Gtk.ToggleButton(label=_("Bar"))

        self._btn_bar.set_group(self._btn_lines)
        self._btn_lines.set_active(True)

        self._btn_lines.connect("toggled", self._on_style_toggled, ChartStyle.LINES)
        self._btn_bar.connect("toggled", self._on_style_toggled, ChartStyle.BAR)

        self.append(self._btn_lines)
        self.append(self._btn_bar)

    def _on_style_toggled(self, button: Gtk.ToggleButton, style: ChartStyle) -> None:
        if not button.get_active():
            return
        if self.on_style_changed is not None:
            self.on_style_changed(style)
