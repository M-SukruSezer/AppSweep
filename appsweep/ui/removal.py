"""The uninstall dialog: review, confirm, watch it happen."""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from ..executor import describe, execute
from ..leftovers import scan_for
from ..i18n import N_, _
from ..models import App, Plan, Residue
from ..util import human_size  # noqa: E402
from . import appicon
from .task import run_async

def _conf_label(confidence: str) -> tuple[str, str]:
    return {
        "high": (_("Certain"), "as-conf-high"),
        "medium": (_("Likely"), "as-conf-medium"),
        "low": (_("Guess"), "as-conf-low"),
    }[confidence]


class RemovalDialog(Adw.Dialog):
    """Review page → progress page → result page."""

    __gtype_name__ = "AppSweepRemovalDialog"

    def __init__(
        self,
        apps: list[App],
        installed: list[App],
        backends: dict,
        *,
        on_finished: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__()
        self.apps = apps
        self.installed = installed
        self.backends = backends
        self.on_finished = on_finished
        self.residue_rows: list[tuple[Gtk.CheckButton, Residue]] = []
        self._plans: list[Plan] = []
        self._running = False

        self.set_title(_("Uninstall"))
        self.set_content_width(620)
        self.set_content_height(620)
        self.set_can_close(True)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT)
        self.stack.add_named(self._build_review(), "review")
        self.stack.add_named(self._build_progress(), "progress")
        self.set_child(self.stack)

        self._build_plans()
        self._start_residue_scan()

    # ----------------------------------------------------------- review UI
    def _build_review(self) -> Gtk.Widget:
        self.header = Adw.HeaderBar(show_end_title_buttons=False)
        cancel = Gtk.Button(label=_("Cancel"))
        cancel.connect("clicked", lambda *_: self.close())
        self.go_btn = Gtk.Button(label=_("Uninstall"))
        self.go_btn.add_css_class("destructive-action")
        self.go_btn.connect("clicked", self._on_go)
        self.header.pack_start(cancel)
        self.header.pack_end(self.go_btn)

        total = sum(a.size_bytes for a in self.apps)

        self.target_group = Adw.PreferencesGroup(
            title=N_("Uninstalling {n} app", "Uninstalling {n} apps",
                     len(self.apps)).format(n=len(self.apps)),
            description=_("{size} of installed files").format(
                size=human_size(total)),
        )
        for a in self.apps[:12]:
            row = Adw.ActionRow(
                title=GLib.markup_escape_text(a.name),
                subtitle=GLib.markup_escape_text(
                    f"{a.source.label} · {a.ident}"
                    + (f" · {a.version}" if a.version else "")
                ),
            )
            # The icon matters most here: this is the last screen before
            # the software is gone, so the user should recognise it.
            img = Gtk.Image(pixel_size=32, valign=Gtk.Align.CENTER)
            appicon.apply(img, a)
            row.add_prefix(img)
            lbl = Gtk.Label(label=human_size(a.size_bytes), valign=Gtk.Align.CENTER)
            lbl.add_css_class("dim-label")
            lbl.add_css_class("numeric")
            row.add_suffix(lbl)
            self.target_group.add(row)
        if len(self.apps) > 12:
            self.target_group.add(
                Adw.ActionRow(title=_("…and {n} more").format(
                    n=len(self.apps) - 12))
            )

        # --- options
        opts = Adw.PreferencesGroup(
            title=_("How thoroughly"),
            description=_("These apply to every app in this operation."),
        )
        self.purge_row = Adw.SwitchRow(
            title=_("Remove settings and data too"),
            subtitle=_("Without this, config files are kept so a reinstall "
                       "picks up where you left off"),
            active=True,
        )
        self.purge_row.connect("notify::active", lambda *_: self._refresh_plans())
        self.autoremove_row = Adw.SwitchRow(
            title=_("Remove dependencies nothing else needs"),
            subtitle=_("The equivalent of apt autoremove, run automatically"),
            active=True,
        )
        self.autoremove_row.connect("notify::active",
                                    lambda *_: self._refresh_plans())
        self.trash_row = Adw.SwitchRow(
            title=_("Move leftover files to the trash"),
            subtitle=_("Recoverable for as long as your trash keeps them. "
                       "Turn off to delete immediately"),
            active=True,
        )
        opts.add(self.purge_row)
        opts.add(self.autoremove_row)
        opts.add(self.trash_row)

        # --- leftovers
        self.residue_group = Adw.PreferencesGroup(
            title=_("Leftover files"),
            description=_("Searching your home directory and /etc…"),
        )
        self.residue_spinner = Adw.ActionRow(
            title=_("Scanning"), subtitle=_("This takes a few seconds")
        )
        self.residue_spinner.add_prefix(Gtk.Spinner(spinning=True))
        self.residue_group.add(self.residue_spinner)

        # --- commands
        self.cmd_group = Adw.PreferencesGroup(title=_("Commands"))
        self.cmd_expander = Adw.ExpanderRow(
            title=_("Show exactly what will run"),
            subtitle=_("Nothing happens until you press Uninstall"),
        )
        self.cmd_text = Gtk.Label(
            xalign=0, selectable=True, wrap=True, wrap_mode=2,
            margin_top=8, margin_bottom=8, margin_start=12, margin_end=12,
        )
        self.cmd_text.add_css_class("monospace")
        self.cmd_text.add_css_class("caption")
        self.cmd_expander.add_row(Adw.Bin(child=self.cmd_text))
        self.cmd_group.add(self.cmd_expander)

        self.notes_group = Adw.PreferencesGroup()
        self.notes_group.set_visible(False)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                        margin_top=18, margin_bottom=18,
                        margin_start=18, margin_end=18)
        inner.append(self.target_group)
        inner.append(opts)
        inner.append(self.residue_group)
        inner.append(self.notes_group)
        inner.append(self.cmd_group)

        scroller = Gtk.ScrolledWindow(child=inner, vexpand=True)
        view = Adw.ToolbarView(content=scroller)
        view.add_top_bar(self.header)
        return view

    # --------------------------------------------------------- progress UI
    def _build_progress(self) -> Gtk.Widget:
        self.prog_header = Adw.HeaderBar(show_end_title_buttons=False)
        self.close_btn = Gtk.Button(label=_("Close"), sensitive=False)
        self.close_btn.connect("clicked", lambda *_: self.close())
        self.prog_header.pack_end(self.close_btn)

        self.status = Adw.StatusPage(
            title=_("Uninstalling"),
            description=_("A password prompt will appear if administrator "
                          "access is needed."),
        )
        self.status.set_child(
            Gtk.Spinner(spinning=True, width_request=32, height_request=32)
        )

        self.log_buffer = Gtk.TextBuffer()
        self.log_view = Gtk.TextView(
            buffer=self.log_buffer, editable=False, monospace=True,
            cursor_visible=False, left_margin=8, right_margin=8,
            top_margin=8, bottom_margin=8,
        )
        self.log_scroller = Gtk.ScrolledWindow(
            child=self.log_view, vexpand=True, min_content_height=220
        )
        self.log_scroller.add_css_class("card")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=12, margin_bottom=18,
                      margin_start=18, margin_end=18)
        box.append(self.status)
        box.append(self.log_scroller)

        view = Adw.ToolbarView(content=box)
        view.add_top_bar(self.prog_header)
        return view

    # -------------------------------------------------------------- plans
    def _build_plans(self) -> None:
        purge = self.purge_row.get_active() if hasattr(self, "purge_row") else True
        auto = (
            self.autoremove_row.get_active()
            if hasattr(self, "autoremove_row") else True
        )
        self._plans = []
        blocked: list[str] = []
        for app in self.apps:
            backend = self.backends.get(app.source)
            if backend is None:
                blocked.append(
                    _("No backend available for {name}.").format(name=app.name))
                continue
            plan = backend.removal_plan(app, purge=purge, autoremove=auto)
            if not plan.steps:
                blocked.extend(plan.notes or [
                    _("{name} cannot be removed.").format(name=app.name)])
                continue
            self._plans.append(plan)
        self._blocked = blocked

    def _refresh_plans(self) -> None:
        self._build_plans()
        self._update_commands()

    def _update_commands(self) -> None:
        lines: list[str] = []
        for p in self._plans:
            lines += describe(p)
        for check, r in self.residue_rows:
            if check.get_active():
                verb = (_("trash") if self.trash_row.get_active()
                        else _("delete"))
                lines.append(f"{verb} {r.path}")
        self.cmd_text.set_text("\n".join(lines) or _("nothing to do"))

        notes: list[str] = list(self._blocked)
        for p in self._plans:
            notes += p.notes
        self.notes_group.set_visible(bool(notes))
        if notes:
            # Rebuild cheaply: only ever a handful of notes.
            if hasattr(self, "_note_rows"):
                for row in self._note_rows:
                    self.notes_group.remove(row)
            self._note_rows = []
            seen = set()
            for n in notes:
                if n in seen:
                    continue
                seen.add(n)
                row = Adw.ActionRow(
                    title=GLib.markup_escape_text(n), title_lines=0
                )
                row.add_prefix(Gtk.Image(icon_name="dialog-information-symbolic"))
                row.add_css_class("property")
                self.notes_group.add(row)
                self._note_rows.append(row)

        self.go_btn.set_sensitive(bool(self._plans) or bool(self.residue_rows))

    # ---------------------------------------------------------- residue
    def _start_residue_scan(self) -> None:
        def work() -> list[Residue]:
            out: list[Residue] = []
            seen: set[str] = set()
            for app in self.apps:
                for r in scan_for(app, self.installed):
                    if r.path in seen:
                        continue
                    seen.add(r.path)
                    out.append(r)
            out.sort(key=lambda r: (-r.size_bytes, r.path))
            return out

        run_async(work, self._on_residue_done)

    def _on_residue_done(self, residues: list[Residue]) -> None:
        self.residue_group.remove(self.residue_spinner)
        if not residues:
            self.residue_group.set_description(
                _("Nothing left behind — the package manager covers "
                  "everything these apps installed.")
            )
            row = Adw.ActionRow(title=_("No leftovers found"))
            row.add_prefix(Gtk.Image(icon_name="object-select-symbolic"))
            self.residue_group.add(row)
            self._update_commands()
            return

        total = sum(r.size_bytes for r in residues)
        self.residue_group.set_description(
            _("{n} paths · {size}. Matched by name, so review anything "
              "marked “Guess” before removing it.").format(
                  n=len(residues), size=human_size(total))
        )
        for r in residues:
            label, css = _conf_label(r.confidence)
            row = Adw.ActionRow(
                title=GLib.markup_escape_text(_shorten(r.path)),
                subtitle=GLib.markup_escape_text(
                    _kind_label(r.kind)
                    + (_(" · matched “{token}”").format(token=r.matched_token)
                       if r.matched_token else "")
                    + (_(" · needs administrator access")
                       if r.needs_root else "")
                ),
            )
            row.set_tooltip_text(r.path)
            check = Gtk.CheckButton(
                valign=Gtk.Align.CENTER, active=r.confidence != "low"
            )
            check.connect("toggled", lambda *_: self._update_commands())
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

            self.residue_group.add(row)
            self.residue_rows.append((check, r))
        self._update_commands()

    def chosen_residues(self) -> list[Residue]:
        return [r for check, r in self.residue_rows if check.get_active()]

    # ---------------------------------------------------------- execution
    def _on_go(self, _btn) -> None:
        residues = self.chosen_residues()
        root_residues = [r for r in residues if r.needs_root]
        if root_residues:
            self._confirm_root(residues)
        else:
            self._run(residues)

    def _confirm_root(self, residues: list[Residue]) -> None:
        root = [r for r in residues if r.needs_root]
        dlg = Adw.AlertDialog(
            heading=_("Delete system files as administrator?"),
            body=(
                N_("{n} of the selected paths lives outside your home "
                   "directory:",
                   "{n} of the selected paths live outside your home "
                   "directory:", len(root)).format(n=len(root))
                + "\n\n"
                + "\n".join(f"• {r.path}" for r in root[:8])
                + ("\n…" if len(root) > 8 else "")
                + "\n\n"
                + _("These are deleted outright, not moved to the trash.")
            ),
        )
        dlg.add_response("cancel", _("Cancel"))
        dlg.add_response("skip", _("Skip Those"))
        dlg.add_response("go", _("Delete Them"))
        dlg.set_response_appearance("go", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")

        def answered(_d, response: str) -> None:
            if response == "go":
                self._run(residues)
            elif response == "skip":
                self._run([r for r in residues if not r.needs_root])

        dlg.connect("response", answered)
        dlg.present(self)

    def _run(self, residues: list[Residue]) -> None:
        self._running = True
        self.set_can_close(False)
        self.stack.set_visible_child_name("progress")
        permanent = not self.trash_row.get_active()
        plans = list(self._plans)

        def emit(line: str) -> None:
            GLib.idle_add(self._append_log, line)

        def work() -> bool:
            ok = True
            # Residues are handled once, alongside the first plan, so that a
            # single pkexec prompt covers the whole operation.
            first = True
            if not plans:
                return execute(Plan(), residues, permanent_delete=permanent,
                               emit=emit)
            for p in plans:
                ok = execute(
                    p,
                    residues if first else (),
                    permanent_delete=permanent,
                    emit=emit,
                ) and ok
                first = False
            return ok

        run_async(work, self._on_execute_done,
                  lambda exc: self._on_execute_done(False, str(exc)))

    def _append_log(self, line: str) -> bool:
        end = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end, line + "\n")
        mark = self.log_buffer.create_mark(None, self.log_buffer.get_end_iter(),
                                           False)
        self.log_view.scroll_to_mark(mark, 0.0, False, 0.0, 1.0)
        self.log_buffer.delete_mark(mark)
        return False

    def _on_execute_done(self, ok: bool, error: str = "") -> None:
        self._running = False
        self.set_can_close(True)
        self.close_btn.set_sensitive(True)
        self.status.set_child(None)
        if ok:
            self.status.set_icon_name("object-select-symbolic")
            self.status.set_title(_("Done"))
            self.status.set_description(
                _("The software and the leftovers you selected are gone.")
            )
        else:
            self.status.set_icon_name("dialog-warning-symbolic")
            self.status.set_title(_("Finished with problems"))
            self.status.set_description(
                error or _("Some steps did not complete. The log below has "
                           "the details — a cancelled password prompt is the "
                           "usual cause.")
            )
        if self.on_finished:
            self.on_finished(ok)


def _kind_label(kind: str) -> str:
    return {
        "config": _("settings"),
        "data": _("data"),
        "cache": _("cache"),
        "state": _("state"),
        "system": _("system"),
    }.get(kind, kind)


def _shorten(path: str) -> str:
    import os

    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home) else path
