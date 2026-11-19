"""AppImages — files on disk with no package manager behind them."""
from __future__ import annotations

import os
import re
from pathlib import Path

from ..models import App, Plan, Source, Step
from ..i18n import _
from ..util import tokenize
from .base import Backend

SEARCH_DIRS = (
    "~/Applications",
    "~/.local/bin",
    "~/bin",
    "~/Downloads",
    "~/İndirilenler",
    "~/Desktop",
    "~/Masaüstü",
    "~/opt",
    "/opt",
)
_VER = re.compile(r"[-_]v?(\d+[\d.]*)")


class AppImageBackend(Backend):
    source = Source.APPIMAGE
    tool = "filesystem"

    @classmethod
    def available(cls) -> bool:
        return True

    def list_apps(self) -> list[App]:
        found: dict[str, App] = {}
        for raw in SEARCH_DIRS:
            d = Path(os.path.expanduser(raw))
            if not d.is_dir():
                continue
            try:
                entries = list(d.iterdir())
            except OSError:
                continue
            for f in entries:
                if not f.is_file() or f.is_symlink():
                    continue
                if f.suffix.lower() != ".appimage":
                    continue
                try:
                    size = f.stat().st_size
                except OSError:
                    continue
                stem = f.stem
                m = _VER.search(stem)
                version = m.group(1) if m else ""
                pretty = _VER.sub("", stem).replace("-", " ").replace("_", " ")
                pretty = re.sub(r"\s*(x86[_-]?64|amd64|aarch64|linux)\s*", " ",
                                pretty, flags=re.I).strip() or stem
                key = str(f)
                found[key] = App(
                    ident=key,
                    name=pretty,
                    version=version,
                    source=Source.APPIMAGE,
                    size_bytes=size,
                    summary=str(f.parent),
                    tokens=tokenize(pretty, stem, stem.split("-")[0]),
                    extra={"path": key, "executable":
                           "1" if os.access(f, os.X_OK) else ""},
                )
        return list(found.values())

    def removal_plan(self, app: App, *, purge: bool, autoremove: bool) -> Plan:
        plan = Plan()
        path = app.extra.get("path", app.ident)
        plan.steps.append(
            Step(["__trash__", path], needs_root=False,
                 description=_("Move {name} to the trash").format(
                     name=os.path.basename(path)))
        )
        for desk in _desktop_entries_for(app):
            plan.steps.append(
                Step(["__trash__", desk], needs_root=False,
                     description=_("Remove its launcher ({name})").format(
                         name=os.path.basename(desk)))
            )
        plan.notes.append(
            _("AppImages are single files, so there is nothing to uninstall "
              "— AppSweep moves the file and its launcher to the trash and "
              "then looks for leftover settings.")
        )
        return plan


def _desktop_entries_for(app: App) -> list[str]:
    """.desktop files in the user's app dir that point at this AppImage."""
    out: list[str] = []
    target = app.extra.get("path", app.ident)
    d = Path.home() / ".local/share/applications"
    if not d.is_dir():
        return out
    try:
        entries = list(d.glob("*.desktop"))
    except OSError:
        return out
    for f in entries:
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        if target in text:
            out.append(str(f))
    return out
