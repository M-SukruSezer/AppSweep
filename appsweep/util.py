"""Small helpers: process running, size formatting, safe deletion."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(slots=True)
class Result:
    code: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def run(argv: list[str], timeout: int = 120, env: dict | None = None) -> Result:
    """Run a command, never raising. Returns captured output."""
    merged = {**os.environ, "LC_ALL": "C", "LANG": "C"}
    if env:
        merged.update(env)
    try:
        p = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged,
            check=False,
        )
        return Result(p.returncode, p.stdout, p.stderr)
    except FileNotFoundError:
        return Result(127, "", f"{argv[0]}: not found")
    except subprocess.TimeoutExpired:
        return Result(124, "", f"{argv[0]}: timed out after {timeout}s")
    except OSError as exc:                                   # pragma: no cover
        return Result(1, "", str(exc))


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def human_size(n: int) -> str:
    if n <= 0:
        return "—"
    units = ("B", "KB", "MB", "GB", "TB")
    f = float(n)
    for u in units:
        if f < 1024 or u == units[-1]:
            return f"{f:.0f} {u}" if u in ("B", "KB") else f"{f:.1f} {u}"
        f /= 1024
    return f"{f:.1f} TB"


def dir_size(path: str, cap_entries: int = 60_000) -> int:
    """Disk usage of a tree. Does not follow symlinks, counts hardlinks once."""
    total = 0
    seen: set[tuple[int, int]] = set()
    entries = 0
    stack = [path]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    entries += 1
                    if entries > cap_entries:
                        return total
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            st = e.stat(follow_symlinks=False)
                            ino = (st.st_dev, st.st_ino)
                            if st.st_nlink > 1:
                                if ino in seen:
                                    continue
                                seen.add(ino)
                            total += st.st_size
                    except OSError:
                        continue
        except OSError:
            try:
                st = os.lstat(cur)
                total += st.st_size
            except OSError:
                pass
    return total


_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def tokenize(*values: str) -> list[str]:
    """Normalise names into comparable lowercase tokens."""
    out: list[str] = []
    for v in values:
        if not v:
            continue
        v = v.strip().lower()
        for part in (v, *_TOKEN_SPLIT.split(v)):
            part = part.strip()
            if len(part) >= 3 and part not in out:
                out.append(part)
    return out
