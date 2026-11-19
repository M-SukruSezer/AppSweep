"""Draw the icon for an installed app into a Gtk.Image.

Two things need care here:

*Textures are cached.* Snap launchers point at PNGs on disk, and a list
view rebinds rows constantly while scrolling. Decoding the same file on
every bind would make scrolling stutter, so decoded textures are kept.

*A missing icon must not show as a broken image.* ``set_from_icon_name``
with a name the theme does not have renders the "image-missing" glyph,
which looks like a bug. Every name is checked against the theme first and
falls back to a generic icon for that source.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gdk, Gtk  # noqa: E402

from .. import icons
from ..models import App

#: Decoded images, keyed by path. Bounded so a system with hundreds of
#: snaps cannot grow this without limit.
_textures: dict[str, Gdk.Texture | None] = {}
_MAX_TEXTURES = 512

_has_icon_cache: dict[str, bool] = {}
_file_lookup_cache: dict[str, str] = {}


def add_icon_search_paths(display: Gdk.Display | None = None) -> None:
    """Teach the icon theme where Flatpak and snapd export their icons.

    Without this a Flatpak's icon name never resolves, because GTK does not
    search the Flatpak export directories by default.
    """
    display = display or Gdk.Display.get_default()
    if display is None:
        return
    theme = Gtk.IconTheme.get_for_display(display)
    existing = set(theme.get_search_path() or [])
    for d in icons.EXTRA_ICON_DIRS:
        if d not in existing:
            theme.add_search_path(d)


def _theme_has(name: str) -> bool:
    cached = _has_icon_cache.get(name)
    if cached is not None:
        return cached
    display = Gdk.Display.get_default()
    if display is None:
        return False
    ok = Gtk.IconTheme.get_for_display(display).has_icon(name)
    _has_icon_cache[name] = ok
    return ok


def _texture(path: str) -> Gdk.Texture | None:
    if path in _textures:
        return _textures[path]
    if len(_textures) >= _MAX_TEXTURES:
        _textures.clear()
    try:
        tex = Gdk.Texture.new_from_filename(path)
    except Exception:            # noqa: BLE001 - any decode failure
        tex = None
    _textures[path] = tex
    return tex


def apply(image: Gtk.Image, app: App) -> None:
    """Set ``image`` to the best icon known for ``app``."""
    icon = app.icon or ""

    if icon.startswith("/"):
        tex = _texture(icon)
        if tex is not None:
            image.set_from_paintable(tex)
            return
    elif icon:
        if _theme_has(icon):
            image.set_from_icon_name(icon)
            return
        # The theme does not know the name, but the image may still be on
        # disk outside any theme index.
        found = _file_lookup_cache.get(icon)
        if found is None:
            found = icons.find_image_for_name(icon)
            _file_lookup_cache[icon] = found
        if found:
            tex = _texture(found)
            if tex is not None:
                image.set_from_paintable(tex)
                return

    name = icons.fallback(app)
    image.set_from_icon_name(
        name if _theme_has(name) else "application-x-executable-symbolic")
    # A placeholder should not compete with the real logos beside it.
    image.add_css_class("as-placeholder-icon")
    return


def reset(image: Gtk.Image) -> None:
    """Clear per-row state before the row is reused."""
    image.remove_css_class("as-placeholder-icon")
