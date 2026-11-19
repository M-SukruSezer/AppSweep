"""Debian / Ubuntu packages via dpkg-query and apt-get."""
from __future__ import annotations

import os

from ..models import App, Plan, Source, Step
from ..i18n import _
from ..util import dir_size, have, run, tokenize
from .base import Backend, launcher_packages

# Packages whose removal would take the desktop or the system with them.
#
# Split in two on purpose. Matching every one of these as a prefix marks
# gnome-shell-extension-manager as critical because it begins with
# "gnome-shell" — an ordinary application that the user could then neither
# see nor remove. Only real families belong in the prefix list.
_CRITICAL_EXACT = frozenset({
    "libc6", "dpkg", "apt", "bash", "coreutils", "sudo",
    "gnome-shell", "mutter", "gdm3", "network-manager",
    "policykit-1", "polkitd",
})
_CRITICAL_PREFIXES = (
    "linux-image", "linux-headers", "linux-modules", "grub", "shim",
    "systemd", "ubuntu-desktop", "ubuntu-minimal", "ubuntu-standard",
    "xorg",
)


def _is_critical(pkg: str, essential: str, priority: str) -> bool:
    return (
        essential.strip().lower() == "yes"
        or priority.strip().lower() in ("required", "important")
        or pkg in _CRITICAL_EXACT
        or pkg.startswith(_CRITICAL_PREFIXES)
    )
_LIBRARY_SECTIONS = {
    "libs", "libdevel", "oldlibs", "debug", "kernel", "doc", "fonts",
    "localization", "translations", "perl", "python", "ruby", "javascript",
    "introspection", "metapackages", "admin", "shells", "utils", "devel",
}


class DpkgBackend(Backend):
    source = Source.APT
    tool = "apt"

    @classmethod
    def available(cls) -> bool:
        return have("dpkg-query") and have("apt-get")

    # ---------------------------------------------------------------- listing
    def list_apps(self) -> list[App]:
        fmt = (
            "${Package}\t${Version}\t${Installed-Size}\t${Section}\t"
            "${Priority}\t${Essential}\t${binary:Summary}\n"
        )
        res = run(["dpkg-query", "-W", "-f", fmt], timeout=90)
        if not res.ok and not res.out:
            return []

        launchers = launcher_packages("dpkg")
        apps: list[App] = []
        for line in res.out.splitlines():
            parts = line.split("\t")
            if len(parts) < 6:
                continue
            pkg, ver, isize, section, prio, essential = parts[:6]
            summary = parts[6] if len(parts) > 6 else ""
            if not pkg:
                continue
            try:
                size = int(isize) * 1024 if isize.strip() else 0
            except ValueError:
                size = 0

            sec = section.rsplit("/", 1)[-1].lower()
            critical = _is_critical(pkg, essential, prio)
            is_lib = (
                critical
                or sec in _LIBRARY_SECTIONS
                or pkg.startswith(("lib", "python3-", "python-", "gir1.2-",
                                   "golang-", "node-", "fonts-", "linux-"))
                or pkg.endswith(("-dev", "-doc", "-common", "-data", "-dbg",
                                 "-l10n", "-locale"))
            )
            # A package that ships a .desktop launcher is an application
            # whatever its section says — unless it is system-critical.
            # Sections like admin, utils and devel hold both plumbing and
            # real programs, so the launcher is the better signal.
            if not critical and pkg in launchers:
                is_lib = False

            apps.append(
                App(
                    ident=pkg,
                    name=pkg,
                    version=ver,
                    source=Source.APT,
                    size_bytes=size,
                    summary=summary.strip(),
                    tokens=tokenize(pkg, *_strip_suffixes(pkg)),
                    is_library=is_lib,
                    extra={"section": sec, "critical": "1" if critical else ""},
                )
            )
        self._mark_orphans(apps)
        return apps

    def _mark_orphans(self, apps: list[App]) -> None:
        names = {a.ident for a in self._parse_autoremovable()}
        if not names:
            return
        for a in apps:
            if a.ident in names:
                a.is_orphan = True

    def _parse_autoremovable(self) -> list[App]:
        res = run(["apt-get", "--dry-run", "autoremove"], timeout=90)
        out: list[App] = []
        for line in res.out.splitlines():
            if line.startswith("Remv "):
                pkg = line.split()[1]
                out.append(App(ident=pkg, name=pkg, source=Source.APT,
                               is_orphan=True, tokens=tokenize(pkg)))
        return out

    def orphans(self) -> list[App]:
        found = self._parse_autoremovable()
        if not found:
            return []
        sizes = {a.ident: a.size_bytes for a in self.list_apps()}
        for a in found:
            a.size_bytes = sizes.get(a.ident, 0)
        return found

    # ---------------------------------------------------------------- removal
    def removal_plan(self, app: App, *, purge: bool, autoremove: bool) -> Plan:
        plan = Plan()
        if app.extra.get("critical"):
            plan.notes.append(
                _("“{pkg}” is marked essential or required by the "
                  "distribution. AppSweep will not remove it.").format(
                      pkg=app.ident)
            )
            return plan

        argv = ["apt-get", "-y", "purge" if purge else "remove"]
        if autoremove:
            argv.append("--autoremove")
        argv.append(app.ident)
        plan.steps.append(
            Step(
                argv=argv,
                needs_root=True,
                description=(
                    (_("Purge {pkg}") if purge else _("Remove {pkg}")).format(
                        pkg=app.ident)
                    + (_(" and its unused dependencies") if autoremove else "")
                ),
            )
        )
        if purge:
            plan.notes.append(
                _("Purge also deletes this package's files under /etc.")
            )
        return plan

    def orphan_cleanup_plan(self) -> Plan:
        plan = Plan()
        plan.steps.append(
            Step(["apt-get", "-y", "--purge", "autoremove"], needs_root=True,
                 description=_("Remove packages no longer needed by "
                               "anything"))
        )
        return plan

    def cache_cleanup_plan(self) -> Plan:
        plan = Plan()
        plan.steps.append(
            Step(["apt-get", "clean"], needs_root=True,
                 description=_("Empty the downloaded .deb cache"))
        )
        return plan

    def cache_size(self) -> int:
        return dir_size("/var/cache/apt/archives")


def _strip_suffixes(pkg: str) -> list[str]:
    out = []
    for suf in ("-bin", "-gtk", "-qt", "-gtk3", "-common", "-core", "-cli",
                "-gui", "-data", "-full", "3", "2"):
        if pkg.endswith(suf) and len(pkg) > len(suf) + 2:
            out.append(pkg[: -len(suf)])
    return out
