"""Core data types shared by every backend."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Source(str, Enum):
    """Where a piece of software came from."""

    APT = "apt"
    DNF = "dnf"
    PACMAN = "pacman"
    FLATPAK = "flatpak"
    SNAP = "snap"
    APPIMAGE = "appimage"
    # Language package managers. These install into a prefix rather than
    # through the distribution, so the distro's database knows nothing
    # about them and no system tool ever cleans them up.
    PIP = "pip"
    PIPX = "pipx"
    NPM = "npm"
    CARGO = "cargo"

    @property
    def label(self) -> str:
        return {
            Source.APT: "APT / dpkg",
            Source.DNF: "DNF / rpm",
            Source.PACMAN: "Pacman",
            Source.FLATPAK: "Flatpak",
            Source.SNAP: "Snap",
            Source.APPIMAGE: "AppImage",
            Source.PIP: "pip",
            Source.PIPX: "pipx",
            Source.NPM: "npm (global)",
            Source.CARGO: "cargo",
        }[self]

    @property
    def is_language_manager(self) -> bool:
        """True for per-language managers rather than system ones."""
        return self in (Source.PIP, Source.PIPX, Source.NPM, Source.CARGO)


@dataclass(slots=True)
class App:
    """One installed piece of software, normalised across backends."""

    ident: str                      # backend-native id used for removal
    name: str                       # human readable name
    version: str = ""
    source: Source = Source.APT
    size_bytes: int = 0             # 0 when the backend cannot tell
    summary: str = ""
    # Extra tokens (binary names, app-ids, exec names) used by the leftover
    # scanner to recognise config/cache directories belonging to this app.
    tokens: list[str] = field(default_factory=list)
    # True for things that are libraries/runtimes rather than user-facing apps.
    is_library: bool = False
    # True when the backend reports the package as a dependency nothing needs.
    is_orphan: bool = False
    # Backend-specific payload (e.g. flatpak arch/branch, snap revision).
    extra: dict[str, str] = field(default_factory=dict)
    # Icon theme name or absolute image path, filled in by appsweep.icons.
    # Empty means nothing matched and the UI should use a generic icon.
    icon: str = ""

    @property
    def key(self) -> str:
        return f"{self.source.value}:{self.ident}"


@dataclass(slots=True)
class Residue:
    """A file or directory left behind by an app."""

    path: str
    size_bytes: int
    kind: str          # "config" | "data" | "cache" | "state" | "system"
    matched_token: str
    confidence: str    # "high" | "medium" | "low"
    needs_root: bool = False


@dataclass(slots=True)
class Step:
    """A single shell command that makes up part of an operation."""

    argv: list[str]
    needs_root: bool = False
    description: str = ""


@dataclass(slots=True)
class Plan:
    """Everything that will happen, assembled before anything is executed."""

    steps: list[Step] = field(default_factory=list)
    residues: list[Residue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def needs_root(self) -> bool:
        return any(s.needs_root for s in self.steps) or any(
            r.needs_root for r in self.residues
        )
