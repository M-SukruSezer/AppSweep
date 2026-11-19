"""Work out how this copy of AppSweep was installed, and how to remove it.

An application that removes software should be able to remove itself, and
it should do it the way the system expects: a package installed with apt
has to leave through apt, or dpkg's database is left describing files that
are no longer there.

So this module does not delete anything. It identifies the installation and
produces the command a person would have typed, which the interface then
runs in a terminal where they can read it, confirm it and see it finish.
"""
from __future__ import annotations

import os
import shlex
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import LANGUAGES, _

PACKAGE = "appsweep"
DESKTOP_FILE = "io.github.appsweep.AppSweep.desktop"
ICON_BASE = "io.github.appsweep.AppSweep"


@dataclass(slots=True)
class Installation:
    """How AppSweep got onto this machine."""

    method: str                      # deb | rpm | pacman | user | source
    label: str                       # what to tell the user
    detail: str                      # where it lives
    command: str = ""                # shell command that removes it
    removable: bool = True
    paths: list[str] = field(default_factory=list)


def package_root() -> Path:
    """The directory the ``appsweep`` package sits in."""
    return Path(__file__).resolve().parent.parent


def _owner_package(path: Path) -> tuple[str, str] | None:
    """(manager, package) that claims ``path``, if any."""
    probes = (
        ("deb", ["dpkg-query", "-S", str(path)]),
        ("rpm", ["rpm", "-qf", str(path)]),
        ("pacman", ["pacman", "-Qoq", str(path)]),
    )
    from .util import have, run

    for manager, argv in probes:
        if not have(argv[0]):
            continue
        res = run(argv, timeout=20)
        if not res.ok or not res.out.strip():
            continue
        out = res.out.strip().splitlines()[0]
        if manager == "deb":
            name = out.split(":")[0].strip()
        elif manager == "rpm":
            # rpm answers with the full NEVRA; the name is the leading part.
            name = out.split("-")[0].strip()
        else:
            name = out.strip()
        if name:
            return manager, name
    return None


def detect() -> Installation:
    """Identify this installation. Never raises."""
    root = package_root()
    here = Path(__file__).resolve()

    owner = _owner_package(here)
    if owner is not None:
        manager, name = owner
        if manager == "deb":
            return Installation(
                method="deb",
                label=_("Installed as a Debian package ({pkg})").format(
                    pkg=name),
                detail=str(root),
                command=f"sudo apt remove {shlex.quote(name)}",
            )
        if manager == "rpm":
            tool = "dnf" if shutil.which("dnf") else "zypper"
            return Installation(
                method="rpm",
                label=_("Installed as an RPM package ({pkg})").format(
                    pkg=name),
                detail=str(root),
                command=f"sudo {tool} remove {shlex.quote(name)}",
            )
        return Installation(
            method="pacman",
            label=_("Installed with pacman ({pkg})").format(pkg=name),
            detail=str(root),
            command=f"sudo pacman -R {shlex.quote(name)}",
        )

    # install.sh puts everything under a prefix, with the package in
    # <prefix>/share/appsweep.
    if root.name == PACKAGE and root.parent.name == "share":
        prefix = root.parent.parent
        paths = _user_install_paths(prefix)
        existing = [p for p in paths if os.path.lexists(p)]
        return Installation(
            method="user",
            label=_("Installed for this user only, under {prefix}").format(
                prefix=prefix),
            detail=str(prefix),
            command=_removal_script(existing),
            paths=existing,
        )

    return Installation(
        method="source",
        label=_("Running from a source folder, not installed"),
        detail=str(root),
        removable=False,
    )


def _user_install_paths(prefix: Path) -> list[str]:
    """Exactly what install.sh puts down. No wildcards."""
    out = [
        str(prefix / "share" / PACKAGE),
        str(prefix / "bin" / PACKAGE),
        str(prefix / "share" / "applications" / DESKTOP_FILE),
        str(prefix / "share" / "icons" / "hicolor" / "scalable" / "apps"
            / f"{ICON_BASE}.svg"),
        str(prefix / "share" / "icons" / "hicolor" / "symbolic" / "apps"
            / f"{ICON_BASE}-symbolic.svg"),
    ]
    for code, _name in LANGUAGES:
        out.append(str(prefix / "share" / "locale" / code / "LC_MESSAGES"
                       / f"{PACKAGE}.mo"))
    return out


def _removal_script(paths: list[str]) -> str:
    if not paths:
        return ""
    quoted = " \\\n    ".join(shlex.quote(p) for p in paths)
    return f"rm -rf \\\n    {quoted}"


#: Terminals to try, with how each takes a command to run.
TERMINALS: tuple[tuple[str, list[str]], ...] = (
    ("ptyxis", ["--"]),
    ("kgx", ["--"]),
    ("gnome-terminal", ["--"]),
    ("konsole", ["-e"]),
    ("xfce4-terminal", ["-x"]),
    ("mate-terminal", ["--"]),
    ("tilix", ["-e"]),
    ("kitty", []),
    ("alacritty", ["-e"]),
    ("foot", []),
    ("xterm", ["-e"]),
)


def terminal_argv(script: str) -> list[str] | None:
    """A command line that opens a terminal running ``script``.

    Returns None when no terminal emulator can be found, which the caller
    has to handle: the command is still worth showing so the user can run
    it themselves.
    """
    from .util import have

    preferred = os.environ.get("TERMINAL", "").strip()
    candidates: list[tuple[str, list[str]]] = []
    if preferred:
        flags = dict(TERMINALS).get(os.path.basename(preferred), ["-e"])
        candidates.append((preferred, flags))
    candidates.extend(TERMINALS)

    for name, flags in candidates:
        if not have(name):
            continue
        return [name, *flags, "sh", "-c", script]
    return None


def session_script(install: Installation) -> str:
    """The shell the terminal runs: show the command, run it, then wait."""
    header = _("Removing AppSweep")
    done = _("Finished. Press Enter to close this window.")
    return (
        f"printf '%s\\n\\n' {shlex.quote(header)}; "
        f"printf '$ %s\\n\\n' {shlex.quote(install.command)}; "
        f"{install.command}; "
        f"status=$?; "
        f"printf '\\n%s\\n' {shlex.quote(done)}; "
        f"read _unused; "
        f"exit $status"
    )
