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
from khtheme import sddmconf, span

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
    """SDDM's config cascade and the root helper, against a fake /etc."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="kh-sddm-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.lib, self.etc, self.themes = self.tmp / "lib", self.tmp / "etc", self.tmp / "themes"
        for folder in (self.lib, self.etc, self.themes):
            folder.mkdir()
        for theme in ("KingdomHearts-OrgXIII", "KingdomHearts-Sora", "sugar-dark"):
            (self.themes / theme).mkdir()
            (self.themes / theme / "metadata.desktop").write_text("[SddmGreeterTheme]\n")
        self.kde = self.etc / "kde_settings.conf"
        patches = [mock.patch.object(sddmconf, "CONF_DIRS", [self.lib, self.etc]),
                   mock.patch.object(sddmconf, "CONF", self.tmp / "sddm.conf"),
                   mock.patch.object(sddmconf, "THEMES", self.themes),
                   mock.patch.object(sddmconf, "KDE_CONF", self.kde),
                   mock.patch.object(sddmconf, "LEGACY_CONF", self.etc / "10-kingdom-hearts.conf")]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_the_last_file_by_name_wins(self) -> None:
        (self.lib / "default.conf").write_text("[Theme]\nCurrent=\n")
        (self.etc / "10-kingdom-hearts.conf").write_text("[Theme]\nCurrent=KingdomHearts\n")
        self.kde.write_text("[Autologin]\nUser=\n\n[Theme]\nCurrent=sugar-dark\n")
        self.assertEqual(sddmconf.current(), ("sugar-dark", self.kde))

    def test_etc_sddm_conf_overrides_the_folders(self) -> None:
        self.kde.write_text("[Theme]\nCurrent=sugar-dark\n")
        (self.tmp / "sddm.conf").write_text("[Theme]\nCurrent=maya\n")
        self.assertEqual(sddmconf.current()[0], "maya")

    def test_other_keys_named_current_do_not_count(self) -> None:
        (self.etc / "a.conf").write_text("[Users]\nCurrent=x\n")
        self.assertEqual(sddmconf.current(), ("", None))

    def test_setting_a_value_keeps_every_other_line(self) -> None:
        text = "[Autologin]\nRelogin=false\n\n[Theme]\nCurrent=sugar-dark\nCursorTheme=breeze\n"
        self.assertEqual(sddmconf.with_ini_value(text, "Theme", "Current", "KingdomHearts-Sora"),
                         "[Autologin]\nRelogin=false\n\n[Theme]\nCurrent=KingdomHearts-Sora\nCursorTheme=breeze\n")

    def test_a_missing_group_or_key_is_added(self) -> None:
        self.assertEqual(sddmconf.with_ini_value("", "Theme", "Current", "X"), "[Theme]\nCurrent=X\n")
        self.assertEqual(sddmconf.with_ini_value("[General]\nA=1\n", "Theme", "Current", "X"),
                         "[General]\nA=1\n\n[Theme]\nCurrent=X\n")
        self.assertEqual(sddmconf.with_ini_value("[Theme]\nCursorTheme=b\n", "Theme", "Current", "X"),
                         "[Theme]\nCurrent=X\nCursorTheme=b\n")

    def test_without_a_password_it_follows_only_between_our_themes(self) -> None:
        self.kde.write_text("[Theme]\nCurrent=KingdomHearts-OrgXIII\n")
        self.assertEqual(sddmconf.select("KingdomHearts-Sora", restricted=True), 0)
        self.assertEqual(sddmconf.current(), ("KingdomHearts-Sora", self.kde))

    def test_without_a_password_another_choice_is_left_alone(self) -> None:
        self.kde.write_text("[Theme]\nCurrent=sugar-dark\n")
        self.assertEqual(sddmconf.select("KingdomHearts-Sora", restricted=True), 3)
        self.assertEqual(sddmconf.current()[0], "sugar-dark")
        self.kde.write_text("[Theme]\nCurrent=KingdomHearts-Sora\n")
        self.assertEqual(sddmconf.select("sugar-dark", restricted=True), 3)

    def test_as_root_any_installed_theme_is_selected(self) -> None:
        self.kde.write_text("[Theme]\nCurrent=sugar-dark\n")
        self.assertEqual(sddmconf.select("KingdomHearts-OrgXIII", restricted=False), 0)
        self.assertEqual(sddmconf.select("missing", restricted=False), 2)
        self.assertEqual(sddmconf.select("../../etc", restricted=False), 2)
        self.assertEqual(sddmconf.current()[0], "KingdomHearts-OrgXIII")

    def test_the_old_drop_in_is_removed(self) -> None:
        (self.etc / "10-kingdom-hearts.conf").write_text("[Theme]\nCurrent=KingdomHearts\n")
        self.assertEqual(sddmconf.select("KingdomHearts-Sora", restricted=False), 0)
        self.assertFalse((self.etc / "10-kingdom-hearts.conf").exists())
        self.assertEqual(sddmconf.current(), ("KingdomHearts-Sora", self.kde))


class SpanGeometry(unittest.TestCase):
    def test_landscape_beside_portrait(self) -> None:
        # 1920x1080 at (0,287) next to a 1080x1920 portrait at (1920,0): a
        # 3000x1920 box; a 3840x2160 picture covers it at 1.125 pixels per unit.
        screens = [span.Rect(0, 287, 1920, 1080), span.Rect(1920, 0, 1080, 1920)]
        self.assertEqual(span.bounds(screens), span.Rect(0, 0, 3000, 1920))
        left, right = span.crops((3840, 2160), screens)
        self.assertEqual(left, (232, 323, 2160, 1215))
        self.assertEqual(right, (2392, 0, 1215, 2160))
        # Neighbouring screens get neighbouring pixels.
        self.assertEqual(left[0] + left[2], right[0])

    def test_slices_keep_their_screens_shape(self) -> None:
        screens = [span.Rect(0, 0, 2560, 1440), span.Rect(2560, 0, 1920, 1080)]
        for (x, y, w, h), screen in zip(span.crops((3840, 2160), screens), screens):
            self.assertAlmostEqual(w / h, screen.width / screen.height, places=2)
            self.assertLessEqual(x + w, 3840)
            self.assertLessEqual(y + h, 2160)


class SpanChoice(unittest.TestCase):
    """Which picture `span_wallpaper` spreads, with the desktop faked."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="kh-span-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.ours = self.tmp / "wallpapers" / "KingdomHearts"
        (self.ours / "contents" / "images").mkdir(parents=True)
        (self.ours / "contents" / "images" / "3840x2160.jpg").write_bytes(b"x")
        self.mine = self.tmp / "holiday.jpg"
        self.mine.write_bytes(b"x")
        self.desks: list[dict] = []
        self.set_calls: list[dict] = []
        self.cut = mock.Mock()
        root = self.tmp / "span"
        patches = [
            mock.patch.object(install, "SPAN_ROOT", root),
            mock.patch.object(install, "SPAN_STATE", self.tmp / "span.json"),
            mock.patch.object(install, "desktop_screens", lambda: self.desks),
            mock.patch.object(install, "set_desktop_pictures", self.set_calls.append),
            mock.patch.object(install.span, "size", lambda _p: (3840, 2160)),
            mock.patch.object(install.span, "cut", self.cut),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def two(self, first: str, second: str) -> None:
        self.desks = [{"screen": 0, "image": first, "rect": [0, 287, 1920, 1080]},
                      {"screen": 1, "image": second, "rect": [1920, 0, 1080, 1920]}]

    def test_our_picture_is_spread_over_two_screens(self) -> None:
        self.two(f"file://{self.ours}", f"file://{self.ours}")
        install.span_wallpaper(auto=True)
        self.assertEqual(self.cut.call_count, 2)
        urls = self.set_calls[-1]
        self.assertEqual(sorted(urls), [0, 1])
        self.assertTrue(all(install.is_span(u) for u in urls.values()))

    def test_a_picture_of_the_users_own_is_left_alone(self) -> None:
        self.two(f"file://{self.mine}", f"file://{self.mine}")
        install.span_wallpaper(auto=True)
        self.assertEqual(self.set_calls, [])

    def test_a_new_screen_joins_the_span(self) -> None:
        self.two(f"file://{self.ours}", f"file://{self.ours}")
        install.span_wallpaper(auto=True)
        spanned = self.set_calls[-1]
        self.desks = [{"screen": 0, "image": spanned[0], "rect": [0, 0, 1920, 1080]},
                      {"screen": 1, "image": spanned[1], "rect": [1920, 0, 1920, 1080]},
                      {"screen": 2, "image": f"file://{self.mine}", "rect": [3840, 0, 1920, 1080]}]
        install.span_wallpaper(auto=True)
        self.assertEqual(sorted(self.set_calls[-1]), [0, 1, 2])

    def test_changing_a_spanned_screen_to_ones_own_picture_stops_following(self) -> None:
        self.two(f"file://{self.ours}", f"file://{self.ours}")
        install.span_wallpaper(auto=True)
        spanned = self.set_calls[-1]
        self.two(spanned[0], f"file://{self.mine}")
        calls = len(self.set_calls)
        install.span_wallpaper(auto=True)
        self.assertEqual(len(self.set_calls), calls)

    def one(self, image: str) -> None:
        self.desks = [{"screen": 0, "image": image, "rect": [0, 0, 1920, 1080]}]

    def test_a_single_screen_is_never_touched(self) -> None:
        for image in (f"file://{self.ours}", f"file://{self.mine}", ""):
            self.one(image)
            install.span_wallpaper(auto=True)
            install.span_wallpaper(auto=True)
        self.assertEqual(self.set_calls, [])
        self.cut.assert_not_called()
        self.assertFalse((self.tmp / "span").exists())

    def test_a_single_screen_needs_no_imagemagick(self) -> None:
        self.one(f"file://{self.ours}")
        with mock.patch.object(install.shutil, "which", return_value=None):
            install.span_wallpaper(auto=True)
        self.assertEqual(self.set_calls, [])

    def test_a_second_screen_attached_later_is_spanned(self) -> None:
        self.one(f"file://{self.ours}")
        install.span_wallpaper(auto=True)
        # Plasma gives the new screen's desktop some picture of its own.
        self.desks.append({"screen": 1, "image": "file:///usr/share/wallpapers/Next", "rect": [1920, 0, 1080, 1920]})
        install.span_wallpaper(auto=True)
        self.assertEqual(sorted(self.set_calls[-1]), [0, 1])

    def test_a_single_screens_own_picture_is_kept_when_a_screen_is_added(self) -> None:
        self.one(f"file://{self.ours}")
        install.span_wallpaper(auto=True)
        self.one(f"file://{self.mine}")
        self.desks.append({"screen": 1, "image": f"file://{self.ours}", "rect": [1920, 0, 1920, 1080]})
        install.span_wallpaper(auto=True)
        self.assertEqual(self.set_calls, [])

    def test_one_screen_shows_the_whole_picture(self) -> None:
        self.two(f"file://{self.ours}", f"file://{self.ours}")
        install.span_wallpaper(auto=True)
        self.desks = [{"screen": 0, "image": self.set_calls[-1][0], "rect": [0, 0, 1920, 1080]}]
        install.span_wallpaper(auto=True)
        self.assertEqual(self.set_calls[-1], {0: f"file://{self.ours}"})


if __name__ == "__main__":
    unittest.main()
