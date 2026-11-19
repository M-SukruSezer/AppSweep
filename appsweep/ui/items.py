"""GObject wrappers so dataclasses can live in Gtk list models."""
from __future__ import annotations

from gi.repository import GObject

from ..models import App, Residue


class AppItem(GObject.Object):
    __gtype_name__ = "AppSweepAppItem"

    selected = GObject.Property(type=bool, default=False)

    def __init__(self, app: App) -> None:
        super().__init__()
        self.app = app

    @property
    def key(self) -> str:
        return self.app.key


class ResidueItem(GObject.Object):
    __gtype_name__ = "AppSweepResidueItem"

    selected = GObject.Property(type=bool, default=False)

    def __init__(self, residue: Residue) -> None:
        super().__init__()
        self.residue = residue
