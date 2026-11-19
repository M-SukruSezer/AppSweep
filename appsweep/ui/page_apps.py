"""The Applications page: everything installed, from every source."""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk  # noqa: E402

from .. import icons
from ..backends import detect
from ..i18n import N_, _
from ..models import App, Source
from ..util import human_size  # noqa: E402
from . import appicon
from .items import AppItem
from .task import run_async


def _source_choices() -> tuple[tuple[str, Source | None], ...]:
    # Built lazily so the translation catalogue is loaded by the time the
    # labels are produced.
    return (
        (_("All sources"), None),
        ("APT / dpkg", Source.APT),
        ("DNF / rpm", Source.DNF),
        ("Pacman", Source.PACMAN),
        ("Flatpak", Source.FLATPAK),
        ("Snap", Source.SNAP),
        ("AppImage", Source.APPIMAGE),
        ("pip", Source.PIP),
        ("pipx", Source.PIPX),
        ("npm", Source.NPM),
        ("cargo", Source.CARGO),
    )


_BADGE_CSS = {
    Source.APT: "badge-apt",
    Source.DNF: "badge-dnf",
    Source.PACMAN: "badge-pacman",
    Source.FLATPAK: "badge-flatpak",
    Source.SNAP: "badge-snap",
    Source.APPIMAGE: "badge-appimage",
    Source.PIP: "badge-pip",
    Source.PIPX: "badge-pipx",
    Source.NPM: "badge-npm",
    Source.CARGO: "badge-cargo",
}


class AppsPage(Adw.Bin):
    __gtype_name__ = "AppSweepAppsPage"

    def __init__(self, on_uninstall: Callable[[list[App]], None]) -> None:
        super().__init__()
        self._on_uninstall = on_uninstall
        self._all: list[App] = []
        self.backends: dict[Source, object] = {}
        self._loading = True
        self._choices = _source_choices()

        self.store = Gio.ListStore(item_type=AppItem)
        self.filter = Gtk.CustomFilter.new(self._filter_fn)
        filtered = Gtk.FilterListModel(model=self.store, filter=self.filter)
        self.sorter = Gtk.CustomSorter.new(self._sort_fn)
        sorted_model = Gtk.SortListModel(model=filtered, sorter=self.sorter)
        self.model = sorted_model
        self.selection = Gtk.NoSelection(model=sorted_model)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._row_setup)
        factory.connect("bind", self._row_bind)
        factory.connect("unbind", self._row_unbind)

        self.list_view = Gtk.ListView(
            model=self.selection, factory=factory, single_click_activate=False
        )
        self.list_view.add_css_class("navigation-sidebar")

        self.scroller = Gtk.ScrolledWindow(
            hexpand=True, vexpand=True, child=self.list_view
        )

        self.empty = Adw.StatusPage(
            icon_name="edit-find-symbolic",
            title=_("No matches"),
            description=_("Try a different search, or widen the filters."),
        )
        self.spinner = Adw.StatusPage(
            title=_("Reading installed software"),
            description=_("Querying every package manager on this system…"),
            child=Gtk.Spinner(spinning=True, width_request=32, height_request=32),
        )

        self.body = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.body.add_named(self.spinner, "loading")
        self.body.add_named(self.scroller, "list")
        self.body.add_named(self.empty, "empty")
        self.body.set_visible_child_name("loading")

        self.set_child(self._build(self.body))

    # ------------------------------------------------------------- chrome
    def _build(self, body: Gtk.Widget) -> Gtk.Widget:
        self.search = Gtk.SearchEntry(
            placeholder_text=_("Search installed software"), hexpand=True
        )
        self.search.connect("search-changed", lambda *_a: self._refilter())

        self.source_drop = Gtk.DropDown.new_from_strings(
            [c[0] for c in self._choices]
        )
        self.source_drop.connect("notify::selected", lambda *_a: self._refilter())

        self.sort_drop = Gtk.DropDown.new_from_strings(
            [_("Largest first"), _("Name"), _("Source")]
        )
        self.sort_drop.connect("notify::selected", lambda *_a: self._resort())

        self.system_toggle = Gtk.ToggleButton(
            icon_name="applications-engineering-symbolic",
            tooltip_text=_("Also show libraries, runtimes and system packages"),
        )
        self.system_toggle.connect("toggled", lambda *_a: self._refilter())

        self.orphan_toggle = Gtk.ToggleButton(
            icon_name="user-trash-symbolic",
            tooltip_text=_("Show only packages nothing depends on any more"),
        )
        self.orphan_toggle.connect("toggled", lambda *_a: self._refilter())

        bar = Gtk.Box(spacing=6, margin_top=6, margin_bottom=6,
                      margin_start=12, margin_end=12)
        bar.append(self.search)
        bar.append(self.source_drop)
        bar.append(self.sort_drop)
        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL,
                                 margin_top=4, margin_bottom=4))
        bar.append(self.system_toggle)
        bar.append(self.orphan_toggle)

        self.summary = Gtk.Label(xalign=0, margin_start=12, margin_bottom=6)
        self.summary.add_css_class("dim-label")
        self.summary.add_css_class("caption")

        # Selection action bar, revealed only when something is ticked.
        self.sel_label = Gtk.Label(xalign=0, hexpand=True)
        self.sel_label.add_css_class("heading")
        clear = Gtk.Button(label=_("Clear"))
        clear.connect("clicked", lambda *_a: self.clear_selection())
        self.uninstall_btn = Gtk.Button(label=_("Uninstall…"))
        self.uninstall_btn.add_css_class("destructive-action")
        self.uninstall_btn.connect("clicked", self._do_uninstall)

        action_box = Gtk.Box(spacing=12, margin_top=8, margin_bottom=8,
                             margin_start=12, margin_end=12)
        action_box.append(self.sel_label)
        action_box.append(clear)
        action_box.append(self.uninstall_btn)
        self.action_revealer = Gtk.Revealer(child=action_box, reveal_child=False)
        self.action_revealer.add_css_class("toolbar")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(bar)
        box.append(self.summary)
        box.append(Gtk.Separator())
        box.append(body)
        box.append(self.action_revealer)
        return box

    # -------------------------------------------------------------- rows
    def _row_setup(self, _factory, list_item: Gtk.ListItem) -> None:
        check = Gtk.CheckButton(valign=Gtk.Align.CENTER)

        image = Gtk.Image(pixel_size=32, valign=Gtk.Align.CENTER)

        name = Gtk.Label(xalign=0, ellipsize=3)
        name.add_css_class("body")
        sub = Gtk.Label(xalign=0, ellipsize=3)
        sub.add_css_class("caption")
        sub.add_css_class("dim-label")
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True,
                       valign=Gtk.Align.CENTER)
        text.append(name)
        text.append(sub)

        badge = Gtk.Label()
        badge.add_css_class("caption")
        badge.add_css_class("as-badge")
        badge.set_valign(Gtk.Align.CENTER)

        size = Gtk.Label(xalign=1, width_chars=9)
        size.add_css_class("numeric")
        size.set_valign(Gtk.Align.CENTER)

        row = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6,
                      margin_start=6, margin_end=6)
        row.append(check)
        row.append(image)
        row.append(text)
        row.append(badge)
        row.append(size)

        list_item.set_child(row)
        list_item._widgets = (check, image, name, sub, badge, size)
        list_item._handler = None

    def _row_bind(self, _factory, list_item: Gtk.ListItem) -> None:
        item: AppItem = list_item.get_item()
        check, image, name, sub, badge, size = list_item._widgets
        app = item.app

        appicon.reset(image)
        appicon.apply(image, app)

        name.set_text(app.name)
        bits = [app.version] if app.version else []
        if app.summary:
            bits.append(app.summary)
        if app.is_orphan:
            bits.append(_("no longer needed by anything"))
        sub.set_text(" · ".join(bits) or app.ident)
        sub.set_tooltip_text(app.ident)

        badge.set_text(app.source.value)
        for css in _BADGE_CSS.values():
            badge.remove_css_class(css)
        badge.add_css_class(_BADGE_CSS[app.source])

        size.set_text(human_size(app.size_bytes))

        check.set_active(item.selected)
        list_item._handler = check.connect(
            "toggled", self._on_check_toggled, item
        )
        if app.extra.get("critical"):
            check.set_sensitive(False)
            check.set_tooltip_text(
                _("Essential to the system — AppSweep will not remove it.")
            )
        else:
            check.set_sensitive(True)
            check.set_tooltip_text(None)

    def _row_unbind(self, _factory, list_item: Gtk.ListItem) -> None:
        check = list_item._widgets[0]
        if list_item._handler is not None:
            check.disconnect(list_item._handler)
            list_item._handler = None

    def _on_check_toggled(self, check: Gtk.CheckButton, item: AppItem) -> None:
        item.selected = check.get_active()
        self._update_selection_bar()

    # ------------------------------------------------------------ loading
    def reload(self, on_done: Callable[[], None] | None = None) -> None:
        self._loading = True
        self.body.set_visible_child_name("loading")
        self.summary.set_text("")

        def work() -> tuple[list[App], dict]:
            backends = detect()
            apps: list[App] = []
            for b in backends:
                apps += b.list_apps()
            # Reading 180-odd desktop files and matching them up is cheap,
            # but it is still file I/O, so it happens here rather than
            # while rows are being drawn.
            icons.annotate(apps)
            return apps, {b.source: b for b in backends}

        def done(result) -> None:
            apps, backends = result
            self._all = apps
            self.backends = backends
            self.store.remove_all()
            for a in apps:
                self.store.append(AppItem(a))
            self._loading = False
            self._refilter()
            if on_done:
                on_done()

        run_async(work, done)

    # ---------------------------------------------------------- filtering
    def _selected_source(self) -> Source | None:
        return self._choices[self.source_drop.get_selected()][1]

    def _filter_fn(self, item: AppItem, *_user_data) -> bool:
        app = item.app
        if not self.system_toggle.get_active() and app.is_library:
            return False
        if self.orphan_toggle.get_active() and not app.is_orphan:
            return False
        src = self._selected_source()
        if src is not None and app.source is not src:
            return False
        q = self.search.get_text().strip().lower()
        if q:
            haystack = f"{app.name} {app.ident} {app.summary}".lower()
            if not all(part in haystack for part in q.split()):
                return False
        return True

    def _sort_fn(self, a: AppItem, b: AppItem, *_user_data) -> int:
        mode = self.sort_drop.get_selected()
        if mode == 0:
            d = b.app.size_bytes - a.app.size_bytes
            if d:
                return 1 if d > 0 else -1
            return _cmp(a.app.name.lower(), b.app.name.lower())
        if mode == 2:
            d = _cmp(a.app.source.value, b.app.source.value)
            if d:
                return d
        return _cmp(a.app.name.lower(), b.app.name.lower())

    def _refilter(self) -> None:
        self.filter.changed(Gtk.FilterChange.DIFFERENT)
        self._update_summary()

    def _resort(self) -> None:
        self.sorter.changed(Gtk.SorterChange.DIFFERENT)

    def _update_summary(self) -> None:
        if self._loading:
            return
        n = self.model.get_n_items()
        total = 0
        for i in range(n):
            total += self.model.get_item(i).app.size_bytes
        self.summary.set_text(
            _("{shown} shown of {total} installed · {size} on disk").format(
                shown=n, total=len(self._all), size=human_size(total)
            )
        )
        self.body.set_visible_child_name("list" if n else "empty")

    # ---------------------------------------------------------- selection
    def selected_apps(self) -> list[App]:
        out = []
        for i in range(self.store.get_n_items()):
            item = self.store.get_item(i)
            if item.selected:
                out.append(item.app)
        return out

    def clear_selection(self) -> None:
        for i in range(self.store.get_n_items()):
            self.store.get_item(i).selected = False
        # Force visible rows to re-read the model.
        self.filter.changed(Gtk.FilterChange.DIFFERENT)
        self._update_selection_bar()

    def _update_selection_bar(self) -> None:
        chosen = self.selected_apps()
        if not chosen:
            self.action_revealer.set_reveal_child(False)
            return
        total = sum(a.size_bytes for a in chosen)
        self.sel_label.set_text(
            N_("{n} app selected · {size}",
               "{n} apps selected · {size}", len(chosen)).format(
                   n=len(chosen), size=human_size(total))
        )
        self.uninstall_btn.set_label(
            _("Uninstall…") if len(chosen) == 1
            else _("Uninstall {n}…").format(n=len(chosen))
        )
        self.action_revealer.set_reveal_child(True)

    def _do_uninstall(self, _btn) -> None:
        chosen = self.selected_apps()
        if chosen:
            self._on_uninstall(chosen)

    @property
    def all_apps(self) -> list[App]:
        return self._all


def _cmp(a, b) -> int:
    return (a > b) - (a < b)
