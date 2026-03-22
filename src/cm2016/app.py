"""CM2016 GTK4 application entry point.

Provides the main Adw.Application and MainWindow that wires together
serial communication, slot panels, and data recording.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk

from cm2016.i18n import _, setup_i18n
from cm2016.serial_reader import SerialReader, detect_cm2016_port

if TYPE_CHECKING:
    from cm2016.protocol import Frame
    from cm2016.session import SlotRecord
from cm2016.export.csv_export import export_csv
from cm2016.export.excel_export import export_excel
from cm2016.export.printer import print_report
from cm2016.persistence.file_io import FILE_EXTENSION, load_session, save_session
from cm2016.persistence.temp_buffer import (
    TempBuffer,
    delete_recovery,
    has_recovery_data,
    load_recovery,
)
from cm2016.session import Session
from cm2016.widgets.chart_widget import ChartPair
from cm2016.widgets.data_table import DataTable
from cm2016.widgets.port_dialog import PortDialog
from cm2016.widgets.slot_sidebar import SlotSidebar

logger = logging.getLogger(__name__)

APP_ID = "com.kernelerror.cm2016"
CSS_PATH = Path(__file__).parent / "style.css"


class MainWindow(Adw.ApplicationWindow):
    """Main application window with sidebar and content area."""

    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app)
        self.set_title(_("Charge Manager CM 2016"))
        self.set_default_size(1024, 700)

        self._reader = SerialReader()
        self._reader.on_frame = self._on_frame_from_thread
        self._reader.on_connection_lost = self._on_connection_lost_from_thread

        self._session = Session()
        self._session.on_record_added = self._on_record_added
        self._session.on_slot_cleared = self._on_slot_cleared
        self._session.on_all_cleared = self._on_all_cleared

        self._recording = False
        self._port: str | None = None
        self._temp_buffer: TempBuffer | None = None
        self._inhibit_cookie: int = 0

        # --- Header bar ---
        header = Adw.HeaderBar()

        # File menu button (Save/Open)
        file_menu = Gio.Menu()
        file_menu.append(_("Save Logged Data") + "  Ctrl+S", "win.save")
        file_menu.append(_("Load Logged Data") + "  Ctrl+O", "win.open")

        file_btn = Gtk.MenuButton(label=_("File"))
        file_btn.set_menu_model(file_menu)
        header.pack_start(file_btn)

        # Port button
        self._port_btn = Gtk.Button(label=_("Port"))
        self._port_btn.set_tooltip_text(_("Select COM-Port"))
        self._port_btn.connect("clicked", self._on_port_clicked)
        header.pack_start(self._port_btn)

        # Start/Stop toggle
        self._toggle_btn = Gtk.ToggleButton(label=_("Start Logging"))
        self._toggle_btn.add_css_class("suggested-action")
        self._toggle_handler_id = self._toggle_btn.connect("toggled", self._on_toggle_logging)
        header.pack_start(self._toggle_btn)

        # Export menu (CSV / Excel)
        export_menu = Gio.Menu()
        export_menu.append(_("CSV"), "win.export-csv")
        export_menu.append(_("Spreadsheet (.xlsx)"), "win.export-excel")
        export_menu_btn = Gtk.MenuButton(label=_("Export"))
        export_menu_btn.set_menu_model(export_menu)
        header.pack_start(export_menu_btn)

        # Print button (disabled during recording)
        self._print_btn = Gtk.Button(label=_("Print"))
        self._print_btn.set_tooltip_text(_("Print measurement report"))
        self._print_btn.connect("clicked", self._on_print)
        header.pack_start(self._print_btn)

        # Keyboard shortcuts and actions
        export_csv_action = Gio.SimpleAction(name="export-csv")
        export_csv_action.connect("activate", lambda *_: self._on_export_csv(None))
        self.add_action(export_csv_action)
        export_excel_action = Gio.SimpleAction(name="export-excel")
        export_excel_action.connect("activate", lambda *_: self._on_export_excel())
        self.add_action(export_excel_action)
        save_action = Gio.SimpleAction(name="save")
        save_action.connect("activate", lambda *_: self._on_save())
        self.add_action(save_action)
        open_action = Gio.SimpleAction(name="open")
        open_action.connect("activate", lambda *_: self._on_open())
        self.add_action(open_action)

        # Clear Data button
        clear_btn = Gtk.Button(label=_("Clear Data"))
        clear_btn.add_css_class("destructive-action")
        clear_btn.connect("clicked", self._on_clear_data)
        header.pack_end(clear_btn)

        # About button
        about_btn = Gtk.Button(label=_("About"))
        about_btn.connect("clicked", self._on_about)
        header.pack_end(about_btn)

        # Display Style toggle (Table / Charts)
        display_items = Gtk.StringList.new([_("Table"), _("Charts")])
        self._display_dropdown = Gtk.DropDown(model=display_items)
        self._display_dropdown.set_selected(0)  # Default: Table
        self._display_dropdown.connect("notify::selected", self._on_display_style_changed)
        header.pack_end(self._display_dropdown)

        # --- Content layout ---
        # Paned: sidebar (slot panels) | content area (table + charts)
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)

        # Sidebar
        self._sidebar = SlotSidebar()
        self._sidebar.on_slot_selected = self._on_slot_selected
        paned.set_start_child(self._sidebar)

        # Content area
        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._content_box.set_hexpand(True)
        self._content_box.set_vexpand(True)

        # Stack for Table / Charts switching
        self._data_table = DataTable()
        self._charts = ChartPair()

        self._content_stack = Gtk.Stack()
        self._content_stack.set_vexpand(True)
        self._content_stack.set_hexpand(True)
        self._content_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._content_stack.set_transition_duration(150)
        self._content_stack.add_named(self._data_table, "table")
        self._content_stack.add_named(self._charts, "charts")
        self._content_stack.set_visible_child_name("table")

        self._content_box.append(self._content_stack)

        # Status bar at bottom
        self._status_label = Gtk.Label(label=_("Select a port and click Start Logging"))
        self._status_label.set_halign(Gtk.Align.START)
        self._status_label.set_margin_start(8)
        self._status_label.set_margin_end(8)
        self._status_label.set_margin_top(4)
        self._status_label.set_margin_bottom(4)
        self._status_label.add_css_class("dim-label")
        self._content_box.append(self._status_label)

        paned.set_end_child(self._content_box)
        paned.set_position(290)

        # --- Main layout with toolbar view ---
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(paned)

        # Toast overlay for notifications
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(toolbar_view)

        self.set_content(self._toast_overlay)

        # --- Auto-detect CM2016 on startup ---
        detected = detect_cm2016_port()
        if detected:
            self._set_port(detected)

        # --- Check for crash recovery ---
        if has_recovery_data():
            GLib.idle_add(self._show_recovery_dialog)

    # --- Port selection ---

    def _on_port_clicked(self, _button: Gtk.Button) -> None:
        dialog = PortDialog(on_port_selected=self._set_port)
        dialog.present(self)

    def _set_port(self, port: str) -> None:
        self._port = port
        self._port_btn.set_label(port.split("/")[-1])
        logger.info("Port selected: %s", port)

    # --- Start/Stop logging ---

    def _on_toggle_logging(self, button: Gtk.ToggleButton) -> None:
        if button.get_active():
            self._start_logging()
        else:
            self._stop_logging()

    def _start_logging(self) -> None:
        if self._port is None:
            # No port selected, show port dialog first
            self._toggle_btn.set_active(False)
            dialog = PortDialog(on_port_selected=self._set_port_and_start)
            dialog.present(self)
            return

        try:
            self._reader.connect(self._port)
        except Exception:
            logger.exception("Failed to connect to %s", self._port)
            self._toggle_btn.set_active(False)
            self._show_toast(_("Failed to connect to port"))
            return

        self._recording = True
        self._temp_buffer = TempBuffer(self._session)
        self._toggle_btn.set_label(_("Stop Logging"))
        self._toggle_btn.remove_css_class("suggested-action")
        self._toggle_btn.add_css_class("destructive-action")
        self._sidebar.set_recording(True)
        self._print_btn.set_sensitive(False)
        self._print_btn.set_tooltip_text(_("Print is disabled during recording"))

        # Inhibit system sleep/suspend during recording
        app = self.get_application()
        if app is not None:
            self._inhibit_cookie = app.inhibit(
                self,
                Gtk.ApplicationInhibitFlags.IDLE | Gtk.ApplicationInhibitFlags.SUSPEND,
                _("CM2016 is recording data"),
            )

        self._status_label.set_text(_("Waiting For Data"))
        logger.info("Logging started on %s", self._port)

    def _set_port_and_start(self, port: str) -> None:
        """Set port from dialog and immediately start logging."""
        self._set_port(port)
        self._toggle_btn.set_active(True)

    def _stop_logging(self) -> None:
        self._reader.disconnect()
        self._recording = False
        if self._temp_buffer:
            self._temp_buffer.cleanup()
            self._temp_buffer = None

        # Uninhibit sleep
        if self._inhibit_cookie:
            app = self.get_application()
            if app is not None:
                app.uninhibit(self._inhibit_cookie)
            self._inhibit_cookie = 0
        self._toggle_btn.set_label(_("Start Logging"))
        self._toggle_btn.remove_css_class("destructive-action")
        self._toggle_btn.add_css_class("suggested-action")
        self._sidebar.set_recording(False)
        self._print_btn.set_sensitive(True)
        self._print_btn.set_tooltip_text(_("Print measurement report"))
        self._status_label.set_text(_("Logging stopped"))
        logger.info("Logging stopped")

    # --- Frame handling ---

    def _on_frame_from_thread(self, frame: Frame) -> None:
        """Called from the serial reader thread. Dispatch to main loop."""
        GLib.idle_add(self._process_frame, frame)

    def _process_frame(self, frame: Frame) -> bool:
        """Process a frame in the GTK main loop."""
        if not self._recording:
            return False

        self._sidebar.update(frame)
        self._session.process_frame(frame)
        self._update_charts()

        if self._temp_buffer:
            self._temp_buffer.on_frame_received()

        record_count = self._session.total_records
        self._status_label.set_text(_("Recording — {count} data points").format(count=record_count))

        return False

    # --- Connection lost ---

    def _on_connection_lost_from_thread(self) -> None:
        """Called from the serial reader thread."""
        GLib.idle_add(self._handle_connection_lost)

    def _handle_connection_lost(self) -> bool:
        """Handle connection loss in the GTK main loop."""
        if not self._recording:
            return False

        # Block the toggle signal to prevent re-entrant _stop_logging call
        self._toggle_btn.handler_block(self._toggle_handler_id)
        try:
            self._stop_logging()
        finally:
            self._toggle_btn.handler_unblock(self._toggle_handler_id)

        self._status_label.set_text(_("Disconnected — CM2016 switched off or unplugged"))
        self._show_toast(_("Recording stopped: CM2016 switched off or disconnected"))
        logger.info("Connection lost")

        return False

    # --- Slot selection ---

    def _on_slot_selected(self, slot_index: int) -> None:
        logger.debug("Slot %d selected", slot_index)
        self._data_table.set_filter_slot(slot_index)
        self._update_charts()

    # --- Display style ---

    def _on_display_style_changed(self, dropdown: Gtk.DropDown, _pspec: object) -> None:
        selected = dropdown.get_selected()
        name = "table" if selected == 0 else "charts"
        self._content_stack.set_visible_child_name(name)

    # --- Chart updates ---

    def _update_charts(self) -> None:
        """Refresh chart data for the selected slot."""
        slot_idx = self._sidebar.selected_index
        records = self._session.get_slot_data(slot_idx)
        self._charts.set_data(records)

    # --- Data management ---

    def _on_record_added(self, slot_index: int, record: SlotRecord) -> None:
        self._data_table.append_record(record)

    def _on_slot_cleared(self, slot_index: int) -> None:
        self._sidebar.clear_slot(slot_index)
        self._data_table.clear_slot(slot_index)
        self._update_charts()

    def _on_all_cleared(self) -> None:
        self._sidebar.clear_all()
        self._data_table.clear()
        self._charts.clear()
        self._status_label.set_text(_("All data cleared"))

    def _on_clear_data(self, _button: Gtk.Button) -> None:
        """Clear all recorded data after confirmation."""
        dialog = Adw.AlertDialog(
            heading=_("Clear Data"),
            body=_("Delete all recorded data for all slots?"),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("clear", _("Clear"))
        dialog.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_clear_confirmed)
        dialog.present(self)

    def _on_clear_confirmed(self, _dialog: Adw.AlertDialog, response: str) -> None:
        if response == "clear":
            self._session.clear()

    # --- Save/Load ---

    def _on_save(self) -> None:
        """Save all slot data to a .cm2016 file."""
        if self._session.total_records == 0:
            self._show_toast(_("No data to save"))
            return

        dialog = Gtk.FileDialog()
        dialog.set_initial_name("recording" + FILE_EXTENSION)

        cm_filter = Gtk.FileFilter()
        cm_filter.set_name(_("CM2016 files"))
        cm_filter.add_pattern("*" + FILE_EXTENSION)
        filters = Gio.ListStore.new(Gtk.FileFilter.__gtype__)
        filters.append(cm_filter)
        dialog.set_filters(filters)

        dialog.save(self, None, self._on_save_done)

    def _on_save_done(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return
        if gfile is None:
            return

        from pathlib import Path

        path = Path(gfile.get_path())
        count = save_session(self._session, path)
        self._show_toast(_("Saved {count} records").format(count=count))

    def _on_open(self) -> None:
        """Load a .cm2016 session file."""
        dialog = Gtk.FileDialog()

        cm_filter = Gtk.FileFilter()
        cm_filter.set_name(_("CM2016 files"))
        cm_filter.add_pattern("*" + FILE_EXTENSION)
        filters = Gio.ListStore.new(Gtk.FileFilter.__gtype__)
        filters.append(cm_filter)
        dialog.set_filters(filters)

        dialog.open(self, None, self._on_open_done)

    def _on_open_done(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        if gfile is None:
            return

        from pathlib import Path

        path = Path(gfile.get_path())
        try:
            loaded = load_session(path)
        except (ValueError, OSError):
            self._show_toast(_("Failed to load file"))
            logger.exception("Failed to load %s", path)
            return

        self._load_session_data(loaded)
        self._show_toast(
            _("Loaded {count} records from {name}").format(
                count=loaded.total_records, name=path.name
            )
        )

    def _load_session_data(self, loaded: Session) -> None:
        """Replace current session with loaded data and update UI."""
        self._session.clear()
        for slot_idx in range(6):
            for record in loaded.get_slot_data(slot_idx):
                self._session.append(slot_idx, record)
        self._update_charts()
        self._status_label.set_text(
            _("{count} data points loaded").format(count=self._session.total_records)
        )

    # --- Recovery ---

    def _show_recovery_dialog(self) -> bool:
        """Show dialog asking whether to resume the last recording."""
        dialog = Adw.AlertDialog(
            heading=_("Continue last recording?"),
            body=_("Recovery data from a previous session was found."),
        )
        dialog.add_response("no", _("No"))
        dialog.add_response("yes", _("Yes"))
        dialog.set_response_appearance("yes", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("yes")
        dialog.set_close_response("no")
        dialog.connect("response", self._on_recovery_response)
        dialog.present(self)
        return False

    def _on_recovery_response(self, _dialog: Adw.AlertDialog, response: str) -> None:
        if response == "yes":
            recovered = load_recovery()
            if recovered:
                self._load_session_data(recovered)
                self._show_toast(
                    _("Restored {count} records").format(count=recovered.total_records)
                )
        delete_recovery()

    # --- Export ---

    def _on_export_csv(self, _button: Gtk.Button) -> None:
        """Export selected slot data to CSV."""
        slot_idx = self._sidebar.selected_index
        records = self._session.get_slot_data(slot_idx)
        if not records:
            self._show_toast(_("No data to export"))
            return

        from datetime import datetime, timezone

        from cm2016.protocol import SLOT_NAMES

        slot_name = SLOT_NAMES[slot_idx].replace(" ", "")
        date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        default_name = f"CM2016_{slot_name}_{date_str}.csv"

        dialog = Gtk.FileDialog()
        dialog.set_initial_name(default_name)

        csv_filter = Gtk.FileFilter()
        csv_filter.set_name(_("CSV files"))
        csv_filter.add_pattern("*.csv")
        filters = Gio.ListStore.new(Gtk.FileFilter.__gtype__)
        filters.append(csv_filter)
        dialog.set_filters(filters)

        dialog.save(self, None, self._on_csv_save_done, records)

    def _on_csv_save_done(
        self,
        dialog: Gtk.FileDialog,
        result: Gio.AsyncResult,
        records: list[SlotRecord],
    ) -> None:
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return  # User cancelled

        if gfile is None:
            return

        from pathlib import Path

        path = Path(gfile.get_path())
        count = export_csv(records, path)
        self._show_toast(_("Exported {count} rows to {name}").format(count=count, name=path.name))
        logger.info("Exported %d rows to %s", count, path)

    def _on_export_excel(self) -> None:
        """Export selected slot data to Excel/Spreadsheet."""
        slot_idx = self._sidebar.selected_index
        records = self._session.get_slot_data(slot_idx)
        if not records:
            self._show_toast(_("No data to export"))
            return

        from datetime import datetime, timezone

        from cm2016.protocol import SLOT_NAMES

        slot_name = SLOT_NAMES[slot_idx]
        date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        default_name = f"CM2016_{slot_name.replace(' ', '')}_{date_str}.xlsx"

        dialog = Gtk.FileDialog()
        dialog.set_initial_name(default_name)

        xlsx_filter = Gtk.FileFilter()
        xlsx_filter.set_name(_("Spreadsheet files"))
        xlsx_filter.add_pattern("*.xlsx")
        filters = Gio.ListStore.new(Gtk.FileFilter.__gtype__)
        filters.append(xlsx_filter)
        dialog.set_filters(filters)

        dialog.save(self, None, self._on_excel_save_done, (records, slot_name))

    def _on_excel_save_done(
        self,
        dialog: Gtk.FileDialog,
        result: Gio.AsyncResult,
        user_data: tuple[list[SlotRecord], str],
    ) -> None:
        records, slot_name = user_data
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return
        if gfile is None:
            return

        from pathlib import Path

        path = Path(gfile.get_path())
        count = export_excel(records, path, slot_name=slot_name)
        self._show_toast(_("Exported {count} rows to {name}").format(count=count, name=path.name))

    # --- Print ---

    def _on_print(self, _button: Gtk.Button) -> None:
        """Print measurement report for selected slot."""
        slot_idx = self._sidebar.selected_index
        records = self._session.get_slot_data(slot_idx)
        if not records:
            self._show_toast(_("No data to print"))
            return

        from cm2016.protocol import SLOT_NAMES

        print_report(self, records, SLOT_NAMES[slot_idx])

    # --- About ---

    def _on_about(self, _button: Gtk.Button) -> None:
        from cm2016 import __version__

        about = Adw.AboutDialog(
            application_name=_("Charge Manager CM 2016"),
            application_icon=APP_ID,
            version=__version__,
            developer_name="Sebastian van de Meer aka Kernel-Error",
            developers=["Sebastian van de Meer <kernel-error@kernel-error.com>"],
            copyright="© 2026 Kernel-Error",
            license_type=Gtk.License.MIT_X11,
            website="https://www.kernel-error.de",
            issue_url="https://github.com/Kernel-Error/voltcraft-cm2016/issues",
            comments=_(
                "Open-source Linux GUI for the Voltcraft Charge Manager CM 2016 "
                "battery charger. Replaces the Windows-only CM2016 Logger software."
            ),
        )
        about.present(self)

    # --- Helpers ---

    def _show_toast(self, message: str) -> None:
        """Show a transient toast notification."""
        toast = Adw.Toast(title=message)
        toast.set_timeout(3)
        self._toast_overlay.add_toast(toast)


class CM2016Application(Adw.Application):
    """Main GTK application for CM2016."""

    def __init__(self) -> None:
        super().__init__(application_id=APP_ID)

        # Keyboard shortcuts
        self.set_accels_for_action("win.save", ["<Control>s"])
        self.set_accels_for_action("win.open", ["<Control>o"])

    def do_activate(self) -> None:
        """Create and present the main window."""
        win = MainWindow(app=self)

        # Register icon search path for our custom icon
        icon_dir = Path(__file__).parent.parent.parent / "data" / "icons"
        if icon_dir.is_dir():
            display = win.get_display()
            if display is not None:
                Gtk.IconTheme.get_for_display(display).add_search_path(
                    str(icon_dir / "hicolor" / "scalable" / "apps")
                )

        # Load CSS
        if CSS_PATH.exists():
            provider = Gtk.CssProvider()
            provider.load_from_path(str(CSS_PATH))
            display = win.get_display()
            if display is not None:
                Gtk.StyleContext.add_provider_for_display(
                    display,
                    provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
                )

        win.present()


def main() -> None:
    """Entry point for the cm2016 command."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    setup_i18n()

    app = CM2016Application()
    app.run()
