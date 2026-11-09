#!/usr/bin/env python3
"""Install and apply a variant in a real, private Plasma session; check the
Keyblade Browser survives a login and photograph the desktop.

    ./tools/nestedplasma.py                       # this checkout's build, both variants
    ./tools/nestedplasma.py --variant Sora
    ./tools/nestedplasma.py --installed           # the system package (kingdom-hearts-plasma)

A headless KWin is started on its own D-Bus session, runtime folder and home
folder, so the running desktop and the real home are never touched. Inside it
the steps a user takes run as they would on a desktop:

  1. the Plasma shell starts on a fresh home (stock layout)
  2. the themes are installed (unless --installed) and the variant is applied
  3. the shell is stopped and started again, as a new login would, after
     sourcing the login scripts the install wrote
  4. Dolphin and Konsole are opened when present and the screen is saved to
     CONTEXT/tmp/previews/desktop-<variant>.png

The check is on what the shell did with the Super + right click binding.
When the shell cannot load a mouse action's plugin it deletes the binding from
its configuration, so the binding has to be in the shell's configuration after
it quit, and the plugin's own "mouse action loaded" record has to be in the
shell's output. With --installed nothing points the shell at this checkout:
the plugin must be where the package put it.

Requires kwin_wayland, plasmashell (with the Plasma Desktop shell),
kactivitymanagerd, dbus-run-session, kquitapp6, qdbus6 and spectacle, and a
GPU render node (/dev/dri/renderD*), without which KWin cannot run.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from khtheme import log, picker  # noqa: E402
from khtheme.palette import VARIANTS, Palette  # noqa: E402

OUT = ROOT / "CONTEXT" / "tmp" / "previews"
SIZE = (1600, 900)
TOOLS = ["kwin_wayland", "plasmashell", "dbus-run-session", "kquitapp6", "qdbus6", "spectacle"]
SHELL_PACKAGE = Path("plasma") / "shells" / "org.kde.plasma.desktop" / "metadata.json"
ACTIVITY_SERVICE = Path("dbus-1") / "services" / "org.kde.ActivityManager.service"
PACKAGE_TOOL = "kingdom-hearts-plasma"
APPLETSRC = "plasma-org.kde.plasma.desktop-appletsrc"
BINDING = ("ActionPlugins][0", "RightButton;MetaModifier")
LOADED = ("keyblade-browser", "mouse action loaded")
# Whole session: two shell starts, install, apply (with its pauses), screenshot.
SESSION_TIMEOUT = 300

# Window rules put the showcase applications where they frame the desktop;
# 3 is "apply initially", 2 matches a substring of the application id.
WINDOW_RULES = """[General]
count=2
rules=1,2

[1]
Description=Dolphin
wmclass=dolphin
wmclassmatch=2
position=90,70
positionrule=3
size=900,560
sizerule=3

[2]
Description=Konsole
wmclass=konsole
wmclassmatch=2
position=760,400
positionrule=3
size=760,400
sizerule=3
"""

# Konsole shows the shell prompt; this one names no real user or machine.
BASHRC = "PS1='[sora@destiny-islands ~]$ '\ncd ~\n"

SESSION = r"""#!/bin/sh
# Runs inside the nested KWin. Each step writes its output and exit status to
# files in the work folder; the caller checks them after KWin exits.
W="{work}"
export QT_QPA_PLATFORM=wayland XDG_CURRENT_DESKTOP=KDE KDE_FULL_SESSION=true KDE_SESSION_VERSION=6

step() {{  # name command...
  name=$1; shift
  "$@" >"$W/$name.log" 2>&1
  echo $? >"$W/$name.status"
}}

wait_shell() {{
  i=0
  while [ $i -lt 120 ]; do
    qdbus6 org.kde.plasmashell /PlasmaShell >/dev/null 2>&1 && return 0
    sleep 0.5; i=$((i + 1))
  done
  return 1
}}

stop_shell() {{  # pid
  kquitapp6 plasmashell >>"$W/quit.log" 2>&1
  i=0
  while kill -0 "$1" 2>/dev/null && [ $i -lt 60 ]; do sleep 0.5; i=$((i + 1)); done
  kill -0 "$1" 2>/dev/null && echo "shell $1 did not quit" >>"$W/quit.log"
  wait "$1"
}}

"{activity_manager}" >"$W/activitymanager.log" 2>&1 &

plasmashell --no-respawn >"$W/shell-first.log" 2>&1 &
shell=$!
wait_shell; echo $? >"$W/shell-first.status"
{install}
step apply {apply}
stop_shell $shell

# A new login: the session sources the login scripts, then starts the shell.
for script in "$XDG_CONFIG_HOME"/plasma-workspace/env/*.sh; do
  [ -r "$script" ] && . "$script"
done
echo "QT_PLUGIN_PATH=$QT_PLUGIN_PATH" >"$W/login.env"
KH_LOG_LEVEL=debug plasmashell --no-respawn >"$W/shell-login.log" 2>&1 &
shell=$!
wait_shell; echo $? >"$W/shell-login.status"
command -v dolphin >/dev/null && dolphin "$HOME" >"$W/dolphin.log" 2>&1 &
sleep 2
command -v konsole >/dev/null && konsole >"$W/konsole.log" 2>&1 &
sleep 8
spectacle -b -n -f -o "$W/desktop.png" >"$W/spectacle.log" 2>&1
stop_shell $shell
"""


def png_size(path: Path) -> tuple[int, int]:
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    return struct.unpack(">II", head[16:24])


def data_dirs() -> list[Path]:
    return [Path(p) for p in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if p]


def activity_manager() -> str | None:
    """The activity manager's program, from its D-Bus service file. The shell
    refuses to load without it, and a private D-Bus session does not always
    start it on demand."""
    for folder in data_dirs():
        service = folder / ACTIVITY_SERVICE
        if service.is_file():
            for line in service.read_text(encoding="utf-8").splitlines():
                if line.startswith("Exec="):
                    return line.split("=", 1)[1].strip()
    return None


def render_nodes() -> list[str]:
    return sorted(str(p) for p in Path("/dev/dri").glob("renderD*")) if Path("/dev/dri").is_dir() else []


def preflight() -> str | None:
    """The activity manager's program when the session can run, else None;
    each problem found is logged."""
    missing = [tool for tool in TOOLS if shutil.which(tool) is None]
    if missing:
        log.error("nestedplasma", "required tools are missing", tools=missing)
        return None
    if not any((folder / SHELL_PACKAGE).is_file() for folder in data_dirs()):
        log.error("nestedplasma", "the Plasma Desktop shell is not installed (package plasma-desktop)",
                  expected=str(SHELL_PACKAGE))
        return None
    if not render_nodes():
        log.error("nestedplasma", "no GPU render node; KWin cannot run without one", looked_in="/dev/dri")
        return None
    program = activity_manager()
    if program is None:
        log.error("nestedplasma", "the activity manager is not installed (package kactivitymanagerd)")
    return program


def read_status(work: Path, name: str) -> int | None:
    try:
        return int((work / f"{name}.status").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def tail(path: Path, chars: int = 1500) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-chars:]
    except OSError:
        return ""


def read_binding(appletsrc: Path) -> str | None:
    """The value of the Super + right click binding in the shell's own file."""
    group, key = BINDING
    current = None
    try:
        lines = appletsrc.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("["):
            current = line.strip()[1:-1]
        elif current == group and line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    return None


def plugin_loaded(shell_log: str) -> bool:
    context, message = LOADED
    for line in shell_log.splitlines():
        if message not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("context") == context and record.get("message") == message:
            return True
    return False


def search_path(name: str, default: str, first: Path | None = None) -> str:
    """An XDG search path without the folders under the real home (the
    running desktop's own settings and data), optionally with `first` ahead."""
    real_home = str(Path.home())
    kept = [p for p in (os.environ.get(name) or default).split(":")
            if p and p != real_home and not p.startswith(real_home + "/")]
    return ":".join(([str(first)] if first else []) + kept)


def private_env(work: Path) -> dict[str, str]:
    """An environment that leads nowhere outside the work folder."""
    home = work / "home"
    runtime = work / "runtime"
    runtime.mkdir(mode=0o700)
    drop = {"WAYLAND_DISPLAY", "DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "SESSION_MANAGER", "QT_PLUGIN_PATH",
            "KH_CURSOR_DIRS", "XDG_SESSION_ID", "XDG_SEAT", "XDG_VTNR", "QT_WAYLAND_RECONNECT"}
    # KDE_* describe the running desktop's session, not this one.
    env = {k: v for k, v in os.environ.items() if k not in drop and not k.startswith("KDE_")}
    env.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(home / ".config"),
        XDG_DATA_HOME=str(home / ".local" / "share"),
        XDG_STATE_HOME=str(home / ".local" / "state"),
        XDG_CACHE_HOME=str(home / ".cache"),
        # A Global Theme writes its defaults to kdedefaults, which a Plasma
        # login puts first on the config search path. The running desktop's
        # own kdedefaults would otherwise fill in every setting left unset here.
        XDG_CONFIG_DIRS=search_path("XDG_CONFIG_DIRS", "/etc/xdg", home / ".config" / "kdedefaults"),
        XDG_DATA_DIRS=search_path("XDG_DATA_DIRS", "/usr/local/share:/usr/share"),
        # Also keeps `systemctl --user` from reaching the real session.
        XDG_RUNTIME_DIR=str(runtime),
        # No system bus either: the machine's disks, network and power state
        # would show in the shell and in Dolphin, and in the screenshot.
        DBUS_SYSTEM_BUS_ADDRESS=f"unix:path={runtime / 'no-system-bus'}",
        KWIN_WAYLAND_NO_PERMISSION_CHECKS="1",
        # Without a terminal Qt would log to the system journal.
        QT_FORCE_STDERR_LOGGING="1",
    )
    return env


def prepare_home(work: Path) -> Path:
    home = work / "home"
    config = home / ".config"
    config.mkdir(parents=True)
    for folder in ("Documents", "Music", "Pictures", "Videos", "Downloads"):
        (home / folder).mkdir()
    (home / ".bashrc").write_text(BASHRC, encoding="utf-8")
    (config / "kwinrulesrc").write_text(WINDOW_RULES, encoding="utf-8")
    (config / "kwinrc").write_text("[Desktops]\nNumber=1\nRows=1\n", encoding="utf-8")
    # The profile Konsole writes on first use; apply --konsole colours existing profiles only.
    profiles = home / ".local" / "share" / "konsole"
    profiles.mkdir(parents=True)
    (profiles / "Main.profile").write_text("[General]\nName=Main\nParent=FALLBACK/\n", encoding="utf-8")
    (config / "konsolerc").write_text("[Desktop Entry]\nDefaultProfile=Main.profile\n", encoding="utf-8")
    return home


def commands(pal: Palette, installed: bool) -> tuple[str, str]:
    """Shell lines for the install step and the apply command."""
    if installed:
        return "", f"{PACKAGE_TOOL} apply {pal.key} --konsole"
    python = sys.executable
    script = ROOT / "install.py"
    return f'step install "{python}" "{script}" install', f'"{python}" "{script}" apply {pal.key} --konsole'


def check(pal: Palette, installed: bool, program: str, keep: bool) -> bool:
    with tempfile.TemporaryDirectory(prefix="khplasma-", delete=not keep) as tmp_name:
        work = Path(tmp_name)
        if keep:
            log.info("nestedplasma", "work folder kept", variant=pal.key, folder=str(work))
        prepare_home(work)
        env = private_env(work)
        install, apply = commands(pal, installed)
        session = work / "session.sh"
        session.write_text(SESSION.format(work=work, activity_manager=program, install=install, apply=apply),
                           encoding="utf-8")
        session.chmod(0o755)
        cmd = [
            "dbus-run-session", "--", "kwin_wayland", "--virtual", "--width", str(SIZE[0]), "--height", str(SIZE[1]),
            "--socket", f"wayland-khplasma-{os.getpid()}", "--no-lockscreen", "--no-global-shortcuts",
            "--exit-with-session", str(session),
        ]
        with log.timed("nestedplasma", "run nested Plasma session", variant=pal.key, installed=installed):
            try:
                result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=SESSION_TIMEOUT)
            except subprocess.TimeoutExpired as exc:
                log.error("nestedplasma", "the nested session did not finish", error=exc, variant=pal.key,
                          timeout_s=SESSION_TIMEOUT, apply_output=tail(work / "apply.log"))
                return False

        ok = True
        steps = [("shell-first", "first shell start"), ("apply", "apply"), ("shell-login", "shell start after login")]
        if not installed:
            steps.insert(1, ("install", "install"))
        for name, what in steps:
            status = read_status(work, name)
            if status != 0:
                ok = False
                log.error("nestedplasma", f"{what} failed", variant=pal.key, exit_status=status,
                          output=tail(work / f"{name}.log"), window_manager=result.stderr[-600:])
        if not ok:
            return False
        log.debug("nestedplasma", "login environment", variant=pal.key,
                  env=tail(work / "login.env", 400).strip())

        binding = read_binding(work / "home" / ".config" / APPLETSRC)
        loaded = plugin_loaded(tail(work / "shell-login.log", 2_000_000))
        fields = dict(variant=pal.key, binding=binding, plugin_loaded=loaded, installed=installed)
        if binding != picker.PLUGIN_ID or not loaded:
            log.error("nestedplasma", "the keyblade browser did not survive the login", **fields,
                      shell_output=tail(work / "shell-login.log"), quit_output=tail(work / "quit.log", 400))
            ok = False
        else:
            log.info("nestedplasma", "the shell loaded the keyblade browser and kept its binding", **fields)

        shot = work / "desktop.png"
        try:
            size = png_size(shot)
        except (OSError, ValueError, struct.error) as exc:
            log.error("nestedplasma", "no usable screenshot", error=exc, variant=pal.key,
                      spectacle=tail(work / "spectacle.log", 600))
            return False
        if size != SIZE:
            log.error("nestedplasma", "screenshot is not of the nested screen; discarded", variant=pal.key, size=size)
            return False
        OUT.mkdir(parents=True, exist_ok=True)
        target = OUT / f"desktop-{pal.key}.png"
        shutil.copyfile(shot, target)
        log.info("nestedplasma", "desktop photographed", variant=pal.key, target=str(target))
        return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--variant", choices=[p.key for p in VARIANTS], help="check a single variant")
    parser.add_argument("--installed", action="store_true",
                        help=f"use the installed package ({PACKAGE_TOOL}) instead of this checkout's build")
    parser.add_argument("--keep", action="store_true", help="keep each session's home folder and logs")
    args = parser.parse_args()
    if args.installed and shutil.which(PACKAGE_TOOL) is None:
        log.error("nestedplasma", "the package is not installed", command=PACKAGE_TOOL)
        return 2
    program = preflight()
    if program is None:
        return 2
    start = time.monotonic()
    failed = [pal.key for pal in VARIANTS if args.variant in (None, pal.key) and not check(pal, args.installed, program, args.keep)]
    if failed:
        log.error("nestedplasma", "check failed", variants=failed)
        return 1
    log.info("nestedplasma", "all variants passed", duration_s=round(time.monotonic() - start))
    return 0


if __name__ == "__main__":
    sys.exit(main())
