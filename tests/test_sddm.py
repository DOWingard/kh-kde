"""The built login screens: each loads in a stand-in for SDDM without a QML
warning and draws its preview, and each menu stands inside its picture."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from support import DIST, require_build

from khtheme import sddm
from khtheme.palette import VARIANTS


class LoginScreens(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="kh-sddm-render-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_each_screen_loads_and_renders_cleanly(self) -> None:
        for pal in VARIANTS:
            root = DIST / "sddm" / sddm.theme_id(pal)
            require_build(root / "Main.qml", root / "assets" / "background.jpg", root / "assets" / sddm.FONT)
            with self.subTest(variant=pal.key):
                target = self.tmp / f"{pal.key}.jpg"
                self.assertTrue(sddm.render_preview(root, target), "render failed or QML warned; see the log")
                self.assertGreater(target.stat().st_size, 10_000)

    def test_the_menus_space_lies_inside_the_picture(self) -> None:
        for key, screen in sddm.SCREENS.items():
            left, top, right, bottom = screen.space
            with self.subTest(variant=key):
                self.assertTrue(0 <= left < right <= 1 and 0 <= top < bottom <= 1)
                self.assertTrue((ROOT_ASSETS / screen.picture).is_file())


ROOT_ASSETS = sddm.ASSETS / "title"

if __name__ == "__main__":
    unittest.main()
