"""Main window: three pages, one shared snapshot of installed software."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk  # noqa: E402

from .. import APP_ID
from ..i18n import N_, _
from ..models import App
from .page_apps import AppsPage
from .page_cleanup import CleanupPage
from .page_leftovers import LeftoversPage
from .removal import RemovalDialog


class MainWindow(Adw.ApplicationWindow):
    __gtype_name__ = "AppSweepWindow"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.set_title("AppSweep")
        self.set_icon_name(APP_ID)
        self.set_default_size(960, 720)
        self.set_size_request(420, 480)

        self.apps_page = AppsPage(on_uninstall=self.open_removal)
        self.leftovers_page = LeftoversPage(
            get_installed=lambda: self.apps_page.all_apps, toast=self.toast
        )
        self.cleanup_page = CleanupPage(toast=self.toast)

        self.stack = Adw.ViewStack()
        self.stack.add_titled_with_icon(
            self.apps_page, "apps", _("Applications"), "view-grid-symbolic"
        )
        self.stack.add_titled_with_icon(
            self.leftovers_page, "leftovers", _("Leftovers"),
            "folder-saved-search-symbolic",
        )
        self.stack.add_titled_with_icon(
            self.cleanup_page, "reclaim", _("Reclaim"), "user-trash-symbolic"
        )
        self.stack.connect("notify::visible-child-name", self._on_page_changed)

        switcher = Adw.ViewSwitcher(
            stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE
        )
        header = Adw.HeaderBar(title_widget=switcher)

        refresh = Gtk.Button(
            icon_name="view-refresh-symbolic",
            tooltip_text=_("Rescan the system")
        )
        refresh.connect("clicked", lambda *_: self.reload())
        header.pack_start(refresh)

        menu = Gio.Menu()
        menu.append(_("Preferences"), "app.preferences")
        menu.append(_("Keyboard Shortcuts"), "app.shortcuts")
        menu.append(_("About AppSweep"), "app.about")
        menu_btn = Gtk.MenuButton(
            icon_name="open-menu-symbolic", menu_model=menu,
            tooltip_text=_("Main menu"),
        )
        header.pack_end(menu_btn)

        self.banner = Adw.Banner(
            title=_("AppSweep deletes files. Every removal is listed before "
                    "it runs, and leftovers go to the trash by default."),
            revealed=False,
        )
        self.banner.set_button_label(_("Got it"))
        self.banner.connect("button-clicked",
                            lambda *_: self.banner.set_revealed(False))

        bottom = Adw.ViewSwitcherBar(stack=self.stack)

        view = Adw.ToolbarView(content=self.stack)
        view.add_top_bar(header)
        view.add_top_bar(self.banner)
        view.add_bottom_bar(bottom)

        self.toasts = Adw.ToastOverlay(child=view)
        self.set_content(self.toasts)

        # Narrow windows get the bottom switcher instead of the header one.
        narrow_title = Adw.WindowTitle(title="AppSweep")
        bp = Adw.Breakpoint.new(
            Adw.BreakpointCondition.parse("max-width: 620px")
        )
        bp.add_setter(bottom, "reveal", True)
        bp.add_setter(header, "title-widget", narrow_title)
        self.add_breakpoint(bp)

        self.reload()

    # ----------------------------------------------------------------- api
    def toast(self, message: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=message, timeout=4))

    def reload(self) -> None:
        self.apps_page.reload(on_done=self._after_reload)
        self.cleanup_page.refresh()

    def _after_reload(self) -> None:
        n = len(self.apps_page.all_apps)
        real = sum(1 for a in self.apps_page.all_apps if not a.is_library)
        self.toast(
            N_("Found {real} application among {total} installed packages.",
               "Found {real} applications among {total} installed packages.",
               real).format(real=real, total=n)
        )

    def _on_page_changed(self, *_args) -> None:
        name = self.stack.get_visible_child_name()
        self.banner.set_revealed(name in ("leftovers", "reclaim"))

    def open_removal(self, apps: list[App]) -> None:
        dlg = RemovalDialog(
            apps,
            self.apps_page.all_apps,
            self.apps_page.backends,
            on_finished=self._after_removal,
        )
        dlg.present(self)

    def _after_removal(self, ok: bool) -> None:
        self.apps_page.clear_selection()
        self.reload()
