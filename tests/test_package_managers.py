from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from restlos.models import SourceKind
from restlos.package_managers import (
    AptAdapter,
    DnfAdapter,
    PacmanAdapter,
    ZypperAdapter,
    native_package_adapter,
)
from restlos.utils import CommandResult, DesktopEntry


def desktop_entry(name: str = "Example App") -> DesktopEntry:
    return DesktopEntry(
        path=Path("/usr/share/applications/example.desktop"),
        name=name,
        generic_name="Example",
        comment="Example application",
        exec_line="/usr/bin/example",
        icon="example",
        app_id="example",
        hidden=False,
        no_display=False,
    )


class PackageManagerTests(unittest.TestCase):
    @patch("restlos.package_managers.run_command")
    def test_apt_maps_desktop_file_to_package(self, command) -> None:
        entry = desktop_entry()
        command.return_value = CommandResult(
            ("dpkg-query",),
            0,
            f"example-app: {entry.path}\n",
            "",
        )
        records = AptAdapter().scan([entry])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source, SourceKind.APT)
        self.assertEqual(records[0].package_id, "example-app")
        self.assertEqual(records[0].metadata["package_manager"], "apt-get")

    @patch("restlos.package_managers.run_command")
    def test_apt_purge_preview_accepts_purg_output(self, command) -> None:
        command.return_value = CommandResult(
            ("apt-get",),
            0,
            "The following packages will be REMOVED:\n  example-app*\n"
            "Purg example-app [1.2.3]\n",
            "",
        )
        preview = AptAdapter().preview_removal("example-app")
        self.assertEqual(preview.removed_packages, ("example-app",))
        self.assertEqual(preview.error, "")

    @patch("restlos.package_managers.run_command")
    def test_dnf_maps_rpm_owned_desktop_file(self, command) -> None:
        command.return_value = CommandResult(("rpm",), 0, "example-app\n", "")
        records = DnfAdapter().scan([desktop_entry()])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source, SourceKind.DNF)
        self.assertEqual(records[0].key, "dnf:example-app")

    @patch("restlos.package_managers.run_command")
    def test_zypper_maps_rpm_owned_desktop_file(self, command) -> None:
        command.return_value = CommandResult(("rpm",), 0, "example-app\n", "")
        records = ZypperAdapter().scan([desktop_entry()])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source, SourceKind.ZYPPER)
        self.assertEqual(records[0].key, "zypper:example-app")

    @patch("restlos.package_managers.run_command")
    def test_pacman_maps_owned_desktop_file(self, command) -> None:
        entry = desktop_entry()
        command.return_value = CommandResult(
            ("pacman",),
            0,
            f"{entry.path} is owned by example-app 1.2.3-1\n",
            "",
        )
        records = PacmanAdapter().scan([entry])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source, SourceKind.PACMAN)
        self.assertEqual(records[0].package_id, "example-app")

    @patch("restlos.package_managers.shutil.which")
    def test_native_adapter_prefers_zypper_over_dnf_on_rpm_system(self, which) -> None:
        available = {"rpm", "zypper", "dnf"}
        which.side_effect = lambda name: f"/usr/bin/{name}" if name in available else None
        self.assertIsInstance(native_package_adapter(), ZypperAdapter)

    @patch("restlos.package_managers.shutil.which")
    def test_os_release_wins_when_multiple_managers_exist(self, which) -> None:
        available = {"dpkg-query", "apt-get", "pacman"}
        which.side_effect = lambda name: f"/usr/bin/{name}" if name in available else None
        with tempfile.TemporaryDirectory() as temporary:
            os_release = Path(temporary) / "os-release"
            os_release.write_text('ID="manjaro"\nID_LIKE="arch"\n', encoding="utf-8")
            self.assertIsInstance(native_package_adapter(os_release), PacmanAdapter)

    def test_arch_package_ids_may_contain_at_sign(self) -> None:
        adapter = PacmanAdapter()
        self.assertFalse(adapter.is_protected("example@app"))


if __name__ == "__main__":
    unittest.main()
