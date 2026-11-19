"""``python3 -m appsweep`` — GUI by default, CLI when given arguments."""
from __future__ import annotations

import sys


def main() -> int:
    argv = sys.argv[1:]
    if argv and not argv[0].startswith("-"):
        from .cli import main as cli_main

        return cli_main(argv)
    if argv and argv[0] in ("-h", "--help", "--version"):
        from .cli import main as cli_main

        return cli_main(argv)
    from .ui.app import main as gui_main

    return gui_main([sys.argv[0]])


if __name__ == "__main__":
    raise SystemExit(main())
