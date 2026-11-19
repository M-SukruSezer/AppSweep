"""Backend interface. One subclass per packaging format."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod

from ..models import App, Plan, Source
from ..util import have, run

#: Where system packages put their launchers.
DESKTOP_DIRS: tuple[str, ...] = (
    "/usr/share/applications",
    "/usr/local/share/applications",
)


def launcher_packages(manager: str) -> set[str]:
    """Packages that install a .desktop launcher, per the package database.

    Whether something is an application is best answered by asking which
    package owns each launcher. Comparing a package's *name* against the
    launcher's filename does not work: a package called ``appsweep``
    installs ``io.github.appsweep.AppSweep.desktop``, and reverse-DNS
    launcher names are now the norm — so a name comparison quietly files
    most modern applications under "library" and hides them.

    One query covers every launcher at once; on a typical desktop that is
    a tenth of a second.
    """
    files: list[str] = []
    for d in DESKTOP_DIRS:
        try:
            files += [os.path.join(d, f) for f in os.listdir(d)
                      if f.endswith(".desktop")]
        except OSError:
            continue
    if not files:
        return set()

    if manager == "dpkg":
        if not have("dpkg-query"):
            return set()
        res = run(["dpkg-query", "-S", *files], timeout=90)
        out: set[str] = set()
        for line in res.out.splitlines():
            head, sep, _rest = line.partition(": ")
            if not sep:
                continue
            for name in head.split(","):
                # dpkg may answer "pkg:amd64"; the architecture is not
                # part of the name.
                name = name.strip().split(":")[0].strip()
                if name:
                    out.add(name)
        return out

    if manager == "rpm":
        if not have("rpm"):
            return set()
        res = run(["rpm", "-qf", "--qf", "%{NAME}\n", *files], timeout=90)
        return {line.strip() for line in res.out.splitlines()
                if line.strip() and " " not in line.strip()}

    if manager == "pacman":
        if not have("pacman"):
            return set()
        res = run(["pacman", "-Qoq", *files], timeout=90)
        return {line.strip() for line in res.out.splitlines() if line.strip()}

    return set()


class Backend(ABC):
    """A source of installed software that can also uninstall it."""

    source: Source
    #: Human readable name of the tool that does the work.
    tool: str = ""

    @classmethod
    @abstractmethod
    def available(cls) -> bool:
        """True when this backend can run on the current system."""

    @abstractmethod
    def list_apps(self) -> list[App]:
        """Every installed item this backend knows about."""

    @abstractmethod
    def removal_plan(self, app: App, *, purge: bool, autoremove: bool) -> Plan:
        """Commands that uninstall ``app``. Must not execute anything."""

    def orphans(self) -> list[App]:
        """Packages installed as dependencies that nothing needs any more."""
        return []

    def orphan_cleanup_plan(self) -> Plan:
        return Plan()

    def cache_cleanup_plan(self) -> Plan:
        """Commands that free package-manager cache space."""
        return Plan()

    def cache_size(self) -> int:
        return 0
