"""Save and load CM2016 recording sessions to/from .cm2016 files (JSON)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from cm2016.session import SLOT_COUNT, Session, SlotRecord

logger = logging.getLogger(__name__)

FILE_VERSION = 1
FILE_EXTENSION = ".cm2016"


def save_session(session: Session, path: Path) -> int:
    """Save all slot data to a .cm2016 JSON file.

    Args:
        session: The session to save.
        path: Output file path.

    Returns:
        Total number of records saved.
    """
    slots_data: dict[str, list[dict]] = {}
    total = 0
    for slot_idx in range(SLOT_COUNT):
        records = session.get_slot_data(slot_idx)
        slots_data[str(slot_idx)] = [_record_to_dict(r) for r in records]
        total += len(records)

    data = {
        "version": FILE_VERSION,
        "saved_at": datetime.now(tz=timezone.utc).isoformat(),
        "slots": slots_data,
    }

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Saved %d records to %s", total, path)
    return total


def load_session(path: Path) -> Session:
    """Load a session from a .cm2016 JSON file.

    Args:
        path: Input file path.

    Returns:
        A new Session populated with the loaded data.

    Raises:
        ValueError: If the file format is invalid.
    """
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)

    version = data.get("version")
    if version != FILE_VERSION:
        msg = f"Unsupported file version: {version}"
        raise ValueError(msg)

    session = Session()
    slots = data.get("slots", {})

    for slot_key, records_data in slots.items():
        slot_idx = int(slot_key)
        for rec_data in records_data:
            record = _dict_to_record(rec_data, slot_idx)
            session.append(slot_idx, record)

    logger.info("Loaded %d records from %s", session.total_records, path)
    return session


def _record_to_dict(record: SlotRecord) -> dict:
    """Convert a SlotRecord to a JSON-serializable dict."""
    return {
        "ts": record.timestamp.isoformat(),
        "prog": record.program,
        "status": record.status,
        "chem": record.chemistry,
        "rt_min": record.runtime_minutes,
        "rt_fmt": record.runtime_formatted,
        "v": record.voltage,
        "i": record.current,
        "ccap": record.charge_capacity,
        "dcap": record.discharge_capacity,
    }


def _dict_to_record(d: dict, slot_index: int) -> SlotRecord:
    """Convert a dict from JSON back to a SlotRecord."""
    return SlotRecord(
        timestamp=datetime.fromisoformat(d["ts"]),
        slot_index=slot_index,
        program=d["prog"],
        status=d["status"],
        chemistry=d["chem"],
        runtime_minutes=d["rt_min"],
        runtime_formatted=d["rt_fmt"],
        voltage=d["v"],
        current=d["i"],
        charge_capacity=d["ccap"],
        discharge_capacity=d["dcap"],
    )
