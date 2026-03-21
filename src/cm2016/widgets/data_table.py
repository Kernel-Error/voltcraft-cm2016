"""Data table widget for CM2016 recording data.

Displays logged slot records in a scrollable Gtk.ColumnView with
autoscroll and per-slot filtering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk

from cm2016.i18n import _

if TYPE_CHECKING:
    from cm2016.session import SlotRecord


class RecordObject(GObject.Object):
    """GObject wrapper around a SlotRecord for use in Gio.ListStore."""

    def __init__(self, record: SlotRecord) -> None:
        super().__init__()
        self.record = record


class DataTable(Gtk.Box):
    """Scrollable data table showing logged measurement records.

    Columns: Slot, Time, Program, Actual, Voltage(V), Current(A),
    CCAP(mAh), DCAP(mAh), Chemistry.
    """

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._filter_slot: int | None = None
        self._autoscroll = True

        # Toolbar with autoscroll toggle
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        toolbar.set_margin_start(4)
        toolbar.set_margin_end(4)
        toolbar.set_margin_top(4)
        toolbar.set_margin_bottom(4)

        self._filter_label = Gtk.Label(label=_("All Slots"))
        self._filter_label.set_hexpand(True)
        self._filter_label.set_halign(Gtk.Align.START)
        toolbar.append(self._filter_label)

        self._autoscroll_btn = Gtk.ToggleButton(label=_("Autoscroll"))
        self._autoscroll_btn.set_active(True)
        self._autoscroll_btn.connect("toggled", self._on_autoscroll_toggled)
        toolbar.append(self._autoscroll_btn)

        self.append(toolbar)

        # Data model — holds ALL records (unfiltered)
        self._all_items: list[SlotRecord] = []

        # Filtered model for display
        self._store = Gtk.StringList()  # Dummy, replaced by ColumnView setup
        self._list_store = gi_new_list_store()

        # Filter model
        self._filter_model = Gtk.FilterListModel(model=self._list_store)
        self._custom_filter = Gtk.CustomFilter.new(self._filter_func)
        self._filter_model.set_filter(self._custom_filter)

        # Selection model (multi-select for clipboard)
        self._selection = Gtk.MultiSelection(model=self._filter_model)

        # Column view
        self._column_view = Gtk.ColumnView(model=self._selection)
        self._column_view.set_show_row_separators(True)
        self._column_view.set_show_column_separators(True)
        self._column_view.add_css_class("data-table")

        # Define columns
        columns = [
            (_("Slot"), self._setup_slot, self._bind_slot, 50),
            (_("Time"), self._setup_text, self._bind_time, 80),
            (_("Program"), self._setup_text, self._bind_program, 80),
            (_("Actual"), self._setup_text, self._bind_actual, 80),
            (_("Voltage (V)"), self._setup_text, self._bind_voltage, 90),
            (_("Current (A)"), self._setup_text, self._bind_current, 90),
            (_("CCAP (mAh)"), self._setup_text, self._bind_ccap, 90),
            (_("DCAP (mAh)"), self._setup_text, self._bind_dcap, 90),
            (_("Chemistry"), self._setup_text, self._bind_chemistry, 70),
        ]

        for title, setup_fn, bind_fn, width in columns:
            factory = Gtk.SignalListItemFactory()
            factory.connect("setup", setup_fn)
            factory.connect("bind", bind_fn)
            col = Gtk.ColumnViewColumn(title=title, factory=factory)
            col.set_fixed_width(width)
            self._column_view.append_column(col)

        # Scrolled window
        self._scrolled = Gtk.ScrolledWindow()
        self._scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._scrolled.set_vexpand(True)
        self._scrolled.set_hexpand(True)
        self._scrolled.set_child(self._column_view)

        self.append(self._scrolled)

        # --- Right-click context menu ---
        self._popover_menu = self._build_context_menu()
        self._popover_menu.set_parent(self._column_view)

        click_gesture = Gtk.GestureClick(button=3)  # Right-click
        click_gesture.connect("released", self._on_right_click)
        self._column_view.add_controller(click_gesture)

        # --- Ctrl+C keyboard shortcut ---
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self._column_view.add_controller(key_controller)

    # --- Public API ---

    def append_record(self, record: SlotRecord) -> None:
        """Add a record to the table."""
        obj = RecordObject(record)
        self._list_store.append(obj)
        self._all_items.append(record)

        if self._autoscroll:
            self._scroll_to_bottom()

    def set_filter_slot(self, slot_index: int | None) -> None:
        """Filter table to show only records from a specific slot.

        Args:
            slot_index: 0-5 to filter, None to show all.
        """
        self._filter_slot = slot_index
        if slot_index is not None:
            from cm2016.protocol import SLOT_NAMES

            self._filter_label.set_text(SLOT_NAMES[slot_index])
        else:
            self._filter_label.set_text(_("All Slots"))
        self._custom_filter.changed(Gtk.FilterChange.DIFFERENT)

    def clear(self) -> None:
        """Remove all records from the table."""
        self._list_store.remove_all()
        self._all_items.clear()

    def clear_slot(self, slot_index: int) -> None:
        """Remove all records for a specific slot."""
        # Iterate backwards to safely remove items
        n = self._list_store.get_n_items()
        for i in range(n - 1, -1, -1):
            obj = self._list_store.get_item(i)
            if obj is not None and obj.record.slot_index == slot_index:
                self._list_store.remove(i)
        self._all_items = [r for r in self._all_items if r.slot_index != slot_index]

    # --- Filter ---

    def _filter_func(self, item: GObject.Object) -> bool:
        if self._filter_slot is None:
            return True
        if not isinstance(item, RecordObject):
            return True
        return item.record.slot_index == self._filter_slot

    # --- Autoscroll ---

    def _on_autoscroll_toggled(self, button: Gtk.ToggleButton) -> None:
        self._autoscroll = button.get_active()
        if self._autoscroll:
            self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        """Scroll to the last row."""
        GLib.idle_add(self._do_scroll_to_bottom)

    def _do_scroll_to_bottom(self) -> bool:
        vadj = self._scrolled.get_vadjustment()
        if vadj is not None:
            vadj.set_value(vadj.get_upper())
        return False

    # --- Clipboard ---

    def _build_context_menu(self) -> Gtk.PopoverMenu:
        """Build the right-click context menu."""
        menu = Gio.Menu()
        menu.append(_("Copy Selected Rows"), "table.copy-selected")
        menu.append(_("Copy All Rows"), "table.copy-all")

        # Register actions
        action_group = Gio.SimpleActionGroup()

        copy_selected = Gio.SimpleAction(name="copy-selected")
        copy_selected.connect("activate", lambda *_: self._copy_selected_to_clipboard())
        action_group.add_action(copy_selected)

        copy_all = Gio.SimpleAction(name="copy-all")
        copy_all.connect("activate", lambda *_: self._copy_all_to_clipboard())
        action_group.add_action(copy_all)

        self._column_view.insert_action_group("table", action_group)

        return Gtk.PopoverMenu(menu_model=menu)

    def _on_right_click(
        self,
        _gesture: Gtk.GestureClick,
        _n_press: int,
        x: float,
        y: float,
    ) -> None:
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        self._popover_menu.set_pointing_to(rect)
        self._popover_menu.popup()

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        if keyval == Gdk.KEY_c and state & Gdk.ModifierType.CONTROL_MASK:
            self._copy_selected_to_clipboard()
            return True
        return False

    def _copy_selected_to_clipboard(self) -> None:
        """Copy selected rows as TSV to clipboard."""
        records = self._get_selected_records()
        if not records:
            return
        tsv = _records_to_tsv(records)
        clipboard = self._column_view.get_clipboard()
        clipboard.set(tsv)

    def _copy_all_to_clipboard(self) -> None:
        """Copy all visible (filtered) rows as TSV to clipboard."""
        records = self._get_all_visible_records()
        if not records:
            return
        tsv = _records_to_tsv(records)
        clipboard = self._column_view.get_clipboard()
        clipboard.set(tsv)

    def _get_selected_records(self) -> list[SlotRecord]:
        """Get records for selected rows."""
        records: list[SlotRecord] = []
        bitset = self._selection.get_selection()
        n = self._filter_model.get_n_items()
        for i in range(n):
            if bitset.contains(i):
                obj = self._filter_model.get_item(i)
                if isinstance(obj, RecordObject):
                    records.append(obj.record)
        return records

    def _get_all_visible_records(self) -> list[SlotRecord]:
        """Get all records currently visible (after filtering)."""
        records: list[SlotRecord] = []
        for i in range(self._filter_model.get_n_items()):
            obj = self._filter_model.get_item(i)
            if isinstance(obj, RecordObject):
                records.append(obj.record)
        return records

    # --- Column factories ---

    @staticmethod
    def _setup_text(_factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        label.set_margin_start(4)
        label.set_margin_end(4)
        list_item.set_child(label)

    @staticmethod
    def _setup_slot(_factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        label = Gtk.Label()
        label.set_halign(Gtk.Align.CENTER)
        list_item.set_child(label)

    @staticmethod
    def _get_record(list_item: Gtk.ListItem) -> SlotRecord | None:
        obj = list_item.get_item()
        if isinstance(obj, RecordObject):
            return obj.record
        return None

    @classmethod
    def _bind_slot(cls, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        record = cls._get_record(list_item)
        label = list_item.get_child()
        if record and isinstance(label, Gtk.Label):
            label.set_text(str(record.slot_index + 1))

    @classmethod
    def _bind_time(cls, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        record = cls._get_record(list_item)
        label = list_item.get_child()
        if record and isinstance(label, Gtk.Label):
            label.set_text(record.runtime_formatted)

    @classmethod
    def _bind_program(cls, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        record = cls._get_record(list_item)
        label = list_item.get_child()
        if record and isinstance(label, Gtk.Label):
            label.set_text(record.program)

    @classmethod
    def _bind_actual(cls, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        record = cls._get_record(list_item)
        label = list_item.get_child()
        if record and isinstance(label, Gtk.Label):
            label.set_text(record.status)

    @classmethod
    def _bind_voltage(cls, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        record = cls._get_record(list_item)
        label = list_item.get_child()
        if record and isinstance(label, Gtk.Label):
            label.set_text(f"{record.voltage:.3f}")

    @classmethod
    def _bind_current(cls, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        record = cls._get_record(list_item)
        label = list_item.get_child()
        if record and isinstance(label, Gtk.Label):
            label.set_text(f"{record.current:.3f}")

    @classmethod
    def _bind_ccap(cls, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        record = cls._get_record(list_item)
        label = list_item.get_child()
        if record and isinstance(label, Gtk.Label):
            label.set_text(f"{record.charge_capacity:.2f}")

    @classmethod
    def _bind_dcap(cls, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        record = cls._get_record(list_item)
        label = list_item.get_child()
        if record and isinstance(label, Gtk.Label):
            label.set_text(f"{record.discharge_capacity:.2f}")

    @classmethod
    def _bind_chemistry(cls, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        record = cls._get_record(list_item)
        label = list_item.get_child()
        if record and isinstance(label, Gtk.Label):
            label.set_text(record.chemistry)


def _records_to_tsv(records: list[SlotRecord]) -> str:
    """Convert records to tab-separated values with header row."""
    header = "\t".join(
        [
            "Slot",
            "Time",
            "Program",
            "Actual",
            "Voltage (V)",
            "Current (A)",
            "CCAP (mAh)",
            "DCAP (mAh)",
            "Chemistry",
        ]
    )
    lines = [header]
    for r in records:
        lines.append(
            "\t".join(
                [
                    str(r.slot_index + 1),
                    r.runtime_formatted,
                    r.program,
                    r.status,
                    f"{r.voltage:.3f}",
                    f"{r.current:.3f}",
                    f"{r.charge_capacity:.2f}",
                    f"{r.discharge_capacity:.2f}",
                    r.chemistry,
                ]
            )
        )
    return "\n".join(lines) + "\n"


def gi_new_list_store() -> gi.repository.Gio.ListStore:  # type: ignore[name-defined]
    """Create a Gio.ListStore for RecordObject items."""
    return Gio.ListStore.new(RecordObject.__gtype__)
