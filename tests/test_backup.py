from __future__ import annotations

import json
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from restlos.backup import BackupError, BackupManager
from restlos.models import AppRecord, BackupItem, Confidence, RemovalAction, RemovalPlan, RemovalTarget, SourceKind
from restlos.recovery import RecoveryManager
from restlos.remover import RemovalExecutor


class FailingBackup:
    def create(self, _targets, *, progress=None):
        raise BackupError("Datenträger voll")


class RecordingBackup:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def create(self, _targets, *, progress=None):
        self.events.append("backup")
        return "", []


class RecordingExecutor(RemovalExecutor):
    def __init__(self, home: Path, events: list[str]) -> None:
        super().__init__(home, backup=RecordingBackup(events))
        self.events = events

    def related_processes(self, _plan):
        return [(123, "Demo")]

    def stop_processes(self, _processes):
        self.events.append("stop")


class BackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        for path in (".config", ".cache", ".local/share", ".local/state"):
            (self.home / path).mkdir(parents=True, exist_ok=True)
        self.manager = BackupManager(self.home)
        self.app = AppRecord(
            key="manual:demo",
            name="Demo App",
            source=SourceKind.MANUAL,
            package_id="demo-app",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_backup_selects_user_data_but_not_cache_or_game_installation(self) -> None:
        config = self.home / ".config/demo-app"
        cache = self.home / ".cache/demo-app"
        game = self.home / "Games/Demo"
        for path in (config, cache, game):
            path.mkdir(parents=True)
        targets = [
            RemovalTarget(config, "Einstellungen", 4, Confidence.CERTAIN),
            RemovalTarget(cache, "Cache", 9, Confidence.CERTAIN),
            RemovalTarget(game, "Steam-Spielordner", 20, Confidence.CERTAIN),
        ]
        self.assertEqual([item.path for item in self.manager.candidates(targets)], [config])

    def test_backup_rejects_own_storage_and_paths_escaping_through_symlink_parent(self) -> None:
        own_state = self.home / ".local/state/restlos"
        own_state.mkdir(parents=True)
        outside = Path(self.temporary.name).parent / f"{self.home.name}-outside"
        outside.mkdir()
        self.addCleanup(lambda: outside.rmdir() if outside.exists() else None)
        linked_root = self.home / ".config/linked"
        linked_root.symlink_to(outside, target_is_directory=True)
        escaped = linked_root / "settings"
        escaped.mkdir()
        targets = [
            RemovalTarget(own_state, "Anwendungsdaten", 1, Confidence.CERTAIN),
            RemovalTarget(escaped, "Einstellungen", 1, Confidence.CERTAIN),
        ]
        self.assertEqual(self.manager.candidates(targets), [])
        escaped.rmdir()

    def test_backup_skips_symlinks_and_restores_without_overwrite(self) -> None:
        config = self.home / ".config/demo-app"
        config.mkdir()
        (config / "settings.json").write_text('{"theme":"dark"}', encoding="utf-8")
        outside = self.home / "outside.txt"
        outside.write_text("keep", encoding="utf-8")
        (config / "external-link").symlink_to(outside)
        archive_path, items = self.manager.create(
            [RemovalTarget(config, "Einstellungen", 16, Confidence.CERTAIN)]
        )
        self.assertEqual(len(items), 1)
        with tarfile.open(archive_path, "r:gz") as archive:
            names = archive.getnames()
        self.assertNotIn("items/0000/external-link", names)
        self.assertIn("manifest.json", names)

        for child in config.iterdir():
            child.unlink()
        config.rmdir()
        self.manager.restore_item(Path(archive_path), items[0])
        self.assertEqual((config / "settings.json").read_text(encoding="utf-8"), '{"theme":"dark"}')
        self.assertEqual(outside.read_text(encoding="utf-8"), "keep")
        with self.assertRaises(FileExistsError):
            self.manager.restore_item(Path(archive_path), items[0])

    def test_failed_backup_aborts_before_any_removal(self) -> None:
        config = self.home / ".config/demo-app"
        config.mkdir()
        plan = RemovalPlan(
            app=self.app,
            targets=[RemovalTarget(config, "Einstellungen", 0, Confidence.CERTAIN)],
            actions=[RemovalAction("Marker anlegen", ("/usr/bin/touch", str(self.home / "action-ran")))],
        )
        result = RemovalExecutor(self.home, backup=FailingBackup()).execute(
            plan,
            permanent=True,
            create_backup=True,
        )
        self.assertFalse(result.success)
        self.assertTrue(config.exists())
        self.assertFalse((self.home / "action-ran").exists())
        self.assertIn("nichts entfernt", result.errors[0])

    def test_related_processes_stop_before_backup_snapshot(self) -> None:
        events: list[str] = []
        result = RecordingExecutor(self.home, events).execute(
            RemovalPlan(app=self.app),
            permanent=True,
            create_backup=True,
        )
        self.assertTrue(result.success, result.errors)
        self.assertEqual(events, ["stop", "backup"])

    def test_restore_rejects_archive_path_traversal(self) -> None:
        self.manager.backup_directory.mkdir(parents=True)
        archive_path = self.manager.backup_directory / "malicious.tar.gz"
        original = self.home / ".config/demo-app"
        manifest = {
            "schema": 1,
            "items": [
                {
                    "original_path": str(original),
                    "archive_member": "items/0000",
                    "size": 4,
                    "restored_at": "",
                }
            ],
        }
        with tarfile.open(archive_path, "w:gz") as archive:
            encoded = json.dumps(manifest).encode()
            info = tarfile.TarInfo("manifest.json")
            info.size = len(encoded)
            archive.addfile(info, io.BytesIO(encoded))
            bad = tarfile.TarInfo("items/0000/../../outside.txt")
            bad.size = 4
            archive.addfile(bad, io.BytesIO(b"evil"))
        with self.assertRaises(BackupError):
            self.manager.restore_item(
                archive_path,
                BackupItem(str(original), "items/0000", 4),
            )
        self.assertFalse((self.home / "outside.txt").exists())

    def test_permanent_removal_backup_is_listed_and_restored(self) -> None:
        config = self.home / ".config/demo-app"
        config.mkdir()
        (config / "settings.json").write_text("safe", encoding="utf-8")
        plan = RemovalPlan(
            app=self.app,
            targets=[RemovalTarget(config, "Einstellungen", 4, Confidence.CERTAIN)],
        )
        removed = RemovalExecutor(self.home).execute(plan, permanent=True, create_backup=True)
        self.assertTrue(removed.success, removed.errors)
        self.assertFalse(config.exists())
        self.assertEqual(len(removed.backup_items), 1)
        payload = json.loads(Path(removed.receipt_path).read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], 3)
        self.assertTrue(Path(payload["safety_backup"]["archive_path"]).is_file())

        manager = RecoveryManager(self.home)
        records = manager.list_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(len(records[0].available_backup_items), 1)
        restored = manager.restore(removed.recovery_id)
        self.assertTrue(restored.success, restored.errors)
        self.assertEqual((config / "settings.json").read_text(encoding="utf-8"), "safe")


if __name__ == "__main__":
    unittest.main()
