"""The Leftovers page: residue from software removed long ago."""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from ..executor import execute
from ..i18n import N_, _
from ..leftovers import scan_unclaimed, total_size
from ..models import App, Plan, Residue
from ..util import human_size  # noqa: E402
from .task import run_async

def _conf_label(confidence: str) -> tuple[str, str]:
    return {
        "high": (_("Certain"), "as-conf-high"),
        "medium": (_("Likely"), "as-conf-medium"),
        "low": (_("Guess"), "as-conf-low"),
    }[confidence]


def _kind_label(kind: str) -> str:
    return {
        "config": _("settings"),
        "data": _("data"),
        "cache": _("cache"),
        "state": _("state"),
        "system": _("system"),
    }.get(kind, kind)


class LeftoversPage(Adw.Bin):
    __gtype_name__ = "AppSweepLeftoversPage"

    def __init__(self, get_installed: Callable[[], list[App]],
                 toast: Callable[[str], None]) -> None:
        super().__init__()
        self._get_installed = get_installed
        self._toast = toast
        self.rows: list[tuple[Gtk.CheckButton, Residue]] = []

        self.intro = Adw.StatusPage(
            icon_name="folder-saved-search-symbolic",
            title=_("Find what uninstalling left behind"),
            description=_(
                "Package managers remove the program but keep your settings, "
                "caches and data. Over years that adds up, and nothing "
                "cleans it up for you.\n\n"
                "AppSweep lists directories under your home folder, /etc and "
                "/var/lib that no installed app accounts for. It matches by "
                "name, so it shows you how sure it is and never removes "
                "anything you have not ticked."
            ),
        )
        scan_btn = Gtk.Button(label=_("Scan for leftovers"),
                              halign=Gtk.Align.CENTER)
        scan_btn.add_css_class("suggested-action")
        scan_btn.add_css_class("pill")
        scan_btn.connect("clicked", lambda *_: self.scan())
        self.intro.set_child(scan_btn)

        self.busy = Adw.StatusPage(
            title=_("Scanning"),
            description=_("Measuring directories and checking them against "
                          "the package database…"),
            child=Gtk.Spinner(spinning=True, width_request=32, height_request=32),
        )

        self.results_group = Adw.PreferencesGroup()
        self.opts_group = Adw.PreferencesGroup(title=_("Options"))
        self.cache_row = Adw.SwitchRow(
            title=_("Include caches"),
            subtitle=_("~/.cache regenerates on its own, so it is skipped "
                       "by default"),
        )
        self.cache_row.connect("notify::active", lambda *_: self.scan())
        self.system_row = Adw.SwitchRow(
            title=_("Include system directories"),
            subtitle=_("/etc, /var/lib and /opt — needs administrator access "
                       "to clean"),
            active=True,
        )
        self.system_row.connect("notify::active", lambda *_: self.scan())
        self.opts_group.add(self.cache_row)
        self.opts_group.add(self.system_row)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                        margin_top=18, margin_bottom=18,
                        margin_start=18, margin_end=18)
        inner.append(self.results_group)
        inner.append(self.opts_group)
        self.results = Gtk.ScrolledWindow(child=inner, vexpand=True)

        self.sel_label = Gtk.Label(xalign=0, hexpand=True)
        self.sel_label.add_css_class("heading")
        rescan = Gtk.Button(label=_("Rescan"))
        rescan.connect("clicked", lambda *_: self.scan())
        self.del_btn = Gtk.Button(label=_("Remove selected"))
        self.del_btn.add_css_class("destructive-action")
        self.del_btn.connect("clicked", self._on_remove)
        bar = Gtk.Box(spacing=12, margin_top=8, margin_bottom=8,
                      margin_start=12, margin_end=12)
        bar.append(self.sel_label)
        bar.append(rescan)
        bar.append(self.del_btn)
        self.action_revealer = Gtk.Revealer(child=bar, reveal_child=False)
        self.action_revealer.add_css_class("toolbar")

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(self.intro, "intro")
        self.stack.add_named(self.busy, "busy")
        self.stack.add_named(self.results, "results")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.stack)
        box.append(self.action_revealer)
        self.set_child(box)

    # ------------------------------------------------------------- scanning
    def scan(self) -> None:
        installed = self._get_installed()
        if not installed:
            self._toast(_("Still reading installed software — try again "
                          "in a moment."))
            return
        self.stack.set_visible_child_name("busy")
        self.action_revealer.set_reveal_child(False)
        include_cache = self.cache_row.get_active()
        include_system = self.system_row.get_active()

        def work() -> list[Residue]:
            return scan_unclaimed(
                installed,
                include_cache=include_cache,
                include_system=include_system,
            )

        run_async(work, self._on_scanned)

    def _on_scanned(self, residues: list[Residue]) -> None:
        for check, _res in self.rows:
            row = check.get_ancestor(Adw.ActionRow)
            if row is not None:
                self.results_group.remove(row)
        self.rows = []

        if not residues:
            self.intro.set_icon_name("object-select-symbolic")
            self.intro.set_title(_("Nothing unaccounted for"))
            self.intro.set_description(
                _("Every settings directory on this system belongs to "
                  "something you still have installed.")
            )
            self.stack.set_visible_child_name("intro")
            return

        self.results_group.set_title(
            N_("{n} directory no installed app claims",
               "{n} directories no installed app claims",
               len(residues)).format(n=len(residues))
        )
        self.results_group.set_description(
            _("{size} in total. “Guess” entries are often legitimate — "
              "open the path before ticking it.").format(
                  size=human_size(total_size(residues)))
        )
        for r in residues:
            label, css = _conf_label(r.confidence)
            row = Adw.ActionRow(
                title=GLib.markup_escape_text(_shorten(r.path)),
                subtitle=GLib.markup_escape_text(
                    _kind_label(r.kind)
                    + (_(" · administrator access") if r.needs_root else "")
                ),
            )
            row.set_tooltip_text(r.path)
            check = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            check.connect("toggled", lambda *_: self._update_bar())
            row.add_prefix(check)

            badge = Gtk.Label(label=label, valign=Gtk.Align.CENTER)
            badge.add_css_class("caption")
            badge.add_css_class("as-badge")
            badge.add_css_class(css)
            row.add_suffix(badge)

            size = Gtk.Label(label=human_size(r.size_bytes),
                             valign=Gtk.Align.CENTER)
            size.add_css_class("dim-label")
            size.add_css_class("numeric")
            row.add_suffix(size)

            open_btn = Gtk.Button(
                icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER,
                tooltip_text=_("Open this folder in Files"),
            )
            open_btn.add_css_class("flat")
            open_btn.connect("clicked", self._open, r.path)
            row.add_suffix(open_btn)

            self.results_group.add(row)
            self.rows.append((check, r))

        self.stack.set_visible_child_name("results")
        self._update_bar()

    def _open(self, _btn, path: str) -> None:
        Gtk.FileLauncher(file=Gio_file(path)).launch(
            self.get_root(), None, None
        )

    # ------------------------------------------------------------ selection
    def _update_bar(self) -> None:
        chosen = [r for c, r in self.rows if c.get_active()]
        if not chosen:
            self.action_revealer.set_reveal_child(False)
            return
        self.sel_label.set_text(
            _("{n} selected · {size}").format(
                n=len(chosen), size=human_size(total_size(chosen)))
        )
        self.action_revealer.set_reveal_child(True)

    def _on_remove(self, _btn) -> None:
        chosen = [r for c, r in self.rows if c.get_active()]
        if not chosen:
            return
        root = [r for r in chosen if r.needs_root]
        body = (
            N_("{n} directory, {size}.", "{n} directories, {size}.",
               len(chosen)).format(n=len(chosen),
                                   size=human_size(total_size(chosen)))
            + "\n\n"
            + "\n".join(f"• {_shorten(r.path)}" for r in chosen[:10])
            + ("\n…" if len(chosen) > 10 else "")
        )
        if root:
            body += "\n\n" + N_(
                "{n} is outside your home directory and will be deleted "
                "outright, with administrator access.",
                "{n} are outside your home directory and will be deleted "
                "outright, with administrator access.", len(root)
            ).format(n=len(root))
        else:
            body += "\n\n" + _(
                "These go to the trash, so you can still get them back.")

        dlg = Adw.AlertDialog(heading=_("Remove these leftovers?"), body=body)
        dlg.add_response("cancel", _("Cancel"))
        dlg.add_response("go", _("Remove"))
        dlg.set_response_appearance("go", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        dlg.connect("response", lambda _d, resp: (
            self._do_remove(chosen) if resp == "go" else None
        ))
        dlg.present(self.get_root())

    def _do_remove(self, chosen: list[Residue]) -> None:
        self.stack.set_visible_child_name("busy")
        self.busy.set_title(_("Removing"))
        self.busy.set_description(_("Moving files to the trash…"))
        lines: list[str] = []

        def work() -> bool:
            return execute(Plan(), chosen, permanent_delete=False,
                           emit=lines.append)

        def done(ok: bool) -> None:
            self.busy.set_title(_("Scanning"))
            self.busy.set_description(
                _("Measuring directories and checking them against the "
                  "package database…")
            )
            failed = sum(1 for line in lines if line.startswith("FAILED"))
            if ok and not failed:
                self._toast(
                    N_("Removed {n} leftover directory ({size} freed).",
                       "Removed {n} leftover directories ({size} freed).",
                       len(chosen)).format(
                           n=len(chosen),
                           size=human_size(total_size(chosen)))
                )
            else:
                self._toast(
                    N_("{n} path could not be removed.",
                       "{n} paths could not be removed.", failed).format(
                           n=failed))
            self.scan()

        run_async(work, done)


def Gio_file(path: str):
    from gi.repository import Gio

    return Gio.File.new_for_path(path)


def _shorten(path: str) -> str:
    import os

    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home) else path
