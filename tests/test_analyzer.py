from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from restlos.analyzer import PathGuard, RemovalAnalyzer, UnsafeTargetError
from restlos.models import AppRecord, SourceKind
from restlos.utils import CommandResult


class AnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name) / "home"
        self.home.mkdir()
        for relative in (
            ".config",
            ".cache",
            ".local/share/applications",
            ".local/share/pixmaps",
            ".local/state",
            ".local/bin",
            ".var/app",
            "Games",
            "Downloads",
        ):
            (self.home / relative).mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_guard_rejects_broad_and_shared_paths(self) -> None:
        guard = PathGuard(self.home)
        for path in (
            self.home,
            self.home / ".config",
            self.home / ".local/share",
            self.home / ".local/share/flatpak",
            self.home / ".cache/flatpak",
            self.home / ".local/share/lutris",
            self.home / ".cache/lutris",
            self.home / ".local/share/Steam",
            self.home / ".steam/debian-installation",
        ):
            with self.subTest(path=path), self.assertRaises(UnsafeTargetError):
                guard.validate(path)

    def test_pristontale_style_manual_install_is_grouped(self) -> None:
        install_root = self.home / "Games/PristontaleEU"
        (install_root / "game-compat/pfx/drive_c").mkdir(parents=True)
        (install_root / "game-compat/pfx/drive_c/Game.exe").write_bytes(b"game")
        source_root = self.home / "Downloads/pristontale-eu-linux-installer"
        source_root.mkdir()
        archive = self.home / "Downloads/pristontale-eu-linux-installer.zip"
        archive.write_bytes(b"zip")
        config = self.home / ".config/pristontale-eu"
        config.mkdir()
        launcher = self.home / ".local/bin/pristontale-eu"
        launcher.write_text(
            f"#!/bin/sh\ninstall_directory='{install_root}'\nexec python3 app.py\n",
            encoding="utf-8",
        )
        desktop = self.home / ".local/share/applications/eu.pristontale.PTLinux.desktop"
        desktop.write_text("[Desktop Entry]\nType=Application\n", encoding="utf-8")

        app = AppRecord(
            key="manual:eu.pristontale.PTLinux",
            name="PristonTale EU",
            source=SourceKind.MANUAL,
            package_id="eu.pristontale.PTLinux",
            exec_line=str(launcher),
            desktop_files=(str(desktop),),
            metadata={"executable": str(launcher)},
        )
        plan = RemovalAnalyzer(self.home).analyze(app)
        paths = {target.path for target in plan.targets}
        self.assertIn(install_root, paths)
        self.assertIn(source_root, paths)
        self.assertIn(archive, paths)
        self.assertIn(config, paths)
        self.assertIn(launcher, paths)
        self.assertIn(desktop, paths)

    def test_flatpak_shared_directories_are_never_targets(self) -> None:
        (self.home / ".cache/flatpak").mkdir()
        (self.home / ".local/share/flatpak").mkdir()
        app_data = self.home / ".var/app/org.blender.Blender"
        app_data.mkdir()
        app = AppRecord(
            key="flatpak:user:org.blender.Blender",
            name="Blender",
            source=SourceKind.FLATPAK,
            package_id="org.blender.Blender",
            metadata={"installation": "user"},
        )
        plan = RemovalAnalyzer(self.home).analyze(app)
        paths = {target.path for target in plan.targets}
        self.assertIn(app_data, paths)
        self.assertNotIn(self.home / ".cache/flatpak", paths)
        self.assertNotIn(self.home / ".local/share/flatpak", paths)
        self.assertEqual(plan.actions[0].command[:3], ("/usr/bin/flatpak", "--user", "uninstall"))

    def test_manager_owned_external_library_path_is_allowed_exactly(self) -> None:
        external_game = self.home.parent / "external-library/Test Quest"
        external_game.mkdir(parents=True)
        owned = json.dumps([{"path": str(external_game), "reason": "Steam-Spielordner"}])
        trusted = json.dumps([str(external_game)])
        app = AppRecord(
            key="steam:test",
            name="Test Quest",
            source=SourceKind.STEAM,
            package_id="steam-123",
            metadata={"owned_paths": owned, "trusted_paths": trusted},
        )
        plan = RemovalAnalyzer(self.home).analyze(app)
        self.assertIn(external_game, {target.path for target in plan.targets})

    def test_default_wine_prefix_is_kept_but_matching_program_folder_is_found(self) -> None:
        program = self.home / ".wine/drive_c/Program Files (x86)/Example Game"
        program.mkdir(parents=True)
        (program / "Game.exe").write_bytes(b"exe")
        desktop = self.home / ".local/share/applications/wine/Programs/Example Game.desktop"
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text("entry", encoding="utf-8")
        app = AppRecord(
            key="wine:example",
            name="Example Game",
            source=SourceKind.WINE,
            package_id="Example Game",
            exec_line=f'env WINEPREFIX="{self.home / ".wine"}" wine Game.exe',
            desktop_files=(str(desktop),),
            metadata={"wine_prefix": str(self.home / ".wine")},
        )
        plan = RemovalAnalyzer(self.home).analyze(app)
        paths = {target.path for target in plan.targets}
        self.assertIn(program, paths)
        self.assertNotIn(self.home / ".wine", paths)
        self.assertTrue(any("Standard-Wine-Präfix" in warning for warning in plan.warnings))

    @patch("restlos.package_managers.run_command")
    def test_apt_action_is_blocked_when_simulation_removes_core_system(self, command) -> None:
        command.return_value = CommandResult(
            ("apt-get",),
            0,
            "Remv harmless-app [1.0]\nRemv zorin-os-desktop [18.0]\n",
            "",
        )
        app = AppRecord(
            key="apt:harmless-app",
            name="Harmless App",
            source=SourceKind.APT,
            package_id="harmless-app",
        )
        plan = RemovalAnalyzer(self.home).analyze(app)
        self.assertEqual(plan.actions, [])
        self.assertEqual(plan.targets, [])
        self.assertTrue(any("Systemkomponenten" in warning for warning in plan.warnings))

    @patch("restlos.package_managers.run_command")
    def test_dnf_action_uses_preview_and_trusted_command(self, command) -> None:
        command.return_value = CommandResult(
            ("dnf",),
            1,
            "Removing:\n"
            " harmless-app x86_64 1.0 updates 1 M\n"
            "Removing unused dependencies:\n"
            " helper-lib noarch 2.0 updates 2 M\n"
            "Transaction Summary\n",
            "Operation aborted.\n",
        )
        app = AppRecord(
            key="dnf:harmless-app",
            name="Harmless App",
            source=SourceKind.DNF,
            package_id="harmless-app",
            metadata={"package_manager": "dnf"},
        )
        plan = RemovalAnalyzer(self.home).analyze(app)
        self.assertEqual(plan.actions[0].command[0], "/usr/bin/pkexec")
        self.assertEqual(Path(plan.actions[0].command[1]).name, "dnf")
        self.assertEqual(plan.actions[0].command[2:], ("-y", "remove", "harmless-app"))
        self.assertTrue(any("helper-lib" in warning for warning in plan.warnings))

    @patch("restlos.package_managers.run_command")
    def test_pacman_action_is_blocked_for_core_dependency(self, command) -> None:
        command.return_value = CommandResult(
            ("pacman",),
            0,
            "harmless-app\nsystemd\n",
            "",
        )
        app = AppRecord(
            key="pacman:harmless-app",
            name="Harmless App",
            source=SourceKind.PACMAN,
            package_id="harmless-app",
            metadata={"package_manager": "pacman"},
        )
        plan = RemovalAnalyzer(self.home).analyze(app)
        self.assertEqual(plan.actions, [])
        self.assertTrue(any("systemd" in warning for warning in plan.warnings))

    @patch("restlos.package_managers.run_command")
    def test_zypper_action_uses_dry_run_result(self, command) -> None:
        command.return_value = CommandResult(
            ("zypper",),
            0,
            "The following 2 packages are going to be REMOVED:\n"
            "  harmless-app helper-lib\n\n"
            "2 packages to remove.\n",
            "",
        )
        app = AppRecord(
            key="zypper:harmless-app",
            name="Harmless App",
            source=SourceKind.ZYPPER,
            package_id="harmless-app",
            metadata={"package_manager": "zypper"},
        )
        plan = RemovalAnalyzer(self.home).analyze(app)
        self.assertEqual(
            plan.actions[0].command,
            (
                "/usr/bin/pkexec",
                "/usr/bin/zypper",
                "--non-interactive",
                "remove",
                "--clean-deps",
                "harmless-app",
            ),
        )
        self.assertTrue(any("helper-lib" in warning for warning in plan.warnings))


if __name__ == "__main__":
    unittest.main()
