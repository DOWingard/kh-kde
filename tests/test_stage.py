"""`install.py stage`: the system-wide layout a distribution package installs,
and the per-user tool working against it."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import DIST, ROOT, require_build, user_env

from khtheme import VERSION, kvantum
from khtheme.colorscheme import scheme_id
from khtheme.palette import VARIANTS
from khtheme.sounds import THEME_ID as SOUND_THEME


class StagedPackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_build(DIST / "picker" / "build" / "qt-plugin-dir")
        cls.tmp = Path(tempfile.mkdtemp(prefix="kh-stage-"))
        cls.dest = cls.tmp / "pkg"
        result = subprocess.run([sys.executable, str(ROOT / "install.py"), "stage", "--destdir", str(cls.dest)],
                                capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise AssertionError(f"stage failed:\n{result.stderr[-3000:]}")
        cls.usr = cls.dest / "usr"
        cls.share = cls.usr / "share"
        cls.record = json.loads((cls.share / "kingdom-hearts-plasma" / "system-install.json").read_text())

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_every_part_is_in_place(self) -> None:
        share = self.share
        expected = [
            share / "Kvantum" / kvantum.THEME,
            share / "sounds" / SOUND_THEME / "index.theme",
            share / "wallpapers" / "KingdomHearts" / "metadata.json",
            share / "sddm" / "themes" / "KingdomHearts-OrgXIII" / "Main.qml",
            share / "sddm" / "themes" / "KingdomHearts-Sora" / "Main.qml",
            share / "fonts" / "KingdomHearts" / "KHMenu.otf",
        ]
        for pal in VARIANTS:
            expected += [
                share / "color-schemes" / f"{scheme_id(pal)}.colors",
                share / "plasma" / "look-and-feel" / pal.theme_id / "metadata.json",
                share / "plasma" / "desktoptheme" / pal.theme_id / "metadata.json",
                share / "kwin" / "decorations" / pal.decoration_id / "contents" / "ui" / "main.qml",
                share / "icons" / pal.theme_id / "index.theme",
                share / "icons" / pal.cursor_id / "keyblades" / "manifest.json",
                share / "konsole" / f"{pal.theme_id}.colorscheme",
            ]
        missing = [str(p.relative_to(self.dest)) for p in expected if not p.exists()]
        self.assertEqual(missing, [])

    def test_commands_are_executable(self) -> None:
        for name in ("kh-keyblade", "kingdom-hearts-plasma"):
            path = self.usr / "bin" / name
            self.assertTrue(os.access(path, os.X_OK), f"{name} is not executable")
        launcher = (self.usr / "bin" / "kingdom-hearts-plasma").read_text()
        self.assertIn("/usr/share/kingdom-hearts-plasma/install.py", launcher)

    def test_record_points_at_the_staged_plugin(self) -> None:
        self.assertEqual(self.record["version"], VERSION)
        plugin = self.dest / self.record["plugin"].lstrip("/")
        self.assertTrue(plugin.is_file(), f"recorded plugin {self.record['plugin']} was not staged")
        self.assertEqual(plugin.parent.parts[-2:], ("plasma", "containmentactions"))
        self.assertEqual(self.record["keyblade_tool"], "/usr/bin/kh-keyblade")

    def test_cursor_aliases_stay_links(self) -> None:
        for pal in VARIANTS:
            alias = self.share / "icons" / pal.cursor_id / "cursors" / "question_arrow"
            self.assertTrue(alias.is_symlink(), f"{alias} was copied as a file")

    def test_status_finds_the_package_themes(self) -> None:
        home = self.tmp / "home"
        home.mkdir(exist_ok=True)
        result = subprocess.run([sys.executable, str(self.share / "kingdom-hearts-plasma" / "install.py"), "status"],
                                env=user_env(home, [self.share]), capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        report = json.loads(result.stdout)
        self.assertEqual(report["missing"], {pal.key: [] for pal in VARIANTS})
        self.assertEqual(report["package"], VERSION)


if __name__ == "__main__":
    unittest.main()
