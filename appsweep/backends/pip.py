"""Python packages installed with pip.

The hard problem here is not listing packages, it is telling apart the two
populations that share one import path:

*distribution-managed*
    Installed by apt/dnf/pacman as ``python3-numpy`` and friends, living in
    ``dist-packages``. ``pip uninstall`` on these corrupts the distro's
    package database — on Debian and Ubuntu the interpreter is even marked
    ``EXTERNALLY-MANAGED`` (PEP 668) to say so. AppSweep leaves them out of
    its list entirely: the dpkg/rpm backend already reports them under
    their real package name, and that is where they should be removed.

*pip-managed*
    Installed by the user with ``pip install``, into the user site
    directory or a virtual environment. These are what this backend owns.

Everything is read by running a short script under the *target* interpreter,
so the backend works for any Python, not only the one AppSweep itself runs
under. That also keeps the inspected environment out of our own process.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from ..i18n import _
from ..models import App, Plan, Source, Step
from ..util import have, run, tokenize
from .base import Backend

#: Removing these with pip breaks the ability to install anything again.
PROTECTED = frozenset({"pip", "setuptools", "wheel", "packaging",
                       "pkg_resources", "distlib", "importlib-metadata"})

#: Path fragments that mean "the distribution installed this, not pip".
_DISTRO_MARKERS = ("/dist-packages", "/site-packages/debian",
                   "/usr/lib/python3/dist-packages")

# Runs under the inspected interpreter. Emits one JSON document.
_PROBE = r"""
import json, os, sys
try:
    from importlib.metadata import distributions
except Exception:
    print("[]"); raise SystemExit(0)

# Extra site directories to inspect, passed as arguments. With none, the
# interpreter's own search path is used.
extra = sys.argv[1:]
found = distributions(path=extra) if extra else distributions()

out = []
for d in found:
    try:
        name = d.metadata["Name"]
    except Exception:
        name = None
    if not name:
        continue
    path = getattr(d, "_path", None)
    location = str(path.parent) if path is not None else ""
    scripts = []
    try:
        for ep in d.entry_points:
            if ep.group == "console_scripts":
                scripts.append(ep.name)
    except Exception:
        pass
    size = 0
    files = 0
    try:
        for f in (d.files or []):
            try:
                fp = d.locate_file(f)
                size += os.path.getsize(fp)
                files += 1
            except OSError:
                continue
    except Exception:
        pass
    out.append({
        "name": name,
        "version": d.version or "",
        "location": location,
        "dist_info": str(path) if path is not None else "",
        "scripts": scripts,
        "size": size,
        "files": files,
        "summary": (d.metadata.get("Summary") or "")[:200],
    })
json.dump({"packages": out, "prefix": sys.prefix,
           "base_prefix": getattr(sys, "base_prefix", sys.prefix),
           "version": "%d.%d" % sys.version_info[:2]}, sys.stdout)
"""


class PipBackend(Backend):
    source = Source.PIP
    tool = "pip"

    def __init__(
        self,
        python: str | None = None,
        search_paths: list[str] | None = None,
    ) -> None:
        # Defaults to the interpreter AppSweep runs under, which is the one
        # whose `pip` the user gets from the shell in the common case.
        self.python = python or sys.executable or "python3"
        # Optional explicit site directories, e.g. to inspect a virtual
        # environment or a --target installation.
        self.search_paths = list(search_paths or [])
        self._distro_managed = 0

    @classmethod
    def available(cls) -> bool:
        exe = sys.executable or "python3"
        if not exe:
            return False
        res = run([exe, "-c", "import importlib.metadata"], timeout=30)
        return res.ok

    # ---------------------------------------------------------------- listing
    def _probe(self) -> dict:
        # -I isolates the probe from the inspected environment's own sitecustomize
        # and from the current directory, but still reads its site-packages.
        argv = [self.python, "-I", "-c", _PROBE, *self.search_paths]
        res = run(argv, timeout=120)
        if not res.ok or not res.out.strip():
            return {"packages": []}
        try:
            return json.loads(res.out)
        except json.JSONDecodeError:
            return {"packages": []}

    def list_apps(self) -> list[App]:
        data = self._probe()
        pyver = data.get("version", "")
        self._distro_managed = 0
        out: list[App] = []

        for pkg in data.get("packages", []):
            location = pkg.get("location", "")
            if _is_distro_managed(location):
                # Reported by the system backend under its real package
                # name; listing it twice would invite a dangerous removal.
                self._distro_managed += 1
                continue

            scripts = pkg.get("scripts") or []
            name = pkg["name"]
            writable = _writable(pkg.get("dist_info") or location)
            out.append(
                App(
                    ident=name,
                    name=name,
                    version=pkg.get("version", ""),
                    source=Source.PIP,
                    size_bytes=int(pkg.get("size") or 0),
                    summary=pkg.get("summary") or location,
                    tokens=tokenize(name, name.replace("-", "_"), *scripts),
                    # A Python package with no command of its own is a
                    # library that something else depends on.
                    is_library=not scripts,
                    extra={
                        "location": location,
                        "scripts": ",".join(scripts),
                        "python": pyver,
                        "needs_root": "" if writable else "1",
                        "critical": "1" if name.lower() in PROTECTED else "",
                    },
                )
            )
        return out

    @property
    def distro_managed_count(self) -> int:
        """How many packages were skipped as distribution-owned."""
        return self._distro_managed

    # ---------------------------------------------------------------- removal
    def removal_plan(self, app: App, *, purge: bool, autoremove: bool) -> Plan:
        plan = Plan()
        if app.extra.get("critical"):
            plan.notes.append(
                _("“{pkg}” is part of pip's own machinery; removing it would "
                  "leave you unable to install Python packages. AppSweep will "
                  "not remove it.").format(pkg=app.ident)
            )
            return plan
        if _is_distro_managed(app.extra.get("location", "")):
            plan.notes.append(
                _("“{pkg}” was installed by your distribution, not by pip. "
                  "Remove it through the system package manager instead.")
                .format(pkg=app.ident)
            )
            return plan

        plan.steps.append(
            Step(
                [self.python, "-m", "pip", "uninstall", "-y", app.ident],
                needs_root=bool(app.extra.get("needs_root")),
                description=_("Uninstall the Python package {pkg}").format(
                    pkg=app.ident),
            )
        )
        plan.notes.append(
            _("pip removes only this package. Anything it pulled in as a "
              "dependency stays, because pip keeps no record of what was "
              "installed to satisfy what.")
        )
        return plan

    def cache_cleanup_plan(self) -> Plan:
        plan = Plan()
        plan.steps.append(
            Step([self.python, "-m", "pip", "cache", "purge"],
                 needs_root=False,
                 description=_("Empty pip's wheel cache"))
        )
        return plan

    def cache_size(self) -> int:
        res = run([self.python, "-m", "pip", "cache", "dir"], timeout=30)
        if not res.ok:
            return 0
        d = res.out.strip()
        if not d or not os.path.isdir(d):
            return 0
        from ..util import dir_size

        return dir_size(d)


def _is_distro_managed(location: str) -> bool:
    if not location:
        return False
    if any(m in location for m in _DISTRO_MARKERS):
        return True
    # A file the package database claims is not pip's to remove.
    if location.startswith("/usr/lib") or location.startswith("/usr/lib64"):
        return True
    return False


def _writable(path: str) -> bool:
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    return os.access(p, os.W_OK)
