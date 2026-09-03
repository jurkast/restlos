from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from restlos.analyzer import PathGuard, RemovalAnalyzer, UnsafeTargetError
from restlos.models import AppRecord, Confidence, RemovalAction, RemovalPlan, RemovalTarget, SourceKind
from restlos.package_managers import RemovalPreview
from restlos.remover import RemovalExecutor
from restlos.safety import ReviewRequired, _mount_points, optional_fingerprint, path_fingerprint, seal_plan
from restlos.sharing import protect_shared_targets


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "home"
        self.home.mkdir()
        self.data = self.home / "Games/Alpha"
        self.data.mkdir(parents=True)
        self.save = self.data / "save.bin"
        self.save.write_bytes(b"first save")
        self.app = self.record("alpha", self.data)
        self.apps = [self.app]
        self.executor = RemovalExecutor(self.home, inventory_provider=lambda: self.apps)
        self.executor.related_processes = Mock(return_value=[])
        self.executor.stop_processes = Mock()

    def record(self, key, root, *, source=SourceKind.PORTABLE, **metadata):
        return AppRecord(key, key.title(), source, key,
                         metadata={"install_root": str(root), "owned_paths": json.dumps([
                             {"path": str(root), "reason": "Game data"}]), **metadata})

    def plan(self):
        plan = RemovalAnalyzer(self.home).analyze(self.app, applications=self.apps)
        self.assertFalse(plan.safety_error, plan.safety_error)
        self.assertIsNotNone(plan.snapshot)
        return plan

    def assert_blocked(self, plan):
        with patch("restlos.remover.subprocess.run") as run:
            result = self.executor.execute(plan)
        self.assertFalse(result.success, result.errors)
        self.assertTrue(result.review_required, result.errors)
        run.assert_not_called()
        self.assertTrue(self.data.exists())
        return result

    def test_unchanged_plan_can_remove_test_data(self):
        result = self.executor.execute(self.plan())
        self.assertTrue(result.success, result.errors)
        self.assertFalse(self.data.exists())

    def test_plan_without_review_cannot_execute(self):
        plan = RemovalPlan(self.app, [RemovalTarget(self.data, "Data", 0, Confidence.CERTAIN)])
        self.assert_blocked(plan)

    def test_nested_edit_addition_and_missing_target_invalidate_review(self):
        for change in (lambda: self.save.write_bytes(b"other save"),
                       lambda: (self.data / "new.txt").write_text("new"),
                       lambda: self.save.unlink()):
            with self.subTest(change=change):
                plan = self.plan()
                change()
                self.assert_blocked(plan)

    def test_replaced_directory_is_detected_even_with_same_name_and_files(self):
        plan = self.plan()
        self.data.rename(self.data.with_name("old-alpha"))
        self.data.mkdir()
        self.save.write_bytes(b"first save")
        self.assert_blocked(plan)

    def test_symlink_swap_never_deletes_destination(self):
        plan = self.plan()
        old = self.data.with_name("keep")
        self.data.rename(old)
        self.data.symlink_to(old, target_is_directory=True)
        self.assert_blocked(plan)
        self.assertTrue((old / "save.bin").exists())

    def test_parent_symlink_swap_is_detected(self):
        plan = self.plan()
        parent = self.home / "Games"
        old = self.home / "OldGames"
        parent.rename(old)
        parent.symlink_to(old, target_is_directory=True)
        self.assert_blocked(plan)
        self.assertTrue((old / "Alpha/save.bin").exists())

    def test_existing_parent_symlink_escape_and_dotdot_are_rejected(self):
        config = self.home / ".config"
        config.mkdir()
        outside = self.home / "Documents"
        outside.mkdir()
        (config / "alias").symlink_to(outside, target_is_directory=True)
        guard = PathGuard(self.home)
        for path in (config / "alias/precious", config / "../Documents/precious"):
            with self.subTest(path=path), self.assertRaises(UnsafeTargetError):
                guard.validate(path)

    def test_changed_unselected_data_is_preserved(self):
        plan = self.plan()
        for target in plan.targets:
            target.selected = False
        self.save.write_text("new save")
        result = self.executor.execute(plan)
        self.assertTrue(result.success, result.errors)
        self.assertTrue(self.save.exists())

    def test_added_target_or_changed_command_cannot_bypass_review(self):
        for change in (
            lambda plan: plan.targets.append(RemovalTarget(self.home, "Bad", 0, Confidence.CERTAIN)),
            lambda plan: plan.actions.append(RemovalAction("Bad", ("must-not-run",))),
            lambda plan: plan.app.metadata.update(trusted_paths='["/"]'),
        ):
            with self.subTest(change=change):
                plan = self.plan()
                change(plan)
                self.assert_blocked(plan)

    def test_new_application_requires_new_analysis_before_any_side_effect(self):
        plan = self.plan()
        self.apps.append(self.record("beta", self.data))
        self.executor.backup = Mock()
        self.assert_blocked(plan)
        self.executor.related_processes.assert_not_called()
        self.executor.stop_processes.assert_not_called()
        self.executor.backup.create.assert_not_called()

    def test_changed_indirect_reference_is_detected(self):
        other = self.home / "Games/Beta"
        other.mkdir()
        link = self.home / "beta-link"
        link.symlink_to(other, target_is_directory=True)
        self.apps.append(self.record("beta", link))
        plan = self.plan()
        link.unlink()
        link.symlink_to(self.data, target_is_directory=True)
        self.assert_blocked(plan)

    def test_shutdown_save_change_requires_new_confirmation(self):
        plan = self.plan()
        self.executor.related_processes.return_value = [(123, "test-only")]
        self.executor.stop_processes.side_effect = lambda _p: self.save.write_text("saved on exit")
        self.executor.backup = Mock()
        self.assert_blocked(plan)
        self.executor.stop_processes.assert_called_once()
        self.executor.backup.create.assert_not_called()

    def test_change_during_backup_aborts_before_removal(self):
        plan = self.plan()
        def backup(*_args, **_kwargs):
            self.save.write_text("changed during backup")
            return "", []
        self.executor.backup = Mock()
        self.executor.backup.create.side_effect = backup
        result = self.executor.execute(plan, create_backup=True)
        self.assertTrue(result.review_required)
        self.assertTrue(self.save.exists())

    def test_unreadable_check_fails_closed(self):
        plan = self.plan()
        with patch("restlos.safety.path_fingerprint", side_effect=PermissionError("test denial")):
            self.assert_blocked(plan)

    def test_special_file_and_scan_limit_fail_closed(self):
        with self.assertRaises(ReviewRequired):
            path_fingerprint(self.data, max_entries=1)
        os.mkfifo(self.data / "pipe")
        with self.assertRaises(ReviewRequired):
            path_fingerprint(self.data)

    def test_mount_point_is_not_traversed(self):
        with patch("restlos.safety.os.path.ismount", return_value=True), self.assertRaises(ReviewRequired):
            path_fingerprint(self.data)

    def test_same_device_bind_mount_inside_target_is_rejected(self):
        mount = self.data / "bind"
        mount.mkdir()
        with patch("restlos.safety._mount_points", return_value={Path("/"), mount}), \
             patch("restlos.safety.os.path.ismount", return_value=False), self.assertRaises(ReviewRequired):
            path_fingerprint(self.data)

    def test_mount_table_errors_and_changes_fail_closed(self):
        with patch("pathlib.Path.read_text", side_effect=PermissionError("denied")), self.assertRaises(PermissionError):
            _mount_points()
        with patch("pathlib.Path.read_text", return_value="broken"), self.assertRaises(ReviewRequired):
            _mount_points()
        with patch("restlos.safety._mount_points", side_effect=[{Path("/")}, {Path("/"), Path("/new-mount")}]), \
             self.assertRaises(ReviewRequired):
            path_fingerprint(self.data)

    def test_mount_table_decodes_escaped_spaces(self):
        with patch("pathlib.Path.read_text", return_value=r"31 20 0:24 / /games/My\040Games rw - ext4 /dev/test rw"):
            self.assertEqual(_mount_points(), {Path("/games/My Games")})

    def test_vanished_child_during_optional_check_is_not_missing_root(self):
        with patch("restlos.safety.path_fingerprint", side_effect=FileNotFoundError("child")), \
             self.assertRaises(FileNotFoundError):
            optional_fingerprint(self.data)

    def test_last_moment_read_error_stops_further_targets(self):
        plan = self.plan()
        def progress(message, _fraction):
            if message.startswith("Entferne "):
                self.data.rename(self.data.with_name("kept"))
        result = self.executor.execute(plan, progress=progress)
        self.assertTrue(result.review_required)
        self.assertTrue((self.data.with_name("kept") / "save.bin").exists())

    def test_symlink_inside_target_is_not_followed(self):
        outside = self.home / "outside"
        outside.mkdir()
        keep = outside / "keep"
        keep.write_text("keep")
        (self.data / "link").symlink_to(outside, target_is_directory=True)
        plan = self.plan()
        keep.write_text("still keep")
        result = self.executor.execute(plan)
        self.assertTrue(result.success, result.errors)
        self.assertTrue(keep.exists())

    def test_native_preview_is_rechecked_and_changed_dependencies_abort(self):
        self.app.source = SourceKind.APT
        adapter = Mock()
        adapter.preview_removal.return_value = RemovalPreview(("alpha",))
        adapter.is_protected.return_value = False
        adapter.removal_label.return_value = "Test package removal"
        adapter.removal_command.return_value = ("must-not-run",)
        with patch("restlos.analyzer.adapter_for_source", return_value=adapter), \
             patch("restlos.safety.adapter_for_source", return_value=adapter), \
             patch("restlos.safety.package_state", return_value="unchanged"):
            plan = self.plan()
            adapter.preview_removal.return_value = RemovalPreview(("alpha", "other-app"))
            self.assert_blocked(plan)

    def test_changed_package_version_aborts_even_if_same_packages_would_be_removed(self):
        with patch("restlos.safety.package_state", return_value="version-one") as state:
            plan = self.plan()
            state.return_value = "version-two"
            self.assert_blocked(plan)

    def test_failed_package_query_blocks_analysis_and_execution(self):
        with patch("restlos.safety.package_state", side_effect=ReviewRequired("package query failed")):
            plan = RemovalAnalyzer(self.home).analyze(self.app, applications=self.apps)
            self.assertTrue(plan.safety_error)
            self.assert_blocked(plan)

    def test_target_already_removed_by_package_action_does_not_fail_trash_mode(self):
        plan = self.plan()
        plan.actions.append(RemovalAction("Test only", ("fake-package-manager",)))
        seal_plan(plan, self.apps, home=self.home)
        def remove_test_target(*args, **kwargs):
            self.save.unlink()
            self.data.rmdir()
            return subprocess.CompletedProcess(args[0], 0, "", "")
        with patch("restlos.remover.subprocess.run", side_effect=remove_test_target):
            result = self.executor.execute(plan, permanent=False)
        self.assertTrue(result.success, result.errors)
        self.assertEqual(result.recovery_items, [])

    def test_changed_launcher_metadata_prevents_internal_action(self):
        metadata = self.home / ".config/heroic/installed.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text('{"alpha":{}}')
        plan = self.plan()
        plan.actions.append(RemovalAction("Test metadata", internal_kind="json-remove-key",
                                         parameters={"path": str(metadata), "key": "alpha"}))
        seal_plan(plan, self.apps, home=self.home)
        metadata.write_text('{"alpha":{},"beta":{}}')
        self.assert_blocked(plan)
        self.assertIn("alpha", json.loads(metadata.read_text()))


    def test_shared_game_root_is_locked_and_names_other_game(self):
        self.apps.append(self.record("beta", self.data, source=SourceKind.LUTRIS))
        plan = self.plan()
        target = next(target for target in plan.targets if target.path == self.data)
        self.assertFalse(target.selected)
        self.assertEqual(target.shared_with[0].app_name, "Beta")
        self.assertIn(str(self.data), target.shared_with[0].reference_path)
        result = self.executor.execute(plan)
        self.assertTrue(result.success, result.errors)
        self.assertTrue(self.save.exists())
        receipt = json.loads(Path(result.receipt_path).read_text())
        self.assertTrue(receipt["shared_paths"])

    def test_shared_flag_cannot_be_forced_through_model_or_executor(self):
        self.apps.append(self.record("beta", self.data))
        plan = self.plan()
        plan.targets[0].selected = True
        self.assertEqual(plan.selected_targets, [])
        self.assert_blocked(plan)

    def test_reference_inside_target_protects_entire_parent(self):
        child = self.data / "OtherGame"
        child.mkdir()
        self.apps.append(self.record("beta", child))
        plan = self.plan()
        self.assertEqual(plan.selected_targets, [])

    def test_target_inside_another_apps_root_is_protected(self):
        self.apps.append(self.record("beta", self.data.parent))
        plan = self.plan()
        self.assertEqual(plan.selected_targets, [])

    def test_similar_names_and_sibling_folders_do_not_establish_sharing(self):
        other = self.data.with_name("AlphaTwo")
        other.mkdir()
        self.apps.append(self.record("alpha-two", other))
        self.assertTrue(self.plan().selected_targets)

    def test_separate_roots_with_common_wine_prefix_are_protected(self):
        prefix = self.home / "Games/CommonPrefix"
        prefix.mkdir()
        (prefix / "drive_c").mkdir()
        (prefix / "system.reg").write_text("Wine registry")
        beta = self.home / "Games/Beta"
        beta.mkdir()
        self.app.source = SourceKind.LUTRIS
        self.app.metadata["wine_prefix"] = str(prefix)
        self.apps.append(self.record("beta", beta, source=SourceKind.LUTRIS, wine_prefix=str(prefix)))
        plan = self.plan()
        shared = next(target for target in plan.targets if target.path == prefix)
        self.assertFalse(shared.selected)
        self.assertEqual(shared.shared_with[0].app_key, "beta")
        self.assertIn(self.data, [target.path for target in plan.selected_targets])

    def test_lutris_config_alone_does_not_add_arbitrary_prefix_for_deletion(self):
        folder = self.home / "Games/Unrelated"
        folder.mkdir()
        self.app.source = SourceKind.LUTRIS
        self.app.metadata["wine_prefix"] = str(folder)
        self.assertNotIn(folder, [target.path for target in self.plan().targets])

    def test_standard_personal_folders_stay_protected_even_if_marked_trusted(self):
        for name in ("Documents", "Dokumente", "Pictures", "Bilder", "Music", "Musik", "Videos"):
            folder = self.home / name
            with self.subTest(folder=folder), self.assertRaises(UnsafeTargetError):
                PathGuard(self.home).validate(folder, (folder,))

    def test_flatpak_and_snap_purge_cannot_bypass_shared_path_protection(self):
        self.apps.append(self.record("beta", self.data))
        for source in (SourceKind.FLATPAK, SourceKind.SNAP):
            with self.subTest(source=source):
                self.app.source = source
                plan = RemovalPlan(self.app, [RemovalTarget(self.data, "Data", 0, Confidence.CERTAIN)])
                protect_shared_targets(plan, self.apps, self.home)
                self.assertTrue(plan.safety_error)
                self.assert_blocked(plan)

    def test_distinct_symlink_can_be_removed_without_deleting_shared_destination(self):
        link = self.home / "Games/AlphaLink"
        link.symlink_to(self.data, target_is_directory=True)
        self.apps.append(self.record("beta", self.data))
        plan = RemovalPlan(self.app, [RemovalTarget(link, "Link", 0, Confidence.CERTAIN)])
        protect_shared_targets(plan, self.apps, self.home)
        self.assertTrue(plan.selected_targets)
        seal_plan(plan, self.apps, home=self.home)
        result = self.executor.execute(plan)
        self.assertTrue(result.success, result.errors)
        self.assertFalse(link.is_symlink())
        self.assertTrue(self.save.exists())

    def test_new_scan_record_replaces_stale_ui_selection(self):
        stale = self.record("alpha", self.home / "Games/OldAlpha")
        plan = RemovalAnalyzer(self.home).analyze(stale, applications=self.apps)
        self.assertEqual(plan.app.metadata["install_root"], str(self.data))
        self.assertTrue(plan.selected_targets)
