"""Rust binaries installed with ``cargo install``.

``cargo install --list`` is the only record of these. Nothing else on the
system knows they exist, which is exactly why they go unnoticed.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from ..i18n import _
from ..models import App, Plan, Source, Step
from ..util import dir_size, have, run, tokenize
from .base import Backend

# "ripgrep v14.1.0:" or "ripgrep v14.1.0 (/path/to/src):"
_HEAD = re.compile(r"^(\S+)\s+v([^\s:]+)(?:\s+\(([^)]*)\))?:\s*$")


def cargo_home() -> Path:
    env = os.environ.get("CARGO_HOME")
    if env:
        return Path(env)
    return Path.home() / ".cargo"


class CargoBackend(Backend):
    source = Source.CARGO
    tool = "cargo"

    @classmethod
    def available(cls) -> bool:
        return have("cargo")

    # ---------------------------------------------------------------- listing
    def list_apps(self) -> list[App]:
        res = run(["cargo", "install", "--list"], timeout=90)
        if not res.ok and not res.out:
            return []

        bindir = cargo_home() / "bin"
        out: list[App] = []
        current: dict | None = None

        def flush() -> None:
            if current is None:
                return
            size = 0
            for b in current["bins"]:
                try:
                    size += os.path.getsize(bindir / b)
                except OSError:
                    continue
            out.append(
                App(
                    ident=current["name"],
                    name=current["name"],
                    version=current["version"],
                    source=Source.CARGO,
                    size_bytes=size,
                    summary=(
                        _("provides: {bins}").format(
                            bins=", ".join(current["bins"]))
                        if current["bins"] else str(bindir)
                    ),
                    tokens=tokenize(current["name"],
                                    current["name"].replace("-", "_"),
                                    *current["bins"]),
                    is_library=False,
                    extra={
                        "bins": ",".join(current["bins"]),
                        "source": current["source"] or "",
                    },
                )
            )

        for line in res.out.splitlines():
            m = _HEAD.match(line)
            if m:
                flush()
                current = {"name": m.group(1), "version": m.group(2),
                           "source": m.group(3), "bins": []}
            elif line.startswith((" ", "\t")) and current is not None:
                binary = line.strip()
                if binary:
                    current["bins"].append(binary)
        flush()
        return out

    # ---------------------------------------------------------------- removal
    def removal_plan(self, app: App, *, purge: bool, autoremove: bool) -> Plan:
        plan = Plan()
        plan.steps.append(
            Step(
                ["cargo", "uninstall", app.ident],
                # cargo installs into CARGO_HOME, which lives in $HOME.
                needs_root=False,
                description=_("Uninstall the Rust binary {pkg}").format(
                    pkg=app.ident),
            )
        )
        return plan

    def cache_cleanup_plan(self) -> Plan:
        plan = Plan()
        if have("cargo-cache"):
            plan.steps.append(
                Step(["cargo", "cache", "--autoclean"], needs_root=False,
                     description=_("Trim cargo's registry cache"))
            )
        else:
            plan.notes.append(
                _("Cargo has no built-in command to prune its registry "
                  "cache. Install cargo-cache (cargo install cargo-cache) "
                  "and AppSweep will offer to trim it.")
            )
        return plan

    def cache_size(self) -> int:
        total = 0
        for sub in ("registry/cache", "registry/src", "git/db",
                    "git/checkouts"):
            d = cargo_home() / sub
            if d.is_dir():
                total += dir_size(str(d))
        return total
