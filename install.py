#!/usr/bin/env python3
"""Install, apply, revert and remove the Kingdom Hearts Plasma themes.

    ./install.py install            copy built assets from dist/ into ~/.local/share (and ~/.config/Kvantum)
    ./install.py apply OrgXIII      switch the desktop to a variant (OrgXIII | Sora)
    ./install.py revert             restore the settings saved before the first apply
    ./install.py status             show what is installed and what is active
    ./install.py keyblade [<name>]  list the pointer keyblades, or point with one
    ./install.py uninstall          remove every installed file (revert first)
    ./install.py sddm               print the root commands that install the login theme

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
import shutil
import subprocess
import sys
import time
from pathlib import Path

from khtheme import kvantum, log, picker, wallpapers
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
def cmd_install(_args) -> int:
    if not DIST.is_dir():
        log.error("install", "nothing to install: run ./build.py first", dist=str(DIST))
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
        "colour scheme": DATA / "color-schemes" / f"{scheme_id(pal)}.colors",
        "plasma style": DATA / "plasma" / "desktoptheme" / pal.theme_id / "metadata.json",
        "global theme": DATA / "plasma" / "look-and-feel" / pal.theme_id / "metadata.json",
        "window decoration": DATA / "kwin" / "decorations" / pal.decoration_id / "contents" / "ui" / "main.qml",
        "icons": DATA / "icons" / pal.theme_id / "index.theme",
        "cursors": TREES["cursors"] / pal.cursor_id / "cursors" / "default",
        "wallpaper": DATA / "wallpapers" / PREFIX / "metadata.json",
        "sound theme": DATA / "sounds" / SOUND_THEME / "index.theme",
        "kvantum style": TREES["Kvantum"] / kvantum.THEME / f"{kvantum.theme_name(pal)}.kvconfig",
    }
    return [name for name, path in expected.items() if not path.exists()]


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
        standin = DATA / "wallpapers" / wallpapers.default_for(pal).package_id
        if standin.is_dir():
            log.info("install", "wallpaper is already selected; switching away and back so the rebuilt picture loads")
            run(["plasma-apply-wallpaperimage", str(standin)], "set stand-in wallpaper", check=False)
            time.sleep(SWITCH_PAUSE)
        else:
            log.warn("install", "no stand-in picture installed; a rebuilt wallpaper may only show after the next login",
                     expected=str(standin))
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
        log.error("install", "the cursor theme is not selectable; is it installed under ~/.icons?",
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
    if not PLUGIN.is_file():
        log.warn("install", "keyblade browser not installed; Super + right click left as it was", expected=str(PLUGIN))
        return
    write_setting(*SETTINGS["meta_right_window"], PASS_CLICK)
    bound = read_setting(*SETTINGS["meta_right_desktop"]) == picker.PLUGIN_ID
    if not bound:
        # The shell only writes this group from its own settings page, so it
        # is safe to change while the shell runs; it is read on restart.
        write_setting(*SETTINGS["meta_right_desktop"], picker.PLUGIN_ID)
    added = export_plugin_path()
    outdated = shell_started_before(PLUGIN)
    if not bound or added or outdated:
        log.info("install", "restarting the Plasma shell to load the keyblade browser",
                 newly_bound=not bound, plugin_path_added=added, plugin_updated=outdated)
        restart_shell()
    log.info("install", "Super + right click on the desktop opens the keyblade browser", plugin=picker.PLUGIN_ID)


def disable_keyblade_browser(saved: dict) -> None:
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
    wallpaper = DATA / "wallpapers" / PREFIX
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
    reload_cursors(pal)
    reload_decoration(pal)
    notify_style_change()
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
    report = {
        "installed": {pal.key: not missing_components(pal) for pal in VARIANTS},
        "missing": {pal.key: missing_components(pal) for pal in VARIANTS},
        "active": {name: read_setting(*spec) for name, spec in SETTINGS.items()},
        "keyblade": read_setting(KEYBLADE_RC.name, ["Keyblade"], "Current") or None,
        "keyblade_browser": PLUGIN.is_file(),
        "backup": str(BACKUP) if BACKUP.exists() else None,
    }
    print(json.dumps(report, indent=2))
    return 0


def cmd_keyblade(args) -> int:
    tool = picker.cli(DIST)
    if not tool.is_file():
        log.error("install", "keyblade tool not built; run './build.py --only picker'", expected=str(tool))
        return 2
    command = [str(tool), "equip", args.name] if args.name else [str(tool), "list"]
    # Output (the list) goes straight to the terminal.
    result = subprocess.run(command, timeout=60)
    if result.returncode != 0:
        log.error("install", "keyblade tool failed", exit_code=result.returncode, command=command[1])
    return result.returncode


def cmd_sddm(_args) -> int:
    source = DIST / "sddm" / PREFIX
    if not source.is_dir():
        log.error("install", "login theme not built; run './build.py --only sddm'", expected=str(source))
        return 2
    print(
        "# The login screen lives in system directories, so these need root:\n"
        f"sudo cp -r {source} /usr/share/sddm/themes/\n"
        "sudo mkdir -p /etc/sddm.conf.d\n"
        f"printf '[Theme]\\nCurrent={PREFIX}\\n' | sudo tee /etc/sddm.conf.d/10-kingdom-hearts.conf\n"
        "# undo: sudo rm /etc/sddm.conf.d/10-kingdom-hearts.conf"
    )
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
    sub.add_parser("sddm").set_defaults(fn=cmd_sddm)
    args = parser.parse_args()

    missing = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
    if missing and args.command not in ("sddm", "keyblade"):
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
