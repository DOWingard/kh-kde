#!/usr/bin/python3 -I
"""SDDM's theme setting: reading it through SDDM's config cascade, and the
root helper that changes it.

This file is also installed, root-owned, as the login-screen helper that
`pkexec` runs (see the polkit policy written by install.py). It therefore
imports nothing outside the standard library.

    login-screen KingdomHearts-Sora   select a login theme

Run through pkexec (no password; any local user), the helper only switches
between the installed Kingdom Hearts themes, and only while one of them is
already selected, so a desktop can make the login screen follow its variant
without being able to touch any other choice. Run as root otherwise (sudo),
it selects any installed theme.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path

# SDDM reads these in order, files within a folder sorted by name; a later
# value overrides an earlier one.
CONF_DIRS = [Path("/usr/lib/sddm/sddm.conf.d"), Path("/etc/sddm.conf.d")]
CONF = Path("/etc/sddm.conf")
THEMES = Path("/usr/share/sddm/themes")
# The file System Settings' Login Screen page writes.
KDE_CONF = Path("/etc/sddm.conf.d/kde_settings.conf")
# Written by earlier versions; it sorts before kde_settings.conf and lost to it.
LEGACY_CONF = Path("/etc/sddm.conf.d/10-kingdom-hearts.conf")
OURS = re.compile(r"^KingdomHearts-(OrgXIII|Sora)$")
THEME_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def _log(level: str, message: str, **fields) -> None:
    record = {"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), "level": level,
              "context": "login-screen", "message": message, **fields}
    print(json.dumps(record, default=str), file=sys.stderr)


def files(dirs: list[Path] | None = None, conf: Path | None = None) -> list[Path]:
    dirs = CONF_DIRS if dirs is None else dirs
    conf = CONF if conf is None else conf
    found = [f for d in dirs if d.is_dir() for f in sorted(d.iterdir()) if f.is_file()]
    return found + ([conf] if conf.is_file() else [])


def ini_value(text: str, group: str, key: str) -> str | None:
    """Last value of `key` in `[group]`, or None when the text does not set it."""
    found, section = None, None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif section == group and "=" in line and line.split("=", 1)[0].strip() == key:
            found = line.split("=", 1)[1].strip()
    return found


def with_ini_value(text: str, group: str, key: str, value: str) -> str:
    """`text` with `key` in `[group]` set to `value`, every other line kept."""
    lines = text.splitlines()
    section, group_at, done = None, None, False
    for n, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            if section == group:
                group_at = n
        elif section == group and "=" in stripped and stripped.split("=", 1)[0].strip() == key:
            lines[n] = f"{key}={value}"
            done = True
    if not done:
        if group_at is None:
            lines += ([""] if lines and lines[-1].strip() else []) + [f"[{group}]", f"{key}={value}"]
        else:
            lines.insert(group_at + 1, f"{key}={value}")
    return "\n".join(lines) + "\n"


def current(dirs: list[Path] | None = None, conf: Path | None = None) -> tuple[str, Path | None]:
    """The login theme SDDM will show, and the file that sets it (None: SDDM's default)."""
    value, source = "", None
    for path in files(dirs, conf):
        try:
            found = ini_value(path.read_text(encoding="utf-8", errors="replace"), "Theme", "Current")
        except OSError as exc:
            _log("warn", "could not read an SDDM config file", error=str(exc), path=str(path))
            continue
        if found is not None:
            value, source = found, path
    return value, source


def target_file(source: Path | None) -> Path:
    """The file to write: the one that decides the value now, so nothing read
    later overrides it; a value from SDDM's own defaults goes into System
    Settings' file."""
    if source is not None and source != LEGACY_CONF and str(source).startswith("/etc/"):
        return source
    return KDE_CONF


def is_ours(theme: str) -> bool:
    return bool(OURS.match(theme))


def select(theme: str, restricted: bool) -> int:
    if not THEME_NAME.match(theme):
        _log("error", "not a theme name", theme=theme)
        return 2
    if not (THEMES / theme / "metadata.desktop").is_file():
        _log("error", "login theme is not installed", theme=theme, folder=str(THEMES))
        return 2
    shown, source = current()
    if restricted and not (is_ours(theme) and is_ours(shown)):
        # Without a password only a switch between our own themes is allowed.
        _log("info", "the login screen is not a Kingdom Hearts one; left as it is", current=shown, wanted=theme)
        return 3
    if shown == theme:
        _log("info", "login theme already selected", theme=theme)
        return 0
    path = target_file(source)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".kh-login-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(with_ini_value(text, "Theme", "Current", theme))
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise
    if LEGACY_CONF.exists():
        LEGACY_CONF.unlink()
        _log("info", "removed the drop-in of an earlier version", path=str(LEGACY_CONF))
    after, by = current()
    if after != theme:
        _log("error", "another SDDM config file still overrides the login theme", wanted=theme, shown=after,
             file=str(by))
        return 1
    _log("info", "login theme selected", theme=theme, previous=shown or "<default>", file=str(path))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        _log("error", "usage: login-screen <theme>", args=argv[1:])
        return 2
    if os.geteuid() != 0:
        _log("error", "must run as root (through pkexec or sudo)")
        return 2
    try:
        return select(argv[1], restricted="PKEXEC_UID" in os.environ)
    except Exception as exc:
        _log("error", "selecting the login theme failed", error=str(exc), stack=traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
