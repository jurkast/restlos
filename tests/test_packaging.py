from __future__ import annotations

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from restlos import APP_ID, APP_NAME, __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_appstream_metadata_matches_application(self) -> None:
        template = (PROJECT_ROOT / "assets/io.github.jurkast.Restlos.metainfo.xml.in").read_text(
            encoding="utf-8"
        )
        rendered = template.replace("@VERSION@", __version__).replace("@DATE@", "2026-09-01")
        component = ET.fromstring(rendered)
        self.assertEqual(component.findtext("id"), APP_ID)
        self.assertEqual(component.findtext("name"), APP_NAME)
        self.assertEqual(component.findtext("project_license"), "MIT")
        self.assertEqual(component.findtext("launchable"), f"{APP_ID}.desktop")
        release = component.find("./releases/release")
        self.assertIsNotNone(release)
        self.assertEqual(release.attrib["version"], __version__)

    def test_debian_package_identity_and_dependencies_are_declared(self) -> None:
        control = (PROJECT_ROOT / "packaging/debian/control.in").read_text(encoding="utf-8")
        self.assertIn("Package: restlos-uninstaller", control)
        self.assertIn("python3-gi", control)
        self.assertIn("gir1.2-gtk-4.0", control)
        self.assertIn("policykit-1", control)

        wrapper = (PROJECT_ROOT / "packaging/debian/restlos-wrapper").read_text(encoding="utf-8")
        self.assertIn("RESTLOS_UPDATE_CHANNEL=deb", wrapper)
        self.assertIn("/usr/lib/restlos/run_restlos.py", wrapper)

    def test_launchpad_source_packaging_matches_application(self) -> None:
        control = (PROJECT_ROOT / "debian/control").read_text(encoding="utf-8")
        changelog = (PROJECT_ROOT / "debian/changelog").read_text(encoding="utf-8")
        rules = (PROJECT_ROOT / "debian/rules").read_text(encoding="utf-8")
        source_format = (PROJECT_ROOT / "debian/source/format").read_text(encoding="utf-8")

        self.assertIn("Source: restlos-uninstaller", control)
        self.assertIn("Package: restlos-uninstaller", control)
        self.assertIn("Build-Depends: debhelper-compat (= 13)", control)
        self.assertRegex(changelog.splitlines()[0], rf"\({re.escape(__version__)}-[^)]+\)")
        self.assertIn("RESTLOS_UPDATE_CHANNEL=deb", (
            PROJECT_ROOT / "packaging/debian/restlos-wrapper"
        ).read_text(encoding="utf-8"))
        self.assertIn("/usr/share/metainfo", rules)
        self.assertEqual(source_format.strip(), "3.0 (quilt)")

    def test_snap_manifest_version_matches_project(self) -> None:
        manifest = (PROJECT_ROOT / "snap/snapcraft.yaml").read_text(encoding="utf-8")
        match = re.search(r'^version: "([^"]+)"$', manifest, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), __version__)
        self.assertIn("confinement: classic", manifest)


if __name__ == "__main__":
    unittest.main()
