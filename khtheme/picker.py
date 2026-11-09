"""Build the Keyblade Browser: a Plasma desktop mouse action (C++ plugin) that
opens a grid of keyblades and makes the chosen one the mouse pointer, plus
`kh-keyblade`, the same choice from the command line.

Sources are in picker/; CMake builds them into dist/picker/build/. The plugin
lands in plugins/plasma/containmentactions/ there, a folder Qt finds plugins
in once it is on QT_PLUGIN_PATH. Nothing here depends on the variant, so the
build runs once however many variants are built.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from . import log
from .palette import Palette

SOURCE = Path(__file__).resolve().parent.parent / "picker"
PLUGIN_ID = "kingdomhearts_keyblades"
NAMESPACE = Path("plasma") / "containmentactions"

_done: set[Path] = set()


def build_dir(out: Path) -> Path:
    return out / "picker" / "build"


def plugin_root(out: Path) -> Path:
    """The folder to put on QT_PLUGIN_PATH."""
    return build_dir(out) / "plugins"


def plugin_file(out: Path) -> Path:
    return plugin_root(out) / NAMESPACE / f"{PLUGIN_ID}.so"


def cli(out: Path) -> Path:
    return build_dir(out) / "bin" / "kh-keyblade"


def preview_tool(out: Path) -> Path:
    return build_dir(out) / "bin" / "kh-keyblade-preview"


def _cmake(args: list[str], what: str) -> None:
    start = time.monotonic()
    try:
        result = subprocess.run(["cmake", *args], capture_output=True, text=True, timeout=600)
    except FileNotFoundError as exc:
        log.error("picker", "cmake is not installed", error=exc, step=what)
        raise
    except subprocess.TimeoutExpired as exc:
        log.error("picker", "cmake timed out", error=exc, step=what)
        raise
    duration = round((time.monotonic() - start) * 1000, 1)
    if result.returncode != 0:
        # Compiler errors are in stdout with most generators.
        log.error("picker", f"{what} failed", exit_code=result.returncode, duration_ms=duration,
                  stdout=result.stdout[-3000:], stderr=result.stderr[-2000:])
        raise RuntimeError(f"{what} failed (cmake exited {result.returncode})")
    log.debug("picker", f"{what}: ok", duration_ms=duration)


def build(out: Path, pal: Palette) -> Path:
    target = build_dir(out)
    if target in _done:
        log.debug("picker", "already built in this run", variant=pal.key)
        return target
    with log.timed("picker", "build keyblade browser", target=str(target)):
        configure = ["-S", str(SOURCE), "-B", str(target), "-DCMAKE_BUILD_TYPE=Release"]
        # A build folder keeps the generator it was first made with.
        if not (target / "CMakeCache.txt").exists() and shutil.which("ninja"):
            configure += ["-G", "Ninja"]
        _cmake(configure, "configure")
        _cmake(["--build", str(target)], "compile")
        missing = [str(p) for p in (plugin_file(out), cli(out), preview_tool(out)) if not p.is_file()]
        if missing:
            log.error("picker", "build finished without its outputs", missing=missing)
            raise FileNotFoundError(missing[0])
    _done.add(target)
    log.info("picker", "keyblade browser built", plugin=str(plugin_file(out)), cli=str(cli(out)))
    return target
