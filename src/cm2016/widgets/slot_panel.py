"""Single slot info panel widget for CM2016."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from cm2016.i18n import _
from cm2016.protocol import SLOT_NAMES, SlotData


class SlotPanel(Gtk.Box):
    """Displays live parameters for a single charging slot.

    Shows: Program, Actual, Chemistry, Time, C-CAP, D-CAP, Voltage, Current.
    Background changes from gray to green when recording is active.
    """

    def __init__(self, slot_index: int) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.slot_index = slot_index

        self.add_css_class("slot-panel")
        self.add_css_class("slot-panel-idle")

        self.set_margin_start(4)
        self.set_margin_end(4)
        self.set_margin_top(2)
        self.set_margin_bottom(2)

        # Slot title
        title = Gtk.Label(label=SLOT_NAMES[slot_index])
        title.add_css_class("slot-title")
        title.set_halign(Gtk.Align.CENTER)
        self.append(title)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(separator)

        # Parameter grid: 2 columns of label-value pairs
        grid = Gtk.Grid()
        grid.set_column_spacing(8)
        grid.set_row_spacing(1)
        grid.set_margin_start(4)
        grid.set_margin_end(4)
        grid.set_margin_top(2)
        grid.set_margin_bottom(2)

        # Left column: Program, Actual, Chemistry, Time
        # Right column: C-CAP, D-CAP, Voltage, Current
        self._labels: dict[str, Gtk.Label] = {}

        left_fields = [
            ("program", _("Program:")),
            ("actual", _("Actual:")),
            ("chemistry", _("Chemistry:")),
            ("time", _("Time:")),
        ]
        right_fields = [
            ("ccap", _("C-CAP:")),
            ("dcap", _("D-CAP:")),
            ("voltage", _("Voltage:")),
            ("current", _("Current:")),
        ]

        for row, (key, label_text) in enumerate(left_fields):
            lbl = Gtk.Label(label=label_text)
            lbl.set_halign(Gtk.Align.START)
            lbl.add_css_class("dim-label")
            lbl.add_css_class("caption")
            grid.attach(lbl, 0, row, 1, 1)

            val = Gtk.Label(label="")
            val.set_halign(Gtk.Align.START)
            val.add_css_class("caption")
            grid.attach(val, 1, row, 1, 1)
            self._labels[key] = val

        # Separator between columns
        vsep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        vsep.set_margin_start(4)
        vsep.set_margin_end(4)
        grid.attach(vsep, 2, 0, 1, 4)

        for row, (key, label_text) in enumerate(right_fields):
            lbl = Gtk.Label(label=label_text)
            lbl.set_halign(Gtk.Align.START)
            lbl.add_css_class("dim-label")
            lbl.add_css_class("caption")
            grid.attach(lbl, 3, row, 1, 1)

            val = Gtk.Label(label="")
            val.set_halign(Gtk.Align.START)
            val.add_css_class("caption")
            grid.attach(val, 4, row, 1, 1)
            self._labels[key] = val

        self.append(grid)

    def update(self, slot: SlotData, chemistry: str) -> None:
        """Update the panel with new slot data.

        Args:
            slot: Parsed slot data from a frame.
            chemistry: Battery chemistry string from frame header.
        """
        self._labels["program"].set_text(slot.program.label)
        self._labels["actual"].set_text(slot.status_label)
        self._labels["chemistry"].set_text(chemistry)
        self._labels["time"].set_text(slot.runtime_formatted)
        self._labels["ccap"].set_text(f"{slot.charge_capacity:.2f} mAh")
        self._labels["dcap"].set_text(f"{slot.discharge_capacity:.2f} mAh")
        self._labels["voltage"].set_text(f"{slot.voltage:.3f} V")
        self._labels["current"].set_text(f"{slot.current:.3f} A")

    def clear(self) -> None:
        """Reset all displayed values."""
        for label in self._labels.values():
            label.set_text("")

    def set_recording(self, active: bool) -> None:
        """Toggle the recording visual state (gray/green background)."""
        if active:
            self.remove_css_class("slot-panel-idle")
            self.add_css_class("slot-panel-recording")
        else:
            self.remove_css_class("slot-panel-recording")
            self.add_css_class("slot-panel-idle")
