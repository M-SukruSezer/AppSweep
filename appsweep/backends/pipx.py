"""Python applications installed with pipx.

pipx gives each application its own virtual environment, so these are both
easy to attribute and often surprisingly large — a handful of tools can
hold several hundred megabytes of duplicated dependencies.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..i18n import _
from ..models import App, Plan, Source, Step
from ..util import dir_size, have, run, tokenize
from .base import Backend


def _venv_root() -> Path:
    for env in ("PIPX_HOME",):
        v = os.environ.get(env)
        if v:
            return Path(v) / "venvs"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local/share"
    return base / "pipx/venvs"


class PipxBackend(Backend):
    source = Source.PIPX
    tool = "pipx"

    @classmethod
    def available(cls) -> bool:
        return have("pipx")

    # ---------------------------------------------------------------- listing
    def list_apps(self) -> list[App]:
        res = run(["pipx", "list", "--json"], timeout=120)
        if not res.out.strip():
            return []
        try:
            data = json.loads(res.out)
        except json.JSONDecodeError:
            return []

        root = _venv_root()
        out: list[App] = []
        for venv_name, venv in (data.get("venvs") or {}).items():
            meta = (venv or {}).get("metadata") or {}
            main = meta.get("main_package") or {}
            name = main.get("package") or venv_name
            version = main.get("package_version") or ""
            apps = main.get("apps") or []

            venv_dir = meta.get("venv_dir") or str(root / venv_name)
            size = dir_size(venv_dir) if os.path.isdir(venv_dir) else 0

            out.append(
                App(
                    ident=venv_name,
                    name=name,
                    version=str(version),
                    source=Source.PIPX,
                    size_bytes=size,
                    summary=(
                        _("provides: {bins}").format(bins=", ".join(apps))
                        if apps else venv_dir
                    ),
                    tokens=tokenize(name, venv_name,
                                    name.replace("-", "_"), *apps),
                    is_library=False,
                    extra={"venv_dir": venv_dir, "apps": ",".join(apps)},
                )
            )
        return out

    # ---------------------------------------------------------------- removal
    def removal_plan(self, app: App, *, purge: bool, autoremove: bool) -> Plan:
        plan = Plan()
        plan.steps.append(
            Step(
                ["pipx", "uninstall", app.ident],
                needs_root=False,
                description=_("Uninstall the pipx application {pkg}").format(
                    pkg=app.ident),
            )
        )
        plan.notes.append(
            _("This removes the whole virtual environment pipx made for it, "
              "including its dependencies.")
        )
        return plan

    def cache_cleanup_plan(self) -> Plan:
        plan = Plan()
        # pipx keeps short-lived venvs for `pipx run` under its cache.
        cache = _venv_root().parent / ".cache"
        if cache.is_dir():
            plan.steps.append(
                Step(["pipx", "environment", "--value", "PIPX_HOME"],
                     needs_root=False,
                     description=_("Locate pipx's cache"))
            )
        return plan

    def cache_size(self) -> int:
        cache = _venv_root().parent / ".cache"
        return dir_size(str(cache)) if cache.is_dir() else 0
