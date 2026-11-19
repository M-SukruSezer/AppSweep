"""Globally installed npm packages.

Only the global prefix is considered. A project's ``node_modules`` belongs
to that project, not to the system, and removing it behind the user's back
would break their checkout — ``npm install`` is how it is meant to come and
go.
"""
from __future__ import annotations

import json
import os

from ..i18n import _
from ..models import App, Plan, Source, Step
from ..util import dir_size, have, run, tokenize
from .base import Backend

#: Shipped with Node itself; removing them cripples the toolchain.
PROTECTED = frozenset({"npm", "corepack"})


class NpmBackend(Backend):
    source = Source.NPM
    tool = "npm"

    def __init__(self, prefix: str | None = None) -> None:
        # An explicit prefix is mainly useful for tests; normally npm's own
        # configured global prefix is the right one.
        self.prefix = prefix
        self._root: str | None = None

    @classmethod
    def available(cls) -> bool:
        return have("npm")

    def _argv(self, *args: str) -> list[str]:
        argv = ["npm", *args]
        if self.prefix:
            argv += ["--prefix", self.prefix]
        return argv

    def root(self) -> str:
        if self._root is None:
            res = run(self._argv("root", "-g"), timeout=60)
            self._root = res.out.strip() if res.ok else ""
        return self._root

    # ---------------------------------------------------------------- listing
    def list_apps(self) -> list[App]:
        res = run(self._argv("ls", "-g", "--depth=0", "--json"), timeout=90)
        if not res.out.strip():
            return []
        try:
            data = json.loads(res.out)
        except json.JSONDecodeError:
            return []

        deps = data.get("dependencies") or {}
        root = self.root()
        writable = bool(root) and os.access(root, os.W_OK)
        out: list[App] = []
        for name, info in deps.items():
            if not isinstance(info, dict):
                info = {}
            pkg_dir = os.path.join(root, *name.split("/")) if root else ""
            size = dir_size(pkg_dir) if pkg_dir and os.path.isdir(pkg_dir) else 0
            # A scoped name like @angular/cli also answers to "cli".
            short = name.rsplit("/", 1)[-1]
            out.append(
                App(
                    ident=name,
                    name=name,
                    version=str(info.get("version") or ""),
                    source=Source.NPM,
                    size_bytes=size,
                    summary=root,
                    tokens=tokenize(name, short, name.lstrip("@")),
                    # Global installs are nearly always command line tools;
                    # a global library is the unusual case.
                    is_library=False,
                    extra={
                        "root": root,
                        "needs_root": "" if writable else "1",
                        "critical": "1" if name in PROTECTED else "",
                    },
                )
            )
        return out

    # ---------------------------------------------------------------- removal
    def removal_plan(self, app: App, *, purge: bool, autoremove: bool) -> Plan:
        plan = Plan()
        if app.extra.get("critical"):
            plan.notes.append(
                _("“{pkg}” ships with Node.js itself. AppSweep will not "
                  "remove it.").format(pkg=app.ident)
            )
            return plan
        plan.steps.append(
            Step(
                self._argv("uninstall", "-g", app.ident),
                needs_root=bool(app.extra.get("needs_root")),
                description=_("Uninstall the global npm package {pkg}").format(
                    pkg=app.ident),
            )
        )
        if app.extra.get("needs_root"):
            plan.notes.append(
                _("The global npm prefix is {path}, which your user cannot "
                  "write to, so this step needs administrator access.")
                .format(path=app.extra.get("root") or "/usr/local")
            )
        return plan

    def cache_cleanup_plan(self) -> Plan:
        plan = Plan()
        plan.steps.append(
            Step(self._argv("cache", "clean", "--force"), needs_root=False,
                 description=_("Empty npm's download cache"))
        )
        return plan

    def cache_size(self) -> int:
        res = run(self._argv("config", "get", "cache"), timeout=60)
        d = res.out.strip()
        if not d or not os.path.isdir(d):
            return 0
        return dir_size(d)
