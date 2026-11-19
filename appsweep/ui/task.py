"""Run blocking work off the GTK main loop."""
from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from typing import Any

from gi.repository import GLib


def run_async(
    work: Callable[[], Any],
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> threading.Thread:
    """Call ``work`` on a worker thread, deliver the result on the main loop."""

    def runner() -> None:
        try:
            result = work()
        except Exception as exc:                     # noqa: BLE001
            traceback.print_exc()
            if on_error is not None:
                GLib.idle_add(on_error, exc)
            return
        if on_done is not None:
            GLib.idle_add(on_done, result)

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    return t


def on_main(fn: Callable[..., Any], *args: Any) -> None:
    """Schedule ``fn(*args)`` on the GTK main loop."""
    GLib.idle_add(fn, *args)
