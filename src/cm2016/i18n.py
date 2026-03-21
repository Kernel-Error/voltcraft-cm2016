"""Internationalization setup for CM2016.

Uses gettext with English as source language and German translation.
The system locale determines the active language at runtime.

Usage in other modules::

    from cm2016.i18n import _

    label = _("Start Logging")
"""

from __future__ import annotations

import gettext
import locale
from pathlib import Path

# Domain name for gettext
DOMAIN = "cm2016"

# Locale directory: <project_root>/po/locale/ for development,
# or system locale dirs for installed packages.
_LOCALE_DIR = Path(__file__).parent.parent.parent / "po" / "locale"

_translation: gettext.GNUTranslations | gettext.NullTranslations | None = None


def setup_i18n() -> None:
    """Initialize gettext for the application.

    Call this once at application startup before any translated strings
    are used. Falls back to NullTranslations (passthrough) if no .mo
    file is found for the current locale.
    """
    global _translation

    locale.setlocale(locale.LC_ALL, "")

    locale_dir = str(_LOCALE_DIR) if _LOCALE_DIR.is_dir() else None

    # Build language list: gettext looks for e.g. "de_DE" but our .mo
    # files use the short code "de". Provide both so it finds a match.
    languages = None
    lang_code = locale.getlocale()[0]  # e.g. "de_DE" or "en_US"
    if lang_code:
        short = lang_code.split("_")[0]  # e.g. "de"
        languages = [lang_code, short]

    _translation = gettext.translation(
        DOMAIN,
        localedir=locale_dir,
        languages=languages,
        fallback=True,
    )
    _translation.install()


def _(message: str) -> str:
    """Translate a string using the active translation.

    If setup_i18n() has not been called yet, returns the message unchanged.
    """
    if _translation is None:
        return message
    return _translation.gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    """Translate a string with plural form support."""
    if _translation is None:
        return singular if n == 1 else plural
    return _translation.ngettext(singular, plural, n)
