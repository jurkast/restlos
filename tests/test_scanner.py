from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from restlos.models import SourceKind
from restlos.scanners import ApplicationScanner


class ScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        (self.home / ".local/share/applications").mkdir(parents=True)
        (self.home / "Applications").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @patch("restlos.scanners.shutil.which", return_value=None)
    def test_manual_desktop_and_appimage_are_discovered(self, _which) -> None:
        executable = self.home / ".local/bin/my-tool"
        executable.parent.mkdir(parents=True)
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        desktop = self.home / ".local/share/applications/my-tool.desktop"
        desktop.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=My Tool\n"
            "Comment=Test tool\n"
            f"Exec={executable}\n"
            "Icon=applications-utilities\n",
            encoding="utf-8",
        )
        appimage = self.home / "Applications/Paint-Pro.AppImage"
        appimage.write_bytes(b"appimage")
        scanner = ApplicationScanner(self.home)
        records = scanner.scan()
        by_name = {record.name: record for record in records}
        self.assertEqual(by_name["My Tool"].source, SourceKind.MANUAL)
        self.assertEqual(by_name["Paint Pro"].source, SourceKind.APPIMAGE)


if __name__ == "__main__":
    unittest.main()

