"""Find the icon that belongs to an installed piece of software.

There is no single place to ask. What exists is the set of ``.desktop``
entries on the system, and those are the only authoritative statement of
"this software looks like that": the freedesktop menu spec is what the
desktop itself reads to draw its launchers.

So the strategy is to index every desktop entry once, then match each
installed item to an entry. Matching is deliberately exact — on the stem of
the entry's filename, on the last dotted component of a reverse-DNS stem,
or on the binary in ``Exec=`` — because a wrong icon is worse than no icon:
a stranger's logo next to a package name invites the user to uninstall the
wrong thing.

Icons arrive in two forms and both are handled:

* a *name* to look up in the icon theme (``org.gnome.Nautilus``), which is
  what distribution and Flatpak entries use;
* an *absolute path* to an image (``/snap/clion/current/bin/clion.png``),
  which is what snapd writes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .models import App, Source

HOME = Path.home()

#: Suffixes that mark a release channel or build variant of the *same*
#: application, so the launcher of the base name is still the right icon.
#: Kept deliberately short. Suffixes like -utils, -common, -plugin-rdp or
#: -daemon name a different piece of software that merely ships alongside,
#: and must not inherit the application's logo.
_CHANNEL_SUFFIXES: tuple[str, ...] = (
    "-stable", "-beta", "-nightly", "-unstable", "-bin", "-git",
)


def _norm(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())

#: Every place the desktop looks for launchers, in the order it looks.
DESKTOP_DIRS: tuple[str, ...] = (
    str(HOME / ".local/share/applications"),
    str(HOME / ".local/share/flatpak/exports/share/applications"),
    "/var/lib/flatpak/exports/share/applications",
    "/var/lib/snapd/desktop/applications",
    "/usr/local/share/applications",
    "/usr/share/applications",
)

def project_icon_dir() -> str:
    """AppSweep's own icons when running from a checkout.

    Installed copies put them under the usual share/icons, which GTK
    already searches; this is only so ``./bin/appsweep`` shows the real
    icon instead of a generic one.
    """
    return str(Path(__file__).resolve().parent.parent / "data" / "icons")


#: Icon theme directories GTK does not search by default. Flatpak exports
#: its applications' icons here, so without these a Flatpak's icon name
#: never resolves. AppSweep's own icon directory is included for the same
#: reason when running from a checkout.
EXTRA_ICON_DIRS: tuple[str, ...] = (
    project_icon_dir(),
    str(HOME / ".local/share/flatpak/exports/share/icons"),
    "/var/lib/flatpak/exports/share/icons",
    str(HOME / ".local/share/icons"),
    "/var/lib/snapd/desktop/icons",
)

#: Shown when nothing better is known. Symbolic icons on purpose: these
#: are placeholders, and a flat monochrome glyph recedes next to the real
#: logos instead of competing with them for attention. Still per source,
#: so the row says something true about where the software came from.
FALLBACK: dict[Source, str] = {
    Source.APT: "package-x-generic-symbolic",
    Source.DNF: "package-x-generic-symbolic",
    Source.PACMAN: "package-x-generic-symbolic",
    Source.FLATPAK: "application-x-executable-symbolic",
    Source.SNAP: "application-x-executable-symbolic",
    Source.APPIMAGE: "application-x-executable-symbolic",
    Source.PIP: "utilities-terminal-symbolic",
    Source.PIPX: "utilities-terminal-symbolic",
    Source.NPM: "utilities-terminal-symbolic",
    Source.CARGO: "utilities-terminal-symbolic",
}

#: Libraries and runtimes are not applications; say so rather than giving
#: them a launcher icon they do not have.
LIBRARY_ICON = "application-x-addon-symbolic"


@dataclass(slots=True)
class Entry:
    """One parsed ``.desktop`` file, reduced to what we need."""

    stem: str
    path: str
    icon: str = ""
    name: str = ""
    exec_bin: str = ""
    no_display: bool = False
    #: For snapd entries, the snap that owns this launcher.
    snap: str = ""
    #: Raw Exec line, used to spot AppImage launchers.
    exec_line: str = ""


@dataclass(slots=True)
class DesktopIndex:
    """Every desktop entry on the system, keyed several ways."""

    entries: list[Entry] = field(default_factory=list)
    by_stem: dict[str, Entry] = field(default_factory=dict)
    by_tail: dict[str, Entry] = field(default_factory=dict)
    by_exec: dict[str, Entry] = field(default_factory=dict)
    by_snap: dict[str, Entry] = field(default_factory=dict)
    by_name: dict[str, Entry] = field(default_factory=dict)
    #: Reverse-DNS stems keyed by their trailing components joined and
    #: normalised: org.gnome.Snapshot -> "gnomesnapshot".
    by_rdns: dict[str, Entry] = field(default_factory=dict)
    #: Keys that several unrelated entries claim, and so identify nothing.
    #: Tracked per table: "settings" may be ambiguous as a display name
    #: while being a perfectly good executable name, and one table's
    #: collision must not blind the others.
    ambiguous: dict[int, set[str]] = field(default_factory=dict)

    @classmethod
    def build(cls, dirs: tuple[str, ...] = DESKTOP_DIRS) -> DesktopIndex:
        idx = cls()
        for d in dirs:
            try:
                names = sorted(os.listdir(d))
            except OSError:
                continue
            for fn in names:
                if not fn.endswith(".desktop"):
                    continue
                entry = _parse(os.path.join(d, fn))
                if entry is None:
                    continue
                idx._add(entry)
        idx._drop_ambiguous()
        return idx

    def _drop_ambiguous(self) -> None:
        """Remove keys that point at more than one piece of software.

        Every Steam game ships a launcher whose ``Exec`` is ``steam``, so
        ``by_exec["steam"]`` would otherwise hand the ``steam`` package the
        icon of whichever game sorted first. A key claimed by two unrelated
        entries identifies neither, so it is dropped and those apps fall
        back to a generic icon.
        """
        for table in (self.by_exec, self.by_tail, self.by_name,
                      self.by_rdns):
            bad = self.ambiguous.get(id(table), set())
            for key in [k for k in table if k in bad]:
                del table[key]

    def _add(self, e: Entry) -> None:
        self.entries.append(e)
        stem = e.stem.lower()
        # First writer wins: DESKTOP_DIRS is in the desktop's own
        # precedence order, so a user override beats the system copy.
        self.by_stem.setdefault(stem, e)
        # by_snap is keyed on the owning snap, which is unambiguous by
        # construction, and by_stem on a filename, which is unique per
        # directory. The looser keys can collide, so note when they do.
        if "." in e.stem:
            self._put(self.by_tail, e.stem.rsplit(".", 1)[-1].lower(), e)
        if e.exec_bin:
            self._put(self.by_exec, e.exec_bin.lower(), e)
        if e.snap:
            self.by_snap.setdefault(e.snap.lower(), e)
        if e.name:
            self._put(self.by_name, e.name.lower(), e)
        parts = e.stem.split(".")
        if len(parts) >= 2:
            # "gnome.Snapshot" and "google.Chrome" from the full stem.
            self._put(self.by_rdns, _norm("".join(parts[-2:])), e)

    def _put(self, table: dict[str, Entry], key: str, e: Entry) -> None:
        if not key:
            return
        existing = table.get(key)
        if existing is None:
            table[key] = e
        elif existing.stem != e.stem:
            # Two different launchers want this key; it tells us nothing.
            self.ambiguous.setdefault(id(table), set()).add(key)

    # ------------------------------------------------------------- matching
    def match(self, app: App) -> Entry | None:
        """The desktop entry for ``app``, or None when nothing matches."""
        ident = app.ident.lower()

        if app.source is Source.FLATPAK:
            # The app id *is* the entry's stem.
            return self.by_stem.get(ident)

        if app.source is Source.SNAP:
            return self.by_snap.get(ident) or self.by_stem.get(ident)

        if app.source is Source.APPIMAGE:
            target = app.extra.get("path", "")
            if target:
                for e in self.entries:
                    if target in e.exec_line:
                        return e
            return None

        if app.source in (Source.PIP, Source.PIPX, Source.NPM, Source.CARGO):
            # These install commands, not launchers. Occasionally one does
            # ship a desktop entry, so an exact name match is still worth
            # trying, but nothing looser than that.
            for cmd in _commands(app):
                e = self.by_stem.get(cmd) or self.by_exec.get(cmd)
                if e is not None:
                    return e
            return None

        # Distribution packages. Matching is on the package name itself,
        # never on its split-up tokens: a token match hands
        # remmina-plugin-rdp the Remmina logo and qemu-utils the QEMU one,
        # which reads as "this row is that application" when it is not.
        for key in self._distro_keys(app):
            e = (self.by_stem.get(key)
                 or self.by_tail.get(key)
                 or self.by_exec.get(key))
            if e is not None:
                return e
        # A reverse-DNS launcher for the same name: the package
        # gnome-snapshot owns org.gnome.Snapshot.desktop.
        return self.by_rdns.get(_norm(ident))

    def _distro_keys(self, app: App) -> list[str]:
        """Spellings of a package name that still mean the same software."""
        ident = app.ident.lower()
        keys = [ident]
        for suffix in _CHANNEL_SUFFIXES:
            if ident.endswith(suffix) and len(ident) > len(suffix) + 2:
                keys.append(ident[: -len(suffix)])
        return keys


def _commands(app: App) -> list[str]:
    raw = app.extra.get("scripts") or app.extra.get("bins") \
        or app.extra.get("apps") or ""
    out = [c.strip().lower() for c in raw.split(",") if c.strip()]
    out.append(app.ident.lower())
    return out


def _parse(path: str) -> Entry | None:
    """Read the [Desktop Entry] group of a .desktop file."""
    stem = os.path.basename(path)[: -len(".desktop")]
    snap = ""
    if "/snapd/desktop/" in path and "_" in stem:
        snap = stem.split("_", 1)[0]

    icon = name = exec_line = ""
    no_display = False
    in_group = False
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if line.startswith("["):
                    # Only the main group describes the application itself;
                    # later groups are additional actions with their own
                    # Name and Icon keys.
                    if in_group:
                        break
                    in_group = line.strip() == "[Desktop Entry]"
                    continue
                if not in_group or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key == "Icon" and not icon:
                    icon = value
                elif key == "Name" and not name:
                    name = value
                elif key == "Exec" and not exec_line:
                    exec_line = value
                elif key == "NoDisplay":
                    no_display = value.lower() == "true"
                elif key == "Type" and value not in ("Application", ""):
                    return None
    except OSError:
        return None

    return Entry(
        stem=stem,
        path=path,
        icon=icon,
        name=name,
        exec_bin=_exec_binary(exec_line),
        no_display=no_display,
        snap=snap,
        exec_line=exec_line,
    )


def _exec_binary(exec_line: str) -> str:
    """The program name out of an Exec line, field codes and env stripped."""
    for token in exec_line.split():
        if token.startswith("%"):
            continue
        if token in ("env", "sh", "-c", "/bin/sh", "/usr/bin/env", "bash"):
            continue
        if "=" in token and not token.startswith("/"):
            continue          # VAR=value prefix
        return os.path.basename(token).strip('"\'')
    return ""


def resolve(app: App, index: DesktopIndex) -> str:
    """Icon name or absolute image path for ``app``; "" when unknown.

    The caller decides what to draw when this returns nothing; see
    :func:`fallback`.
    """
    entry = index.match(app)
    if entry is not None and entry.icon:
        icon = entry.icon
        if icon.startswith("/"):
            return icon if os.path.exists(icon) else ""
        # Some entries name an image file rather than a theme icon.
        if icon.endswith((".png", ".svg", ".xpm")):
            found = _find_image(icon)
            if found:
                return found
            icon = icon.rsplit(".", 1)[0]
        return icon
    return ""


def fallback(app: App) -> str:
    if app.is_library:
        return LIBRARY_ICON
    return FALLBACK.get(app.source, "application-x-executable")


def _find_image(filename: str) -> str:
    """An icon referenced by filename rather than by theme name."""
    for d in ("/usr/share/pixmaps", "/usr/share/icons",
              str(HOME / ".local/share/icons")):
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
    return ""


#: Where an application may drop an icon without registering it with any
#: icon theme. Searched only when the theme itself does not know the name.
_IMAGE_ROOTS: tuple[str, ...] = (
    "/usr/share/pixmaps",
    "/usr/share/icons/hicolor",
    str(HOME / ".local/share/icons/hicolor"),
    "/var/lib/flatpak/exports/share/icons/hicolor",
)
_SIZES: tuple[str, ...] = (
    "scalable", "512x512", "256x256", "192x192", "128x128", "96x96",
    "64x64", "48x48", "32x32",
)


def find_image_for_name(name: str) -> str:
    """Locate an image file for a bare icon name, or "".

    Some packages ship ``Icon=thunderbird`` while installing the image
    outside any theme index, so the theme lookup fails even though the file
    is right there. Called from the UI only when the theme comes up empty.
    """
    if not name or "/" in name:
        return ""
    for root in _IMAGE_ROOTS:
        if not os.path.isdir(root):
            continue
        for ext in (".svg", ".png", ".xpm"):
            direct = os.path.join(root, name + ext)
            if os.path.exists(direct):
                return direct
        for size in _SIZES:
            for ext in (".svg", ".png"):
                p = os.path.join(root, size, "apps", name + ext)
                if os.path.exists(p):
                    return p
    return ""


def annotate(apps: list[App], index: DesktopIndex | None = None) -> DesktopIndex:
    """Fill in ``App.icon`` for every app. Safe to call off the main thread."""
    idx = index or DesktopIndex.build()
    for app in apps:
        app.icon = resolve(app, idx) or ""
    return idx
