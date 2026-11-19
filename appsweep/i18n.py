"""Translation setup and the language rule.

Which language the app starts in:

1. what the user chose, if they have chosen (stored in the settings file);
2. otherwise Turkish *only* when the desktop itself is Turkish;
3. otherwise English — not the desktop's language.

Step 3 is the part that differs from plain gettext. Left to itself gettext
would hunt through the whole ``LANGUAGE`` list and fall back to the source
strings anyway, which happens to be English, but it would also pick up a
Turkish translation on, say, an ``en_GB:tr`` system. The rule here is
explicit instead: Turkish for Turkish desktops, English everywhere else,
until the user says otherwise.

``_`` and ``N_`` are functions that consult the *current* catalogue on each
call rather than being bound to one at import time, so switching language
at runtime reaches every module that already imported them.
"""
from __future__ import annotations

import gettext
import locale
import os
from pathlib import Path

from . import settings

DOMAIN = "appsweep"

#: Languages the interface ships. Order is the order shown in Preferences.
LANGUAGES: tuple[tuple[str, str], ...] = (
    ("en", "English"),
    ("tr", "Türkçe"),
)

SETTINGS_KEY = "language"


def _locale_dirs() -> list[Path]:
    """Where a compiled catalogue might live, checkout first."""
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "data" / "locale",          # running from a checkout
        here / "locale",                          # bundled inside the package
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        / "locale",
        Path("/usr/local/share/locale"),
        Path("/usr/share/locale"),
    ]
    return [c for c in candidates if c.is_dir()]


def system_is_turkish() -> bool:
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if not value:
            continue
        # LANGUAGE may hold a colon-separated priority list.
        first = value.split(":")[0].strip().lower()
        if first in ("c", "posix", ""):
            continue
        return first.startswith("tr")
    return False


def default_language() -> str:
    """The language to use on a machine where nothing has been chosen."""
    return "tr" if system_is_turkish() else "en"


def current_language() -> str:
    """The language in force: the user's choice, else the default rule."""
    override = os.environ.get("APPSWEEP_LANG")
    if override:
        return override
    chosen = settings.get(SETTINGS_KEY)
    if isinstance(chosen, str) and chosen in dict(LANGUAGES):
        return chosen
    return default_language()


def _load(code: str) -> gettext.NullTranslations:
    for d in _locale_dirs():
        try:
            return gettext.translation(DOMAIN, localedir=str(d),
                                       languages=[code])
        except FileNotFoundError:
            continue
    # English is the source language, so no catalogue is needed for it.
    return gettext.NullTranslations()


_current = _load(current_language())


def _(message: str) -> str:
    """Translate a string using the catalogue in force right now."""
    return _current.gettext(message)


def N_(singular: str, plural: str, n: int) -> str:
    """Plural-aware translation."""
    return _current.ngettext(singular, plural, n)


def set_language(code: str) -> None:
    """Switch catalogue. Widgets already built keep their old strings."""
    global _current
    _current = _load(code)


def setup_locale() -> None:
    """Apply the user's locale for number and date formatting."""
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass
