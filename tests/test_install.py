"""install.py helpers: where installed themes are looked up, and spotting a
keyblade plugin that a libplasma soname bump left unloadable."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import DIST, require_build

import install

PLUGIN = DIST / "picker" / "build" / "plugins" / "plasma" / "containmentactions" / "kingdomhearts_keyblades.so"


class FindInstalled(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="kh-find-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.user = self.tmp / "user" / "color-schemes"
        self.system = self.tmp / "system"
        for folder in (self.user, self.system / "color-schemes"):
            folder.mkdir(parents=True)
        patches = [mock.patch.dict(install.TREES, {"color-schemes": self.user}),
                   mock.patch.object(install, "SYSTEM_DATA", [self.system])]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_the_users_copy_comes_first(self) -> None:
        (self.user / "X.colors").write_text("user")
        (self.system / "color-schemes" / "X.colors").write_text("system")
        self.assertEqual(install.find_installed("color-schemes", "X.colors"), self.user / "X.colors")

    def test_falls_back_to_the_system_copy(self) -> None:
        (self.system / "color-schemes" / "X.colors").write_text("system")
        self.assertEqual(install.find_installed("color-schemes", "X.colors"), self.system / "color-schemes" / "X.colors")

    def test_none_when_nowhere(self) -> None:
        self.assertIsNone(install.find_installed("color-schemes", "X.colors"))


class StalePlugin(unittest.TestCase):
    def setUp(self) -> None:
        require_build(PLUGIN)
        self.tmp = Path(tempfile.mkdtemp(prefix="kh-stale-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_a_fresh_build_loads(self) -> None:
        self.assertEqual(install.unresolved_libraries(PLUGIN), [])

    def test_a_bumped_libplasma_soname_is_reported(self) -> None:
        data = PLUGIN.read_bytes()
        match = re.search(rb"libPlasma\.so\.(\d+)\x00", data)
        self.assertIsNotNone(match, "the plugin does not link libplasma")
        number = match.group(1)
        # Same length, so the ELF string table stays intact.
        other = (b"0" if number[:1] == b"9" else b"9") * len(number)
        stale = self.tmp / PLUGIN.name
        stale.write_bytes(data[:match.start(1)] + other + data[match.end(1):])
        self.assertEqual(install.unresolved_libraries(stale), [f"libPlasma.so.{other.decode()}"])

    def test_the_hint_matches_how_it_was_installed(self) -> None:
        record = self.tmp / "system-install.json"
        record.write_text(json.dumps({"version": "0", "plugin": "/x", "keyblade_tool": "/y"}))
        with mock.patch.object(install, "SYSTEM_INSTALL", record):
            self.assertIn("yay -S --rebuild", install.rebuild_hint())
        with mock.patch.object(install, "SYSTEM_INSTALL", self.tmp / "absent.json"):
            self.assertIn("./build.py --only picker", install.rebuild_hint())


if __name__ == "__main__":
    unittest.main()
