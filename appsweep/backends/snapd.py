"""Snap packages."""
from __future__ import annotations

import os
import re

from ..models import App, Plan, Source, Step
from ..i18n import _
from ..util import have, run, tokenize
from .base import Backend

_CORE = re.compile(r"^(core\d*|snapd|bare|gtk-common-themes|gnome-\d+-\d+-\d+"
                   r"|kde-frameworks-\d+.*|qt\d+-.*|.*-core\d*)$")


class SnapBackend(Backend):
    source = Source.SNAP
    tool = "snap"

    @classmethod
    def available(cls) -> bool:
        return have("snap") and os.path.exists("/run/snapd.socket")

    def list_apps(self) -> list[App]:
        res = run(["snap", "list", "--all"], timeout=60)
        if not res.ok:
            return []
        lines = res.out.splitlines()
        if len(lines) < 2:
            return []

        sizes = self._sizes()
        seen: dict[str, App] = {}
        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 5:
                continue
            name, ver, rev, tracking, publisher = parts[:5]
            notes = parts[5] if len(parts) > 5 else ""
            if "disabled" in notes and name in seen:
                continue
            is_lib = bool(_CORE.match(name)) or "base" in notes
            app = App(
                ident=name,
                name=name,
                version=ver,
                source=Source.SNAP,
                size_bytes=sizes.get(name, 0),
                summary=f"{publisher} · rev {rev} · {tracking}",
                tokens=tokenize(name),
                is_library=is_lib,
                extra={"revision": rev, "notes": notes},
            )
            seen[name] = app
        return list(seen.values())

    def _sizes(self) -> dict[str, int]:
        """Snap sizes come from the squashfs files in /var/lib/snapd/snaps."""
        out: dict[str, int] = {}
        d = "/var/lib/snapd/snaps"
        try:
            entries = os.listdir(d)
        except OSError:
            return out
        for fn in entries:
            if not fn.endswith(".snap"):
                continue
            stem = fn[: -len(".snap")]
            name = stem.rsplit("_", 1)[0]
            try:
                sz = os.path.getsize(os.path.join(d, fn))
            except OSError:
                continue
            out[name] = max(out.get(name, 0), sz)
        return out

    def removal_plan(self, app: App, *, purge: bool, autoremove: bool) -> Plan:
        plan = Plan()
        if app.ident in ("snapd", "core", "core18", "core20", "core22", "core24"):
            plan.notes.append(
                _("“{pkg}” is the snap runtime itself; removing it breaks "
                  "every other snap. AppSweep will not remove it.").format(
                      pkg=app.ident)
            )
            return plan
        argv = ["snap", "remove", app.ident]
        if purge:
            argv.append("--purge")
        plan.steps.append(
            Step(argv, needs_root=True,
                 description=_("Remove snap {pkg}").format(pkg=app.ident))
        )
        plan.notes.append(
            _("Without --purge, snapd keeps a snapshot of this snap's data; "
              "with it, the data is gone immediately.")
            if not purge else
            _("--purge skips the data snapshot — removal is immediate and "
              "final.")
        )
        return plan

    def cache_cleanup_plan(self) -> Plan:
        plan = Plan()
        plan.steps.append(
            Step(["snap", "set", "system", "refresh.retain=2"], needs_root=True,
                 description=_("Keep only 2 old revisions of each snap"))
        )
        return plan

    def disabled_revisions(self) -> list[tuple[str, str, int]]:
        """Old, disabled snap revisions — pure wasted space."""
        res = run(["snap", "list", "--all"], timeout=60)
        out: list[tuple[str, str, int]] = []
        sizes = self._sizes()
        for line in res.out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 6 and "disabled" in parts[5]:
                out.append((parts[0], parts[2], sizes.get(parts[0], 0)))
        return out
