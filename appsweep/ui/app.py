"""Application entry point for the graphical interface."""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from .. import APP_ID, __version__, i18n, selfremove
from ..i18n import _
from . import appicon
from .preferences import PreferencesDialog
from .style import CSS
from .window import MainWindow

PROJECT_URL = "https://github.com/M-SukruSezer/AppSweep"
#: Not a real URI. The About dialog only offers links, so the uninstall
#: entry is a link whose activation is intercepted before anything tries
#: to open it.
UNINSTALL_URI = "appsweep:uninstall"
ISSUE_URL = "https://github.com/M-SukruSezer/AppSweep/issues"


class AppSweepApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.window: MainWindow | None = None

        for name, cb, accels in (
            ("about", self._on_about, None),
            ("preferences", self._on_preferences, ["<Primary>comma"]),
            ("shortcuts", self._on_shortcuts, ["<Primary>question"]),
            ("refresh", lambda *_a: self.window and self.window.reload(),
             ["<Primary>r", "F5"]),
            ("quit", lambda *_a: self.quit(), ["<Primary>q", "<Primary>w"]),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            self.add_action(action)
            if accels:
                self.set_accels_for_action(f"app.{name}", accels)

    # ------------------------------------------------------------- startup
    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        i18n.setup_locale()
        appicon.add_icon_search_paths()
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def do_activate(self) -> None:
        if self.window is None:
            self.window = MainWindow(application=self)
        self.window.present()

    # ------------------------------------------------------------- actions
    def _on_preferences(self, *_args) -> None:
        dlg = PreferencesDialog(on_language_changed=self._relanguage)
        dlg.present(self.window)

    def _relanguage(self, _code: str) -> None:
        """Rebuild the window so every string is read again.

        Widgets take their text when they are built, so switching catalogue
        only reaches the interface if the interface is built again. The
        rescan that costs is the same one the refresh button does.
        """
        old = self.window
        self.window = MainWindow(application=self)
        self.window.present()
        if old is not None:
            old.destroy()

    def build_about(self) -> Adw.AboutDialog:
        """Assemble the About dialog. Separate from presenting it so
        its contents can be checked without a display."""
        about = Adw.AboutDialog(
            application_name="AppSweep",
            application_icon=APP_ID,
            version=__version__,
            developer_name="Muhammed Şükrü SEZER",
            comments=_(
                "One uninstaller for every way Linux installs software.\n\n"
                "AppSweep lists what apt, dnf, pacman, Flatpak, Snap, "
                "AppImage, pip, pipx, npm and cargo have put on this "
                "machine, removes any of it in one step, and then finds the "
                "settings, caches and data that uninstalling leaves behind."
            ),
            website=PROJECT_URL,
            issue_url=ISSUE_URL,
            license_type=Gtk.License.GPL_3_0,
            copyright="© 2026 Muhammed Şükrü SEZER",
            release_notes=_RELEASE_NOTES,
            release_notes_version=__version__,
            debug_info=_debug_info(),
            debug_info_filename="appsweep-debug.txt",
            developers=["Muhammed Şükrü SEZER"],
            designers=["Muhammed Şükrü SEZER"],
            # TRANSLATORS: put your name here, one per line.
            translator_credits=_("translator-credits"),
        )
        about.add_link(_("Source code"), PROJECT_URL)
        about.add_link(_("Uninstall AppSweep…"), UNINSTALL_URI)
        about.connect("activate-link", self._on_about_link)
        about.add_acknowledgement_section(
            _("Built on"),
            [
                "GTK — https://www.gtk.org",
                "libadwaita — https://gitlab.gnome.org/GNOME/libadwaita",
                "PyGObject — https://pygobject.gnome.org",
            ],
        )
        about.add_acknowledgement_section(
            _("Safety rules"),
            [
                _("Protected paths are refused outright"),
                _("Leftovers go to the trash, not /dev/null"),
                _("Every command is shown before it runs"),
            ],
        )
        about.add_legal_section(
            _("Icon"),
            _("The application icon is part of AppSweep and is released "
              "under the same licence. It follows the GNOME icon template "
              "and uses the GNOME palette."),
            Gtk.License.CUSTOM,
            None,
        )
        return about

    def _on_about(self, *_args) -> None:
        self.build_about().present(self.window)

    # --------------------------------------------------------- uninstall
    def _on_about_link(self, dialog: Adw.AboutDialog, uri: str) -> bool:
        if uri != UNINSTALL_URI:
            return False            # an ordinary link; let it open
        dialog.close()
        self.ask_to_uninstall()
        return True

    def ask_to_uninstall(self) -> None:
        """Show what removing this copy would run, then run it."""
        install = selfremove.detect()

        if not install.removable:
            dlg = Adw.AlertDialog(
                heading=_("Nothing to uninstall"),
                body=_("This copy is running straight from a source folder, "
                       "so nothing has been installed on the system.\n\n{path}"
                       ).format(path=install.detail),
            )
            dlg.add_response("ok", _("Close"))
            dlg.present(self.window)
            return

        argv = selfremove.terminal_argv(selfremove.session_script(install))
        body = (
            install.label + "\n\n"
            + _("This runs in a terminal window, where you can read it and "
                "confirm it:") + "\n\n"
            + install.command + "\n\n"
            + _("AppSweep stays open; close it when the terminal is done.")
        )
        if argv is None:
            body = (
                install.label + "\n\n"
                + _("No terminal application was found, so run this "
                    "yourself:") + "\n\n"
                + install.command
            )
            dlg = Adw.AlertDialog(heading=_("Uninstall AppSweep"), body=body)
            dlg.add_response("ok", _("Close"))
            dlg.present(self.window)
            return

        dlg = Adw.AlertDialog(heading=_("Uninstall AppSweep?"), body=body)
        dlg.add_response("cancel", _("Cancel"))
        dlg.add_response("go", _("Open Terminal"))
        dlg.set_response_appearance("go", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        dlg.connect("response", lambda _d, r: (
            self._launch_uninstall(argv) if r == "go" else None))
        dlg.present(self.window)

    def _launch_uninstall(self, argv: list[str]) -> None:
        try:
            Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE)
        except GLib.Error as exc:
            dlg = Adw.AlertDialog(
                heading=_("Could not open a terminal"),
                body=str(exc),
            )
            dlg.add_response("ok", _("Close"))
            dlg.present(self.window)

    def _on_shortcuts(self, *_args) -> None:
        dlg = Adw.AlertDialog(
            heading=_("Keyboard shortcuts"),
            body=(
                _("Ctrl+R or F5\tRescan the system") + "\n"
                + _("Ctrl+F\t\tSearch installed software") + "\n"
                + _("Ctrl+,\t\tPreferences") + "\n"
                + _("Ctrl+Q\t\tQuit")
            ),
        )
        dlg.add_response("ok", _("Close"))
        dlg.present(self.window)


#: Shown under "What's New". Kept in the source so it ships with the build.
_RELEASE_NOTES = """
<ul>
  <li>Her kurulu yazılım, kaynağına bakmaksızın tek listede ve kendi
      logosuyla görünüyor.</li>
  <li>pip, pipx, npm ve cargo ile kurulanlar da listeye katıldı.</li>
  <li>Kaldırma işleminden sonra geride kalan ayar, önbellek ve veri
      klasörleri bulunuyor.</li>
  <li>Arayüz Türkçe ve İngilizce; dil Tercihler'den değiştirilebiliyor.</li>
</ul>
"""


def _debug_info() -> str:
    """What someone would need to know to act on a bug report."""
    from ..backends import detect

    lines = [
        f"AppSweep {__version__}",
        f"Python {platform.python_version()}",
        f"GTK {Gtk.MAJOR_VERSION}.{Gtk.MINOR_VERSION}.{Gtk.MICRO_VERSION}",
        f"libadwaita {Adw.MAJOR_VERSION}.{Adw.MINOR_VERSION}."
        f"{Adw.MICRO_VERSION}",
        "",
        f"OS: {_os_name()}",
        f"Desktop: {os.environ.get('XDG_CURRENT_DESKTOP', 'unknown')}",
        f"Session: {os.environ.get('XDG_SESSION_TYPE', 'unknown')}",
        "",
        f"Interface language: {i18n.current_language()}"
        f" (system default would be {i18n.default_language()})",
        f"LANG={os.environ.get('LANG', '')}",
        "",
        "Backends detected:",
    ]
    try:
        for b in detect():
            lines.append(f"  {b.source.value}")
    except Exception as exc:                       # noqa: BLE001
        lines.append(f"  (could not probe: {exc})")
    return "\n".join(lines)


def _os_name() -> str:
    try:
        with open("/etc/os-release", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    return line.partition("=")[2].strip().strip('"')
    except OSError:
        pass
    return platform.platform()


def main(argv: list[str] | None = None) -> int:
    return AppSweepApp().run(argv if argv is not None else sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
