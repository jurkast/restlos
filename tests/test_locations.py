from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from restlos.locations import LocationResolver, folder_for_path
from restlos.models import AppRecord, Confidence, RemovalAction, RemovalPlan, RemovalTarget, SourceKind
from restlos.utils import CommandResult


class LocationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def app(self, source=SourceKind.PORTABLE, **kwargs) -> AppRecord:
        return AppRecord(key="test:demo", name="Demo", source=source, package_id="demo", **kwargs)

    def file(self, relative: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test", encoding="utf-8")
        return path

    def test_directory_opens_itself(self) -> None:
        self.assertEqual(folder_for_path(self.root), self.root)

    def test_executable_desktop_and_special_names_open_parent(self) -> None:
        for name in ("run.AppImage", "app.desktop", "a b # % ü ' $() ;.exe"):
            path = self.file("Applications/" + name)
            self.assertEqual(folder_for_path(path), path.parent)

    def test_symlinks_show_link_parent_not_target(self) -> None:
        destination = self.root / "real-folder"
        destination.mkdir()
        directory = self.root / "links"
        directory.mkdir()
        for name, target in (("directory-link", destination), ("broken-link", self.root / "missing")):
            link = directory / name
            link.symlink_to(target)
            self.assertEqual(folder_for_path(link), directory)

    def test_missing_relative_remote_and_special_paths_are_rejected(self) -> None:
        for path in (Path("relative/file"), Path("https://example.com"), Path("/tmp/bad\0path")):
            with self.assertRaises(ValueError):
                folder_for_path(path)
        with self.assertRaises(FileNotFoundError):
            folder_for_path(self.root / "missing")
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            folder_for_path(fifo)

    @patch("restlos.locations.run_command")
    def test_locations_do_not_mutate_plan_or_execute_launcher(self, command) -> None:
        path = self.file("Games/My Game/run.exe")
        app = self.app(metadata={"install_root": str(path.parent), "executable": str(path)})
        app.exec_line = "sh -c 'must-not-run'"
        target = RemovalTarget(path, "Programmdatei", 4, Confidence.CERTAIN, selected=False)
        plan = RemovalPlan(app, [target], [RemovalAction("must not run", ("false",))])
        original = plan.to_dict()
        result = LocationResolver().inspect(app, plan)
        self.assertEqual([item.path for item in result.locations], [path.parent, path])
        self.assertEqual(plan.to_dict(), original)
        command.assert_not_called()

    def test_other_app_plan_is_ignored(self) -> None:
        path = self.file("other/settings.json")
        app = self.app()
        other = self.app()
        other.key = "other"
        plan = RemovalPlan(other, [RemovalTarget(path, "Settings", 4, Confidence.HIGH)])
        self.assertEqual(LocationResolver().inspect(app, plan).locations, [])

    def test_launcher_metadata_and_deselected_targets_are_included_once(self) -> None:
        config = self.file(".config/lutris/games/demo.yml")
        launcher = self.file(".local/share/applications/demo.desktop")
        app = self.app(SourceKind.LUTRIS, desktop_files=(str(launcher),), metadata={
            "owned_paths": json.dumps([{"path": str(config)}, {"path": str(config)}, {"path": 123}]),
        })
        plan = RemovalPlan(app, [RemovalTarget(config, "Settings", 4, Confidence.POSSIBLE, False)])
        result = LocationResolver().inspect(app, plan)
        self.assertEqual([item.path for item in result.locations], [config, launcher])

    def test_invalid_and_missing_metadata_is_ignored(self) -> None:
        app = self.app(metadata={"install_root": "https://bad", "executable": "/not/present", "owned_paths": "{"})
        self.assertEqual(LocationResolver().inspect(app).locations, [])
        app.metadata["owned_paths"] = "null"
        self.assertEqual(LocationResolver().inspect(app).locations, [])

    @patch("restlos.locations.run_command")
    def test_native_queries_are_read_only_and_shared_ancestors_are_omitted(self, command) -> None:
        binary = self.file("usr/bin/demo")
        data = self.file("usr/share/demo/data.dat")
        for source, binary_name, option in (
            (SourceKind.APT, "dpkg-query", "--listfiles"),
            (SourceKind.DNF, "rpm", "-ql"),
            (SourceKind.ZYPPER, "rpm", "-ql"),
            (SourceKind.PACMAN, "pacman", "-Qql"),
        ):
            with self.subTest(source=source):
                command.return_value = CommandResult((), 0, f"/\n{self.root}\n{binary}\n{binary}\n{data}\n/not/present\n", "")
                result = LocationResolver().inspect(self.app(source))
                self.assertEqual([item.path for item in result.locations], [binary.parent, data.parent])
                actual = command.call_args.args[0]
                self.assertEqual(Path(actual[0]).name, binary_name)
                self.assertEqual(actual[1:], (option, "demo"))
                self.assertTrue(Path(actual[0]).is_absolute())
                self.assertEqual(command.call_args.kwargs, {"timeout": 15})

    @patch("restlos.locations.run_command")
    def test_invalid_package_id_never_becomes_an_option_or_command(self, command) -> None:
        for package in ("--help", "demo;touch /tmp/file", "../../etc", "demo\nother"):
            app = self.app(SourceKind.APT)
            app.package_id = package
            self.assertTrue(LocationResolver().inspect(app).warnings)
        command.assert_not_called()

    @patch("restlos.locations.run_command")
    def test_failed_query_keeps_user_locations_and_warns(self, command) -> None:
        path = self.file(".config/demo/settings")
        command.return_value = CommandResult((), 127, "", "timed out")
        app = self.app(SourceKind.APT)
        plan = RemovalPlan(app, [RemovalTarget(path, "Settings", 4, Confidence.HIGH)])
        result = LocationResolver().inspect(app, plan)
        self.assertEqual([item.path for item in result.locations], [path])
        self.assertEqual(len(result.warnings), 1)

    @patch("restlos.locations.run_command")
    def test_flatpak_uses_exact_installation_scope(self, command) -> None:
        command.return_value = CommandResult((), 0, str(self.root) + "\n", "")
        for installation, expected in (("user", "--user"), ("system", "--system"), ("games", "--installation=games")):
            result = LocationResolver().inspect(self.app(SourceKind.FLATPAK, metadata={"installation": installation}))
            self.assertEqual([item.path for item in result.locations], [self.root])
            self.assertEqual(command.call_args.args[0][1:], ("info", expected, "--show-location", "demo"))

    @patch("restlos.locations.run_command")
    def test_flatpak_rejects_invalid_scope(self, command) -> None:
        result = LocationResolver().inspect(self.app(SourceKind.FLATPAK, metadata={"installation": "--bad scope"}))
        self.assertTrue(result.warnings)
        command.assert_not_called()

    def test_limit_is_explicit_and_does_not_change_targets(self) -> None:
        app = self.app()
        plan = RemovalPlan(app, [RemovalTarget(self.file(f"data/{n}"), "Data", 4, Confidence.HIGH) for n in range(4)])
        result = LocationResolver(limit=2).inspect(app, plan)
        self.assertEqual(len(result.locations), 2)
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(len(plan.selected_targets), 4)

    def test_snap_current_revision_and_alternative_mount_root(self) -> None:
        revision = self.root / "snap/demo/12"
        revision.mkdir(parents=True)
        (revision.parent / "current").symlink_to("12")
        with patch("restlos.locations.SNAP_MOUNT_ROOTS", (self.root / "missing", self.root / "snap")):
            result = LocationResolver().inspect(self.app(SourceKind.SNAP))
        self.assertEqual([item.path for item in result.locations], [revision])
        self.assertEqual(folder_for_path(result.locations[0].path), revision)

    def test_missing_snap_mount_is_reported(self) -> None:
        with patch("restlos.locations.SNAP_MOUNT_ROOTS", (self.root,)):
            result = LocationResolver().inspect(self.app(SourceKind.SNAP))
        self.assertEqual(result.locations, [])
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
