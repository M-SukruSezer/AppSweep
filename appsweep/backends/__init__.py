"""Backend registry and detection."""
from __future__ import annotations

from ..models import Source
from .appimage import AppImageBackend
from .base import Backend
from .cargo import CargoBackend
from .dpkg import DpkgBackend
from .flatpak import FlatpakBackend
from .npm import NpmBackend
from .pacman import PacmanBackend
from .pip import PipBackend
from .pipx import PipxBackend
from .rpmdnf import DnfBackend
from .snapd import SnapBackend

#: System package managers first, then the per-language ones. The order
#: decides the order things appear in when sorting by source.
ALL: tuple[type[Backend], ...] = (
    DpkgBackend,
    DnfBackend,
    PacmanBackend,
    FlatpakBackend,
    SnapBackend,
    AppImageBackend,
    PipBackend,
    PipxBackend,
    NpmBackend,
    CargoBackend,
)


def detect() -> list[Backend]:
    """Instantiate every backend usable on this machine."""
    return [cls() for cls in ALL if cls.available()]


def by_source() -> dict[Source, Backend]:
    return {b.source: b for b in detect()}


__all__ = ["ALL", "Backend", "detect", "by_source"]
