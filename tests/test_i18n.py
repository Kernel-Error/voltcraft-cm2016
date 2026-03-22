"""Tests for cm2016.i18n — internationalization setup (Issue #7)."""

from __future__ import annotations

from unittest.mock import patch

import cm2016.i18n as i18n_mod


class TestSetupI18n:
    """Test setup_i18n() handles locale failures gracefully."""

    def _reset(self) -> None:
        """Reset the module-level translation to None."""
        i18n_mod._translation = None

    def test_setup_succeeds_normally(self) -> None:
        self._reset()
        i18n_mod.setup_i18n()
        assert i18n_mod._translation is not None
        assert isinstance(i18n_mod._("Hello"), str)

    def test_bad_locale_does_not_crash(self) -> None:
        self._reset()
        import locale

        with patch.object(locale, "setlocale", side_effect=locale.Error("bad locale")):
            i18n_mod.setup_i18n()

        # Should fall back to English passthrough
        assert i18n_mod._translation is not None
        assert i18n_mod._("Hello") == "Hello"

    def test_underscore_before_setup_returns_message(self) -> None:
        self._reset()
        assert i18n_mod._("test string") == "test string"

    def test_ngettext_before_setup(self) -> None:
        self._reset()
        assert i18n_mod.ngettext("one item", "many items", 1) == "one item"
        assert i18n_mod.ngettext("one item", "many items", 2) == "many items"
