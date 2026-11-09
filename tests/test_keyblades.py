"""kh-keyblade against cursor themes a package installed system-wide: it must
change a copy in the user's ~/.icons, never the read-only system theme."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import DIST, log_messages, require_build, user_env

TOOL = DIST / "picker" / "build" / "bin" / "kh-keyblade"
THEMES = sorted((DIST / "cursors").glob("KingdomHearts-*-Cursors"))
STAMP = Path("keyblades") / "system-copy"


class SystemWideCursorThemes(unittest.TestCase):
    def setUp(self) -> None:
        require_build(TOOL, DIST / "cursors")
        self.assertEqual(len(THEMES), 2, "expected the light and the dark cursor theme in dist/cursors")
        self.tmp = Path(tempfile.mkdtemp(prefix="kh-keyblades-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.system = self.tmp / "system"
        for theme in THEMES:
            shutil.copytree(theme, self.system / "icons" / theme.name, symlinks=True)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.env = user_env(self.home, [self.system])

    def tool(self, *args: str) -> subprocess.CompletedProcess:
        result = subprocess.run([str(TOOL), *args], env=self.env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, f"kh-keyblade {' '.join(args)} failed:\n{result.stderr[-3000:]}")
        return result

    def user_copy(self, theme: Path) -> Path:
        return self.home / ".icons" / theme.name

    def system_copy(self, theme: Path) -> Path:
        return self.system / "icons" / theme.name

    def bump_package(self, theme: Path) -> None:
        """What an upgrade does: the package's files get a new modification time."""
        manifest = self.system_copy(theme) / "keyblades" / "manifest.json"
        later = manifest.stat().st_mtime + 100
        os.utime(manifest, (later, later))

    def test_lists_the_keyblades_of_a_system_theme(self) -> None:
        keyblades = json.loads(self.tool("list").stdout)
        slugs = [k["slug"] for k in keyblades]
        self.assertIn("kingdom-key", slugs)
        self.assertGreaterEqual(len(slugs), 18)

    def test_equip_rewrites_a_user_copy_and_leaves_the_system_theme(self) -> None:
        self.tool("equip", "oblivion", "--no-reload")
        for theme in THEMES:
            copy = self.user_copy(theme)
            self.assertTrue((copy / STAMP).is_file(), f"{copy} has no stamp naming the package build")
            alias = copy / "cursors" / "question_arrow"
            self.assertTrue(alias.is_symlink(), "cursor aliases must stay links")
            self.assertFalse(os.path.isabs(os.readlink(alias)), "an absolute alias would point at the old system cursor")
            pointer = (copy / "cursors" / "default").read_bytes()
            self.assertNotEqual(pointer, (self.system_copy(theme) / "cursors" / "default").read_bytes(),
                                "the user copy still shows the original keyblade")
            self.assertEqual((self.system_copy(theme) / "cursors" / "default").read_bytes(),
                             (theme / "cursors" / "default").read_bytes(), "the system theme was modified")

    def test_equipping_again_keeps_the_copy(self) -> None:
        self.tool("equip", "oblivion", "--no-reload")
        before = {t.name: self.user_copy(t).stat().st_ino for t in THEMES}
        result = self.tool("equip", "oathkeeper", "--no-reload")
        after = {t.name: self.user_copy(t).stat().st_ino for t in THEMES}
        self.assertEqual(before, after, "an unchanged package must not be copied again")
        self.assertNotIn("system-wide cursor theme copied for this user", log_messages(result.stderr))

    def test_a_package_upgrade_makes_the_copy_again(self) -> None:
        self.tool("equip", "oblivion", "--no-reload")
        theme = THEMES[0]
        before = self.user_copy(theme).stat().st_ino
        self.bump_package(theme)
        self.tool("restore", "--no-reload")
        self.assertNotEqual(before, self.user_copy(theme).stat().st_ino, "the copy from the old package was kept")
        stamp = (self.user_copy(theme) / STAMP).read_text().strip()
        expected = round((self.system_copy(theme) / "keyblades" / "manifest.json").stat().st_mtime * 1000)
        self.assertAlmostEqual(int(stamp), expected, delta=1)

    def test_the_users_own_install_is_never_replaced(self) -> None:
        theme = THEMES[0]
        shutil.copytree(theme, self.user_copy(theme), symlinks=True)
        before = self.user_copy(theme).stat().st_ino
        self.bump_package(theme)
        self.tool("equip", "oblivion", "--no-reload")
        self.assertEqual(before, self.user_copy(theme).stat().st_ino)
        self.assertFalse((self.user_copy(theme) / STAMP).exists())


if __name__ == "__main__":
    unittest.main()
