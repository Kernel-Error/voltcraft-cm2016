"""Tests for cm2016.widgets.data_table (Issue #13)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cm2016.session import SlotRecord

try:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk  # noqa: F401

    from cm2016.widgets.data_table import DataTable, _records_to_tsv

    GTK_AVAILABLE = True
except (ImportError, ValueError):
    GTK_AVAILABLE = False


def _make_record(slot_index: int = 0, voltage: float = 1.32) -> SlotRecord:
    base = datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc)
    return SlotRecord(
        timestamp=base + timedelta(seconds=slot_index * 2),
        slot_index=slot_index,
        program="Charge",
        status="Charge",
        chemistry="NiMH",
        runtime_minutes=10,
        runtime_formatted="0:10",
        voltage=voltage,
        current=0.5,
        charge_capacity=100.0,
        discharge_capacity=0.0,
    )


# --- Pure function tests (no GTK needed) ---


@pytest.mark.skipif(not GTK_AVAILABLE, reason="GTK 4 not available")
class TestRecordsToTsv:
    """Test the _records_to_tsv helper function."""

    def test_header_row_present(self) -> None:
        tsv = _records_to_tsv([_make_record()])
        header = tsv.split("\n")[0]
        expected_cols = [
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
        assert header == "\t".join(expected_cols)

    def test_single_record_formatting(self) -> None:
        record = _make_record(slot_index=0, voltage=1.32)
        tsv = _records_to_tsv([record])
        data_line = tsv.strip().split("\n")[1]
        fields = data_line.split("\t")
        assert fields[0] == "1"  # slot_index 0 → display as 1
        assert fields[1] == "0:10"
        assert fields[2] == "Charge"
        assert fields[3] == "Charge"
        assert fields[4] == "1.320"
        assert fields[5] == "0.500"
        assert fields[8] == "NiMH"

    def test_multiple_records_line_count(self) -> None:
        records = [_make_record(i) for i in range(5)]
        tsv = _records_to_tsv(records)
        lines = tsv.strip().split("\n")
        assert len(lines) == 6  # 1 header + 5 data

    def test_slot_index_one_based(self) -> None:
        record = _make_record(slot_index=3)
        tsv = _records_to_tsv([record])
        data_line = tsv.strip().split("\n")[1]
        assert data_line.startswith("4\t")


# --- GTK widget tests ---


@pytest.mark.skipif(not GTK_AVAILABLE, reason="GTK 4 not available")
class TestDataTable:
    """Test DataTable widget operations."""

    def test_initial_state_empty(self) -> None:
        table = DataTable()
        assert table._list_store.get_n_items() == 0
        assert table._all_items == []

    def test_append_record(self) -> None:
        table = DataTable()
        table.append_record(_make_record())
        assert table._list_store.get_n_items() == 1
        assert len(table._all_items) == 1

    def test_clear_removes_all(self) -> None:
        table = DataTable()
        table.append_record(_make_record(0))
        table.append_record(_make_record(1))
        table.clear()
        assert table._list_store.get_n_items() == 0
        assert table._all_items == []

    def test_clear_slot_removes_correct_records(self) -> None:
        table = DataTable()
        table.append_record(_make_record(slot_index=0))
        table.append_record(_make_record(slot_index=1))
        table.clear_slot(0)
        assert table._list_store.get_n_items() == 1
        assert len(table._all_items) == 1
        assert table._all_items[0].slot_index == 1

    def test_autoscroll_default_true(self) -> None:
        table = DataTable()
        assert table._autoscroll is True

    def test_filter_label_all_slots(self) -> None:
        table = DataTable()
        assert "All" in table._filter_label.get_text()

    def test_filter_slot_changes_label(self) -> None:
        table = DataTable()
        table.set_filter_slot(0)
        label_text = table._filter_label.get_text()
        assert label_text != ""
        assert "All" not in label_text

    def test_filter_slot_none_restores_all(self) -> None:
        table = DataTable()
        table.set_filter_slot(0)
        table.set_filter_slot(None)
        assert "All" in table._filter_label.get_text()
