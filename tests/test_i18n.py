from __future__ import annotations

import json
import ast
import tempfile
import unittest
from pathlib import Path

from restlos.i18n import ENGLISH, LanguageSettings, configure, display_text, translate


class I18nTests(unittest.TestCase):
    def tearDown(self) -> None:
        configure("de")

    def test_german_and_english_catalog(self) -> None:
        configure("en")
        self.assertEqual(translate("Löschplan"), "Removal plan")
        self.assertEqual(display_text("Steam-Spiel · App-ID 42"), "Steam game · App ID 42")
        self.assertEqual(
            display_text("Flatpak „org.demo.App“ samt App-Daten entfernen"),
            "Remove Flatpak “org.demo.App” including app data",
        )
        configure("de")
        self.assertEqual(translate("Löschplan"), "Löschplan")

    def test_language_setting_is_private_and_preserves_other_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary)
            path = config / "restlos/settings.json"
            path.parent.mkdir()
            path.write_text(json.dumps({"automatic_updates": True}), encoding="utf-8")
            settings = LanguageSettings(config_home=config)
            settings.set("en")
            self.assertEqual(settings.selected(), "en")
            self.assertTrue(json.loads(path.read_text(encoding="utf-8"))["automatic_updates"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_invalid_or_corrupt_setting_falls_back_to_system(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary)
            path = config / "restlos/settings.json"
            path.parent.mkdir()
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(LanguageSettings(config_home=config).selected(), "system")

    def test_every_explicit_gui_and_cli_message_has_an_english_translation(self) -> None:
        project = Path(__file__).resolve().parents[1]
        missing: list[str] = []
        for relative in ("restlos/gui.py", "restlos/cli.py"):
            tree = ast.parse((project / relative).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "_"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                    and node.args[0].value not in ENGLISH
                ):
                    missing.append(f"{relative}:{node.lineno}: {node.args[0].value}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
