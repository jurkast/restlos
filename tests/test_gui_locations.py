"""GUI wiring checks; skip on systems without GTK or a display."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from restlos.locations import AppLocation, LocationResult
from restlos.models import AppRecord, Confidence, RemovalPlan, RemovalTarget, SourceKind

try:
    from restlos.gui import Gio, Gtk, MainWindow, RestlosApplication, TargetRow
    GTK_AVAILABLE = Gtk.init_check()
except (ImportError, ValueError):
    GTK_AVAILABLE = False


@unittest.skipUnless(GTK_AVAILABLE, "GTK 4 and a display are required")
class LocationGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = Gtk.Application(
            application_id="io.github.jurkast.Restlos.LocationTests",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        cls.application.register(None)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        with patch.object(MainWindow, "_load_applications"):
            self.window = MainWindow(self.application)
        self.addCleanup(self.window.destroy)

    def test_application_initialization_supports_baseline_gtk_and_glib(self) -> None:
        with patch("restlos.gui.UpdateState") as state, patch("restlos.gui.LanguageSettings") as settings:
            state.return_value.automatic_checks_enabled.return_value = False
            settings.return_value.selected.return_value = "system"
            application = RestlosApplication()
        self.assertEqual(application.get_flags(), Gio.ApplicationFlags(0))
        self.assertIsNotNone(application.lookup_action("check-updates"))
        self.assertTrue(self.window.search.get_property("placeholder-text"))

    def test_target_folder_button_leaves_selection_unchanged(self) -> None:
        target = RemovalTarget(self.root, "Data", 0, Confidence.HIGH, False)
        changed, opened = Mock(), Mock()
        row = TargetRow(target, changed, opened)
        row.get_child().get_last_child().emit("clicked")
        opened.assert_called_once_with(self.root)
        changed.assert_not_called()
        self.assertFalse(target.selected)

    @patch("restlos.gui.Gio.AppInfo.get_default_for_type")
    def test_desktop_file_is_passed_to_directory_handler_as_parent(self, get_manager) -> None:
        desktop = self.root / "run.desktop"
        desktop.write_text("[Desktop Entry]\nExec=must-not-run\n", encoding="utf-8")
        self.window._open_folder(desktop)
        get_manager.assert_called_once_with("inode/directory", False)
        args = get_manager.return_value.launch.call_args.args
        self.assertEqual(args[0][0].get_path(), str(self.root))

    @patch("restlos.gui.Gtk.MessageDialog")
    @patch("restlos.gui.Gio.AppInfo.get_default_for_type")
    def test_missing_file_does_not_launch_anything(self, get_manager, message) -> None:
        self.window._open_folder(self.root / "missing")
        get_manager.assert_not_called()
        message.return_value.present.assert_called_once()

    @patch("restlos.gui.Gtk.MessageDialog")
    @patch("restlos.gui.Gio.AppInfo.get_default_for_type", return_value=None)
    def test_missing_file_manager_shows_error(self, get_manager, message) -> None:
        self.window._open_folder(self.root)
        message.return_value.present.assert_called_once()

    def test_closed_dialog_ignores_late_results(self) -> None:
        dialog, rows, status = Mock(), Mock(), Mock()
        self.window._locations_dialog = None
        self.assertFalse(self.window._locations_loaded(dialog, rows, status, LocationResult(), None))
        rows.append.assert_not_called()
        status.set_text.assert_not_called()

    def test_location_buttons_use_their_own_paths(self) -> None:
        second = self.root / "second"
        second.mkdir()
        dialog = Gtk.Dialog(transient_for=self.window)
        self.addCleanup(dialog.destroy)
        self.window._locations_dialog = dialog
        rows, status = Gtk.ListBox(), Gtk.Label()
        result = LocationResult([AppLocation(self.root, "Data"), AppLocation(second, "Data")])
        self.window._locations_loaded(dialog, rows, status, result, None)
        with patch.object(self.window, "_open_folder") as opened:
            for n, path in enumerate((self.root, second)):
                rows.get_row_at_index(n).get_child().get_last_child().emit("clicked")
                opened.assert_called_with(path, dialog)

    def test_failed_analysis_cannot_leave_previous_apps_plan_active(self) -> None:
        app = AppRecord("portable:test", "Test", SourceKind.PORTABLE, "test")
        self.window.current_app = app
        self.window.current_plan = RemovalPlan(app)
        with patch("restlos.gui.threading.Thread"):
            self.window._analyze_current()
        self.assertIsNone(self.window.current_plan)
        self.assertFalse(self.window.remove_button.get_sensitive())
        self.window._analysis_loaded(None, "test error")
        self.assertTrue(self.window.locations_button.get_sensitive())
        self.assertFalse(self.window.remove_button.get_sensitive())


if __name__ == "__main__":
    unittest.main()
