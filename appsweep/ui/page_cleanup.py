"""The Reclaim page: orphans, caches and stale snap revisions."""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from ..backends import detect
from ..backends.snapd import SnapBackend
from ..executor import describe, execute
from ..i18n import N_, _
from ..models import Plan
from ..util import human_size  # noqa: E402
from .task import run_async


class CleanupPage(Adw.Bin):
    __gtype_name__ = "AppSweepCleanupPage"

    def __init__(self, toast: Callable[[str], None]) -> None:
        super().__init__()
        self._toast = toast
        self._rows: list[Gtk.Widget] = []

        self.group = Adw.PreferencesGroup(
            title=_("Space you can get back"),
            description=_("Nothing here is something you installed on "
                          "purpose."),
        )
        self.busy = Adw.PreferencesGroup()
        self.busy_row = Adw.ActionRow(
            title=_("Adding it up"),
            subtitle=_("Measuring caches and asking each package manager "
                       "what it no longer needs"),
        )
        self.busy_row.add_prefix(Gtk.Spinner(spinning=True))
        self.busy.add(self.busy_row)

        self.total_label = Gtk.Label(xalign=0)
        self.total_label.add_css_class("title-1")
        self.total_sub = Gtk.Label(xalign=0)
        self.total_sub.add_css_class("dim-label")
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                       margin_bottom=6)
        head.append(self.total_label)
        head.append(self.total_sub)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                        margin_top=18, margin_bottom=18,
                        margin_start=18, margin_end=18)
        inner.append(head)
        inner.append(self.busy)
        inner.append(self.group)
        self.set_child(Gtk.ScrolledWindow(child=inner, vexpand=True))

    # ------------------------------------------------------------- refresh
    def refresh(self) -> None:
        self.busy.set_visible(True)
        for row in self._rows:
            self.group.remove(row)
        self._rows = []
        self.total_label.set_text("…")
        self.total_sub.set_text("")

        def work() -> list[dict]:
            out: list[dict] = []
            for b in detect():
                cache = b.cache_size()
                if cache > 1024 * 1024:
                    out.append({
                        "title": _("{source} download cache").format(
                            source=b.source.label),
                        "subtitle": _("Installer files already applied. Safe "
                                      "to empty; they re-download if ever "
                                      "needed."),
                        "size": cache,
                        "plan": b.cache_cleanup_plan(),
                        "icon": "folder-download-symbolic",
                    })
                orphans = b.orphans()
                if orphans:
                    names = ", ".join(o.ident for o in orphans[:6])
                    if len(orphans) > 6:
                        names += _(", and {n} more").format(
                            n=len(orphans) - 6)
                    out.append({
                        "title": N_(
                            "{n} unused dependency ({source})",
                            "{n} unused dependencies ({source})",
                            len(orphans)).format(
                                n=len(orphans), source=b.source.label),
                        "subtitle": names,
                        "size": sum(o.size_bytes for o in orphans),
                        "plan": b.orphan_cleanup_plan(),
                        "icon": "view-list-symbolic",
                    })
                if isinstance(b, SnapBackend):
                    stale = b.disabled_revisions()
                    if stale:
                        plan = Plan()
                        from ..models import Step
                        for name, rev, _size in stale:
                            plan.steps.append(Step(
                                ["snap", "remove", name, f"--revision={rev}"],
                                needs_root=True,
                                description=_(
                                    "Drop {name} revision {rev}").format(
                                        name=name, rev=rev),
                            ))
                        out.append({
                            "title": N_(
                                "{n} superseded snap revision",
                                "{n} superseded snap revisions",
                                len(stale)).format(n=len(stale)),
                            "subtitle": ", ".join(
                                _("{name} (rev {rev})").format(name=n, rev=r)
                                for n, r, _sz in stale[:6]
                            ),
                            "size": sum(s for _n, _r, s in stale),
                            "plan": plan,
                            "icon": "software-update-available-symbolic",
                        })
            return out

        run_async(work, self._populate)

    def _populate(self, entries: list[dict]) -> None:
        self.busy.set_visible(False)
        total = sum(e["size"] for e in entries)
        if not entries:
            self.total_label.set_text(_("Nothing to reclaim"))
            self.total_sub.set_text(
                _("No stale caches, no orphaned packages. This system is "
                  "tidy.")
            )
            return
        self.total_label.set_text(human_size(total))
        self.total_sub.set_text(
            N_("across {n} item you can clear",
               "across {n} items you can clear", len(entries)).format(
                   n=len(entries))
        )

        for e in sorted(entries, key=lambda x: -x["size"]):
            row = Adw.ActionRow(
                title=GLib.markup_escape_text(e["title"]),
                subtitle=GLib.markup_escape_text(e["subtitle"]),
                subtitle_lines=2,
            )
            row.add_prefix(Gtk.Image(icon_name=e["icon"]))
            size = Gtk.Label(label=human_size(e["size"]),
                             valign=Gtk.Align.CENTER)
            size.add_css_class("numeric")
            size.add_css_class("heading")
            row.add_suffix(size)
            btn = Gtk.Button(label=_("Clear"), valign=Gtk.Align.CENTER)
            btn.connect("clicked", self._confirm, e)
            row.add_suffix(btn)
            self.group.add(row)
            self._rows.append(row)

    # ------------------------------------------------------------- actions
    def _confirm(self, btn: Gtk.Button, entry: dict) -> None:
        cmds = "\n".join(describe(entry["plan"]))
        dlg = Adw.AlertDialog(
            heading=_("Clear “{item}”?").format(item=entry["title"]),
            body=_("This frees about {size}.").format(
                size=human_size(entry["size"]))
            + "\n\n" + _("It runs:") + f"\n{cmds}",
        )
        dlg.add_response("cancel", _("Cancel"))
        dlg.add_response("go", _("Clear"))
        dlg.set_response_appearance("go", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        dlg.connect("response", lambda _d, resp: (
            self._run(btn, entry) if resp == "go" else None
        ))
        dlg.present(self.get_root())

    def _run(self, btn: Gtk.Button, entry: dict) -> None:
        btn.set_sensitive(False)
        btn.set_label(_("Clearing…"))
        plan = entry["plan"]

        def work() -> bool:
            return execute(plan, emit=lambda s: None)

        def done(ok: bool) -> None:
            if ok:
                self._toast(_("Freed about {size}.").format(
                    size=human_size(entry["size"])))
            else:
                self._toast(_("That did not complete — administrator access "
                              "may have been declined."))
            self.refresh()

        run_async(work, done)
