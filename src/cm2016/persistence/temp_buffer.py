"""Temporary file buffering for crash recovery.

During recording, session data is periodically flushed to a temp file
in ``~/.local/share/cm2016/``. On clean stop, the temp file is deleted.
On startup, if a temp file exists, the user is offered to resume.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from cm2016.persistence.file_io import load_session, save_session

if TYPE_CHECKING:
    from cm2016.session import Session

logger = logging.getLogger(__name__)

TEMP_DIR_NAME = "cm2016"
TEMP_FILE_NAME = "recovery.cm2016"

# Flush interval: save temp file every N frames
FLUSH_INTERVAL = 15  # ~30 seconds at 2s per frame


def _get_temp_dir() -> Path:
    """Get the XDG data directory for temp files."""
    import os

    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / TEMP_DIR_NAME


def _get_temp_path() -> Path:
    """Get the full path to the temp recovery file."""
    return _get_temp_dir() / TEMP_FILE_NAME


class TempBuffer:
    """Manages periodic temp file saves for crash recovery.

    Usage::

        buf = TempBuffer(session)
        # Call on_frame_received() for each new frame during recording
        buf.on_frame_received()
        # On clean stop:
        buf.cleanup()
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._frame_count = 0

    def on_frame_received(self) -> None:
        """Called after each frame is processed. Flushes periodically."""
        self._frame_count += 1
        if self._frame_count % FLUSH_INTERVAL == 0:
            self.flush()

    def flush(self) -> None:
        """Save current session to temp file."""
        if self._session.total_records == 0:
            return
        try:
            temp_path = _get_temp_path()
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            save_session(self._session, temp_path)
            logger.debug("Flushed %d records to temp file", self._session.total_records)
        except OSError:
            logger.warning("Failed to write temp file", exc_info=True)

    def cleanup(self) -> None:
        """Delete the temp file (called on clean stop)."""
        temp_path = _get_temp_path()
        try:
            if temp_path.exists():
                temp_path.unlink()
                logger.debug("Deleted temp file")
        except OSError:
            logger.warning("Failed to delete temp file", exc_info=True)
        self._frame_count = 0


def has_recovery_data() -> bool:
    """Check if a temp recovery file exists."""
    return _get_temp_path().exists()


def load_recovery() -> Session | None:
    """Load the recovery session from the temp file.

    Returns:
        Loaded Session, or None if no recovery data or loading fails.
    """
    temp_path = _get_temp_path()
    if not temp_path.exists():
        return None
    try:
        session = load_session(temp_path)
        logger.info("Loaded recovery data: %d records", session.total_records)
        return session
    except (ValueError, OSError, KeyError):
        logger.warning("Failed to load recovery data", exc_info=True)
        return None


def delete_recovery() -> None:
    """Delete the recovery temp file."""
    temp_path = _get_temp_path()
    try:
        if temp_path.exists():
            temp_path.unlink()
    except OSError:
        pass
