from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from restlos.models import AppRecord, Confidence, RecoveryItem, RemovalPlan, RemovalTarget, SourceKind
from restlos.recovery import RecoveryManager, TrashBackend
from restlos.remover import RemovalExecutor


class FakeTrashBackend:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir()
        self.entries: dict[str, str] = {}
        self.stored: dict[str, Path] = {}
        self.counter = 0

    def list_entries(self) -> dict[str, str]:
        return dict(self.entries)

    def move(self, path: Path, size: int = 0) -> RecoveryItem:
        self.counter += 1
        uri = f"trash:///restlos-test-{self.counter}"
        destination = self.root / f"item-{self.counter}"
        path.rename(destination)
        self.entries[uri] = str(path.absolute())
        self.stored[uri] = destination
        return RecoveryItem(str(path.absolute()), uri, size)

    def restore(self, item: RecoveryItem) -> None:
        if self.entries.get(item.trash_uri) != item.original_path:
            raise OSError("Papierkorbeintrag stimmt nicht überein")
        original = Path(item.original_path)
        if original.exists() or original.is_symlink():
            raise FileExistsError(f"Am ursprünglichen Ort existiert bereits etwas: {original}")
        self.stored[item.trash_uri].rename(original)
        self.entries.pop(item.trash_uri)


class RecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        for path in (".config", ".cache", ".local/share", ".local/state"):
            (self.home / path).mkdir(parents=True, exist_ok=True)
        self.trash = FakeTrashBackend(self.home / "fake-trash")
        self.app = AppRecord(
            key="manual:demo",
            name="Demo App",
            source=SourceKind.MANUAL,
            package_id="demo-app",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_trash_removal_is_listed_and_can_be_restored(self) -> None:
        config = self.home / ".config/demo-app"
        config.mkdir()
        (config / "settings.json").write_text('{"theme":"dark"}', encoding="utf-8")
        plan = RemovalPlan(
            app=self.app,
            targets=[RemovalTarget(config, "Einstellungen", 16, Confidence.CERTAIN)],
        )

        result = RemovalExecutor(self.home, trash=self.trash).execute(plan, permanent=False)

        self.assertTrue(result.success, result.errors)
        self.assertFalse(config.exists())
        self.assertEqual(len(result.recovery_items), 1)
        receipt = Path(result.receipt_path)
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], 2)
        self.assertEqual(payload["mode"], "trash")
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)

        manager = RecoveryManager(self.home, trash=self.trash)
        records = manager.list_records()
        self.assertEqual([record.recovery_id for record in records], [result.recovery_id])
        self.assertEqual(records[0].available_size, 16)

        restored = manager.restore(result.recovery_id)
        self.assertTrue(restored.success, restored.errors)
        self.assertEqual(restored.restored_paths, [str(config)])
        self.assertEqual((config / "settings.json").read_text(encoding="utf-8"), '{"theme":"dark"}')
        self.assertEqual(manager.list_records(), [])

    def test_restore_never_overwrites_a_recreated_path(self) -> None:
        config = self.home / ".config/demo-app"
        config.mkdir()
        (config / "old.txt").write_text("old", encoding="utf-8")
        plan = RemovalPlan(
            app=self.app,
            targets=[RemovalTarget(config, "Einstellungen", 3, Confidence.CERTAIN)],
        )
        removed = RemovalExecutor(self.home, trash=self.trash).execute(plan, permanent=False)
        config.mkdir()
        (config / "new.txt").write_text("new", encoding="utf-8")

        restored = RecoveryManager(self.home, trash=self.trash).restore(removed.recovery_id)

        self.assertFalse(restored.success)
        self.assertIn("existiert bereits", restored.errors[0])
        self.assertEqual((config / "new.txt").read_text(encoding="utf-8"), "new")
        self.assertEqual(len(self.trash.entries), 1)

    def test_control_scan_separates_residual_and_intentionally_kept_paths(self) -> None:
        selected = self.home / ".config/demo-app"
        residual = self.home / ".cache/demo-app"
        kept = self.home / ".local/share/demo-app"
        selected.mkdir()
        residual.mkdir()
        kept.mkdir()
        plan = RemovalPlan(
            app=self.app,
            targets=[
                RemovalTarget(selected, "Einstellungen", 0, Confidence.CERTAIN),
                RemovalTarget(kept, "Anwendungsdaten", 0, Confidence.POSSIBLE, selected=False),
            ],
        )

        result = RemovalExecutor(self.home, trash=self.trash).execute(plan, permanent=True)

        self.assertTrue(result.success, result.errors)
        self.assertEqual(result.residual_paths, [str(residual)])
        self.assertEqual(result.kept_paths, [str(kept)])
        payload = json.loads(Path(result.receipt_path).read_text(encoding="utf-8"))
        self.assertEqual(payload["residual_paths"], [str(residual)])
        self.assertEqual(payload["kept_paths"], [str(kept)])

    def test_invalid_recovery_identifier_is_rejected(self) -> None:
        result = RecoveryManager(self.home, trash=self.trash).restore("../../other")
        self.assertFalse(result.success)
        self.assertIn("Ungültige", result.errors[0])

    def test_gio_backend_tracks_the_exact_new_trash_uri_and_restores_it(self) -> None:
        original = self.home / ".config/gio-demo"
        original.write_text("payload", encoding="utf-8")
        uri = "trash:///gio-demo"
        listed = False

        def runner(command, **_kwargs):
            nonlocal listed
            if command[1:] == ("trash", "--list"):
                output = f"{uri}\t{original}\n" if listed else ""
                return subprocess.CompletedProcess(command, 0, output, "")
            if command[1:] == ("trash", str(original)):
                original.unlink()
                listed = True
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[1:] == ("trash", "--restore", uri):
                original.write_text("payload", encoding="utf-8")
                listed = False
                return subprocess.CompletedProcess(command, 0, "", "")
            raise AssertionError(command)

        backend = TrashBackend(gio_path="/fake/gio", runner=runner)
        item = backend.move(original, 7)
        self.assertEqual(item.trash_uri, uri)
        self.assertFalse(original.exists())
        backend.restore(item)
        self.assertEqual(original.read_text(encoding="utf-8"), "payload")


if __name__ == "__main__":
    unittest.main()
