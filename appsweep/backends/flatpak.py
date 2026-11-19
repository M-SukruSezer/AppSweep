"""Flatpak applications and runtimes."""
from __future__ import annotations

import os
from pathlib import Path

from ..models import App, Plan, Source, Step
from ..i18n import _
from ..util import dir_size, have, run, tokenize
from .base import Backend

_COLS = "application,version,name,size,origin,installation,branch,arch,ref"


class FlatpakBackend(Backend):
    source = Source.FLATPAK
    tool = "flatpak"

    @classmethod
    def available(cls) -> bool:
        return have("flatpak")

    def list_apps(self) -> list[App]:
        apps = self._list("--app", is_library=False)
        runtimes = self._list("--runtime", is_library=True)
        return apps + runtimes

    def _list(self, which: str, *, is_library: bool) -> list[App]:
        res = run(["flatpak", "list", which, "--columns", _COLS], timeout=60)
        if not res.ok:
            return []
        out: list[App] = []
        for line in res.out.splitlines():
            parts = line.split("\t")
            if len(parts) < 6 or not parts[0].strip():
                continue
            appid, ver, name, size, origin, installation = (
                p.strip() for p in parts[:6]
            )
            branch = parts[6].strip() if len(parts) > 6 else ""
            out.append(
                App(
                    ident=appid,
                    name=name or appid,
                    version=ver,
                    source=Source.FLATPAK,
                    size_bytes=_parse_size(size),
                    summary=f"{origin or 'unknown remote'} · {installation}",
                    tokens=tokenize(appid, appid.rsplit(".", 1)[-1], name),
                    is_library=is_library,
                    extra={
                        "installation": installation or "system",
                        "branch": branch,
                        "origin": origin,
                    },
                )
            )
        return out

    def orphans(self) -> list[App]:
        res = run(["flatpak", "uninstall", "--unused", "--assumeno"], timeout=60)
        text = res.out + res.err
        found: list[App] = []
        for line in text.splitlines():
            parts = line.split()
            for tok in parts:
                if tok.count("/") == 2 and tok.count(".") >= 2:
                    appid = tok.split("/")[0]
                    found.append(
                        App(ident=appid, name=appid, source=Source.FLATPAK,
                            is_orphan=True, is_library=True,
                            tokens=tokenize(appid))
                    )
                    break
        return found

    def removal_plan(self, app: App, *, purge: bool, autoremove: bool) -> Plan:
        plan = Plan()
        system = app.extra.get("installation", "system") != "user"
        argv = ["flatpak", "uninstall", "-y",
                "--system" if system else "--user"]
        if purge:
            argv.append("--delete-data")
        argv.append(app.ident)
        plan.steps.append(
            Step(argv, needs_root=system,
                 description=_("Uninstall Flatpak {pkg}").format(
                     pkg=app.ident))
        )
        if autoremove:
            plan.steps.append(
                Step(["flatpak", "uninstall", "--unused", "-y",
                      "--system" if system else "--user"],
                     needs_root=system,
                     description=_("Remove runtimes nothing uses any "
                                   "more"))
            )
        if purge:
            plan.notes.append(
                _("--delete-data removes this app's ~/.var/app directory.")
            )
        else:
            # Offer the per-app data dir as residue instead.
            d = Path.home() / ".var/app" / app.ident
            if d.is_dir():
                plan.notes.append(
                    _("App data kept at {path}").format(path=d))
        return plan

    def orphan_cleanup_plan(self) -> Plan:
        plan = Plan()
        plan.steps.append(
            Step(["flatpak", "uninstall", "--unused", "-y", "--system"],
                 needs_root=True,
                 description=_("Remove unused system runtimes"))
        )
        plan.steps.append(
            Step(["flatpak", "uninstall", "--unused", "-y", "--user"],
                 needs_root=False,
                 description=_("Remove unused user runtimes"))
        )
        return plan

    def cache_cleanup_plan(self) -> Plan:
        plan = Plan()
        plan.steps.append(
            Step(["flatpak", "repair", "--system"], needs_root=True,
                 description=_("Prune stale objects from the Flatpak "
                               "repository"))
        )
        return plan

    def cache_size(self) -> int:
        total = 0
        for p in ("/var/tmp/flatpak-cache-*",
                  os.path.expanduser("~/.cache/flatpak/system-cache")):
            if "*" not in p and os.path.isdir(p):
                total += dir_size(p)
        d = os.path.expanduser("~/.cache/flatpak")
        if os.path.isdir(d):
            total += dir_size(d)
        return total


def _parse_size(text: str) -> int:
    text = text.strip().replace(",", ".")
    if not text:
        return 0
    units = {"b": 1, "kb": 1000, "mb": 1000**2, "gb": 1000**3, "tb": 1000**4,
             "kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4}
    num = ""
    for ch in text:
        if ch.isdigit() or ch == ".":
            num += ch
        elif ch == " " and not num:
            continue
        else:
            break
    if not num:
        return 0
    unit = text[len(num):].strip().lower() or "b"
    return int(float(num) * units.get(unit, 1))
