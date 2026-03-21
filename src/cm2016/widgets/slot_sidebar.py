"""Sidebar containing 6 slot panels for CM2016."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from cm2016.protocol import SLOT_COUNT, Frame
from cm2016.widgets.slot_panel import SlotPanel

if TYPE_CHECKING:
    from collections.abc import Callable


class SlotSidebar(Gtk.Box):
    """Vertical stack of 6 SlotPanel widgets.

    Clicking a panel selects that slot for the table/chart view.
    """

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_size_request(280, -1)

        self._panels: list[SlotPanel] = []
        self._selected_index: int = 0
        self.on_slot_selected: Callable[[int], None] | None = None

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        inner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        for i in range(SLOT_COUNT):
            panel = SlotPanel(slot_index=i)

            # Wrap in a click gesture for slot selection
            click = Gtk.GestureClick()
            click.connect("released", self._on_panel_clicked, i)
            panel.add_controller(click)

            inner_box.append(panel)
            self._panels.append(panel)

        scrolled.set_child(inner_box)
        self.append(scrolled)

        # Highlight the initially selected slot
        self._update_selection()

    @property
    def selected_index(self) -> int:
        """Index of the currently selected slot (0-5)."""
        return self._selected_index

    def select_slot(self, index: int) -> None:
        """Programmatically select a slot."""
        if 0 <= index < SLOT_COUNT:
            self._selected_index = index
            self._update_selection()
            if self.on_slot_selected is not None:
                self.on_slot_selected(index)

    def update(self, frame: Frame) -> None:
        """Update all panels from a parsed frame."""
        chemistry = frame.header.chemistry.label
        for panel, slot in zip(self._panels, frame.slots, strict=True):
            panel.update(slot, chemistry)

    def set_recording(self, active: bool) -> None:
        """Toggle recording state on all panels."""
        for panel in self._panels:
            panel.set_recording(active)

    def clear_all(self) -> None:
        """Clear all panels."""
        for panel in self._panels:
            panel.clear()

    def clear_slot(self, slot_index: int) -> None:
        """Clear a single slot panel."""
        if 0 <= slot_index < len(self._panels):
            self._panels[slot_index].clear()

    def _on_panel_clicked(
        self,
        _gesture: Gtk.GestureClick,
        _n_press: int,
        _x: float,
        _y: float,
        index: int,
    ) -> None:
        self.select_slot(index)

    def _update_selection(self) -> None:
        """Update visual selection highlight."""
        for i, panel in enumerate(self._panels):
            if i == self._selected_index:
                panel.add_css_class("slot-panel-selected")
            else:
                panel.remove_css_class("slot-panel-selected")
