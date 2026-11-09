"""tools/release.py: the GitHub address the PKGBUILD downloads from."""

from __future__ import annotations

import unittest

import support  # noqa: F401  (puts tools/ on the import path)

import release


class ProjectUrl(unittest.TestCase):
    def test_remote_forms(self) -> None:
        for remote in ("https://github.com/DOWingard/kh-kde.git", "https://github.com/DOWingard/kh-kde",
                       "git@github.com:DOWingard/kh-kde.git", "ssh://git@github.com/DOWingard/kh-kde.git"):
            with self.subTest(remote=remote):
                self.assertEqual(release.project_url(remote), "https://github.com/DOWingard/kh-kde")

    def test_other_hosts_are_refused(self) -> None:
        with self.assertRaises(release.ReleaseError):
            release.project_url("https://gitlab.com/someone/kh-kde.git")


if __name__ == "__main__":
    unittest.main()
