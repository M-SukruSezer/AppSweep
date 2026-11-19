"""Arch Linux packages via pacman."""
from __future__ import annotations

from ..models import App, Plan, Source, Step
from ..i18n import _
from ..util import dir_size, have, run, tokenize
from .base import Backend

_CRITICAL = ("linux", "glibc", "systemd", "pacman", "bash", "coreutils",
             "grub", "sudo", "filesystem", "gcc-libs", "base")


class PacmanBackend(Backend):
    source = Source.PACMAN
    tool = "pacman"

    @classmethod
    def available(cls) -> bool:
        return have("pacman")

    def list_apps(self) -> list[App]:
        res = run(["pacman", "-Qi"], timeout=90)
        if not res.ok and not res.out:
            return []
        out: list[App] = []
        cur: dict[str, str] = {}

        def flush() -> None:
            name = cur.get("Name", "")
            if not name:
                return
            critical = name in _CRITICAL or name.startswith("linux")
            reason = cur.get("Install Reason", "")
            out.append(App(
                ident=name,
                name=name,
                version=cur.get("Version", ""),
                source=Source.PACMAN,
                size_bytes=_parse_isize(cur.get("Installed Size", "")),
                summary=cur.get("Description", ""),
                tokens=tokenize(name),
                is_library=(critical or name.startswith("lib")
                            or name.endswith(("-doc", "-docs"))),
                extra={"critical": "1" if critical else "",
                       "reason": reason},
            ))

        for line in res.out.splitlines():
            if not line.strip():
                flush()
                cur = {}
                continue
            if ":" in line and not line.startswith(" "):
                k, _, v = line.partition(":")
                cur[k.strip()] = v.strip()
        flush()
        return out

    def orphans(self) -> list[App]:
        res = run(["pacman", "-Qdtq"], timeout=60)
        return [
            App(ident=n, name=n, source=Source.PACMAN, is_orphan=True,
                tokens=tokenize(n))
            for n in res.out.split()
            if n
        ]

    def removal_plan(self, app: App, *, purge: bool, autoremove: bool) -> Plan:
        plan = Plan()
        if app.extra.get("critical"):
            plan.notes.append(
                _("“{pkg}” is part of the base system. AppSweep will not "
                  "remove it.").format(pkg=app.ident)
            )
            return plan
        flags = "-R"
        if purge:
            flags += "n"          # also remove saved config files
        if autoremove:
            flags += "s"          # remove dependencies no longer needed
        plan.steps.append(Step(["pacman", flags, "--noconfirm", app.ident],
                               needs_root=True,
                               description=_("Remove {pkg}").format(
                                   pkg=app.ident)))
        return plan

    def orphan_cleanup_plan(self) -> Plan:
        plan = Plan()
        res = run(["pacman", "-Qdtq"], timeout=60)
        names = [n for n in res.out.split() if n]
        if names:
            plan.steps.append(Step(["pacman", "-Rns", "--noconfirm", *names],
                                   needs_root=True,
                                   description=_(
                                       "Remove {n} orphans").format(
                                           n=len(names))))
        return plan

    def cache_cleanup_plan(self) -> Plan:
        plan = Plan()
        if have("paccache"):
            # paccache keeps the most recent version, which is far less
            # drastic than emptying the cache outright.
            step = Step(
                ["paccache", "-rk1"],
                needs_root=True,
                description=_("Keep one cached version per package"),
            )
        else:
            step = Step(
                ["pacman", "-Sc", "--noconfirm"],
                needs_root=True,
                description=_("Remove cached packages"),
            )
        plan.steps.append(step)
        return plan

    def cache_size(self) -> int:
        return dir_size("/var/cache/pacman/pkg")


def _parse_isize(text: str) -> int:
    text = text.strip().replace(",", ".")
    if not text:
        return 0
    num, _, unit = text.partition(" ")
    try:
        val = float(num)
    except ValueError:
        return 0
    mult = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3,
            "TiB": 1024**4}.get(unit.strip(), 1)
    return int(val * mult)
