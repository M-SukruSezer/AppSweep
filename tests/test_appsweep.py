"""Unit tests for AppSweep.

Run with:  python3 -m unittest discover -s tests -v

The parsers for cargo and pipx are exercised against captured output from
those tools, because neither is necessarily installed on the machine
running the tests. The safety rules and the leftover-attribution logic get
the most attention here: they are the parts where a bug deletes data.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from appsweep import (icons, leftovers, safety,          # noqa: E402
                      selfremove, util)
from appsweep.backends import (base, cargo, dpkg,        # noqa: E402
                               npm, pip, pipx)
from appsweep.models import App, Plan, Residue, Source    # noqa: E402


def _result(out: str = "", code: int = 0, err: str = "") -> util.Result:
    return util.Result(code, out, err)


# --------------------------------------------------------------------- cargo
CARGO_LIST = """\
bat v0.24.0:
    bat
cargo-cache v0.8.3:
    cargo-cache
ripgrep v14.1.1 (/home/u/src/ripgrep):
    rg
tokei v12.1.2:
    tokei
"""


class TestCargoParser(unittest.TestCase):
    def _apps(self, output: str) -> list[App]:
        with mock.patch.object(cargo, "run", return_value=_result(output)):
            return cargo.CargoBackend().list_apps()

    def test_parses_every_entry(self):
        apps = self._apps(CARGO_LIST)
        self.assertEqual([a.ident for a in apps],
                         ["bat", "cargo-cache", "ripgrep", "tokei"])

    def test_parses_versions_without_the_v(self):
        apps = {a.ident: a for a in self._apps(CARGO_LIST)}
        self.assertEqual(apps["bat"].version, "0.24.0")
        self.assertEqual(apps["ripgrep"].version, "14.1.1")

    def test_records_binaries_and_local_source(self):
        apps = {a.ident: a for a in self._apps(CARGO_LIST)}
        self.assertEqual(apps["ripgrep"].extra["bins"], "rg")
        self.assertEqual(apps["ripgrep"].extra["source"],
                         "/home/u/src/ripgrep")
        self.assertEqual(apps["bat"].extra["source"], "")

    def test_binary_names_become_search_tokens(self):
        # Binary names are what the leftover scanner matches directories
        # against: tokei's config lives in ~/.config/tokei, not
        # ~/.config/<crate name>.
        apps = {a.ident: a for a in self._apps(CARGO_LIST)}
        self.assertIn("tokei", apps["tokei"].tokens)
        self.assertIn("cache", apps["cargo-cache"].tokens)

    def test_very_short_binary_names_are_deliberately_not_tokens(self):
        # "rg" is two characters. Tokens that short can only ever match a
        # two-character directory, and those are excluded as too ambiguous
        # to attribute, so carrying them would add risk and no reach.
        apps = {a.ident: a for a in self._apps(CARGO_LIST)}
        self.assertNotIn("rg", apps["ripgrep"].tokens)
        self.assertEqual(leftovers._score("rg", ["rg"])[0], 0)
        self.assertFalse(leftovers._is_candidate_name("rg"))

    def test_empty_output_is_not_an_error(self):
        self.assertEqual(self._apps(""), [])

    def test_removal_needs_no_root(self):
        apps = self._apps(CARGO_LIST)
        plan = cargo.CargoBackend().removal_plan(
            apps[0], purge=True, autoremove=True)
        self.assertEqual(len(plan.steps), 1)
        self.assertFalse(plan.needs_root)
        self.assertEqual(plan.steps[0].argv, ["cargo", "uninstall", "bat"])


# ---------------------------------------------------------------------- pipx
PIPX_JSON = """
{"pipx_spec_version": "0.1", "venvs": {
  "black": {"metadata": {"main_package": {
      "package": "black", "package_version": "24.8.0",
      "apps": ["black", "blackd"]},
      "venv_dir": "/home/u/.local/share/pipx/venvs/black"}},
  "httpie": {"metadata": {"main_package": {
      "package": "httpie", "package_version": "3.2.2",
      "apps": ["http", "https", "httpie"]},
      "venv_dir": "/home/u/.local/share/pipx/venvs/httpie"}}
}}
"""


class TestPipxParser(unittest.TestCase):
    def _apps(self, output: str) -> list[App]:
        # The fixture's venv paths do not exist here, so isdir is stubbed
        # alongside dir_size.
        with mock.patch.object(pipx, "run", return_value=_result(output)), \
             mock.patch.object(pipx, "dir_size", return_value=123456), \
             mock.patch.object(pipx.os.path, "isdir", return_value=True):
            return pipx.PipxBackend().list_apps()

    def test_lists_each_venv(self):
        apps = {a.ident: a for a in self._apps(PIPX_JSON)}
        self.assertEqual(set(apps), {"black", "httpie"})
        self.assertEqual(apps["black"].version, "24.8.0")

    def test_provided_commands_become_tokens(self):
        apps = {a.ident: a for a in self._apps(PIPX_JSON)}
        self.assertIn("blackd", apps["black"].tokens)
        self.assertIn("https", apps["httpie"].tokens)

    def test_size_comes_from_the_venv_directory(self):
        apps = self._apps(PIPX_JSON)
        self.assertTrue(all(a.size_bytes == 123456 for a in apps))

    def test_malformed_json_is_survivable(self):
        self.assertEqual(self._apps("not json at all"), [])

    def test_removal_mentions_the_whole_environment(self):
        apps = self._apps(PIPX_JSON)
        plan = pipx.PipxBackend().removal_plan(
            apps[0], purge=True, autoremove=True)
        self.assertFalse(plan.needs_root)
        self.assertTrue(any("dependencies" in n or "bağımlılık" in n
                            for n in plan.notes))


# ----------------------------------------------------------------------- npm
NPM_JSON = """
{"name": "lib", "dependencies": {
  "typescript": {"version": "5.5.4"},
  "@angular/cli": {"version": "18.2.0"}
}}
"""


class TestNpmParser(unittest.TestCase):
    def _apps(self, output: str, writable: bool = True) -> list[App]:
        b = npm.NpmBackend()
        b._root = "/usr/local/lib/node_modules"
        with mock.patch.object(npm, "run", return_value=_result(output)):
            with mock.patch.object(npm, "dir_size", return_value=5_000_000):
                with mock.patch.object(npm.os, "access",
                                       return_value=writable):
                    with mock.patch.object(npm.os.path, "isdir",
                                           return_value=True):
                        return b.list_apps()

    def test_lists_global_packages(self):
        apps = {a.ident: a for a in self._apps(NPM_JSON)}
        self.assertEqual(set(apps), {"typescript", "@angular/cli"})
        self.assertEqual(apps["typescript"].version, "5.5.4")

    def test_scoped_names_also_match_their_short_name(self):
        apps = {a.ident: a for a in self._apps(NPM_JSON)}
        self.assertIn("cli", apps["@angular/cli"].tokens)

    def test_unwritable_prefix_requires_root(self):
        apps = self._apps(NPM_JSON, writable=False)
        plan = npm.NpmBackend().removal_plan(
            apps[0], purge=True, autoremove=True)
        self.assertTrue(plan.needs_root)

    def test_writable_prefix_does_not_require_root(self):
        apps = self._apps(NPM_JSON, writable=True)
        plan = npm.NpmBackend().removal_plan(
            apps[0], purge=True, autoremove=True)
        self.assertFalse(plan.needs_root)

    def test_bundled_packages_are_refused(self):
        app = App(ident="npm", name="npm", source=Source.NPM,
                  extra={"critical": "1"})
        plan = npm.NpmBackend().removal_plan(
            app, purge=True, autoremove=True)
        self.assertEqual(plan.steps, [])
        self.assertTrue(plan.notes)


# ----------------------------------------------------------------------- pip
class TestPipClassification(unittest.TestCase):
    def test_dist_packages_is_distribution_managed(self):
        for loc in ("/usr/lib/python3/dist-packages",
                    "/usr/lib/python3.12/dist-packages",
                    "/usr/lib64/python3.11/site-packages"):
            self.assertTrue(pip._is_distro_managed(loc), loc)

    def test_user_and_venv_locations_are_pip_managed(self):
        for loc in (os.path.expanduser("~/.local/lib/python3.12/site-packages"),
                    "/home/u/venv/lib/python3.12/site-packages",
                    "/opt/myapp/venv/lib/python3.11/site-packages"):
            self.assertFalse(pip._is_distro_managed(loc), loc)

    def test_distribution_owned_package_removal_is_refused(self):
        app = App(ident="numpy", name="numpy", source=Source.PIP,
                  extra={"location": "/usr/lib/python3/dist-packages"})
        plan = pip.PipBackend().removal_plan(
            app, purge=True, autoremove=True)
        self.assertEqual(plan.steps, [])
        self.assertTrue(plan.notes)

    def test_pips_own_machinery_is_refused(self):
        for name in ("pip", "setuptools", "wheel"):
            app = App(ident=name, name=name, source=Source.PIP,
                      extra={"critical": "1", "location": "/tmp/site"})
            plan = pip.PipBackend().removal_plan(
                app, purge=True, autoremove=True)
            self.assertEqual(plan.steps, [], name)

    def test_ordinary_package_is_removable(self):
        app = App(ident="rich", name="rich", source=Source.PIP,
                  extra={"location": "/home/u/.local/lib/python3.12/"
                                     "site-packages"})
        plan = pip.PipBackend().removal_plan(
            app, purge=True, autoremove=True)
        self.assertEqual(len(plan.steps), 1)
        self.assertIn("uninstall", plan.steps[0].argv)
        self.assertIn("rich", plan.steps[0].argv)


# -------------------------------------------------------------------- safety
class TestSafety(unittest.TestCase):
    def test_protected_locations_are_refused(self):
        for p in ("/", "/etc", "/usr", "/usr/share", "/var/lib", "/home",
                  str(safety.HOME), str(safety.HOME / ".config"),
                  str(safety.HOME / ".ssh"), str(safety.HOME / ".local/share")):
            self.assertFalse(safety.is_safe(p), p)

    def test_xdg_user_directories_are_refused_in_any_language(self):
        # Read from user-dirs.dirs, so a Turkish or German desktop's
        # document folder is protected under its own name.
        for p in safety._xdg_user_dirs():
            self.assertFalse(safety.is_safe(p), p)

    def test_relative_and_traversing_paths_are_refused(self):
        for p in ("etc", "../etc", "", "/etc/../etc"):
            self.assertFalse(safety.is_safe(p), p)

    def test_shared_directories_are_refused(self):
        self.assertFalse(safety.is_safe(
            str(safety.HOME / ".local/share/applications")))
        self.assertFalse(safety.is_safe(str(safety.HOME / ".config/gtk-4.0")))

    def test_refusal_does_not_depend_on_existence(self):
        # A protected path must be refused whether or not it is there.
        missing = "/etc"
        self.assertIsNotNone(safety.why_unsafe(missing))
        ok, msg = leftovers.trash_or_delete(missing)
        self.assertFalse(ok)
        self.assertIn("refused", msg)

    def test_a_real_app_directory_is_allowed(self):
        with tempfile.TemporaryDirectory(
                dir=str(safety.HOME / ".config"),
                prefix="appsweep-test-") as d:
            self.assertTrue(safety.is_safe(d), safety.why_unsafe(d))

    def test_symlinks_are_refused(self):
        base = safety.HOME / ".config"
        link = base / "appsweep-test-link"
        target = tempfile.mkdtemp(prefix="appsweep-test-target-")
        try:
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(target)
            self.assertFalse(safety.is_safe(str(link)))
        finally:
            if link.is_symlink():
                link.unlink()
            os.rmdir(target)


# ----------------------------------------------------------------- leftovers
class TestLeftoverAttribution(unittest.TestCase):
    def test_exact_name_match_scores_highest(self):
        score, token = leftovers._score("vlc", ["vlc", "video"])
        self.assertEqual(score, 100)
        self.assertEqual(token, "vlc")

    def test_reverse_dns_directory_matches_its_app(self):
        score, _tok = leftovers._score("org.gnome.Loupe", ["loupe"])
        self.assertGreaterEqual(score, 95)

    def test_prefix_match_is_weaker_than_exact(self):
        exact, _a = leftovers._score("firefox", ["firefox"])
        prefix, _b = leftovers._score("firefox-esr", ["firefox"])
        self.assertGreater(exact, prefix)

    def test_unrelated_names_do_not_match(self):
        score, _tok = leftovers._score("pulse", ["vlc"])
        self.assertEqual(score, 0)

    def test_shared_directories_are_never_candidates(self):
        for name in ("gtk-3.0", "applications", "icons", "systemd", "dconf"):
            self.assertFalse(leftovers._is_candidate_name(name), name)

    def test_a_still_installed_app_wins_the_directory(self):
        # Removing chrome-gnome-shell must not take ~/.config/google-chrome,
        # because the installed google-chrome explains that name better.
        removing = App(ident="chrome-gnome-shell", name="chrome-gnome-shell",
                       source=Source.APT,
                       tokens=["chrome-gnome-shell", "chrome", "gnome"])
        staying = App(ident="google-chrome-stable", name="google-chrome",
                      source=Source.APT,
                      tokens=["google-chrome-stable", "google", "chrome",
                              "google-chrome"])
        name = "google-chrome"
        mine, _t = leftovers._score(name, removing.tokens)
        rival, _t2 = leftovers._score(name, staying.tokens)
        self.assertGreaterEqual(rival, mine,
                                "the installed app must win the directory")


# --------------------------------------------------------------------- icons
DESKTOP_FILES = {
    # A reverse-DNS launcher, as GNOME apps ship.
    "org.gnome.Nautilus.desktop": """\
[Desktop Entry]
Type=Application
Name=Files
Exec=nautilus --new-window %U
Icon=org.gnome.Nautilus

[Desktop Action new-window]
Name=New Window
Icon=should-not-be-picked-up
""",
    # Two Steam games that both run the steam binary: "steam" as an
    # executable key is therefore ambiguous and must identify neither.
    "steam-albion.desktop": """\
[Desktop Entry]
Type=Application
Name=Albion Online
Exec=steam steam://rungameid/761890
Icon=steam_icon_761890
""",
    "steam-dota.desktop": """\
[Desktop Entry]
Type=Application
Name=Dota 2
Exec=steam steam://rungameid/570
Icon=steam_icon_570
""",
    # A Flatpak export: stem is the application id.
    "com.github.hugolabe.Wike.desktop": """\
[Desktop Entry]
Type=Application
Name=Wike
Exec=/usr/bin/flatpak run --branch=stable com.github.hugolabe.Wike
Icon=com.github.hugolabe.Wike
""",
    # A link, not an application: must be ignored entirely.
    "some-bookmark.desktop": """\
[Desktop Entry]
Type=Link
Name=A Bookmark
URL=https://example.invalid
Icon=bookmark
""",
}

# snapd writes an absolute icon path. Two cases matter: the file is there,
# and the file is not (a snap mid-refresh, or a stale launcher).
SNAP_PRESENT = "realsnap"
SNAP_MISSING = "ghostsnap"


class TestIconIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        apps_dir = Path(self.tmp.name) / "applications"
        snap_dir = Path(self.tmp.name) / "snapd/desktop/applications"
        apps_dir.mkdir(parents=True)
        snap_dir.mkdir(parents=True)
        for name, body in DESKTOP_FILES.items():
            (apps_dir / name).write_text(body)
        # One snap whose icon file really exists, one whose does not.
        self.icon_file = Path(self.tmp.name) / "realsnap.png"
        self.icon_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        (snap_dir / f"{SNAP_PRESENT}_{SNAP_PRESENT}.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Real Snap\n"
            f"Exec=/snap/bin/{SNAP_PRESENT}\nIcon={self.icon_file}\n")
        (snap_dir / f"{SNAP_MISSING}_{SNAP_MISSING}.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Ghost Snap\n"
            f"Exec=/snap/bin/{SNAP_MISSING}\n"
            "Icon=/snap/ghostsnap/current/nope.png\n")
        self.index = icons.DesktopIndex.build((str(apps_dir), str(snap_dir)))

    def tearDown(self):
        self.tmp.cleanup()

    def _app(self, ident, source, **extra):
        return App(ident=ident, name=ident, source=source,
                   tokens=[ident], extra=extra)

    def test_link_entries_are_ignored(self):
        self.assertNotIn("some-bookmark", self.index.by_stem)

    def test_only_the_main_group_is_read(self):
        entry = self.index.by_stem["org.gnome.nautilus"]
        self.assertEqual(entry.icon, "org.gnome.Nautilus")
        self.assertEqual(entry.name, "Files")

    def test_exec_field_codes_are_stripped(self):
        self.assertEqual(self.index.by_stem["org.gnome.nautilus"].exec_bin,
                         "nautilus")

    def test_package_matches_its_reverse_dns_launcher(self):
        app = self._app("nautilus", Source.APT)
        self.assertEqual(icons.resolve(app, self.index), "org.gnome.Nautilus")

    def test_shared_executable_is_treated_as_ambiguous(self):
        # Both Steam games claim Exec=steam, so the steam package must not
        # inherit whichever game happened to sort first.
        self.assertIsNone(self.index.by_exec.get("steam"))
        self.assertEqual(icons.resolve(self._app("steam", Source.APT),
                                       self.index), "")

    def test_plugin_packages_do_not_inherit_the_app_icon(self):
        # remmina-plugin-rdp is not Remmina; nautilus-sendto is not Files.
        for ident in ("nautilus-sendto", "nautilus-extension-foo"):
            self.assertEqual(
                icons.resolve(self._app(ident, Source.APT), self.index), "",
                ident)

    def test_release_channel_suffix_still_matches(self):
        # A -stable or -bin build is the same application.
        app = self._app("nautilus-stable", Source.APT)
        self.assertEqual(icons.resolve(app, self.index), "org.gnome.Nautilus")

    def test_flatpak_matches_on_application_id(self):
        app = App(ident="com.github.hugolabe.Wike", name="Wike",
                  source=Source.FLATPAK, tokens=["wike"])
        self.assertEqual(icons.resolve(app, self.index),
                         "com.github.hugolabe.Wike")

    def test_snap_matches_on_the_owning_snap(self):
        app = App(ident=SNAP_PRESENT, name=SNAP_PRESENT, source=Source.SNAP,
                  tokens=[SNAP_PRESENT])
        self.assertEqual(icons.resolve(app, self.index), str(self.icon_file))

    def test_absolute_icon_path_that_is_gone_resolves_to_nothing(self):
        # Better a generic icon than a path the UI cannot load.
        app = App(ident=SNAP_MISSING, name=SNAP_MISSING, source=Source.SNAP,
                  tokens=[SNAP_MISSING])
        self.assertEqual(icons.resolve(app, self.index), "")

    def test_language_managers_do_not_borrow_desktop_icons(self):
        # A pip package called "nautilus" is not the Files application.
        app = App(ident="nautilus-helper", name="nautilus-helper",
                  source=Source.PIP, tokens=["nautilus"], extra={})
        self.assertEqual(icons.resolve(app, self.index), "")

    def test_fallback_is_per_source_and_never_empty(self):
        for src in Source:
            app = App(ident="x", name="x", source=src)
            self.assertTrue(icons.fallback(app), src)

    def test_libraries_get_a_package_icon(self):
        app = App(ident="libfoo", name="libfoo", source=Source.APT,
                  is_library=True)
        self.assertEqual(icons.fallback(app), icons.LIBRARY_ICON)

    def test_annotate_fills_every_app(self):
        apps = [self._app("nautilus", Source.APT),
                self._app("nothing-here", Source.APT)]
        icons.annotate(apps, self.index)
        self.assertEqual(apps[0].icon, "org.gnome.Nautilus")
        self.assertEqual(apps[1].icon, "")


# ------------------------------------------------------------------ executor
class TestExecutorSafety(unittest.TestCase):
    def test_dry_run_changes_nothing(self):
        from appsweep.executor import execute

        d = tempfile.mkdtemp(dir=str(safety.HOME / ".config"),
                             prefix="appsweep-test-")
        try:
            res = Residue(path=d, size_bytes=0, kind="config",
                          matched_token="x", confidence="high")
            lines: list[str] = []
            execute(Plan(), [res], dry_run=True, emit=lines.append)
            self.assertTrue(os.path.isdir(d), "dry run deleted the directory")
            self.assertTrue(any("would" in line for line in lines))
        finally:
            if os.path.isdir(d):
                os.rmdir(d)

    def test_protected_residue_is_reported_as_failed(self):
        from appsweep.executor import execute

        res = Residue(path=str(safety.HOME), size_bytes=0, kind="config",
                      matched_token="x", confidence="high")
        lines: list[str] = []
        ok = execute(Plan(), [res], emit=lines.append)
        self.assertFalse(ok)
        self.assertTrue(any("refused" in line for line in lines))


# ------------------------------------------------------------ preferences
class TestSettingsStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self.tmp.name
        import importlib

        from appsweep import settings as settings_mod
        self.settings = importlib.reload(settings_mod)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._old
        self.tmp.cleanup()

    def test_missing_file_reads_as_empty(self):
        self.assertEqual(self.settings.load(), {})
        self.assertIsNone(self.settings.get("language"))

    def test_roundtrip(self):
        self.assertTrue(self.settings.set("language", "tr"))
        self.assertEqual(self.settings.get("language"), "tr")
        self.assertTrue(self.settings.config_file().exists())

    def test_setting_one_key_keeps_the_others(self):
        self.settings.set("language", "tr")
        self.settings.set("other", 42)
        self.assertEqual(self.settings.get("language"), "tr")
        self.assertEqual(self.settings.get("other"), 42)

    def test_corrupt_file_does_not_raise(self):
        self.settings.config_dir().mkdir(parents=True, exist_ok=True)
        self.settings.config_file().write_text("{ not json")
        self.assertEqual(self.settings.load(), {})

    def test_file_holding_a_list_is_ignored(self):
        self.settings.config_dir().mkdir(parents=True, exist_ok=True)
        self.settings.config_file().write_text("[1, 2, 3]")
        self.assertEqual(self.settings.load(), {})


class TestLanguageRule(unittest.TestCase):
    """The rule: the user's choice, else Turkish only on a Turkish desktop."""

    LOCALE_VARS = ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._saved = {k: os.environ.get(k)
                       for k in (*self.LOCALE_VARS, "XDG_CONFIG_HOME",
                                 "APPSWEEP_LANG")}
        os.environ["XDG_CONFIG_HOME"] = self.tmp.name
        os.environ.pop("APPSWEEP_LANG", None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()
        self._reload()

    def _reload(self):
        import importlib

        from appsweep import i18n as i18n_mod
        from appsweep import settings as settings_mod
        importlib.reload(settings_mod)
        return importlib.reload(i18n_mod)

    def _with_env(self, **env):
        for k in self.LOCALE_VARS:
            os.environ.pop(k, None)
        os.environ.update(env)
        return self._reload()

    def test_turkish_desktop_starts_turkish(self):
        self.assertEqual(self._with_env(LANG="tr_TR.UTF-8").default_language(),
                         "tr")

    def test_every_other_desktop_starts_english(self):
        for lang in ("en_US.UTF-8", "de_DE.UTF-8", "ja_JP.UTF-8",
                     "fr_FR.UTF-8", "C", "POSIX"):
            self.assertEqual(
                self._with_env(LANG=lang).default_language(), "en", lang)

    def test_no_locale_variables_at_all_starts_english(self):
        self.assertEqual(self._with_env().default_language(), "en")

    def test_language_list_is_read_by_its_first_entry(self):
        # LANGUAGE=en_GB:tr means "English first", so English it is.
        mod = self._with_env(LANGUAGE="en_GB:tr", LANG="en_GB.UTF-8")
        self.assertEqual(mod.default_language(), "en")
        mod = self._with_env(LANGUAGE="tr:en", LANG="en_GB.UTF-8")
        self.assertEqual(mod.default_language(), "tr")

    def test_c_locale_is_skipped_in_favour_of_the_next_variable(self):
        mod = self._with_env(LC_ALL="C", LANG="tr_TR.UTF-8")
        self.assertEqual(mod.default_language(), "tr")

    def test_a_stored_choice_beats_the_system(self):
        mod = self._with_env(LANG="de_DE.UTF-8")
        from appsweep import settings as settings_mod
        settings_mod.set(mod.SETTINGS_KEY, "tr")
        mod = self._reload()
        self.assertEqual(mod.current_language(), "tr")

    def test_a_stored_choice_can_also_pick_english_on_a_turkish_desktop(self):
        mod = self._with_env(LANG="tr_TR.UTF-8")
        from appsweep import settings as settings_mod
        settings_mod.set(mod.SETTINGS_KEY, "en")
        mod = self._reload()
        self.assertEqual(mod.current_language(), "en")
        self.assertEqual(mod.default_language(), "tr")

    def test_a_nonsense_stored_value_falls_back_to_the_rule(self):
        mod = self._with_env(LANG="tr_TR.UTF-8")
        from appsweep import settings as settings_mod
        settings_mod.set(mod.SETTINGS_KEY, "klingon")
        mod = self._reload()
        self.assertEqual(mod.current_language(), "tr")

    def test_switching_language_reaches_already_imported_callers(self):
        # _ is a function, not a value bound at import time, so a module
        # that did `from ..i18n import _` still follows the switch.
        mod = self._with_env(LANG="en_US.UTF-8")
        before = mod._("Applications")
        mod.set_language("tr")
        after = mod._("Applications")
        self.assertNotEqual(before, after)
        self.assertEqual(after, "Uygulamalar")


# ------------------------------------------------------------------- icon
class TestIconAssets(unittest.TestCase):
    ROOT = Path(__file__).resolve().parent.parent

    def test_both_icon_files_exist(self):
        for rel in ("data/icons/hicolor/scalable/apps/"
                    "io.github.appsweep.AppSweep.svg",
                    "data/icons/hicolor/symbolic/apps/"
                    "io.github.appsweep.AppSweep-symbolic.svg"):
            self.assertTrue((self.ROOT / rel).is_file(), rel)

    def test_icons_are_wellformed_svg_on_the_adwaita_canvas(self):
        import xml.etree.ElementTree as ET

        full = self.ROOT / ("data/icons/hicolor/scalable/apps/"
                            "io.github.appsweep.AppSweep.svg")
        root = ET.parse(full).getroot()
        self.assertTrue(root.tag.endswith("svg"))
        self.assertEqual(root.get("viewBox"), "0 0 128 128")

        sym = self.ROOT / ("data/icons/hicolor/symbolic/apps/"
                           "io.github.appsweep.AppSweep-symbolic.svg")
        sroot = ET.parse(sym).getroot()
        self.assertEqual(sroot.get("viewBox"), "0 0 16 16")

    def test_symbolic_icon_is_monochrome(self):
        sym = (self.ROOT / "data/icons/hicolor/symbolic/apps/"
               "io.github.appsweep.AppSweep-symbolic.svg").read_text()
        # A symbolic icon must take the colour it is drawn in.
        self.assertIn("currentColor", sym)
        self.assertNotIn("#", sym.split("-->")[-1])

    def test_svg_element_is_near_the_start_of_the_file(self):
        """gdk-pixbuf identifies an image by sniffing its opening bytes.

        A long comment above the <svg> element pushes it past that window,
        and the loader then refuses the file outright — GTK's icon theme
        still resolves it, so the icon looks fine in the application while
        the desktop shows nothing at all. Keep the element at the top.
        """
        for rel in ("data/icons/hicolor/scalable/apps/"
                    "io.github.appsweep.AppSweep.svg",
                    "data/icons/hicolor/symbolic/apps/"
                    "io.github.appsweep.AppSweep-symbolic.svg"):
            raw = (self.ROOT / rel).read_bytes()
            self.assertNotEqual(raw.find(b"<svg"), -1, rel)
            self.assertLess(raw.find(b"<svg"), 200,
                            f"{rel}: <svg> is too far into the file for "
                            f"gdk-pixbuf to recognise it")

    def test_icons_load_through_gdk_pixbuf(self):
        try:
            import gi
            gi.require_version("GdkPixbuf", "2.0")
            from gi.repository import GdkPixbuf
        except (ImportError, ValueError):
            self.skipTest("GdkPixbuf not available")
        for rel in ("data/icons/hicolor/scalable/apps/"
                    "io.github.appsweep.AppSweep.svg",
                    "data/icons/hicolor/symbolic/apps/"
                    "io.github.appsweep.AppSweep-symbolic.svg"):
            pb = GdkPixbuf.Pixbuf.new_from_file_at_size(
                str(self.ROOT / rel), 64, 64)
            self.assertEqual(pb.get_width(), 64, rel)

    def test_desktop_entry_points_at_the_icon(self):
        text = (self.ROOT / "data/io.github.appsweep.AppSweep.desktop").read_text()
        self.assertIn("Icon=io.github.appsweep.AppSweep", text)


# ------------------------------------------------------- what is an app
DPKG_LINES = "\n".join([
    # package, version, size, section, priority, essential, summary
    "appsweep\t0.1.2\t372\tadmin\toptional\tno\tuninstaller",
    "vendorapp\t1.0\t900\tutils\toptional\tno\ta vendor app",
    "gnome-shell\t50\t9000\tgnome\toptional\tno\tthe shell",
    "gnome-shell-extension-manager\t0.6\t800\tgnome\toptional\tno\tmanager",
    "libfoo1\t1.0\t100\tlibs\toptional\tno\ta library",
    "systemd-oomd\t255\t50\tadmin\toptional\tno\toom daemon",
])


class TestLauncherOwnership(unittest.TestCase):
    """Who owns a .desktop file is a question for the package database.

    Comparing a package name to a launcher filename fails for every
    application that names its launcher in reverse DNS, which is most of
    them: appsweep installs io.github.appsweep.AppSweep.desktop.
    """

    def _launchers(self, output):
        with mock.patch.object(base, "have", return_value=True), \
             mock.patch.object(base.os, "listdir",
                               return_value=["a.desktop", "b.desktop"]), \
             mock.patch.object(base, "run", return_value=_result(output)):
            return base.launcher_packages("dpkg")

    def test_reverse_dns_launcher_is_attributed_to_its_package(self):
        got = self._launchers(
            "appsweep: /usr/share/applications/io.github.appsweep.AppSweep.desktop")
        self.assertEqual(got, {"appsweep"})

    def test_architecture_qualifier_is_not_part_of_the_name(self):
        got = self._launchers(
            "foo:amd64: /usr/share/applications/foo.desktop")
        self.assertEqual(got, {"foo"})

    def test_a_launcher_claimed_by_several_packages_credits_each(self):
        got = self._launchers(
            "one, two: /usr/share/applications/shared.desktop")
        self.assertEqual(got, {"one", "two"})

    def test_no_desktop_directories_means_no_claims(self):
        with mock.patch.object(base.os, "listdir", side_effect=OSError):
            self.assertEqual(base.launcher_packages("dpkg"), set())


class TestDpkgClassification(unittest.TestCase):
    def _apps(self, launchers):
        def fake_run(argv, **kw):
            if argv[0] == "dpkg-query" and "-W" in argv:
                return _result(DPKG_LINES + "\n")
            return _result("", code=1)

        with mock.patch.object(dpkg, "run", fake_run), \
             mock.patch.object(dpkg, "launcher_packages",
                               return_value=set(launchers)):
            return {a.ident: a for a in dpkg.DpkgBackend().list_apps()}

    def test_a_package_that_ships_a_launcher_is_an_application(self):
        # Both sit in sections the heuristics would otherwise call library.
        apps = self._apps({"appsweep", "vendorapp"})
        self.assertFalse(apps["appsweep"].is_library)
        self.assertFalse(apps["vendorapp"].is_library)

    def test_without_a_launcher_those_sections_stay_hidden(self):
        apps = self._apps(set())
        self.assertTrue(apps["appsweep"].is_library)

    def test_a_library_stays_a_library(self):
        apps = self._apps({"appsweep"})
        self.assertTrue(apps["libfoo1"].is_library)

    def test_critical_names_match_exactly_not_as_prefixes(self):
        # gnome-shell-extension-manager is an ordinary application that
        # merely begins with the name of one that is not.
        apps = self._apps({"gnome-shell", "gnome-shell-extension-manager"})
        self.assertTrue(apps["gnome-shell"].extra["critical"])
        self.assertFalse(apps["gnome-shell-extension-manager"].extra["critical"])
        self.assertFalse(apps["gnome-shell-extension-manager"].is_library)

    def test_real_families_are_still_matched_by_prefix(self):
        apps = self._apps(set())
        self.assertTrue(apps["systemd-oomd"].extra["critical"])

    def test_a_launcher_cannot_make_a_critical_package_removable(self):
        apps = self._apps({"gnome-shell"})
        self.assertTrue(apps["gnome-shell"].is_library)
        plan = dpkg.DpkgBackend().removal_plan(
            apps["gnome-shell"], purge=True, autoremove=True)
        self.assertEqual(plan.steps, [])


# -------------------------------------------------------------- selfremove
class TestInstallationDetection(unittest.TestCase):
    """AppSweep has to leave the way it arrived.

    Removing a packaged copy with rm would leave the package database
    describing files that are no longer there, so the method matters as
    much as the deletion.
    """

    def _owner(self, manager_output, which):
        """Pretend exactly one package manager answers."""
        def fake_have(cmd):
            return cmd == which

        def fake_run(argv, **kw):
            if argv[0] == which:
                return _result(manager_output)
            return _result("", code=1)

        with mock.patch.object(selfremove, "_owner_package",
                               wraps=selfremove._owner_package):
            with mock.patch("appsweep.util.have", fake_have), \
                 mock.patch("appsweep.util.run", fake_run):
                return selfremove._owner_package(Path("/usr/share/appsweep"
                                                      "/appsweep/__init__.py"))

    def test_dpkg_answer_is_parsed(self):
        got = self._owner("appsweep: /usr/share/appsweep/appsweep/__init__.py",
                          "dpkg-query")
        self.assertEqual(got, ("deb", "appsweep"))

    def test_rpm_answer_is_parsed(self):
        got = self._owner("appsweep-0.1.1-1.noarch", "rpm")
        self.assertEqual(got, ("rpm", "appsweep"))

    def test_pacman_answer_is_parsed(self):
        got = self._owner("appsweep", "pacman")
        self.assertEqual(got, ("pacman", "appsweep"))

    def test_unowned_path_is_not_claimed(self):
        def fake_have(cmd):
            return cmd == "dpkg-query"

        def fake_run(argv, **kw):
            return _result("", code=1, err="no path found")

        with mock.patch("appsweep.util.have", fake_have), \
             mock.patch("appsweep.util.run", fake_run):
            self.assertIsNone(
                selfremove._owner_package(Path("/opt/elsewhere/x.py")))

    def test_a_source_checkout_is_not_removable(self):
        with mock.patch.object(selfremove, "_owner_package",
                               return_value=None):
            with mock.patch.object(selfremove, "package_root",
                                   return_value=Path("/home/u/code/AppSweep")):
                install = selfremove.detect()
        self.assertEqual(install.method, "source")
        self.assertFalse(install.removable)
        self.assertEqual(install.command, "")

    def test_user_install_lists_only_its_own_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / ".local"
            root = prefix / "share" / "appsweep"
            root.mkdir(parents=True)
            (prefix / "bin").mkdir(parents=True)
            (prefix / "bin" / "appsweep").write_text("#!/bin/sh\n")
            with mock.patch.object(selfremove, "_owner_package",
                                   return_value=None):
                with mock.patch.object(selfremove, "package_root",
                                       return_value=root):
                    install = selfremove.detect()
        self.assertEqual(install.method, "user")
        self.assertTrue(install.removable)
        # Only paths that are really there, and every one of them explicit.
        self.assertTrue(install.paths)
        for path in install.paths:
            self.assertTrue(path.startswith(str(prefix)), path)
            self.assertNotIn("*", path)
        self.assertIn("rm -rf", install.command)

    def test_packaged_copies_leave_through_their_package_manager(self):
        for answer, which, expected in (
            ("appsweep: /usr/share/appsweep/appsweep/__init__.py",
             "dpkg-query", "apt remove"),
            ("appsweep-0.1.1-1.noarch", "rpm", "remove"),
            ("appsweep", "pacman", "pacman -R"),
        ):
            def fake_have(cmd, _w=which):
                return cmd == _w

            def fake_run(argv, _w=which, _a=answer, **kw):
                return _result(_a) if argv[0] == _w else _result("", code=1)

            with mock.patch("appsweep.util.have", fake_have), \
                 mock.patch("appsweep.util.run", fake_run):
                install = selfremove.detect()
            self.assertIn(expected, install.command, which)
            self.assertNotIn("rm -rf", install.command, which)

    def test_the_terminal_script_shows_the_command_before_running_it(self):
        install = selfremove.Installation(
            method="deb", label="x", detail="/usr/share/appsweep",
            command="sudo apt remove appsweep")
        script = selfremove.session_script(install)
        self.assertIn("sudo apt remove appsweep", script)
        self.assertIn("read ", script)          # waits, so the user can read

    def test_terminal_argv_ends_with_the_script(self):
        argv = selfremove.terminal_argv("echo hi")
        if argv is None:
            self.skipTest("no terminal emulator on this machine")
        self.assertEqual(argv[-3:], ["sh", "-c", "echo hi"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
