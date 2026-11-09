"""Sound theme built from the menu sound effects in assets/sounds.

One theme serves both variants. Each desktop event is mapped to a menu effect
by what the effect means in the game (confirm, cancel, error, notice, ...).
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
PREFIX = "SE_MENU_"

# event -> (effect, peak level in dBFS). Frequent, small events sit lower.
EVENTS: dict[str, tuple[str, float]] = {
    "dialog-information": ("NOTICE_001", -6),
    "dialog-question": ("COMM_MENU", -6),
    "dialog-warning": ("NOTICE_003", -6),
    "dialog-warning-auth": ("COMM_MENU", -6),
    "dialog-error": ("COMM_NG", -5),
    "dialog-error-serious": ("NET_ERROR", -6),
    "dialog-error-critical": ("NET_ERROR", -6),
    "message-new-instant": ("NOTICE_004", -6),
    "message-new-email": ("NOTICE_004", -6),
    "message-attention": ("NOTICE_003", -6),
    "message-highlight": ("NOTICE_001", -6),
    "message-sent-instant": ("COMM_ENTER_001", -9),
    "message-contact-in": ("COMM_CHECK_ON", -9),
    "message-contact-out": ("COMM_CHECK_OFF", -9),
    "desktop-login": ("TITLE_ENTER", -6),
    "desktop-logout": ("COMM_FADEOUT", -6),
    "service-login": ("COMM_ENTER_001", -8),
    "service-logout": ("COMM_CANCEL", -8),
    "device-added": ("COMM_ENTER_001", -8),
    "device-removed": ("COMM_CANCEL", -8),
    "power-plug": ("COMM_CHECK_ON", -8),
    "power-unplug": ("COMM_CHECK_OFF", -8),
    "audio-volume-change": ("COMM_SELECT", -10),
    "bell": ("COMM_CANCEL", -8),
    "bell-window-system": ("COMM_CANCEL", -8),
    "button-pressed": ("COMM_SELECT", -12),
    "button-pressed-modifier": ("COMM_CHECK_ON", -12),
    "completion-success": ("COMM_SAVEEND", -6),
    "completion-partial": ("NOTICE_001", -6),
    "completion-fail": ("COMM_NG", -6),
    "completion-rotation": ("COMM_PAGESLIDE", -8),
    "complete-media-burn": ("COMM_SAVEEND", -6),
    "complete-media-error": ("COMM_NG", -6),
    "outcome-success": ("RESULT_ITEM_GET", -6),
    "outcome-failure": ("COMM_NG", -6),
    "battery-low": ("NOTICE_003", -6),
    "battery-caution": ("NET_ERROR", -6),
    "battery-full": ("RESULT_ITEM_GET", -6),
    "alarm-clock-elapsed": ("RESULT_LEVELUP_01", -4),
    "trash-empty": ("COMM_FADEOUT", -8),
    "theme-demo": ("TITLE_ENTER", -6),
}

INDEX = f"""[Sound Theme]
Name=Kingdom Hearts
Comment=Menu sound effects from Kingdom Hearts Melody of Memory
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


def _peak(source: Path) -> float:
    """Peak level of the trimmed clip in dBFS."""
    report = _ffmpeg(["-i", str(source), "-af", f"{_TRIM},volumedetect", "-f", "null", "-"], "measure level")
    match = re.search(r"max_volume:\s*(-?[\d.]+) dB", report)
    if not match:
        log.error("sounds", "could not measure the clip's level", source=source.name, report=report[-400:])
        raise ValueError(f"no level reported for {source.name}")
    return float(match.group(1))


def build(out: Path, pal: Palette) -> Path:
    global _built
    root = out / "sounds" / THEME_ID
    if _built:
        log.debug("sounds", "sound theme already built in this run", variant=pal.key)
        return root
    with log.timed("sounds", "build sound theme", target=str(root)):
        missing = sorted({effect for effect, _ in EVENTS.values() if not (ASSETS / f"{PREFIX}{effect}.wav").is_file()})
        if missing:
            log.error("sounds", "sound effects are missing from assets/sounds", effects=missing)
            raise FileNotFoundError(f"missing sound effects: {missing}")
        if root.exists():
            shutil.rmtree(root)
        (root / "stereo").mkdir(parents=True)
        peaks: dict[str, float] = {}
        for event, (effect, target) in EVENTS.items():
            source = ASSETS / f"{PREFIX}{effect}.wav"
            if effect not in peaks:
                peaks[effect] = _peak(source)
            gain = target - peaks[effect]
            _ffmpeg(
                ["-i", str(source), "-af",
                 f"{_TRIM},volume={gain:.2f}dB,afade=t=in:d=0.004,afade=t=out:st={MAX_SECONDS - FADE_OUT}:d={FADE_OUT}",
                 "-t", str(MAX_SECONDS), "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
                 str(root / "stereo" / f"{event}.wav")],
                event,
            )
            log.debug("sounds", "event written", event=event, effect=effect, gain_db=round(gain, 2))
        write_text(root / "index.theme", INDEX)
        log.info("sounds", "sound theme written", events=len(EVENTS), effects=len(peaks))
    _built = True
    return root
