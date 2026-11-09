"""Shared test fixtures: project paths, a throw-away user's environment, and a
check that the build output a test reads exists."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))


def require_build(*paths: Path) -> None:
    """Fail (not skip) when the build output is missing: CI must never pass by
    testing nothing."""
    missing = [str(p) for p in paths if not p.exists() and not p.is_symlink()]
    if missing:
        raise RuntimeError(f"build output missing, run ./build.py first: {missing}")


def user_env(home: Path, data_dirs: list[Path]) -> dict[str, str]:
    """Environment of a fresh user whose system data folders are `data_dirs`."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_STATE_HOME": str(home / ".local" / "state"),
        "XDG_DATA_DIRS": ":".join(str(d) for d in data_dirs),
        "QT_QPA_PLATFORM": "offscreen",
        "KH_LOG_LEVEL": "debug",
    }


def log_messages(stderr: str) -> list[str]:
    """The messages of the JSON log records a tool wrote to stderr."""
    messages = []
    for line in stderr.splitlines():
        try:
            messages.append(json.loads(line)["message"])
        except (ValueError, KeyError, TypeError):
            continue
    return messages
