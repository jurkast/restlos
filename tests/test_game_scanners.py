from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from restlos.game_scanners import GamePlatformScanner
from restlos.models import SourceKind


class GamePlatformScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name) / "home"
        self.home.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_lutris_database_game_and_owned_paths_are_detected(self) -> None:
        data = self.home / ".local/share/lutris"
        game = self.home / "Games/test-lutris"
        config = data / "games/test-lutris-42.yml"
        game.mkdir(parents=True)
        config.parent.mkdir(parents=True)
        config.write_text(f"game:\n  prefix: {game}\n", encoding="utf-8")
        database = data / "pga.db"
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE games (id INTEGER, name TEXT, slug TEXT, platform TEXT, runner TEXT, "
                "directory TEXT, configpath TEXT, service TEXT, service_id TEXT, installed INTEGER)"
            )
            connection.execute(
                "INSERT INTO games VALUES (42, 'Test Quest', 'test-quest', 'Windows', 'wine', ?, "
                "'test-lutris-42', '', '', 1)",
                (str(game),),
            )

        records = GamePlatformScanner(self.home).scan()
        app = next(record for record in records if record.source == SourceKind.LUTRIS)
        owned = {item["path"] for item in json.loads(app.metadata["owned_paths"])}
        actions = json.loads(app.metadata["manager_actions"])
        self.assertEqual(app.name, "Test Quest")
        self.assertIn(str(game), owned)
        self.assertIn(str(config), owned)
        self.assertEqual(actions[0]["kind"], "lutris-database")

    def test_steam_game_is_detected_but_runtime_is_filtered(self) -> None:
        steam = self.home / ".steam/debian-installation"
        steamapps = steam / "steamapps"
        game = steamapps / "common/Test Quest"
        game.mkdir(parents=True)
        (steamapps / "compatdata/123/pfx").mkdir(parents=True)
        (steam / "appcache/librarycache/123").mkdir(parents=True)
        (steam / "appcache/librarycache/123/library_capsule.jpg").write_bytes(b"image")
        (steamapps / "appmanifest_123.acf").write_text(
            '"AppState"\n{\n"appid" "123"\n"name" "Test Quest"\n"installdir" "Test Quest"\n}',
            encoding="utf-8",
        )
        (steamapps / "appmanifest_456.acf").write_text(
            '"AppState"\n{\n"appid" "456"\n"name" "Proton 99"\n"installdir" "Proton 99"\n}',
            encoding="utf-8",
        )

        records = GamePlatformScanner(self.home).scan()
        steam_records = [record for record in records if record.source == SourceKind.STEAM]
        self.assertEqual([record.name for record in steam_records], ["Test Quest"])
        owned = {item["path"] for item in json.loads(steam_records[0].metadata["owned_paths"])}
        self.assertIn(str(game), owned)
        self.assertIn(str(steamapps / "compatdata/123"), owned)

    def test_heroic_bottles_playonlinux_and_orphan_are_detected(self) -> None:
        heroic = self.home / ".config/heroic"
        installed = heroic / "legendaryConfig/legendary/installed.json"
        heroic_game = self.home / "Games/HeroicQuest"
        heroic_prefix = self.home / "Games/HeroicQuestPrefix"
        heroic_game.mkdir(parents=True)
        heroic_prefix.mkdir()
        installed.parent.mkdir(parents=True)
        installed.write_text(
            json.dumps({"hero-1": {"title": "Heroic Quest", "install_path": str(heroic_game)}}),
            encoding="utf-8",
        )
        settings = heroic / "GamesConfig/hero-1.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps({"winePrefix": str(heroic_prefix)}), encoding="utf-8")

        bottle = self.home / ".local/share/bottles/bottles/WorkBottle"
        bottle.mkdir(parents=True)
        (bottle / "bottle.yml").write_text("Name: Work Bottle\n", encoding="utf-8")
        pol_prefix = self.home / ".PlayOnLinux/wineprefix/LegacyGame"
        pol_prefix.mkdir(parents=True)
        orphan = self.home / "Games/PortableThing"
        orphan.mkdir()

        scanner = GamePlatformScanner(self.home)
        managed = scanner.scan()
        sources = {record.source for record in managed}
        self.assertTrue({SourceKind.HEROIC, SourceKind.BOTTLES, SourceKind.PLAYONLINUX} <= sources)
        heroic_app = next(record for record in managed if record.source == SourceKind.HEROIC)
        owned = {item["path"] for item in json.loads(heroic_app.metadata["owned_paths"])}
        self.assertIn(str(heroic_game), owned)
        self.assertIn(str(heroic_prefix), owned)
        orphans = scanner.scan_unmanaged_game_folders(managed)
        self.assertEqual([record.name for record in orphans], ["PortableThing"])


if __name__ == "__main__":
    unittest.main()
