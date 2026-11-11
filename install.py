#!/usr/bin/env python3
"""Install, apply, revert and remove the Kingdom Hearts Plasma themes.

    ./install.py install            copy built assets from dist/ into ~/.local/share (and ~/.config/Kvantum)
    ./install.py apply OrgXIII      switch the desktop to a variant (OrgXIII | Sora)
    ./install.py revert             restore the settings saved before the first apply
    ./install.py status             show what is installed and what is active
    ./install.py keyblade [<name>]  list the pointer keyblades, or point with one
    ./install.py uninstall          remove every installed file (revert first)
    ./install.py sddm [<variant>]   install the login themes and pick one (OrgXIII | Sora | off); asks for sudo
    ./install.py rebind             put Super + right click back if a desktop reset removed it (run at shell start)
    ./install.py stage --destdir D  lay the themes out under D/usr for a distribution package

A distribution package installs everything system-wide with `stage` and puts
this tool on the path as `kingdom-hearts-plasma`; `apply`, `revert`, `status`
and `keyblade` then work the same, finding the themes under /usr/share.

`apply` saves the previous look (theme ids, accent colour, sound theme,
wallpaper plugin, lock-screen wallpaper, copies of the touched config files)
before changing anything, so `revert` goes back to the desktop as it was. The
saved look is refreshed whenever `apply` finds a desktop that is not showing
one of these themes, i.e. after you changed it yourself.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from khtheme import VERSION, kvantum, log, picker, sddm, wallpapers
from khtheme.colorscheme import scheme_id
from khtheme.palette import ORG_XIII, SORA, VARIANTS, Palette
from khtheme.sounds import THEME_ID as SOUND_THEME

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
PREFIX = "KingdomHearts"
# Names under which this project installs things; KWin decoration packages
# follow KWin's own naming scheme instead of the common prefix.
OWN_PREFIXES = (PREFIX, "kwin4_decoration_qml_kingdomhearts_")

HOME = Path.home()
DATA = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local" / "share")
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config")
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or HOME / ".cache")
STATE = Path(os.environ.get("XDG_STATE_HOME") or HOME / ".local" / "state") / "kingdom-hearts-plasma"
BACKUP = STATE / "backup.json"

# dist subtree -> install location; every entry inside is one of our themes.
TREES = {
    "color-schemes": DATA / "color-schemes",
    "plasma/desktoptheme": DATA / "plasma" / "desktoptheme",
    "plasma/look-and-feel": DATA / "plasma" / "look-and-feel",
    "kwin/decorations": DATA / "kwin" / "decorations",
    "icons": DATA / "icons",
    # Not DATA/icons: the cursor chooser in System Settings lists only ~/.icons
    # and the system directories, and installs downloaded cursor themes to
    # ~/.icons itself. KWin and the toolkits all search ~/.icons as well.
    "cursors": HOME / ".icons",
    "wallpapers": DATA / "wallpapers",
    "konsole": DATA / "konsole",
    "sounds": DATA / "sounds",
    "fonts": DATA / "fonts",
    # Kvantum reads user themes from the config directory, not the data one.
    "Kvantum": CONFIG / "Kvantum",
}
# Seconds given to KWin or the shell to let go of what it showed before, when
# something is switched away and back to make a rebuilt version load.
SWITCH_PAUSE = 2.0
# Decoration and cursors shown for that moment; both ship with Plasma.
STANDIN_DECORATION = "org.kde.breeze"
STANDIN_CURSORS = "breeze_cursors"

# Data folders packages install into, in lookup order (XDG base directories).
SYSTEM_DATA = [Path(p) for p in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if p]
# dist subtree -> folder under /usr that a system-wide package installs it to.
SYSTEM_TREES = {
    "color-schemes": "share/color-schemes",
    "plasma/desktoptheme": "share/plasma/desktoptheme",
    "plasma/look-and-feel": "share/plasma/look-and-feel",
    "kwin/decorations": "share/kwin/decorations",
    "icons": "share/icons",
    "cursors": "share/icons",
    "wallpapers": "share/wallpapers",
    "konsole": "share/konsole",
    "sounds": "share/sounds",
    "fonts": "share/fonts",
    "Kvantum": "share/Kvantum",
    "sddm": "share/sddm/themes",
}
SYSTEM_TOOL = "kingdom-hearts-plasma"
# Written by `stage` next to the copy of this script that a package installs:
# where that package put the keyblade plugin and command.
SYSTEM_INSTALL = ROOT / "system-install.json"

# Locations earlier versions installed into; our entries there are removed.
LEGACY_TREES = [DATA / "aurorae" / "themes"]

# The Keyblade Browser plugin gets a folder of its own, which the Plasma
# session puts on QT_PLUGIN_PATH through a login script.
OWN_DATA = DATA / "kingdom-hearts-plasma"
PLUGIN_ROOT = OWN_DATA / "plugins"
PLUGIN = PLUGIN_ROOT / picker.NAMESPACE / f"{picker.PLUGIN_ID}.so"
ENV_SCRIPT = CONFIG / "plasma-workspace" / "env" / "kingdom-hearts-plasma.sh"
KEYBLADE_RC = CONFIG / "kingdom-hearts-plasmarc"
SHELL_SERVICE = "plasma-plasmashell.service"
# Runs `rebind` each time the shell starts, before it reads its mouse actions:
# applying a Global Theme with its desktop layout makes the shell rewrite its
# configuration without them, and the shell itself never puts them back.
SHELL_HOOK = CONFIG / "systemd" / "user" / f"{SHELL_SERVICE}.d" / "kingdom-hearts-plasma.conf"
# What KWin does with Super + right click. Its default, resizing, swallows the
# click even on the desktop. This one activates the window under the pointer
# (the desktop too) and passes the click on, so the shell both gets the click
# and, having keyboard focus, sees the Super key held.
PASS_CLICK = "Activate, raise and pass click"
SHELL_WAIT = 20.0

# (config file, group path, key) read through the KDE config cascade.
SETTINGS = {
    "lookandfeel": ("kdeglobals", ["KDE"], "LookAndFeelPackage"),
    "colorscheme": ("kdeglobals", ["General"], "ColorScheme"),
    "accent": ("kdeglobals", ["General"], "AccentColor"),
    "widgetstyle": ("kdeglobals", ["KDE"], "widgetStyle"),
    "icons": ("kdeglobals", ["Icons"], "Theme"),
    "plasmatheme": ("plasmarc", ["Theme"], "name"),
    "decoration_library": ("kwinrc", ["org.kde.kdecoration2"], "library"),
    "decoration_theme": ("kwinrc", ["org.kde.kdecoration2"], "theme"),
    "cursor": ("kcminputrc", ["Mouse"], "cursorTheme"),
    "sounds": ("kdeglobals", ["Sounds"], "Theme"),
    "kvantum_theme": ("Kvantum/kvantum.kvconfig", ["General"], "theme"),
    "splash": ("ksplashrc", ["KSplash"], "Theme"),
    "splash_engine": ("ksplashrc", ["KSplash"], "Engine"),
    "light_lookandfeel": ("kdeglobals", ["KDE"], "DefaultLightLookAndFeel"),
    "dark_lookandfeel": ("kdeglobals", ["KDE"], "DefaultDarkLookAndFeel"),
    "lock_plugin": ("kscreenlockerrc", ["Greeter"], "WallpaperPlugin"),
    "lock_image": ("kscreenlockerrc", ["Greeter", "Wallpaper", "org.kde.image", "General"], "Image"),
    "lock_preview": ("kscreenlockerrc", ["Greeter", "Wallpaper", "org.kde.image", "General"], "PreviewImage"),
    "meta_right_window": ("kwinrc", ["MouseBindings"], "CommandAll3"),
    "meta_right_desktop": ("plasma-org.kde.plasma.desktop-appletsrc", ["ActionPlugins", "0"], "RightButton;MetaModifier"),
}
CONFIG_FILES = ["kdeglobals", "kwinrc", "plasmarc", "kcminputrc", "ksplashrc", "kscreenlockerrc",
                "plasma-org.kde.plasma.desktop-appletsrc"]

# SDDM reads these in order, files within a folder sorted by name; a later
# value overrides an earlier one.
SDDM_CONF_DIRS = [Path("/usr/lib/sddm/sddm.conf.d"), Path("/etc/sddm.conf.d")]
SDDM_CONF = Path("/etc/sddm.conf")
SDDM_THEMES = Path("/usr/share/sddm/themes")
# The file System Settings' Login Screen page writes; choosing here through it
# keeps that page in step.
SDDM_KDE_CONF = Path("/etc/sddm.conf.d/kde_settings.conf")
# Written by earlier versions; it sorts before kde_settings.conf and so lost to it.
SDDM_LEGACY_CONF = Path("/etc/sddm.conf.d/10-kingdom-hearts.conf")
SDDM_STATE = STATE / "sddm.json"
SDDM_FALLBACK = "breeze"

REQUIRED_TOOLS = ["kreadconfig6", "kwriteconfig6", "plasma-apply-lookandfeel", "plasma-apply-wallpaperimage",
                  "plasma-apply-colorscheme", "plasma-apply-desktoptheme", "plasma-apply-cursortheme", "qdbus6"]


class StepError(RuntimeError):
    pass


def run(cmd: list[str], what: str, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run an external tool, logging duration and any failure with its output."""
    start = time.monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        log.error("install", f"{what}: tool not found", error=exc, command=cmd[0])
        raise StepError(f"{what}: {cmd[0]} is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        log.error("install", f"{what}: timed out", error=exc, command=cmd[0], timeout_s=timeout)
        raise StepError(f"{what}: {cmd[0]} timed out after {timeout}s") from exc
    duration = round((time.monotonic() - start) * 1000, 1)
    if result.returncode != 0:
        level = log.error if check else log.warn
        level("install", f"{what}: exited {result.returncode}", command=" ".join(cmd[:3]),
              stderr=result.stderr.strip()[-1500:], stdout=result.stdout.strip()[-500:], duration_ms=duration)
        if check:
            raise StepError(f"{what}: {cmd[0]} exited {result.returncode}")
    else:
        log.debug("install", f"{what}: ok", command=" ".join(cmd[:3]), duration_ms=duration)
    return result


def read_setting(file: str, groups: list[str], key: str) -> str:
    cmd = ["kreadconfig6", "--file", file]
    for group in groups:
        cmd += ["--group", group]
    return run(cmd + ["--key", key], f"read {file}:{key}").stdout.strip()


def write_setting(file: str, groups: list[str], key: str, value: str | None) -> None:
    cmd = ["kwriteconfig6", "--file", file]
    for group in groups:
        cmd += ["--group", group]
    cmd += ["--key", key]
    cmd += ["--delete"] if value in (None, "") else [value]
    run(cmd, f"write {file}:{key}")
    log.debug("install", "setting written", file=file, group="/".join(groups), key=key, value=value or "<deleted>")


def plasma_script(script: str, what: str) -> str:
    return run(["qdbus6", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript", script], what).stdout.strip()


def variant(key: str) -> Palette:
    for pal in VARIANTS:
        if pal.key.lower() == key.lower():
            return pal
    raise StepError(f"unknown variant {key!r}; choose from {[p.key for p in VARIANTS]}")


def is_ours(name: str) -> bool:
    return name.startswith(OWN_PREFIXES)


def is_user_copy(name: str) -> bool:
    """Kvantum Manager saves a user's edits of a theme as "<Name>#"; those are
    the user's, not ours, and survive installs and uninstalls."""
    return name.endswith("#")


def points_at_ours(value: str) -> bool:
    """True for a setting value (an id or a path) that refers to one of our themes."""
    return any(prefix.lower() in value.lower() for prefix in OWN_PREFIXES)


def remove_entry(path: Path) -> None:
    shutil.rmtree(path) if path.is_dir() and not path.is_symlink() else path.unlink()


# --- install / uninstall -----------------------------------------------------
def search_roots(sub: str) -> list[Path]:
    """Folders a dist subtree may be installed in: the user's first, then the
    system-wide ones a package installs to."""
    if sub == "cursors":
        return [TREES[sub], DATA / "icons", *(d / "icons" for d in SYSTEM_DATA)]
    return [TREES[sub], *(d / sub for d in SYSTEM_DATA)]


def find_installed(sub: str, *parts: str) -> Path | None:
    """The copy the desktop will use of an installed file or folder, if any."""
    for root in search_roots(sub):
        path = root.joinpath(*parts)
        if path.exists():
            return path
    return None


def system_install() -> dict:
    if not SYSTEM_INSTALL.is_file():
        return {}
    try:
        return json.loads(SYSTEM_INSTALL.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warn("install", "package install record unreadable; the keyblade browser may not be found",
                 error=exc, path=str(SYSTEM_INSTALL))
        return {}


def installed_plugin() -> Path | None:
    """The Keyblade Browser plugin the shell loads. A per-user install wins: its
    folder comes first on QT_PLUGIN_PATH."""
    if PLUGIN.is_file():
        return PLUGIN
    recorded = system_install().get("plugin")
    if recorded and Path(recorded).is_file():
        return Path(recorded)
    return None


def unresolved_libraries(binary: Path) -> list[str]:
    """Libraries `binary` was linked against that this system no longer has.
    libplasma raises its soname when its ABI breaks, which leaves a plugin
    built before that unloadable until it is rebuilt."""
    try:
        result = subprocess.run(["ldd", str(binary)], capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.warn("install", "could not check the plugin's libraries", error=exc, plugin=str(binary))
        return []
    return [line.split("=>")[0].strip() for line in result.stdout.splitlines() if "not found" in line]


def rebuild_hint() -> str:
    if system_install():
        return f"rebuild the package: yay -S --rebuild {SYSTEM_TOOL}"
    return "rebuild it: ./build.py --only picker && ./install.py install"


def keyblade_tool() -> Path | None:
    built = picker.cli(DIST)
    if built.is_file():
        return built
    recorded = system_install().get("keyblade_tool") or shutil.which("kh-keyblade")
    return Path(recorded) if recorded and Path(recorded).is_file() else None


def cmd_install(_args) -> int:
    if not DIST.is_dir():
        log.error("install", "nothing to install: run ./build.py first (a system package has installed the themes "
                  "already; use 'apply')", dist=str(DIST))
        return 2
    copied = 0
    pruned = 0
    for sub, target in TREES.items():
        source = DIST / sub
        if not source.is_dir():
            log.warn("install", "component missing from dist, skipped", component=sub)
            continue
        target.mkdir(parents=True, exist_ok=True)
        wanted = set()
        for entry in sorted(source.iterdir()):
            if not is_ours(entry.name):
                log.warn("install", "unexpected entry in dist, skipped", entry=str(entry))
                continue
            wanted.add(entry.name)
            dest = target / entry.name
            try:
                if entry.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(entry, dest, symlinks=True)
                else:
                    shutil.copy2(entry, dest)
            except OSError as exc:
                log.error("install", "copy failed", error=exc, source=str(entry), target=str(dest))
                return 1
            copied += 1
            log.debug("install", "installed", target=str(dest))
        # Entries of ours that the current build no longer produces (renamed or
        # dropped since an earlier install) would linger in the choosers.
        for entry in sorted(target.iterdir()):
            if is_ours(entry.name) and entry.name not in wanted and not is_user_copy(entry.name):
                try:
                    remove_entry(entry)
                    pruned += 1
                    log.info("install", "removed an entry from an earlier version", path=str(entry))
                except OSError as exc:
                    log.warn("install", "could not remove an outdated entry", error=exc, path=str(entry))
    pruned += remove_legacy()
    if not install_keyblade_browser():
        return 1
    clear_caches()
    refresh_icons()
    refresh_fonts()
    log.info("install", "themes installed", entries=copied, outdated_removed=pruned, data_dir=str(DATA))
    return 0


def install_keyblade_browser() -> bool:
    """Install the plugin and the login script that lets the shell find it,
    then put back the keyblade chosen before (the cursors were just replaced)."""
    source = picker.plugin_file(DIST)
    if not source.is_file():
        log.warn("install", "keyblade browser not built; skipped", expected=str(source), hint="./build.py --only picker")
        return True
    try:
        PLUGIN.parent.mkdir(parents=True, exist_ok=True)
        # Copied aside and renamed: a running shell has the old file mapped,
        # and overwriting it in place would crash the shell.
        staged = PLUGIN.with_suffix(".so.new")
        shutil.copy2(source, staged)
        os.replace(staged, PLUGIN)
        ENV_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
        ENV_SCRIPT.write_text(
            "# Lets the Plasma shell find the Keyblade Browser mouse action (Kingdom Hearts theme).\n"
            f'case ":${{QT_PLUGIN_PATH}}:" in\n  *":{PLUGIN_ROOT}:"*) ;;\n'
            f'  *) export QT_PLUGIN_PATH="{PLUGIN_ROOT}${{QT_PLUGIN_PATH:+:$QT_PLUGIN_PATH}}" ;;\nesac\n',
            encoding="utf-8",
        )
    except OSError as exc:
        log.error("install", "could not install the keyblade browser", error=exc, plugin=str(PLUGIN), script=str(ENV_SCRIPT))
        return False
    log.info("install", "keyblade browser installed", plugin=str(PLUGIN), login_script=str(ENV_SCRIPT))
    tool = picker.cli(DIST)
    if tool.is_file():
        run([str(tool), "restore", "--no-reload"], "restore the chosen keyblade", check=False)
    return True


def remove_legacy() -> int:
    removed = 0
    for tree in LEGACY_TREES:
        if not tree.is_dir():
            continue
        for entry in sorted(tree.iterdir()):
            if is_ours(entry.name):
                try:
                    remove_entry(entry)
                    removed += 1
                    log.info("install", "removed an entry from an earlier version", path=str(entry))
                except OSError as exc:
                    log.warn("install", "could not remove an outdated entry", error=exc, path=str(entry))
    return removed


def refresh_icons() -> None:
    """Drop the shared icon cache and tell running programs to reload icons;
    otherwise a rebuilt icon keeps its old rendering until the next login."""
    cache = CACHE / "icon-cache.kcache"
    try:
        cache.unlink(missing_ok=True)
    except OSError as exc:
        log.warn("install", "could not remove the icon cache", error=exc, path=str(cache))
    run(["dbus-send", "--session", "--type=signal", "/KIconLoader", "org.kde.KIconLoader.iconChanged", "int32:0"],
        "announce icon change", check=False)


def refresh_fonts() -> None:
    """Make fontconfig notice added or removed fonts; applications pick them up on start."""
    if shutil.which("fc-cache") is None:
        log.warn("install", "fc-cache not found; new fonts appear after the next login")
        return
    run(["fc-cache", "-f", str(DATA / "fonts")], "refresh font cache", check=False, timeout=120)


def clear_caches() -> None:
    """Plasma caches rendered theme SVGs; stale entries would hide a rebuild."""
    removed = 0
    for pattern in (f"ksvg-elements-{PREFIX}*", f"plasma_theme_{PREFIX}*", f"plasma-svgelements-{PREFIX}*"):
        for path in CACHE.glob(pattern):
            try:
                shutil.rmtree(path) if path.is_dir() else path.unlink()
                removed += 1
            except OSError as exc:
                log.warn("install", "could not remove cache entry", error=exc, path=str(path))
    log.debug("install", "theme caches cleared", removed=removed)


def cmd_uninstall(_args) -> int:
    active = read_setting(*SETTINGS["lookandfeel"])
    if is_ours(active) or is_ours(read_setting(*SETTINGS["plasmatheme"])):
        log.error("install", "a Kingdom Hearts theme is still active; run './install.py revert' first", active=active)
        return 2
    removed = 0
    for target in TREES.values():
        if not target.is_dir():
            continue
        for entry in target.iterdir():
            if is_ours(entry.name) and not is_user_copy(entry.name):
                try:
                    remove_entry(entry)
                    removed += 1
                except OSError as exc:
                    log.error("install", "remove failed", error=exc, path=str(entry))
                    return 1
    removed += remove_legacy()
    remove_shell_hook()
    for path in (OWN_DATA, ENV_SCRIPT, KEYBLADE_RC):
        if path.exists():
            try:
                remove_entry(path)
                removed += 1
            except OSError as exc:
                log.error("install", "remove failed", error=exc, path=str(path))
                return 1
    clear_caches()
    refresh_fonts()
    log.info("install", "themes removed", entries=removed)
    return 0


# --- backup / apply / revert -------------------------------------------------
def desktops_state() -> list[dict]:
    """Wallpaper plugin of every desktop, plus the picture when it is a plain image."""
    out = plasma_script(
        "var out=[]; var ds=desktops(); for (var i=0;i<ds.length;i++){ var d=ds[i];"
        "d.currentConfigGroup=['Wallpaper', d.wallpaperPlugin, 'General'];"
        "out.push({id:d.id,screen:d.screen,plugin:d.wallpaperPlugin,image:String(d.readConfig('Image',''))});}"
        "print(JSON.stringify(out));",
        "read wallpaper plugins",
    )
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        log.warn("install", "could not parse desktop state; wallpaper will not be restorable", error=exc, raw=out[:300])
        return []


def save_backup() -> None:
    settings = {name: read_setting(*spec) for name, spec in SETTINGS.items()}
    showing_ours = is_ours(settings["lookandfeel"]) or is_ours(settings["plasmatheme"])
    earlier: dict = {}
    earlier_desktops: list[dict] = []
    if BACKUP.exists():
        if showing_ours:
            log.info("install", "keeping existing backup of the pre-theme desktop", backup=str(BACKUP))
            return
        # The desktop was changed by hand since that backup was taken; what is
        # on screen now is what a revert should return to.
        try:
            previous = json.loads(BACKUP.read_text(encoding="utf-8"))
            earlier = previous.get("settings", {})
            earlier_desktops = previous.get("desktops") or []
        except (json.JSONDecodeError, OSError) as exc:
            log.warn("install", "existing backup is unreadable and will be replaced", error=exc, backup=str(BACKUP))
        BACKUP.replace(BACKUP.with_suffix(".previous.json"))
        log.info("install", "desktop changed since the last backup; saving the current look instead")
    elif showing_ours:
        # Never record our own theme as "the previous look".
        log.warn("install", "a Kingdom Hearts theme is already active and no backup exists; revert will be unavailable")
        return
    # Settings that still point at one of our themes are leftovers of an earlier
    # apply, not a choice to return to; fall back to the value saved before it.
    for name, value in settings.items():
        if points_at_ours(value):
            settings[name] = earlier.get(name, "") if not points_at_ours(earlier.get(name, "")) else ""
            log.debug("install", "leftover setting replaced in backup", setting=name, restored=settings[name] or "<unset>")
    # KWin's Super + right click setting names nothing of ours, but it is ours
    # while the desktop binding that needs it is still in place.
    if points_at_ours(read_setting(*SETTINGS["meta_right_desktop"])) and settings["meta_right_window"] == PASS_CLICK:
        settings["meta_right_window"] = earlier.get("meta_right_window", "")
        log.debug("install", "leftover setting replaced in backup", setting="meta_right_window",
                  restored=settings["meta_right_window"] or "<unset>")
    # An earlier apply removed the accent colour; switching themes by hand does
    # not bring it back, so an unset accent is taken from the earlier backup.
    if not settings["accent"] and earlier.get("accent"):
        settings["accent"] = earlier["accent"]
        log.info("install", "accent colour carried over from the earlier backup")
    desktops = desktops_state()
    by_id = {d.get("id"): d for d in earlier_desktops}
    for n, desktop in enumerate(desktops):
        if points_at_ours(desktop.get("image", "")) and desktop.get("id") in by_id:
            desktops[n] = by_id[desktop["id"]]
            log.info("install", "wallpaper state carried over from the earlier backup", desktop=desktop.get("id"),
                     plugin=desktops[n].get("plugin"))
    STATE.mkdir(parents=True, exist_ok=True)
    files_dir = STATE / "config-files"
    files_dir.mkdir(exist_ok=True)
    for name in CONFIG_FILES:
        src = CONFIG / name
        if src.is_file():
            shutil.copy2(src, files_dir / name)
    defaults = CONFIG / "kdedefaults"
    if defaults.is_dir():
        shutil.copytree(defaults, files_dir / "kdedefaults", dirs_exist_ok=True)
    data = {
        "saved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "settings": settings,
        "desktops": desktops,
    }
    BACKUP.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    log.info("install", "saved the current look for revert", backup=str(BACKUP), lookandfeel=settings["lookandfeel"])


def missing_components(pal: Palette) -> list[str]:
    expected = {
        "colour scheme": ("color-schemes", f"{scheme_id(pal)}.colors"),
        "plasma style": ("plasma/desktoptheme", pal.theme_id, "metadata.json"),
        "global theme": ("plasma/look-and-feel", pal.theme_id, "metadata.json"),
        "window decoration": ("kwin/decorations", pal.decoration_id, "contents", "ui", "main.qml"),
        "icons": ("icons", pal.theme_id, "index.theme"),
        "cursors": ("cursors", pal.cursor_id, "cursors", "default"),
        "wallpaper": ("wallpapers", PREFIX, "metadata.json"),
        "sound theme": ("sounds", SOUND_THEME, "index.theme"),
        "kvantum style": ("Kvantum", kvantum.THEME, f"{kvantum.theme_name(pal)}.kvconfig"),
    }
    return [name for name, (sub, *parts) in expected.items() if find_installed(sub, *parts) is None]


def set_konsole_scheme(name: str | None, saved: dict | None = None) -> dict:
    """Point every Konsole profile at a colour scheme; returns the previous values."""
    previous = {}
    profiles = sorted((DATA / "konsole").glob("*.profile"))
    if not profiles:
        log.warn("install", "no Konsole profiles found; terminal colours unchanged")
    for profile in profiles:
        text = profile.read_text(encoding="utf-8")
        current = next((ln.split("=", 1)[1] for ln in text.splitlines() if ln.startswith("ColorScheme=")), "")
        previous[profile.name] = current
        value = saved.get(profile.name, current) if saved is not None else name
        run(["kwriteconfig6", "--file", str(profile), "--group", "Appearance", "--key", "ColorScheme", value or ""],
            f"set Konsole colours in {profile.name}")
        log.info("install", "Konsole profile updated", profile=profile.name, scheme=value)
    return previous


def set_wallpaper(pal: Palette, wallpaper: Path) -> None:
    """Show the combined wallpaper package, also when it is already selected.

    The shell keeps a picture it is showing in memory under its path, so a
    rebuilt picture at the same path would not appear. In that case another
    picture is shown for a moment first, which makes the shell drop the old one.
    """
    showing = {desk.get("image", "") for desk in desktops_state()}
    if any(str(wallpaper) in image for image in showing):
        standin = find_installed("wallpapers", wallpapers.default_for(pal).package_id)
        if standin is not None:
            log.info("install", "wallpaper is already selected; switching away and back so the rebuilt picture loads")
            run(["plasma-apply-wallpaperimage", str(standin)], "set stand-in wallpaper", check=False)
            time.sleep(SWITCH_PAUSE)
        else:
            log.warn("install", "no stand-in picture installed; a rebuilt wallpaper may only show after the next login",
                     expected=wallpapers.default_for(pal).package_id)
    run(["plasma-apply-wallpaperimage", str(wallpaper)], "set wallpaper")


def reload_cursors(pal: Palette) -> None:
    """Make the window manager read the cursor theme's files afresh.

    KWin remembers where each cursor shape's file is and loads shapes on first
    use, so a reinstalled or moved theme of the same name would leave it with
    stale shapes or missing files. Selecting another theme and coming back
    makes it look again. Also proves the theme is one the chooser can select.
    """
    standin = run(["plasma-apply-cursortheme", STANDIN_CURSORS], "switch to stand-in cursors", check=False)
    if standin.returncode == 0:
        time.sleep(SWITCH_PAUSE / 2)
    chosen = run(["plasma-apply-cursortheme", pal.cursor_id], "apply cursor theme", check=False)
    if chosen.returncode != 0 or "not find" in (chosen.stdout + chosen.stderr).lower():
        log.error("install", "the cursor theme is not selectable; is it installed?",
                  cursor=pal.cursor_id, output=(chosen.stdout + chosen.stderr).strip()[-400:])
        raise StepError(f"cursor theme {pal.cursor_id} could not be applied")
    log.info("install", "cursor theme reloaded", cursor=pal.cursor_id)


def reload_decoration(pal: Palette) -> None:
    """Make the running window manager load the decoration's files afresh.

    KWin keeps a loaded decoration for as long as any window uses it, so a plain
    reconfigure leaves a reinstalled decoration unseen until the next login.
    Switching to another decoration and back releases it; windows show the
    stand-in frame for a moment. The setting is restored even if a step fails.
    """
    library = SETTINGS["decoration_library"]
    try:
        write_setting(*library, STANDIN_DECORATION)
        run(["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"], "switch to stand-in decoration", check=False)
        time.sleep(SWITCH_PAUSE)
    except StepError as exc:
        log.warn("install", "could not switch decorations; a reinstalled decoration may only load after the next login", error=exc)
    finally:
        write_setting(*library, "org.kde.kwin.aurorae")
        write_setting(*SETTINGS["decoration_theme"], pal.decoration_id)
        run(["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"], "reload window manager", check=False)
    log.info("install", "window decoration reloaded", decoration=pal.decoration_id)


def notify_style_change() -> None:
    """Make running KDE applications rebuild their widget style, which also
    rereads a rebuilt Kvantum theme."""
    run(["dbus-send", "--session", "--type=signal", "/KGlobalSettings", "org.kde.KGlobalSettings.notifyChange",
         "int32:2", "int32:0"], "notify applications of the widget style", check=False)


def session_tool(cmd: list[str], what: str) -> subprocess.CompletedProcess | None:
    """Run a session-management command; None when the tool is missing."""
    try:
        return run(cmd, what, check=False)
    except StepError as exc:
        log.warn("install", f"{what}: unavailable", error=exc)
        return None


def export_plugin_path() -> bool:
    """Put the plugin folder on QT_PLUGIN_PATH of the running session, which the
    login script only does from the next login on. True if it was added now."""
    shown = session_tool(["systemctl", "--user", "show-environment"], "read the session environment")
    if shown is None or shown.returncode != 0:
        log.warn("install", "session environment unreadable; the keyblade browser loads after the next login")
        return False
    current = next((line.split("=", 1)[1] for line in shown.stdout.splitlines() if line.startswith("QT_PLUGIN_PATH=")), "")
    parts = [part for part in current.split(":") if part]
    if str(PLUGIN_ROOT) in parts:
        return False
    value = ":".join([str(PLUGIN_ROOT), *parts])
    run(["systemctl", "--user", "set-environment", f"QT_PLUGIN_PATH={value}"], "add the plugin folder to the session")
    log.info("install", "plugin folder added to the session environment", qt_plugin_path=value)
    return True


def shell_started_before(path: Path) -> bool:
    """True when the running shell started before `path` last changed, so it
    may hold an older copy of that plugin."""
    shown = session_tool(["systemctl", "--user", "show", SHELL_SERVICE, "-p", "ExecMainStartTimestamp",
                          "--timestamp=unix", "--value"], "read when the shell started")
    try:
        started = float(shown.stdout.strip().lstrip("@")) if shown is not None else None
    except ValueError:
        started = None
    if started is None:
        log.debug("install", "shell start time unknown", output=shown.stdout.strip() if shown else None)
        return False
    return path.stat().st_mtime > started


def restart_shell() -> None:
    """Restart the Plasma shell (desktop and panels) and wait until it is back.
    It reads mouse actions and plugin folders only when it starts."""
    state = session_tool(["systemctl", "--user", "is-active", SHELL_SERVICE], "check the shell service")
    if state is None or state.stdout.strip() != "active":
        log.warn("install", "the Plasma shell does not run as a systemd service; log out and in to load the change",
                 service=SHELL_SERVICE)
        return
    run(["systemctl", "--user", "restart", SHELL_SERVICE], "restart the Plasma shell", timeout=90)
    deadline = time.monotonic() + SHELL_WAIT
    while time.monotonic() < deadline:
        probe = session_tool(["qdbus6", "org.kde.plasmashell", "/PlasmaShell"], "wait for the shell")
        if probe is not None and probe.returncode == 0:
            log.info("install", "Plasma shell restarted")
            return
        time.sleep(0.5)
    log.warn("install", "the Plasma shell did not come back on D-Bus in time", waited_s=SHELL_WAIT)


def enable_keyblade_browser() -> None:
    """Bind Super + right click on the desktop to the Keyblade Browser."""
    plugin = installed_plugin()
    if plugin is None:
        log.warn("install", "keyblade browser not installed; Super + right click left as it was", expected=str(PLUGIN),
                 package_record=str(SYSTEM_INSTALL))
        return
    stale = unresolved_libraries(plugin)
    if stale:
        log.error("install", "the keyblade browser was built against libraries this system no longer has; "
                  "Super + right click left as it was", plugin=str(plugin), missing=stale, hint=rebuild_hint())
        return
    write_setting(*SETTINGS["meta_right_window"], PASS_CLICK)
    install_shell_hook()
    bound = read_setting(*SETTINGS["meta_right_desktop"]) == picker.PLUGIN_ID
    if not bound:
        # The shell only writes this group from its own settings page, so it
        # is safe to change while the shell runs; it is read on restart.
        write_setting(*SETTINGS["meta_right_desktop"], picker.PLUGIN_ID)
    # A package puts the plugin in Qt's own folder, which the shell searches anyway.
    added = export_plugin_path() if plugin == PLUGIN else False
    outdated = shell_started_before(plugin)
    if not bound or added or outdated:
        log.info("install", "restarting the Plasma shell to load the keyblade browser",
                 newly_bound=not bound, plugin_path_added=added, plugin_updated=outdated)
        restart_shell()
    log.info("install", "Super + right click on the desktop opens the keyblade browser", plugin=str(plugin))


def hook_command() -> str:
    """The `rebind` command line for the shell hook, quoted for systemd."""
    launcher = Path("/usr/bin") / SYSTEM_TOOL
    if SYSTEM_INSTALL.is_file() and launcher.is_file():
        return f'"{launcher}" rebind'
    return f'"{sys.executable}" "{Path(__file__).resolve()}" rebind'


def install_shell_hook() -> None:
    """Make every shell start put the Super + right click binding back if it was removed."""
    text = (
        "# Kingdom Hearts theme: restores Super + right click (Keyblade Browser) on the\n"
        "# desktop if a desktop layout reset removed it. Removed by revert and uninstall.\n"
        "[Service]\n"
        # The leading '-' keeps a failing or missing command from stopping the shell.
        f"ExecStartPre=-{hook_command()}\n"
    )
    try:
        if SHELL_HOOK.is_file() and SHELL_HOOK.read_text(encoding="utf-8") == text:
            log.debug("install", "shell hook already in place", path=str(SHELL_HOOK))
            return
        SHELL_HOOK.parent.mkdir(parents=True, exist_ok=True)
        SHELL_HOOK.write_text(text, encoding="utf-8")
    except OSError as exc:
        log.warn("install", "could not install the shell hook; a desktop reset will remove Super + right click until "
                 "the next apply", error=exc, path=str(SHELL_HOOK))
        return
    session_tool(["systemctl", "--user", "daemon-reload"], "reload user units")
    log.info("install", "shell hook installed: Super + right click is restored whenever the shell starts",
             path=str(SHELL_HOOK), command=hook_command())


def remove_shell_hook() -> None:
    if not SHELL_HOOK.exists():
        return
    try:
        SHELL_HOOK.unlink()
        if not any(SHELL_HOOK.parent.iterdir()):
            SHELL_HOOK.parent.rmdir()
    except OSError as exc:
        log.warn("install", "could not remove the shell hook", error=exc, path=str(SHELL_HOOK))
        return
    session_tool(["systemctl", "--user", "daemon-reload"], "reload user units")
    log.info("install", "shell hook removed", path=str(SHELL_HOOK))


def cmd_rebind(_args) -> int:
    """Run by the shell hook before the shell starts. Never fails: the shell
    starts either way, so problems are only logged."""
    plugin = installed_plugin()
    if plugin is None:
        log.warn("rebind", "keyblade browser not installed; nothing to bind", expected=str(PLUGIN))
        return 0
    stale = unresolved_libraries(plugin)
    if stale:
        log.error("rebind", "the keyblade browser cannot load until it is rebuilt; binding left as it is",
                  plugin=str(plugin), missing=stale, hint=rebuild_hint())
        return 0
    current = read_setting(*SETTINGS["meta_right_desktop"])
    if current == picker.PLUGIN_ID:
        log.debug("rebind", "Super + right click is bound to the keyblade browser")
    elif current:
        # Something else was chosen on the shell's Mouse Actions page; that choice stands.
        log.info("rebind", "Super + right click is bound to another action; left as it is", action=current)
        return 0
    else:
        write_setting(*SETTINGS["meta_right_desktop"], picker.PLUGIN_ID)
        log.info("rebind", "Super + right click was removed (desktop layout reset); bound to the keyblade browser again")
    if read_setting(*SETTINGS["meta_right_window"]) != PASS_CLICK:
        write_setting(*SETTINGS["meta_right_window"], PASS_CLICK)
        run(["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"], "reload window manager", check=False)
        log.info("rebind", "KWin set to pass Super + right click on to the desktop again")
    return 0


def disable_keyblade_browser(saved: dict) -> None:
    remove_shell_hook()
    write_setting(*SETTINGS["meta_right_window"], saved.get("meta_right_window"))
    if points_at_ours(read_setting(*SETTINGS["meta_right_desktop"])):
        write_setting(*SETTINGS["meta_right_desktop"], saved.get("meta_right_desktop"))
        restart_shell()


def cmd_apply(args) -> int:
    pal = variant(args.variant)
    missing = missing_components(pal)
    if missing:
        log.error("install", "variant is not fully installed; run './install.py install'", variant=pal.key, missing=missing)
        return 2
    save_backup()

    # A custom accent colour overrides every scheme's selection colours, which
    # would replace the variant's palette; it is saved in the backup and removed.
    if read_setting(*SETTINGS["accent"]):
        write_setting(*SETTINGS["accent"], None)
        log.info("install", "removed custom accent colour so the variant's own colours apply")

    # The global theme picks the Kvantum style key (kvantum / kvantum-dark);
    # which Kvantum theme that loads is Kvantum's own setting.
    write_setting(*SETTINGS["kvantum_theme"], kvantum.THEME)
    run(["plasma-apply-lookandfeel", "--keep-auto", "-a", pal.theme_id], "apply global theme", timeout=120)
    if shutil.which("kvantummanager") is None:
        # Without the engine the style key names nothing and Qt would fall back
        # to Fusion; Breeze at least follows the colour scheme.
        write_setting(*SETTINGS["widgetstyle"], "Breeze")
        log.warn("install", "Kvantum is not installed; application widgets use Breeze instead",
                 hint="install the kvantum package and apply again")
    # Re-applying the scheme makes sure colours are regenerated without the accent.
    run(["plasma-apply-colorscheme", scheme_id(pal)], "apply colour scheme", check=False)

    # The combined wallpaper package carries a light and a dark image, so the
    # picture follows the colour scheme when Plasma switches day/night themes.
    wallpaper = find_installed("wallpapers", PREFIX)
    set_wallpaper(pal, wallpaper)

    lock = ["Greeter", "Wallpaper", "org.kde.image", "General"]
    write_setting("kscreenlockerrc", ["Greeter"], "WallpaperPlugin", "org.kde.image")
    write_setting("kscreenlockerrc", lock, "Image", str(wallpaper))
    write_setting("kscreenlockerrc", lock, "PreviewImage", str(wallpaper))

    write_setting(*SETTINGS["sounds"], SOUND_THEME)

    # Pair the variants so Plasma's light/dark switch moves between them.
    write_setting("kdeglobals", ["KDE"], "DefaultDarkLookAndFeel", ORG_XIII.theme_id)
    write_setting("kdeglobals", ["KDE"], "DefaultLightLookAndFeel", SORA.theme_id)

    if args.konsole:
        previous = set_konsole_scheme(pal.theme_id)
        if BACKUP.exists():
            data = json.loads(BACKUP.read_text(encoding="utf-8"))
            data.setdefault("konsole", previous)
            BACKUP.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    enable_keyblade_browser()
    # Puts the chosen keyblade back; with a package install this also makes the
    # user's copy of the cursors again after a package upgrade.
    tool = keyblade_tool()
    if tool is not None:
        run([str(tool), "restore", "--no-reload"], "restore the chosen keyblade", check=False)
    reload_cursors(pal)
    reload_decoration(pal)
    notify_style_change()
    login, _ = sddm_current()
    if not is_ours(login):
        log.info("install", "the login screen is not themed", current=login or "<default>",
                 hint=f"./install.py sddm {pal.key}  (or System Settings > Login Screen)")
    log.info("install", "variant applied", variant=pal.key, theme=pal.theme_id)
    return 0


def cmd_revert(_args) -> int:
    if not BACKUP.exists():
        log.error("install", "no backup found; nothing to revert to", backup=str(BACKUP))
        return 2
    try:
        data = json.loads(BACKUP.read_text(encoding="utf-8"))
        saved = data["settings"]
    except (json.JSONDecodeError, KeyError) as exc:
        log.error("install", "backup file is unreadable", error=exc, backup=str(BACKUP))
        return 1

    failures = []

    def step(what: str, fn) -> None:
        try:
            fn()
        except StepError as exc:
            failures.append(what)
            log.warn("install", "revert step failed, continuing", error=exc, step=what)

    # Re-applying the previous global theme restores its defaults layer; the
    # individual settings the user had on top of it are then put back one by one.
    step("accent colour", lambda: write_setting(*SETTINGS["accent"], saved.get("accent")))
    previous = saved.get("lookandfeel")
    if previous:
        step("global theme", lambda: run(["plasma-apply-lookandfeel", "--keep-auto", "-a", previous], "restore global theme", timeout=120))
    if saved.get("colorscheme"):
        step("colour scheme", lambda: run(["plasma-apply-colorscheme", saved["colorscheme"]], "restore colour scheme"))
    if saved.get("plasmatheme"):
        step("plasma style", lambda: run(["plasma-apply-desktoptheme", saved["plasmatheme"]], "restore plasma style"))
    if saved.get("cursor"):
        step("cursors", lambda: run(["plasma-apply-cursortheme", saved["cursor"]], "restore cursor theme"))
    if saved.get("icons"):
        step("icons", lambda: run(["/usr/lib/plasma-changeicons", saved["icons"]], "restore icon theme"))
    for name in ("decoration_library", "decoration_theme", "widgetstyle", "kvantum_theme", "splash",
                 "splash_engine", "sounds",
                 "light_lookandfeel", "dark_lookandfeel", "lock_plugin", "lock_image", "lock_preview"):
        file, groups, key = SETTINGS[name]
        step(name, lambda f=file, g=groups, k=key, v=saved.get(name): write_setting(f, g, k, v))

    def restore_wallpaper() -> None:
        desktops = data.get("desktops") or []
        if not desktops:
            log.warn("install", "no wallpaper state in backup; wallpaper left as is")
            return
        script = (
            "var saved=" + json.dumps(desktops) + "; var ds=desktops();"
            "for (var i=0;i<ds.length;i++){ for (var j=0;j<saved.length;j++){"
            "if (saved[j].id==ds[i].id){ ds[i].wallpaperPlugin=saved[j].plugin; } } }"
        )
        plasma_script(script, "restore wallpaper plugins")

    step("wallpaper", restore_wallpaper)
    step("keyblade browser", lambda: disable_keyblade_browser(saved))
    if "konsole" in data:
        step("konsole", lambda: set_konsole_scheme(None, saved=data["konsole"]))

    step("window manager", lambda: run(["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"], "reload window manager"))
    notify_style_change()

    if failures:
        log.error("install", "revert finished with failed steps; backup kept", failed=failures, backup=str(BACKUP))
        return 1
    BACKUP.rename(BACKUP.with_suffix(".restored.json"))
    log.info("install", "previous look restored", lookandfeel=previous)
    return 0


def cmd_status(_args) -> int:
    plugin = installed_plugin()
    stale = unresolved_libraries(plugin) if plugin is not None else []
    if stale:
        log.warn("install", "the keyblade browser cannot load until it is rebuilt", missing=stale, hint=rebuild_hint())
    active = {name: read_setting(*spec) for name, spec in SETTINGS.items()}
    bound = active["meta_right_desktop"] == picker.PLUGIN_ID
    if plugin is not None and not bound and is_ours(active["lookandfeel"]):
        # Applying a Global Theme together with its desktop layout makes the
        # shell discard its whole configuration, mouse actions included.
        log.warn("install", "Super + right click no longer opens the keyblade browser (a desktop layout reset "
                 "removes mouse actions)", hint=f"apply the variant again: apply {active['lookandfeel'].split('-')[-1]}")
    report = {
        "installed": {pal.key: not missing_components(pal) for pal in VARIANTS},
        "missing": {pal.key: missing_components(pal) for pal in VARIANTS},
        "active": active,
        "keyblade": read_setting(KEYBLADE_RC.name, ["Keyblade"], "Current") or None,
        "keyblade_browser": plugin is not None and not stale,
        "keyblade_browser_bound": bound,
        "keyblade_browser_missing_libraries": stale,
        "keyblade_browser_shell_hook": SHELL_HOOK.is_file(),
        "login_screen": sddm_current()[0] or None,
        "package": system_install().get("version"),
        "backup": str(BACKUP) if BACKUP.exists() else None,
    }
    print(json.dumps(report, indent=2))
    return 0


def cmd_keyblade(args) -> int:
    tool = keyblade_tool()
    if tool is None:
        log.error("install", "keyblade tool not built; run './build.py --only picker'", expected=str(picker.cli(DIST)))
        return 2
    command = [str(tool), "equip", args.name] if args.name else [str(tool), "list"]
    # Output (the list) goes straight to the terminal.
    result = subprocess.run(command, timeout=60)
    if result.returncode != 0:
        log.error("install", "keyblade tool failed", exit_code=result.returncode, command=command[1])
    return result.returncode


def sddm_files() -> list[Path]:
    files = [f for d in SDDM_CONF_DIRS if d.is_dir() for f in sorted(d.iterdir()) if f.is_file()]
    return files + ([SDDM_CONF] if SDDM_CONF.is_file() else [])


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


def sddm_current() -> tuple[str, Path | None]:
    """The login theme SDDM will show, and the file that sets it (None: SDDM's default)."""
    current, source = "", None
    for path in sddm_files():
        try:
            value = ini_value(path.read_text(encoding="utf-8", errors="replace"), "Theme", "Current")
        except OSError as exc:
            log.warn("sddm", "could not read an SDDM config file", error=exc, path=str(path))
            continue
        if value is not None:
            current, source = value, path
    return current, source


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


def sddm_source(pal: Palette) -> tuple[Path | None, bool]:
    """Where the variant's login theme is: (folder, already in SDDM's theme folder)."""
    built = DIST / "sddm" / sddm.theme_id(pal)
    if built.is_dir():
        return built, False
    installed = SDDM_THEMES / sddm.theme_id(pal)
    return (installed, True) if installed.is_dir() else (None, False)


def choose_login(arg: str | None) -> str:
    """'off' or a variant key: the argument, else asked, else the active variant."""
    keys = [pal.key for pal in VARIANTS] + ["off"]
    if arg:
        match = next((k for k in keys if k.lower() == arg.lower()), None)
        if match is None:
            raise StepError(f"unknown login screen {arg!r}; choose from {keys}")
        return match
    active = read_setting(*SETTINGS["lookandfeel"]) if shutil.which("kreadconfig6") else ""
    default = next((pal.key for pal in VARIANTS if pal.theme_id == active), VARIANTS[0].key)
    if not sys.stdin.isatty():
        log.info("sddm", "no login screen named and no terminal to ask; using the active variant", choice=default)
        return default
    options = [f"Kingdom Hearts – {pal.title} ({'dark' if pal.dark else 'light'})" for pal in VARIANTS]
    options.append("Off: go back to the login screen used before")
    print("Login screen:")
    for n, text in enumerate(options, 1):
        print(f"  {n}. {text}{'  [default]' if keys[n - 1] == default else ''}")
    answer = input(f"Choose 1-{len(options)}: ").strip()
    if not answer:
        return default
    if answer.isdigit() and 1 <= int(answer) <= len(options):
        return keys[int(answer) - 1]
    raise StepError(f"not a choice: {answer!r}")


def cmd_sddm(args) -> int:
    choice = choose_login(args.variant)
    current, source = sddm_current()
    script = ["set -e"]
    if choice == "off":
        try:
            target = json.loads(SDDM_STATE.read_text(encoding="utf-8")).get("previous") or SDDM_FALLBACK
        except (OSError, json.JSONDecodeError) as exc:
            log.warn("sddm", "no record of the earlier login screen; using Plasma's", error=exc, fallback=SDDM_FALLBACK)
            target = SDDM_FALLBACK
    else:
        pal = variant(choice)
        target = sddm.theme_id(pal)
        missing = []
        for each in VARIANTS:
            folder, installed = sddm_source(each)
            if folder is None:
                missing.append(sddm.theme_id(each))
            elif not installed:
                dest = SDDM_THEMES / folder.name
                script.append(f"rm -rf {shlex.quote(str(dest))}")
                script.append(f"cp -r {shlex.quote(str(folder))} {shlex.quote(str(SDDM_THEMES))}/")
                script.append(f"chmod -R u=rwX,go=rX {shlex.quote(str(dest))}")
        if target in missing:
            log.error("sddm", "login theme not built; run './build.py --only sddm'", missing=missing)
            return 2
        if missing:
            log.warn("sddm", "a login theme is not built and is left out", missing=missing)
        legacy = SDDM_THEMES / sddm.LEGACY_ID
        if legacy.is_dir():
            script.append(f"rm -rf {shlex.quote(str(legacy))}")
    # Write where the value SDDM uses now comes from, so nothing later overrides
    # it; a value from SDDM's own defaults goes into System Settings' file.
    conf = source if source is not None and source != SDDM_LEGACY_CONF and str(source).startswith("/etc/") \
        else SDDM_KDE_CONF
    try:
        text = conf.read_text(encoding="utf-8") if conf.is_file() else ""
    except OSError as exc:
        log.error("sddm", "could not read the SDDM config file", error=exc, path=str(conf))
        return 1
    staged = STATE / "sddm-config.new"
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        staged.write_text(with_ini_value(text, "Theme", "Current", target), encoding="utf-8")
    except OSError as exc:
        log.error("sddm", "could not prepare the SDDM config", error=exc, path=str(staged))
        return 1
    script.append(f"mkdir -p {shlex.quote(str(conf.parent))}")
    script.append(f"install -m 644 {shlex.quote(str(staged))} {shlex.quote(str(conf))}")
    if SDDM_LEGACY_CONF.exists():
        script.append(f"rm -f {shlex.quote(str(SDDM_LEGACY_CONF))}")
    shell = "\n".join(script) + "\n"
    if args.print:
        print(f"# Selects login screen {target} (needs root):")
        print(f"sudo sh -c {shlex.quote(shell)}")
        return 0

    log.info("sddm", "setting the login screen; sudo asks for your password", choice=target, previous=current or "<default>",
             config=str(conf))
    started = time.monotonic()
    try:
        # Not captured: sudo needs the terminal to ask for the password.
        result = subprocess.run(["sudo", "sh", "-c", shell], timeout=300)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.error("sddm", "could not run sudo", error=exc, hint="./install.py sddm --print shows the commands")
        return 1
    finally:
        staged.unlink(missing_ok=True)
    if result.returncode != 0:
        log.error("sddm", "installing the login screen failed", exit_code=result.returncode,
                  hint="./install.py sddm --print shows the commands")
        return 1
    if choice != "off" and not is_ours(current):
        try:
            SDDM_STATE.write_text(json.dumps({"previous": current}) + "\n", encoding="utf-8")
        except OSError as exc:
            log.warn("sddm", "could not record the earlier login screen; 'sddm off' will use Plasma's", error=exc)
    shown, by = sddm_current()
    if shown != target:
        log.error("sddm", "another SDDM config file still overrides the login screen", wanted=target, shown=shown,
                  file=str(by))
        return 1
    log.info("sddm", "login screen set; it shows from the next time SDDM starts (log out or reboot)", theme=target,
             config=str(conf), duration_ms=round((time.monotonic() - started) * 1000))
    return 0


def stage_copy(source: Path, target: Path, mode: int | None = None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, symlinks=True)
    else:
        shutil.copy2(source, target)
        if mode is not None:
            target.chmod(mode)


def cmd_stage(args) -> int:
    """Lay the built themes, the keyblade plugin and command, and this tool out
    under DESTDIR/usr the way a system-wide package installs them."""
    if not DIST.is_dir():
        log.error("stage", "nothing to stage: run ./build.py first", dist=str(DIST))
        return 2
    destdir = Path(args.destdir).resolve()
    usr = destdir / "usr"
    plugin, tool = picker.plugin_file(DIST), picker.cli(DIST)
    plugin_dir_record = picker.build_dir(DIST) / "qt-plugin-dir"
    required = [DIST / sub for sub in SYSTEM_TREES] + [plugin, tool, plugin_dir_record]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        # A package must be complete; a partial build would ship silently broken.
        log.error("stage", "build output incomplete; run ./build.py", missing=missing)
        return 2
    qt_plugins = Path(plugin_dir_record.read_text(encoding="utf-8").strip())
    if not qt_plugins.is_absolute():
        log.error("stage", "the recorded Qt plugin folder is not an absolute path", value=str(qt_plugins),
                  record=str(plugin_dir_record))
        return 2

    staged = 0
    try:
        for sub, rel in SYSTEM_TREES.items():
            for entry in sorted((DIST / sub).iterdir()):
                if not is_ours(entry.name):
                    log.warn("stage", "unexpected entry in dist, skipped", entry=str(entry))
                    continue
                stage_copy(entry, usr / rel / entry.name)
                staged += 1
        plugin_target = destdir / qt_plugins.relative_to("/") / picker.NAMESPACE / plugin.name
        stage_copy(plugin, plugin_target, 0o755)
        stage_copy(tool, usr / "bin" / tool.name, 0o755)

        share = usr / "share" / SYSTEM_TOOL
        stage_copy(Path(__file__).resolve(), share / "install.py", 0o755)
        for module in sorted((ROOT / "khtheme").glob("*.py")):
            stage_copy(module, share / "khtheme" / module.name, 0o644)
        record = {
            "version": VERSION,
            "plugin": "/" + str(plugin_target.relative_to(destdir)),
            "keyblade_tool": f"/usr/bin/{tool.name}",
        }
        (share / SYSTEM_INSTALL.name).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        launcher = usr / "bin" / SYSTEM_TOOL
        launcher.write_text(
            "#!/bin/sh\n# Applies, reverts and reports the Kingdom Hearts themes for the current user.\n"
            f'exec python3 /usr/share/{SYSTEM_TOOL}/install.py "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)
    except (OSError, ValueError) as exc:
        log.error("stage", "staging failed", error=exc, destdir=str(destdir))
        return 1
    log.info("stage", "system-wide layout staged", destdir=str(destdir), themes=staged, version=VERSION,
             plugin=record["plugin"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("install").set_defaults(fn=cmd_install)
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("variant", help="OrgXIII (dark) or Sora (light)")
    apply_parser.add_argument("--konsole", action="store_true", help="also switch Konsole profiles to the variant's colours")
    apply_parser.set_defaults(fn=cmd_apply)
    sub.add_parser("revert").set_defaults(fn=cmd_revert)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    keyblade_parser = sub.add_parser("keyblade")
    keyblade_parser.add_argument("name", nargs="?", help="keyblade to point with, e.g. oathkeeper; omit to list them")
    keyblade_parser.set_defaults(fn=cmd_keyblade)
    sub.add_parser("uninstall").set_defaults(fn=cmd_uninstall)
    sddm_parser = sub.add_parser("sddm")
    sddm_parser.add_argument("variant", nargs="?", help="OrgXIII, Sora, or off (the login screen used before); "
                             "omit to choose from a list")
    sddm_parser.add_argument("--print", action="store_true", help="print the root commands instead of running them")
    sddm_parser.set_defaults(fn=cmd_sddm)
    sub.add_parser("rebind").set_defaults(fn=cmd_rebind)
    stage_parser = sub.add_parser("stage")
    stage_parser.add_argument("--destdir", required=True, help="root to lay /usr out under (a package's staging folder)")
    stage_parser.set_defaults(fn=cmd_stage)
    args = parser.parse_args()

    missing = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
    # Staging runs in a package build, where the desktop's tools need not exist.
    if missing and args.command not in ("sddm", "keyblade", "stage"):
        log.error("install", "required KDE tools are missing", tools=missing)
        return 2

    log.info("install", "command started", command=args.command)
    try:
        code = args.fn(args)
    except StepError as exc:
        log.error("install", "command aborted", error=exc, command=args.command)
        return 1
    except Exception as exc:
        log.error("install", "unexpected failure", error=exc, command=args.command)
        return 1
    log.info("install", "command finished", command=args.command, exit_code=code)
    return code


if __name__ == "__main__":
    sys.exit(main())
