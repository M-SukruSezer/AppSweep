"""Preferences: currently just the interface language."""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from .. import i18n, settings


class PreferencesDialog(Adw.PreferencesDialog):
    __gtype_name__ = "AppSweepPreferences"

    def __init__(self, on_language_changed: Callable[[str], None]) -> None:
        super().__init__()
        self._on_language_changed = on_language_changed
        self._ready = False

        self.set_title(i18n._("Preferences"))

        page = Adw.PreferencesPage(
            title=i18n._("General"), icon_name="preferences-system-symbolic"
        )
        group = Adw.PreferencesGroup(
            title=i18n._("Language"),
            description=i18n._(
                "AppSweep starts in Turkish on a Turkish desktop and in "
                "English everywhere else. Your choice here overrides that."
            ),
        )

        codes = [code for code, _name in i18n.LANGUAGES]
        names = [name for _code, name in i18n.LANGUAGES]
        self._codes = codes

        self.row = Adw.ComboRow(
            title=i18n._("Interface language"),
            model=Gtk.StringList.new(names),
        )
        current = i18n.current_language()
        self.row.set_selected(codes.index(current) if current in codes else 0)
        self.row.connect("notify::selected", self._on_selected)
        group.add(self.row)

        page.add(group)
        self.add(page)
        self._ready = True

    def _on_selected(self, *_args) -> None:
        if not self._ready:
            return
        code = self._codes[self.row.get_selected()]
        if code == i18n.current_language():
            return
        settings.set(i18n.SETTINGS_KEY, code)
        i18n.set_language(code)
        self._on_language_changed(code)
