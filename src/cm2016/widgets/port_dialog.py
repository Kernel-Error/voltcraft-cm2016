"""Serial port selection dialog for CM2016."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk

from cm2016.i18n import _
from cm2016.serial_reader import scan_ports_detailed

if TYPE_CHECKING:
    from collections.abc import Callable


class PortDialog(Adw.Dialog):
    """Dialog for selecting a serial port.

    Shows a dropdown of available USB serial ports with a refresh button.
    Calls ``on_port_selected`` with the chosen device path when confirmed.
    """

    def __init__(self, on_port_selected: Callable[[str], None]) -> None:
        super().__init__()
        self.set_title(_("Select COM-Port"))
        self.set_content_width(400)
        self.set_content_height(200)

        self._on_port_selected = on_port_selected
        self._ports: list[tuple[str, str]] = []

        # Main layout
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        # Label
        label = Gtk.Label(label=_("COM-Port"))
        label.set_halign(Gtk.Align.START)
        label.add_css_class("title-4")
        box.append(label)

        # Port dropdown row
        port_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self._dropdown = Gtk.DropDown()
        self._dropdown.set_hexpand(True)
        port_row.append(self._dropdown)

        refresh_btn = Gtk.Button(label=_("Refresh"))
        refresh_btn.connect("clicked", self._on_refresh)
        port_row.append(refresh_btn)

        box.append(port_row)

        # Button row
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END)
        btn_row.set_margin_top(12)

        cancel_btn = Gtk.Button(label=_("Cancel"))
        cancel_btn.connect("clicked", lambda _b: self.close())
        btn_row.append(cancel_btn)

        ok_btn = Gtk.Button(label=_("OK"))
        ok_btn.add_css_class("suggested-action")
        ok_btn.connect("clicked", self._on_ok)
        btn_row.append(ok_btn)

        box.append(btn_row)

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        header.set_show_start_title_buttons(False)
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(box)

        self.set_child(toolbar_view)

        # Initial scan
        self._refresh_ports()

    def _refresh_ports(self) -> None:
        """Scan for available serial ports and populate the dropdown."""
        self._ports = scan_ports_detailed()

        if self._ports:
            labels = [f"{desc} ({dev})" for dev, desc in self._ports]
        else:
            labels = [_("No ports found")]

        string_list = Gtk.StringList.new(labels)
        self._dropdown.set_model(string_list)

    def _on_refresh(self, _button: Gtk.Button) -> None:
        self._refresh_ports()

    def _on_ok(self, _button: Gtk.Button) -> None:
        if not self._ports:
            self.close()
            return

        selected = self._dropdown.get_selected()
        if 0 <= selected < len(self._ports):
            device_path = self._ports[selected][0]
            self._on_port_selected(device_path)

        self.close()
