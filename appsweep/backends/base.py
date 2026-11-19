"""Backend interface. One subclass per packaging format."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import App, Plan, Source


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
