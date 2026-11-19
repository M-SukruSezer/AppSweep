"""Command line interface. Everything the GUI does, scriptably."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .backends import detect
from .executor import describe, execute
from .i18n import N_, _
from .leftovers import scan_for, scan_unclaimed, total_size
from .models import App, Source
from .util import human_size

C_DIM, C_B, C_R, C_Y, C_G, C_0 = (
    ("\033[2m", "\033[1m", "\033[31m", "\033[33m", "\033[32m", "\033[0m")
    if sys.stdout.isatty() else ("", "", "", "", "", "")
)


def _system_label() -> str:
    """Label of whichever system package manager this machine uses."""
    for b in detect():
        if not b.source.is_language_manager:
            return b.source.label
    return _("the system package manager")


def _conf_label(confidence: str) -> str:
    return {
        "high": _("certain"),
        "medium": _("likely"),
        "low": _("guess"),
    }.get(confidence, confidence)


def _kind_label(kind: str) -> str:
    return {
        "config": _("settings"),
        "data": _("data"),
        "cache": _("cache"),
        "state": _("state"),
        "system": _("system"),
    }.get(kind, kind)


def _yes_words() -> set[str]:
    """Affirmative answers, translated.

    English "y"/"yes" stay accepted whatever the locale, so a script that
    pipes "y" keeps working on a Turkish desktop.
    """
    words = {"y", "yes"}
    for w in _("y|yes").split("|"):
        w = w.strip().lower()
        if w:
            words.add(w)
    return words


def _load(sources: list[str] | None) -> tuple[list[App], dict]:
    backends = detect()
    if sources:
        wanted = {s.lower() for s in sources}
        backends = [b for b in backends if b.source.value in wanted]
    apps: list[App] = []
    for b in backends:
        apps += b.list_apps()
    return apps, {b.source: b for b in backends}


def _match(apps: list[App], query: str) -> list[App]:
    q = query.lower()
    exact = [a for a in apps if a.ident.lower() == q or a.name.lower() == q]
    if exact:
        return exact
    return [a for a in apps if q in a.ident.lower() or q in a.name.lower()]


# --------------------------------------------------------------------- list
def cmd_list(ns: argparse.Namespace) -> int:
    apps, _backends = _load(ns.source)
    if not ns.all:
        apps = [a for a in apps if not a.is_library]
    if ns.query:
        apps = _match(apps, ns.query)
    apps.sort(key=lambda a: -a.size_bytes if ns.by_size else 0)
    if not ns.by_size:
        apps.sort(key=lambda a: a.name.lower())

    print(C_B + f"{_('NAME'):38} {_('VERSION'):16} "
          f"{_('SIZE'):>10}  {_('SOURCE')}" + C_0)
    for a in apps:
        flag = f" {C_Y}{_('orphan')}{C_0}" if a.is_orphan else ""
        print(f"{a.name[:38]:38} {a.version[:16]:16} "
              f"{human_size(a.size_bytes):>10}  {a.source.value}{flag}")
    print("\n" + N_("{n} item · {size}", "{n} items · {size}",
                      len(apps)).format(
                          n=len(apps),
                          size=human_size(sum(a.size_bytes for a in apps))))
    return 0


# ------------------------------------------------------------------- remove
def cmd_remove(ns: argparse.Namespace) -> int:
    apps, backends = _load(ns.source)
    found = _match(apps, ns.query)
    if not found:
        print(C_R + _("No installed software matches “{query}”.").format(
            query=ns.query) + C_0)
        return 1
    if len(found) > 1 and not ns.first:
        print(C_Y + _("“{query}” matches {n} items:").format(
            query=ns.query, n=len(found)) + C_0)
        for a in found[:20]:
            print(f"  {a.source.value:9} {a.name}  ({a.ident})")
        print("\n" + _("Be more specific, or pass --first to take the "
                        "top match."))
        return 1

    app = found[0]
    backend = backends[app.source]
    plan = backend.removal_plan(
        app, purge=not ns.keep_config, autoremove=not ns.no_autoremove
    )
    if not plan.steps:
        for n in plan.notes:
            print(f"{C_R}{n}{C_0}")
        return 1

    residues = []
    if not ns.keep_data:
        print(C_DIM + _("scanning for leftover files…") + C_0)
        residues = scan_for(app, apps)
        if ns.only_high:
            residues = [r for r in residues if r.confidence == "high"]

    print(f"\n{C_B}{app.name}{C_0}  {app.version}  "
          f"[{app.source.label}]  {human_size(app.size_bytes)}")
    print("\n" + C_B + _("Will run:") + C_0)
    for line in describe(plan, residues):
        print("  " + line)
    if residues:
        print("\n" + C_B + _("Leftovers found ({size}):").format(
            size=human_size(total_size(residues))) + C_0)
        for r in residues:
            col = {"high": C_G, "medium": C_Y, "low": C_DIM}[r.confidence]
            print(f"  {col}{_conf_label(r.confidence):8}{C_0} "
                  f"{human_size(r.size_bytes):>9} "
                  f"{_kind_label(r.kind):9} {r.path}")
    for n in plan.notes:
        print("\n" + C_DIM + _("note: {note}").format(note=n) + C_0)

    if ns.dry_run:
        print("\n" + C_DIM + _("--dry-run: nothing was changed.") + C_0)
        return 0
    if not ns.yes:
        try:
            answer = input("\n" + _("Proceed? [y/N] ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 130
        if answer not in _yes_words():
            print(_("Cancelled."))
            return 1

    ok = execute(plan, residues, permanent_delete=ns.permanent,
                 emit=lambda s: print("  " + s))
    print("\n" + (C_G + _("Done.") + C_0) if ok
          else "\n" + C_R + _("Finished with errors.") + C_0)
    return 0 if ok else 1


# ---------------------------------------------------------------- leftovers
def cmd_leftovers(ns: argparse.Namespace) -> int:
    apps, _backends = _load(None)
    print(C_DIM + _("indexed {n} installed items; scanning…").format(
        n=len(apps)) + C_0)
    res = scan_unclaimed(apps, include_cache=ns.cache,
                         include_system=not ns.no_system)
    if ns.only_high:
        res = [r for r in res if r.confidence in ("high", "medium")]
    if not res:
        print(C_G + _("Nothing unaccounted for. Your home directory is "
                      "clean.") + C_0)
        return 0

    print("\n" + C_B + N_(
        "{n} directory no installed app accounts for ({size}):",
        "{n} directories no installed app accounts for ({size}):",
        len(res)).format(n=len(res), size=human_size(total_size(res)))
        + C_0 + "\n")
    for r in res:
        col = {"high": C_G, "medium": C_Y, "low": C_DIM}[r.confidence]
        root = f" {C_R}{_('root')}{C_0}" if r.needs_root else ""
        print(f"  {col}{_conf_label(r.confidence):8}{C_0} "
              f"{human_size(r.size_bytes):>9} "
              f"{_kind_label(r.kind):9} {r.path}{root}")

    print("\n" + C_DIM + _(
        "Name matching is a heuristic. Low-confidence entries are\n"
        "often legitimate — review each path before removing it.") + C_0)
    if not ns.remove:
        print("\n" + _("Pass --remove to delete the ones you confirm."))
        return 0

    chosen = [r for r in res if r.confidence in ("high", "medium")]
    if not chosen:
        print(_("Nothing above low confidence to remove."))
        return 0
    print("\n" + C_Y + N_(
        "About to remove {n} path ({size}).",
        "About to remove {n} paths ({size}).", len(chosen)).format(
            n=len(chosen), size=human_size(total_size(chosen))) + C_0)
    for r in chosen:
        print(f"  {r.path}")
    if not ns.yes:
        try:
            answer = input("\n" + _("Proceed? [y/N] ")).strip().lower()
            if answer not in _yes_words():
                print(_("Cancelled."))
                return 1
        except (EOFError, KeyboardInterrupt):
            print()
            return 130
    from .models import Plan
    ok = execute(Plan(), chosen, permanent_delete=ns.permanent,
                 emit=lambda s: print("  " + s))
    return 0 if ok else 1


# -------------------------------------------------------------------- clean
def cmd_clean(ns: argparse.Namespace) -> int:
    from .models import Plan

    backends = detect()
    plan = Plan()
    for b in backends:
        if ns.orphans or ns.all:
            p = b.orphan_cleanup_plan()
            plan.steps += p.steps
            plan.notes += p.notes
        if ns.cache or ns.all:
            p = b.cache_cleanup_plan()
            plan.steps += p.steps
            plan.notes += p.notes
    if not plan.steps:
        print(_("Pick at least one of --orphans, --cache or --all."))
        return 1

    print(C_B + _("Will run:") + C_0)
    for line in describe(plan):
        print("  " + line)
    if ns.dry_run:
        print("\n" + C_DIM + _("--dry-run: nothing was changed.") + C_0)
        return 0
    if not ns.yes:
        try:
            answer = input("\n" + _("Proceed? [y/N] ")).strip().lower()
            if answer not in _yes_words():
                return 1
        except (EOFError, KeyboardInterrupt):
            return 130
    ok = execute(plan, emit=lambda s: print("  " + s))
    return 0 if ok else 1


# ------------------------------------------------------------------- doctor
def cmd_doctor(ns: argparse.Namespace) -> int:
    print(f"{C_B}AppSweep {__version__}{C_0}\n")
    found = detect()
    print(C_B + _("Backends") + C_0)
    for src in Source:
        b = next((x for x in found if x.source is src), None)
        mark = (C_G + _("active") + C_0) if b else (
            C_DIM + _("unavailable") + C_0)
        count = len(b.list_apps()) if b else 0
        extra = "  " + N_("{n} item", "{n} items", count).format(
            n=count) if b else ""
        print(f"  {src.label:14} {mark}{extra}")
        # A pip backend reporting zero is usually not a failure: it means
        # every Python package here came from the distribution. Say so,
        # otherwise the zero looks like a bug.
        skipped = getattr(b, "distro_managed_count", 0) if b else 0
        if skipped:
            print("  " + " " * 14 + C_DIM + N_(
                "{n} package skipped — installed by the distribution, "
                "listed under {other}",
                "{n} packages skipped — installed by the distribution, "
                "listed under {other}", skipped).format(
                    n=skipped, other=_system_label()) + C_0)

    print("\n" + C_B + _("Reclaimable cache") + C_0)
    for b in found:
        sz = b.cache_size()
        if sz:
            print(f"  {b.source.label:14} {human_size(sz)}")

    print("\n" + C_B + _("Orphaned packages") + C_0)
    for b in found:
        orph = b.orphans()
        if orph:
            print(f"  {b.source.label:14} {len(orph)} "
                  f"({human_size(sum(o.size_bytes for o in orph))})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="appsweep",
        description=_("One uninstaller for apt, dnf, pacman, Flatpak, "
                      "Snap and AppImage — with leftover cleanup."),
    )
    p.add_argument("--version", action="version", version=f"appsweep {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    src = dict(action="append", metavar="NAME",
               help=_("limit to a source (apt, dnf, pacman, flatpak, snap, "
                      "appimage)"))

    lp = sub.add_parser("list", help=_("list installed software"))
    lp.add_argument("query", nargs="?", help=_("filter by name"))
    lp.add_argument("--all", action="store_true",
                    help=_("include libraries and runtimes"))
    lp.add_argument("--by-size", action="store_true", help=_("largest first"))
    lp.add_argument("--source", **src)
    lp.set_defaults(func=cmd_list)

    rp = sub.add_parser("remove",
                        help=_("uninstall software and its leftovers"))
    rp.add_argument("query")
    rp.add_argument("--keep-config", action="store_true",
                    help=_("remove but keep system config files (no purge)"))
    rp.add_argument("--keep-data", action="store_true",
                    help=_("do not scan for or delete leftover user data"))
    rp.add_argument("--no-autoremove", action="store_true",
                    help=_("leave unused dependencies installed"))
    rp.add_argument("--only-high", action="store_true",
                    help=_("only delete leftovers matched with high "
                           "confidence"))
    rp.add_argument("--permanent", action="store_true",
                    help=_("delete outright instead of moving to the trash"))
    rp.add_argument("--first", action="store_true",
                    help=_("take the first match instead of refusing"))
    rp.add_argument("-n", "--dry-run", action="store_true")
    rp.add_argument("-y", "--yes", action="store_true")
    rp.add_argument("--source", **src)
    rp.set_defaults(func=cmd_remove)

    fp = sub.add_parser("leftovers",
                        help=_("find residue from software already removed"))
    fp.add_argument("--cache", action="store_true",
                    help=_("also scan ~/.cache"))
    fp.add_argument("--no-system", action="store_true",
                    help=_("skip /etc, /var/lib and /opt"))
    fp.add_argument("--only-high", action="store_true",
                    help=_("hide low-confidence guesses"))
    fp.add_argument("--remove", action="store_true",
                    help=_("delete the medium and high confidence entries"))
    fp.add_argument("--permanent", action="store_true")
    fp.add_argument("-y", "--yes", action="store_true")
    fp.set_defaults(func=cmd_leftovers)

    cp = sub.add_parser("clean",
                        help=_("orphans and package-manager caches"))
    cp.add_argument("--orphans", action="store_true")
    cp.add_argument("--cache", action="store_true")
    cp.add_argument("--all", action="store_true")
    cp.add_argument("-n", "--dry-run", action="store_true")
    cp.add_argument("-y", "--yes", action="store_true")
    cp.set_defaults(func=cmd_clean)

    dp = sub.add_parser("doctor",
                        help=_("what AppSweep can see on this system"))
    dp.set_defaults(func=cmd_doctor)

    return p


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    try:
        return ns.func(ns)
    except KeyboardInterrupt:
        print("\n" + _("Interrupted."))
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
