"""install.py helpers: where installed themes are looked up, spotting a
keyblade plugin that a libplasma soname bump left unloadable, putting back a
Super + right click binding a desktop reset removed, and choosing the login
screen through SDDM's config cascade."""

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


class Rebind(unittest.TestCase):
    """`rebind` against a fake config store instead of kreadconfig6/kwriteconfig6."""

    def setUp(self) -> None:
        self.store: dict = {}
        self.plugin = Path(tempfile.mkdtemp(prefix="kh-rebind-")) / "plugin.so"
        self.addCleanup(shutil.rmtree, self.plugin.parent, ignore_errors=True)
        self.plugin.write_bytes(b"")
        patches = [
            mock.patch.object(install, "read_setting", lambda f, g, k: self.store.get((f, tuple(g), k), "")),
            mock.patch.object(install, "write_setting",
                              lambda f, g, k, v: self.store.__setitem__((f, tuple(g), k), v or "")),
            mock.patch.object(install, "installed_plugin", lambda: self.plugin),
            mock.patch.object(install, "unresolved_libraries", lambda _p: []),
            mock.patch.object(install, "run", mock.Mock()),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def value(self, name: str) -> str:
        file, groups, key = install.SETTINGS[name]
        return self.store.get((file, tuple(groups), key), "")

    def set(self, name: str, value: str) -> None:
        file, groups, key = install.SETTINGS[name]
        self.store[(file, tuple(groups), key)] = value

    def test_a_removed_binding_is_put_back(self) -> None:
        self.assertEqual(install.cmd_rebind(None), 0)
        self.assertEqual(self.value("meta_right_desktop"), install.picker.PLUGIN_ID)
        self.assertEqual(self.value("meta_right_window"), install.PASS_CLICK)

    def test_another_chosen_action_stays(self) -> None:
        self.set("meta_right_desktop", "org.kde.switchwindow")
        self.assertEqual(install.cmd_rebind(None), 0)
        self.assertEqual(self.value("meta_right_desktop"), "org.kde.switchwindow")

    def test_an_unloadable_plugin_is_not_bound(self) -> None:
        with mock.patch.object(install, "unresolved_libraries", lambda _p: ["libPlasma.so.99"]):
            self.assertEqual(install.cmd_rebind(None), 0)
        self.assertEqual(self.value("meta_right_desktop"), "")


class LoginScreenConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="kh-sddm-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.lib, self.etc = self.tmp / "lib", self.tmp / "etc"
        for folder in (self.lib, self.etc):
            folder.mkdir()
        patches = [mock.patch.object(install, "SDDM_CONF_DIRS", [self.lib, self.etc]),
                   mock.patch.object(install, "SDDM_CONF", self.tmp / "sddm.conf")]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_the_last_file_by_name_wins(self) -> None:
        (self.lib / "default.conf").write_text("[Theme]\nCurrent=\n")
        (self.etc / "10-kingdom-hearts.conf").write_text("[Theme]\nCurrent=KingdomHearts\n")
        (self.etc / "kde_settings.conf").write_text("[Autologin]\nUser=\n\n[Theme]\nCurrent=sugar-dark\n")
        self.assertEqual(install.sddm_current(), ("sugar-dark", self.etc / "kde_settings.conf"))

    def test_etc_sddm_conf_overrides_the_folders(self) -> None:
        (self.etc / "kde_settings.conf").write_text("[Theme]\nCurrent=sugar-dark\n")
        (self.tmp / "sddm.conf").write_text("[Theme]\nCurrent=maya\n")
        self.assertEqual(install.sddm_current()[0], "maya")

    def test_other_keys_named_current_do_not_count(self) -> None:
        (self.etc / "a.conf").write_text("[Users]\nCurrent=x\n")
        self.assertEqual(install.sddm_current(), ("", None))

    def test_setting_a_value_keeps_every_other_line(self) -> None:
        text = "[Autologin]\nRelogin=false\n\n[Theme]\nCurrent=sugar-dark\nCursorTheme=breeze\n"
        self.assertEqual(install.with_ini_value(text, "Theme", "Current", "KingdomHearts-Sora"),
                         "[Autologin]\nRelogin=false\n\n[Theme]\nCurrent=KingdomHearts-Sora\nCursorTheme=breeze\n")

    def test_a_missing_group_or_key_is_added(self) -> None:
        self.assertEqual(install.with_ini_value("", "Theme", "Current", "X"), "[Theme]\nCurrent=X\n")
        self.assertEqual(install.with_ini_value("[General]\nA=1\n", "Theme", "Current", "X"),
                         "[General]\nA=1\n\n[Theme]\nCurrent=X\n")
        self.assertEqual(install.with_ini_value("[Theme]\nCursorTheme=b\n", "Theme", "Current", "X"),
                         "[Theme]\nCurrent=X\nCursorTheme=b\n")


if __name__ == "__main__":
    unittest.main()
