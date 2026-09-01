from __future__ import annotations

import configparser
import json
import re
import unittest
from pathlib import Path

from restlos import APP_ID, APP_NAME, APP_TAGLINE, LEGACY_APP_IDS, SELF_PACKAGE_IDS, __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class BrandingTests(unittest.TestCase):
    def test_visible_branding_is_consistent(self) -> None:
        self.assertEqual(APP_NAME, "Restlos Uninstaller")
        self.assertEqual(APP_TAGLINE, "Safe Linux App & Game Uninstaller")

        manifest = json.loads((PROJECT_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], APP_NAME)
        self.assertEqual(manifest["tagline"], APP_TAGLINE)

        desktop = configparser.ConfigParser(interpolation=None)
        desktop.optionxform = str
        desktop.read(PROJECT_ROOT / "assets/io.github.jurkast.Restlos.desktop.in", encoding="utf-8")
        entry = desktop["Desktop Entry"]
        self.assertEqual(entry["Name"], APP_NAME)
        self.assertEqual(entry["Comment"], APP_TAGLINE)
        self.assertIn("uninstaller", entry["Keywords"].casefold())
        self.assertIn("games", entry["Keywords"].casefold())

    def test_github_identity_and_legacy_app_ids_are_consistent(self) -> None:
        self.assertEqual(APP_ID, "io.github.jurkast.Restlos")
        self.assertIn("io.github.jurkastl.Restlos", LEGACY_APP_IDS)
        self.assertIn("io.github.local.Restlos", LEGACY_APP_IDS)
        self.assertIn("restlos-uninstaller", SELF_PACKAGE_IDS)

        project = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        project_version = re.search(r'^version = "([^"]+)"$', project, re.MULTILINE)
        self.assertIsNotNone(project_version)
        self.assertEqual(project_version.group(1), __version__)
        self.assertIn('restlos = "restlos.cli:main"', project)

        manifest = json.loads((PROJECT_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["app_id"], APP_ID)
        self.assertEqual(manifest["version"], __version__)


if __name__ == "__main__":
    unittest.main()
