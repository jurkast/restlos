from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from restlos.models import AppRecord, Confidence, RemovalAction, RemovalPlan, RemovalTarget, SourceKind
from restlos.remover import RemovalExecutor
from restlos.safety import seal_plan


class RemoverTests(unittest.TestCase):
    def setUp(self) -> None:
        for name in ("restlos.scanners.ApplicationScanner.scan", "restlos.remover.RemovalExecutor.related_processes"):
            mocked = patch(name, return_value=[])
            mocked.start()
            self.addCleanup(mocked.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        (self.home / ".config").mkdir()
        (self.home / ".cache").mkdir()
        (self.home / ".local/state").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _app(self) -> AppRecord:
        return AppRecord(
            key="manual:demo",
            name="Demo App",
            source=SourceKind.MANUAL,
            package_id="demo-app",
        )

    def test_permanent_removal_and_receipt(self) -> None:
        config = self.home / ".config/demo-app"
        cache = self.home / ".cache/demo-app"
        config.mkdir()
        cache.mkdir()
        (config / "settings.json").write_text("{}", encoding="utf-8")
        (cache / "cache.bin").write_bytes(b"1234")
        plan = RemovalPlan(
            app=self._app(),
            targets=[
                RemovalTarget(config, "Einstellungen", 2, Confidence.CERTAIN),
                RemovalTarget(cache, "Cache", 4, Confidence.HIGH),
            ],
        )
        seal_plan(plan, [], home=self.home)
        result = RemovalExecutor(self.home).execute(plan, permanent=True)
        self.assertTrue(result.success, result.errors)
        self.assertFalse(config.exists())
        self.assertFalse(cache.exists())
        self.assertTrue(Path(result.receipt_path).is_file())

    def test_unselected_target_is_preserved(self) -> None:
        config = self.home / ".config/demo-app"
        config.mkdir()
        plan = RemovalPlan(
            app=self._app(),
            targets=[
                RemovalTarget(config, "möglicher Treffer", 0, Confidence.POSSIBLE, selected=False),
            ],
        )
        seal_plan(plan, [], home=self.home)
        result = RemovalExecutor(self.home).execute(plan, permanent=True)
        self.assertTrue(result.success)
        self.assertTrue(config.exists())

    def test_symlink_is_unlinked_without_following_target(self) -> None:
        outside = self.home / "important"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep", encoding="utf-8")
        link = self.home / ".config/demo-link"
        link.symlink_to(outside, target_is_directory=True)
        plan = RemovalPlan(
            app=self._app(),
            targets=[RemovalTarget(link, "Starter", 0, Confidence.CERTAIN)],
        )
        seal_plan(plan, [], home=self.home)
        result = RemovalExecutor(self.home).execute(plan, permanent=True)
        self.assertTrue(result.success, result.errors)
        self.assertFalse(link.exists())
        self.assertTrue((outside / "keep.txt").is_file())

    def test_lutris_entry_is_removed_only_after_game_folder(self) -> None:
        database = self.home / ".local/share/lutris/pga.db"
        database.parent.mkdir(parents=True)
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT)")
            connection.execute("CREATE TABLE games_categories (game_id INTEGER, category_id INTEGER)")
            connection.execute("INSERT INTO games VALUES (7, 'Test Quest')")
            connection.execute("INSERT INTO games_categories VALUES (7, 1)")
        game = self.home / "Games/TestQuest"
        game.mkdir(parents=True)
        app = AppRecord(
            key="lutris:7",
            name="Test Quest",
            source=SourceKind.LUTRIS,
            package_id="lutris-7-test-quest",
            metadata={"trusted_paths": json.dumps([str(game)])},
        )
        plan = RemovalPlan(
            app=app,
            targets=[RemovalTarget(game, "Lutris-Spielordner", 0, Confidence.CERTAIN)],
            actions=[
                RemovalAction(
                    label="Lutris-Eintrag entfernen",
                    internal_kind="lutris-database",
                    parameters={"database": str(database), "game_id": "7"},
                )
            ],
        )
        seal_plan(plan, [], home=self.home)
        result = RemovalExecutor(self.home).execute(plan, permanent=True)
        self.assertTrue(result.success, result.errors)
        with sqlite3.connect(database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM games WHERE id=7").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM games_categories WHERE game_id=7").fetchone()[0], 0)

    def test_heroic_installed_json_is_updated_atomically(self) -> None:
        installed = self.home / ".config/heroic/legendaryConfig/legendary/installed.json"
        installed.parent.mkdir(parents=True)
        installed.write_text(json.dumps({"remove-me": {"title": "Game"}, "keep-me": {}}), encoding="utf-8")
        app = AppRecord(
            key="heroic:remove-me",
            name="Game",
            source=SourceKind.HEROIC,
            package_id="heroic-remove-me",
        )
        plan = RemovalPlan(
            app=app,
            actions=[
                RemovalAction(
                    label="Heroic-Eintrag entfernen",
                    internal_kind="json-remove-key",
                    parameters={"path": str(installed), "key": "remove-me"},
                )
            ],
        )
        seal_plan(plan, [], home=self.home)
        result = RemovalExecutor(self.home).execute(plan, permanent=True)
        self.assertTrue(result.success, result.errors)
        self.assertEqual(json.loads(installed.read_text(encoding="utf-8")), {"keep-me": {}})


if __name__ == "__main__":
    unittest.main()
