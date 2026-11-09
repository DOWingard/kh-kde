"""Sound theme built from the game sound effects in assets/sounds.

One theme serves both variants. Every desktop event plays the effect that
serves the same purpose in the games: moving the cursor, confirming, backing
out, being refused, an information pop-up, the low-health alarm, and so on.
The effects carry the names of those purposes (see ASSETS.md for where the
names come from), so the table below reads as "event: what the game does
there".

The effects are trimmed of leading and trailing silence and brought to a
common peak level, because the originals differ by more than 10 dB.

Files are written as WAV, which the sound-theme lookup accepts alongside Ogg,
so the build needs no Vorbis encoder. Events not listed here fall back to the
Ocean theme.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from . import log
from .palette import Palette
from .svg import write_text

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "sounds"
THEME_ID = "KingdomHearts"

# Effects, named for what they accompany in the games.
MOVE = "Menu Move"  # the cursor steps to another entry
SELECT = "Menu Select"  # an entry is confirmed
CLOSE = "Menu Close"  # backing out of a menu
OPEN = "Menu Open"  # a menu or prompt opens
DENIED = "Menu Denied"  # the choice is not allowed
NEXT = "Menu Next"  # turning to the next page
INFORMATION = "Information"  # the information pop-up
POPUP = "Popup"  # a reward pop-up: something that wants a look
LOCK_ON = "Lock On"  # a target is locked
LOCK_OFF = "Lock Off"  # the lock is released
CRITICAL = "Critical Health"  # the alarm while health is nearly gone
GAUGE_FULL = "Drive Max"  # a gauge reaches its maximum
ENERGY = "MP Bubble"  # picking up magic energy
SAVED = "Save Game"  # the game has been saved
REWARD = "Reward"  # something has been obtained
START = "Title Screen Start KH3"  # starting from the title screen
POWER_DOWN = "Computer Off"  # a computer shuts down
PHOTO = "Photo"  # a picture is taken
TIME_UP = "Match Count End"  # a match countdown runs out
VANISH = "Enemy Despawn KH2"  # a defeated enemy disappears
WIN = "Match Win"
LOSE = "Match Lose"
# From Melody of Memory's menus only; no counterpart in the main games.
SERIOUS = "SE_MENU_NET_ERROR"  # its connection-error dialog
CAUTION = "SE_MENU_NOTICE_003"  # a notice of its own; the exact trigger in the game is not identified

# event -> (effect, peak level in dBFS). Frequent, small events sit lower.
EVENTS: dict[str, tuple[str, float]] = {
    # --- notifications: the information pop-up ---
    "message-new-instant": (INFORMATION, -6),
    "message-new-email": (INFORMATION, -6),
    "message": (INFORMATION, -6),
    "message-highlight": (INFORMATION, -6),
    "dialog-information": (INFORMATION, -6),
    "theme-demo": (INFORMATION, -6),
    # --- something asks to be looked at ---
    "message-attention": (POPUP, -6),
    "window-attention": (POPUP, -6),
    "software-update-available": (POPUP, -8),
    "dialog-warning": (CAUTION, -6),
    # --- selection: the cursor moving over choices ---
    "audio-volume-change": (MOVE, -10),
    "completion-rotation": (MOVE, -10),
    "item-selected": (MOVE, -12),
    "menu-replace": (MOVE, -12),
    "notebook-tab-changed": (NEXT, -12),
    # --- confirming ---
    "button-pressed": (SELECT, -12),
    "menu-click": (SELECT, -12),
    "dialog-ok": (SELECT, -9),
    "completion-success": (SELECT, -10),
    "message-sent-instant": (SELECT, -9),
    "service-login": (SELECT, -8),
    "device-added": (SELECT, -8),
    # --- backing out ---
    "dialog-cancel": (CLOSE, -9),
    "menu-popdown": (CLOSE, -12),
    "window-close": (CLOSE, -12),
    "service-logout": (CLOSE, -8),
    "device-removed": (CLOSE, -8),
    # --- a prompt or menu opens ---
    "dialog-question": (OPEN, -6),
    "dialog-warning-auth": (OPEN, -6),
    "menu-popup": (OPEN, -12),
    "window-new": (OPEN, -12),
    # --- refused: the system bell is the desktop's "you cannot do that" ---
    "bell": (DENIED, -9),
    "bell-window-system": (DENIED, -9),
    "completion-fail": (DENIED, -9),
    "dialog-error": (DENIED, -5),
    "outcome-failure": (DENIED, -6),
    "complete-media-error": (DENIED, -6),
    "suspend-error": (DENIED, -6),
    "dialog-error-serious": (SERIOUS, -6),
    "dialog-error-critical": (SERIOUS, -6),
    # --- switches ---
    "button-toggle-on": (LOCK_ON, -12),
    "button-toggle-off": (LOCK_OFF, -12),
    "button-pressed-modifier": (LOCK_ON, -12),
    "message-contact-in": (LOCK_ON, -9),
    "message-contact-out": (LOCK_OFF, -9),
    # --- power: the battery is the health and magic gauge ---
    "battery-low": (CRITICAL, -6),
    "battery-caution": (CRITICAL, -8),
    "battery-full": (GAUGE_FULL, -6),
    "power-plug": (ENERGY, -8),
    "power-unplug": (LOCK_OFF, -8),
    # --- finished work ---
    "outcome-success": (SAVED, -6),
    "complete-media-burn": (SAVED, -6),
    "complete": (REWARD, -6),
    "complete-download": (REWARD, -6),
    "alarm-clock-elapsed": (TIME_UP, -4),
    # --- session ---
    "desktop-login": (START, -6),
    "desktop-logout": (POWER_DOWN, -6),
    # --- the rest ---
    "camera-shutter": (PHOTO, -6),
    "screen-capture": (PHOTO, -8),
    "trash-empty": (VANISH, -8),
    "game-over-winner": (WIN, -6),
    "game-over-loser": (LOSE, -6),
}

INDEX = f"""[Sound Theme]
Name=Kingdom Hearts
Comment=Sound effects from the Kingdom Hearts games, each used for what it means there
Inherits=ocean
Directories=stereo
Example=theme-demo

[stereo]
OutputProfile=stereo
"""

# Cut silence from both ends; reversing the clip lets the same filter trim the tail.
_TRIM = (
    "silenceremove=start_periods=1:start_threshold=-55dB:start_silence=0.01,areverse,"
    "silenceremove=start_periods=1:start_threshold=-55dB:start_silence=0.05,areverse"
)
# Jingles are faded out at this length; an event sound should not outstay its event.
MAX_SECONDS = 4.5
FADE_OUT = 0.8
# Long enough to stop a click at the cut, short enough to leave an effect's attack alone.
FADE_IN = 0.001
# A clip is brought to its event's peak level, but never above this mean
# level: an alarm made of steady tones would otherwise come out far louder
# than a chime with the same peak.
MEAN_CEILING_DB = -20.0
# What every clip goes through before it is measured or written: the same
# stereo fold-down, trim and length. The fold-down runs on floating-point
# samples because a surround source summed into two integer channels clips.
_PREPARE = f"aformat=sample_fmts=flt,aformat=channel_layouts=stereo,{_TRIM},atrim=0:{MAX_SECONDS}"
_MEASURE = "astats=metadata=0:measure_overall=Peak_level+RMS_level:measure_perchannel=none"
_built = False


def _ffmpeg(args: list[str], what: str) -> str:
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-y", *args], check=True, capture_output=True, text=True, timeout=120
        )
    except FileNotFoundError as exc:
        log.error("sounds", "ffmpeg is not installed", error=exc, step=what)
        raise
    except subprocess.TimeoutExpired as exc:
        log.error("sounds", "ffmpeg timed out", error=exc, step=what)
        raise
    except subprocess.CalledProcessError as exc:
        log.error("sounds", "ffmpeg failed", error=exc, step=what, stderr=exc.stderr[-1500:])
        raise
    return result.stderr


def _levels(source: Path) -> tuple[float, float]:
    """Peak and mean level, in dBFS, of the clip as it will be written."""
    report = _ffmpeg(["-i", str(source), "-af", f"{_PREPARE},{_MEASURE}", "-f", "null", "-"], "measure level")
    peak = re.search(r"Peak level dB:\s*(-?[\d.]+)", report)
    mean = re.search(r"RMS level dB:\s*(-?[\d.]+)", report)
    if not peak or not mean:
        log.error("sounds", "could not measure the clip's level", source=source.name, report=report[-400:])
        raise ValueError(f"no level reported for {source.name}")
    return float(peak.group(1)), float(mean.group(1))


def build(out: Path, pal: Palette) -> Path:
    global _built
    root = out / "sounds" / THEME_ID
    if _built:
        log.debug("sounds", "sound theme already built in this run", variant=pal.key)
        return root
    with log.timed("sounds", "build sound theme", target=str(root)):
        missing = sorted({effect for effect, _ in EVENTS.values() if not (ASSETS / f"{effect}.wav").is_file()})
        if missing:
            log.error("sounds", "sound effects are missing from assets/sounds", effects=missing)
            raise FileNotFoundError(f"missing sound effects: {missing}")
        if root.exists():
            shutil.rmtree(root)
        (root / "stereo").mkdir(parents=True)
        levels: dict[str, tuple[float, float]] = {}
        for event, (effect, target) in EVENTS.items():
            source = ASSETS / f"{effect}.wav"
            if effect not in levels:
                levels[effect] = _levels(source)
            peak, mean = levels[effect]
            gain = min(target - peak, MEAN_CEILING_DB - mean)
            if gain < target - peak:
                log.debug("sounds", "dense clip held below its peak target", event=event, effect=effect,
                          peak_dbfs=round(peak + gain, 1), target_dbfs=target)
            _ffmpeg(
                ["-i", str(source), "-af",
                 f"{_PREPARE},volume={gain:.2f}dB,afade=t=in:d={FADE_IN},"
                 f"afade=t=out:st={MAX_SECONDS - FADE_OUT}:d={FADE_OUT}",
                 "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(root / "stereo" / f"{event}.wav")],
                event,
            )
            log.debug("sounds", "event written", event=event, effect=effect, gain_db=round(gain, 2))
        write_text(root / "index.theme", INDEX)
        log.info("sounds", "sound theme written", events=len(EVENTS), effects=len(levels))
    _built = True
    return root
