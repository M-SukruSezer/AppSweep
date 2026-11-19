"""Guard rails for every destructive path AppSweep touches.

Nothing in this project deletes a path that has not passed ``check_path``.
The rules are deliberately paranoid: a false "refuse" costs the user a
manual cleanup, a false "allow" can cost them their home directory.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

HOME = Path.home()


def _xdg_user_dirs() -> set[str]:
    """The user's real Documents/Downloads/… paths, whatever they are called.

    Hardcoding English names would leave a Turkish, German or Japanese
    desktop's document folder unprotected, so the names come from
    ``~/.config/user-dirs.dirs``.
    """
    found: set[str] = set()
    conf = HOME / ".config/user-dirs.dirs"
    try:
        text = conf.read_text(errors="replace")
    except OSError:
        text = ""
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("XDG_") or "=" not in line:
            continue
        _, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if value.startswith("$HOME"):
            value = str(HOME) + value[len("$HOME"):]
        if value.startswith("/") and value != str(HOME):
            found.add(os.path.normpath(value))
    # Common defaults too, in case the file is missing or incomplete.
    for name in ("Desktop", "Documents", "Downloads", "Music", "Pictures",
                 "Videos", "Templates", "Public"):
        found.add(str(HOME / name))
    return found


#: Paths that must never be removed, whatever the caller claims.
NEVER: frozenset[str] = frozenset(
    {
        "/",
        "/bin", "/boot", "/dev", "/etc", "/home", "/lib", "/lib32", "/lib64",
        "/libx32", "/media", "/mnt", "/opt", "/proc", "/root", "/run", "/sbin",
        "/srv", "/sys", "/tmp", "/usr", "/var",
        "/etc/default", "/etc/init.d", "/etc/pam.d", "/etc/skel", "/etc/ssh",
        "/etc/ssl", "/etc/sudoers.d", "/etc/systemd", "/etc/systemd/system",
        "/etc/apt", "/etc/apt/sources.list.d", "/etc/X11", "/etc/fonts",
        "/usr/bin", "/usr/lib", "/usr/local", "/usr/share", "/usr/sbin",
        "/var/cache", "/var/lib", "/var/log", "/var/tmp", "/var/lib/dpkg",
        "/var/lib/flatpak", "/var/lib/snapd", "/var/lib/apt",
        str(HOME),
        str(HOME / ".config"),
        str(HOME / ".cache"),
        str(HOME / ".local"),
        str(HOME / ".local/share"),
        str(HOME / ".local/state"),
        str(HOME / ".local/bin"),
        str(HOME / ".var"),
        str(HOME / ".var/app"),
        str(HOME / "snap"),
        str(HOME / ".ssh"),
        str(HOME / ".gnupg"),
        str(HOME / ".mozilla"),
        str(HOME / ".thunderbird"),
        str(HOME / ".pki"),
        *_xdg_user_dirs(),
    }
)

#: Directories a residue is allowed to live *directly* inside.
ALLOWED_PARENTS: tuple[str, ...] = (
    str(HOME / ".config"),
    str(HOME / ".cache"),
    str(HOME / ".local/share"),
    str(HOME / ".local/state"),
    str(HOME / ".var/app"),
    str(HOME),              # only for dotted dirs, enforced below
    "/etc",
    "/var/lib",
    "/var/cache",
    "/var/log",
    "/opt",
    "/usr/share",
)

#: Names that are shared infrastructure rather than one app's data.
SHARED_NAMES: frozenset[str] = frozenset(
    {
        "applications", "icons", "themes", "fonts", "mime", "locale", "man",
        "doc", "docs", "bin", "lib", "lib64", "include", "share", "pixmaps",
        "dbus-1", "systemd", "autostart", "gtk-3.0", "gtk-4.0", "qt5ct",
        "fontconfig", "pulse", "dconf", "menus", "mimeapps.list", "user-dirs.dirs",
        "trash", "recently-used.xbel", "keyrings", "nautilus", "glib-2.0",
        "gvfs", "gnupg", "ssh", "pki", "cups", "nvidia", "mesa_shader_cache",
        "thumbnails", "tracker3", "flatpak", "snapd", "apt", "dpkg", "alternatives",
    }
)


class Unsafe(Exception):
    """Raised when a path fails the safety check."""


def check_shape(raw: str) -> Path:
    """Check everything that can be judged from the path string alone.

    Split out from :func:`check_path` so a caller can establish that a path
    is *permissible* before asking whether it still exists. Doing it the
    other way round would let a non-existent protected path report back as
    "already gone" rather than "refused", which is the wrong answer to give
    about ``/etc``.
    """
    if not raw or not raw.startswith("/"):
        raise Unsafe(f"not an absolute path: {raw!r}")

    p = PurePosixPath(os.path.normpath(raw))
    s = str(p)

    if ".." in p.parts:
        raise Unsafe(f"path escapes with '..': {raw!r}")
    if s in NEVER:
        raise Unsafe(f"protected location: {s}")
    if len(p.parts) < 3:
        raise Unsafe(f"too close to the filesystem root: {s}")

    name = p.name.lower()
    if name in SHARED_NAMES:
        raise Unsafe(f"shared by many apps: {s}")
    if len(name.lstrip(".")) < 3:
        raise Unsafe(f"name too short to attribute safely: {s}")

    parent = str(p.parent)
    if parent not in ALLOWED_PARENTS:
        raise Unsafe(f"not in a directory AppSweep cleans: {s}")
    if parent == str(HOME) and not name.startswith("."):
        raise Unsafe(f"visible file in home directory: {s}")
    return Path(s)


def check_path(raw: str) -> Path:
    """Full check: the string rules, then what is actually on disk.

    Rejects relative paths, anything in ``NEVER``, anything shallower than
    3 components, anything not directly under an allowed parent, shared
    infrastructure names, symlinks, paths that resolve elsewhere, and
    mount points.
    """
    real = check_shape(raw)
    s = str(real)
    if real.is_symlink():
        raise Unsafe(f"is a symlink: {s}")
    try:
        resolved = real.resolve(strict=True)
    except OSError as exc:
        raise Unsafe(f"cannot resolve {s}: {exc}") from exc
    if str(resolved) != s:
        raise Unsafe(f"resolves elsewhere ({resolved}): {s}")
    if real.is_mount():
        raise Unsafe(f"is a mount point: {s}")
    return real


def is_safe(raw: str) -> bool:
    try:
        check_path(raw)
    except Unsafe:
        return False
    return True


def why_unsafe(raw: str) -> str | None:
    try:
        check_path(raw)
    except Unsafe as exc:
        return str(exc)
    return None
