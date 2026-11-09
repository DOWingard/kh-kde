"""Checks of the installed system package, run by CI after `pacman -U` of the
package makepkg built:

    python3 -m unittest discover -s tests -p installed_package.py -v

Not part of the default test run (the file name does not match test*.py),
since it needs the package installed. Every check runs as a fresh user with
nothing pointing at this checkout, so it sees only what the package put on
the system.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import DIST, require_build, user_env

from khtheme import VERSION, picker
from khtheme.palette import VARIANTS

COMMAND = "kingdom-hearts-plasma"
RECORD = Path("/usr/share/kingdom-hearts-plasma/system-install.json")
SYSTEM_DATA = [Path("/usr/local/share"), Path("/usr/share")]
KEYBLADES = 18


class InstalledPackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which(COMMAND) is None or not RECORD.is_file():
            raise RuntimeError(f"the package is not installed ({COMMAND}, {RECORD})")
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp(prefix="kh-installed-"))
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.env = user_env(self.home, SYSTEM_DATA)

    def run_tool(self, *cmd: str) -> subprocess.CompletedProcess:
        result = subprocess.run(list(cmd), env=self.env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, f"{cmd[0]} {cmd[1]} failed:\n{result.stderr[-3000:]}")
        return result

    def test_status_finds_everything(self) -> None:
        report = json.loads(self.run_tool(COMMAND, "status").stdout)
        self.assertEqual(report["missing"], {pal.key: [] for pal in VARIANTS})
        self.assertTrue(report["keyblade_browser"])
        self.assertEqual(report["keyblade_browser_missing_libraries"], [])
        self.assertEqual(report["package"], VERSION)

    def test_the_plugin_loads_from_the_package(self) -> None:
        """The plugin is found by id through libplasma's loader, the call the
        shell makes for a mouse binding (and the one whose failure makes the
        shell delete the binding). The menu lists the package's keyblades."""
        preview = picker.preview_tool(DIST)
        require_build(preview)
        result = self.run_tool(str(preview), str(self.home / "menu.png"))
        summary = json.loads(result.stdout)
        self.assertEqual(Path(summary["plugin"]).resolve(), Path(self.record["plugin"]).resolve())
        self.assertEqual(len(summary["buttons"]), KEYBLADES)

    def test_equip_copies_the_system_theme(self) -> None:
        tool = self.record["keyblade_tool"]
        self.run_tool(tool, "equip", "oathkeeper", "--no-reload")
        for pal in VARIANTS:
            copy = self.home / ".icons" / pal.cursor_id
            self.assertTrue((copy / "index.theme").is_file(), f"no user copy of {pal.cursor_id}")
        current = (self.home / ".config" / "kingdom-hearts-plasmarc").read_text(encoding="utf-8")
        self.assertIn("Current=oathkeeper", current)
        listed = json.loads(self.run_tool(tool, "list").stdout)
        self.assertEqual(len(listed), KEYBLADES)


if __name__ == "__main__":
    unittest.main()
