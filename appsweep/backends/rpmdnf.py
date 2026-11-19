"""Fedora / RHEL packages via rpm and dnf."""
from __future__ import annotations

from ..models import App, Plan, Source, Step
from ..i18n import _
from ..util import have, run, tokenize
from .base import Backend, launcher_packages

# Exact names where the rest of the family is ordinary software, and
# prefixes where the whole family really is part of the base system. See
# the note in dpkg.py: matching gnome-shell as a prefix also catches
# gnome-shell-extension-manager.
_CRITICAL_EXACT = frozenset({
    "glibc", "dnf", "rpm", "bash", "coreutils", "sudo",
    "gnome-shell", "polkit", "NetworkManager",
})
_CRITICAL_PREFIXES = ("kernel", "systemd", "grub2", "shim")


class DnfBackend(Backend):
    source = Source.DNF
    tool = "dnf"

    @classmethod
    def available(cls) -> bool:
        return have("rpm") and have("dnf")

    def list_apps(self) -> list[App]:
        res = run(
            ["rpm", "-qa", "--qf",
             "%{NAME}\t%{VERSION}-%{RELEASE}\t%{SIZE}\t%{GROUP}\t%{SUMMARY}\n"],
            timeout=90,
        )
        if not res.ok and not res.out:
            return []
        launchers = launcher_packages("rpm")
        out: list[App] = []
        for line in res.out.splitlines():
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            name, ver, size, group = parts[:4]
            summary = parts[4] if len(parts) > 4 else ""
            try:
                sz = int(size)
            except ValueError:
                sz = 0
            critical = (name in _CRITICAL_EXACT
                        or name.startswith(_CRITICAL_PREFIXES))
            is_lib = (
                critical
                or name.startswith(("lib", "python3-", "perl-", "glibc",
                                    "kernel", "font"))
                or name.endswith(("-devel", "-libs", "-doc", "-docs",
                                  "-filesystem", "-langpack"))
                or "System Environment" in group
            )
            # Shipping a launcher settles it: this is an application,
            # whatever group the package declares.
            if not critical and name in launchers:
                is_lib = False
            out.append(App(
                ident=name, name=name, version=ver, source=Source.DNF,
                size_bytes=sz, summary=summary.strip(),
                tokens=tokenize(name), is_library=is_lib,
                extra={"critical": "1" if critical else ""},
            ))
        return out

    def removal_plan(self, app: App, *, purge: bool, autoremove: bool) -> Plan:
        plan = Plan()
        if app.extra.get("critical"):
            plan.notes.append(
                _("“{pkg}” is part of the base system. AppSweep will not "
                  "remove it.").format(pkg=app.ident)
            )
            return plan
        argv = ["dnf", "-y", "remove", app.ident]
        plan.steps.append(Step(argv, needs_root=True,
                               description=_("Remove {pkg}").format(
                                   pkg=app.ident)))
        if autoremove:
            plan.steps.append(Step(
                ["dnf", "-y", "autoremove"], needs_root=True,
                description=_("Remove unneeded dependencies")))
        plan.notes.append(
            _("dnf keeps files under /etc that you have modified; AppSweep "
              "lists them as leftovers afterwards."))
        return plan

    def orphan_cleanup_plan(self) -> Plan:
        plan = Plan()
        plan.steps.append(Step(
            ["dnf", "-y", "autoremove"], needs_root=True,
            description=_("Remove unneeded dependencies")))
        return plan

    def cache_cleanup_plan(self) -> Plan:
        plan = Plan()
        plan.steps.append(Step(["dnf", "clean", "all"], needs_root=True,
                               description=_("Empty the dnf cache")))
        return plan
