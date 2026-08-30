from __future__ import annotations

import json
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from . import APP_ID, APP_NAME, PROJECT_URL, __version__
from .analyzer import RemovalAnalyzer
from .models import AppRecord, Confidence, RemovalPlan, RemovalResult, SourceKind
from .remover import RemovalExecutor
from .scanners import ApplicationScanner
from .utils import format_size


CSS = b"""
window { background: @window_bg_color; }
.sidebar { background: alpha(@view_bg_color, 0.82); border-right: 1px solid alpha(@borders, 0.55); }
.app-list row { border-radius: 10px; margin: 2px 6px; }
.app-list row:selected { background: alpha(@accent_bg_color, 0.18); color: @window_fg_color; }
.app-name { font-weight: 650; }
.muted { color: alpha(@window_fg_color, 0.62); }
.source-badge { border-radius: 999px; padding: 2px 8px; background: alpha(@accent_bg_color, 0.14); color: @accent_color; font-size: 0.86em; }
.hero-title { font-size: 1.65em; font-weight: 750; }
.section-title { font-size: 1.08em; font-weight: 700; }
.card { background: @card_bg_color; border: 1px solid alpha(@borders, 0.55); border-radius: 12px; padding: 14px; }
.warning-card { background: alpha(#f6d32d, 0.10); border: 1px solid alpha(#e5a50a, 0.45); border-radius: 10px; padding: 10px; }
.target-row { border-bottom: 1px solid alpha(@borders, 0.35); padding: 7px 4px; }
.confidence-certain { color: #2ec27e; }
.confidence-high { color: #3584e4; }
.confidence-possible { color: #e5a50a; }
.danger-note { color: #c01c28; font-weight: 650; }
.empty-title { font-size: 1.35em; font-weight: 700; }
"""


def _clear_box(container: Gtk.Widget) -> None:
    child = container.get_first_child()
    while child is not None:
        next_child = child.get_next_sibling()
        if isinstance(container, Gtk.ListBox):
            container.remove(child)
        elif isinstance(container, Gtk.Box):
            container.remove(child)
        child = next_child


def _icon_widget(icon: str, size: int = 40) -> Gtk.Image:
    path = Path(icon)
    if path.is_absolute() and path.exists():
        image = Gtk.Image.new_from_file(str(path))
    else:
        image = Gtk.Image.new_from_icon_name(icon or "application-x-executable")
    image.set_pixel_size(size)
    return image


class ApplicationRow(Gtk.ListBoxRow):
    def __init__(self, record: AppRecord) -> None:
        super().__init__()
        self.record = record
        self.set_activatable(True)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=11)
        box.set_margin_top(9)
        box.set_margin_bottom(9)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.append(_icon_widget(record.icon, 34))

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        labels.set_hexpand(True)
        name = Gtk.Label(label=record.name, xalign=0)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.add_css_class("app-name")
        labels.append(name)
        source = Gtk.Label(label=f"{record.source.value} · {record.package_id}", xalign=0)
        source.set_ellipsize(Pango.EllipsizeMode.END)
        source.add_css_class("muted")
        labels.append(source)
        box.append(labels)
        self.set_child(box)


class TargetRow(Gtk.ListBoxRow):
    def __init__(self, target, changed_callback) -> None:
        super().__init__()
        self.target = target
        self.set_selectable(False)
        self.add_css_class("target-row")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        check = Gtk.CheckButton()
        check.set_active(target.selected)
        check.set_valign(Gtk.Align.CENTER)
        check.connect("toggled", self._on_toggled, changed_callback)
        box.append(check)

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        labels.set_hexpand(True)
        path_label = Gtk.Label(label=str(target.path), xalign=0)
        path_label.set_selectable(True)
        path_label.set_ellipsize(Pango.EllipsizeMode.END)
        path_label.set_tooltip_text(str(target.path))
        labels.append(path_label)
        reason = Gtk.Label(label=target.reason, xalign=0)
        reason.add_css_class("muted")
        labels.append(reason)
        box.append(labels)

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        side.set_valign(Gtk.Align.CENTER)
        size = Gtk.Label(label=format_size(target.size), xalign=1)
        side.append(size)
        confidence = Gtk.Label(label=target.confidence.value, xalign=1)
        confidence.add_css_class(
            {
                Confidence.CERTAIN: "confidence-certain",
                Confidence.HIGH: "confidence-high",
                Confidence.POSSIBLE: "confidence-possible",
            }[target.confidence]
        )
        side.append(confidence)
        box.append(side)
        self.set_child(box)

    def _on_toggled(self, check: Gtk.CheckButton, callback) -> None:
        self.target.selected = check.get_active()
        callback()


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application, title=f"{APP_NAME} – App-Deinstaller")
        self.set_default_size(1120, 760)
        self.set_size_request(840, 560)
        self.apps: list[AppRecord] = []
        self.current_app: AppRecord | None = None
        self.current_plan: RemovalPlan | None = None
        self._legacy_folder_dialog: Gtk.FileChooserNative | None = None
        self.busy = False

        self._build_header()
        self._build_content()
        self._load_applications()

    def _build_header(self) -> None:
        header = Gtk.HeaderBar()
        title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main = Gtk.Label(label=APP_NAME)
        main.add_css_class("app-name")
        sub = Gtk.Label(label="Vollständiger App-Deinstaller")
        sub.add_css_class("muted")
        title.append(main)
        title.append(sub)
        header.set_title_widget(title)

        self.refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self.refresh_button.set_tooltip_text("Programmliste neu einlesen")
        self.refresh_button.connect("clicked", lambda _button: self._load_applications())
        header.pack_start(self.refresh_button)

        menu = Gio.Menu()
        menu.append("Protokollordner öffnen", "app.open-history")
        menu.append("Update-Hilfe", "app.update-help")
        menu.append("Über Restlos", "app.about")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        header.pack_end(menu_button)
        self.set_titlebar(header)

    def _build_content(self) -> None:
        paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        paned.set_position(370)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        self.set_child(paned)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        sidebar.add_css_class("sidebar")
        sidebar.set_size_request(310, -1)
        sidebar.set_margin_top(10)
        sidebar.set_margin_bottom(10)
        sidebar.set_margin_start(8)
        sidebar.set_margin_end(8)

        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Programme durchsuchen …")
        self.search.connect("search-changed", self._on_search_changed)
        sidebar.append(self.search)

        filter_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        sources = ["Alle Quellen", *(source.value for source in SourceKind)]
        self.source_filter = Gtk.DropDown.new_from_strings(sources)
        self.source_filter.set_hexpand(True)
        self.source_filter.set_tooltip_text("Nach Installationsquelle filtern")
        self.source_filter.connect("notify::selected", lambda *_args: self.app_list.invalidate_filter())
        filter_bar.append(self.source_filter)
        folder_button = Gtk.Button(label="Ordner prüfen …")
        folder_button.set_tooltip_text("Einen nicht erkannten Programm- oder Spieleordner manuell analysieren")
        folder_button.connect("clicked", self._choose_folder)
        filter_bar.append(folder_button)
        sidebar.append(filter_bar)

        self.scan_status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.scan_spinner = Gtk.Spinner()
        self.scan_status_label = Gtk.Label(label="Programme werden eingelesen …", xalign=0)
        self.scan_status_label.set_hexpand(True)
        self.scan_status_label.add_css_class("muted")
        self.scan_status.append(self.scan_spinner)
        self.scan_status.append(self.scan_status_label)
        sidebar.append(self.scan_status)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self.app_list = Gtk.ListBox()
        self.app_list.add_css_class("app-list")
        self.app_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.app_list.set_filter_func(self._filter_application)
        self.app_list.connect("row-selected", self._on_app_selected)
        placeholder = Gtk.Label(label="Keine passenden Programme gefunden")
        placeholder.set_margin_top(28)
        placeholder.add_css_class("muted")
        self.app_list.set_placeholder(placeholder)
        scroll.set_child(self.app_list)
        sidebar.append(scroll)
        paned.set_start_child(sidebar)

        self.detail_stack = Gtk.Stack()
        self.detail_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.detail_stack.add_named(self._empty_page(), "empty")
        self.detail_stack.add_named(self._detail_page(), "detail")
        self.detail_stack.add_named(self._progress_page(), "progress")
        self.detail_stack.set_visible_child_name("empty")
        paned.set_end_child(self.detail_stack)

    def _empty_page(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        image = Gtk.Image.new_from_icon_name("edit-delete-symbolic")
        image.set_pixel_size(72)
        image.add_css_class("muted")
        box.append(image)
        title = Gtk.Label(label="Programm auswählen")
        title.add_css_class("empty-title")
        box.append(title)
        note = Gtk.Label(label="Restlos erstellt zuerst einen überprüfbaren Löschplan.")
        note.add_css_class("muted")
        box.append(note)
        return box

    def _detail_page(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        outer.set_margin_top(22)
        outer.set_margin_bottom(18)
        outer.set_margin_start(24)
        outer.set_margin_end(24)

        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        self.detail_icon_box = Gtk.Box()
        hero.append(self.detail_icon_box)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        labels.set_hexpand(True)
        self.detail_name = Gtk.Label(xalign=0)
        self.detail_name.add_css_class("hero-title")
        labels.append(self.detail_name)
        self.detail_description = Gtk.Label(xalign=0)
        self.detail_description.set_wrap(True)
        self.detail_description.add_css_class("muted")
        labels.append(self.detail_description)
        meta = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.detail_source = Gtk.Label()
        self.detail_source.add_css_class("source-badge")
        meta.append(self.detail_source)
        self.detail_id = Gtk.Label(xalign=0)
        self.detail_id.set_selectable(True)
        self.detail_id.add_css_class("muted")
        meta.append(self.detail_id)
        labels.append(meta)
        hero.append(labels)
        self.analyze_button = Gtk.Button(label="Erneut analysieren")
        self.analyze_button.set_valign(Gtk.Align.START)
        self.analyze_button.connect("clicked", lambda _button: self._analyze_current())
        hero.append(self.analyze_button)
        outer.append(hero)

        self.warning_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.warning_box.add_css_class("warning-card")
        self.warning_box.set_visible(False)
        outer.append(self.warning_box)

        section = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        section_title = Gtk.Label(label="Löschplan", xalign=0)
        section_title.add_css_class("section-title")
        section_title.set_hexpand(True)
        section.append(section_title)
        self.plan_summary = Gtk.Label(xalign=1)
        self.plan_summary.add_css_class("muted")
        section.append(self.plan_summary)
        outer.append(section)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        plan_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.action_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.action_card.add_css_class("card")
        plan_box.append(self.action_card)
        self.target_list = Gtk.ListBox()
        self.target_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.target_list.add_css_class("card")
        plan_box.append(self.target_list)
        scroll.set_child(plan_box)
        outer.append(scroll)

        options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.permanent_check = Gtk.CheckButton(label="Benutzerdaten endgültig löschen (nicht in den Papierkorb)")
        self.permanent_check.set_active(True)
        options.append(self.permanent_check)
        self.process_check = Gtk.CheckButton(label="Zugehörige laufende Prozesse automatisch beenden")
        self.process_check.set_active(True)
        options.append(self.process_check)
        outer.append(options)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.delete_note = Gtk.Label(label="Vor dem Löschen erscheint eine letzte Zusammenfassung.", xalign=0)
        self.delete_note.set_hexpand(True)
        self.delete_note.add_css_class("muted")
        bottom.append(self.delete_note)
        self.remove_button = Gtk.Button(label="Restlos entfernen")
        self.remove_button.add_css_class("destructive-action")
        self.remove_button.connect("clicked", self._confirm_removal)
        bottom.append(self.remove_button)
        outer.append(bottom)
        return outer

    def _progress_page(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_size_request(500, -1)
        self.progress_spinner = Gtk.Spinner()
        self.progress_spinner.set_size_request(48, 48)
        box.append(self.progress_spinner)
        self.progress_title = Gtk.Label(label="Entfernung wird vorbereitet …")
        self.progress_title.add_css_class("empty-title")
        self.progress_title.set_wrap(True)
        self.progress_title.set_max_width_chars(58)
        box.append(self.progress_title)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_size_request(480, -1)
        box.append(self.progress_bar)
        note = Gtk.Label(label="Dieses Fenster nicht schließen, solange Paketaktionen laufen.")
        note.add_css_class("muted")
        box.append(note)
        return box

    def _load_applications(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.refresh_button.set_sensitive(False)
        self.scan_spinner.start()
        self.scan_status_label.set_text("Pakete, Spielebibliotheken, Wine und portable Ordner werden eingelesen …")

        def worker() -> None:
            try:
                apps = ApplicationScanner().scan()
                GLib.idle_add(self._applications_loaded, apps, None)
            except Exception as error:  # defensive boundary for the GUI worker
                GLib.idle_add(self._applications_loaded, [], str(error))

        threading.Thread(target=worker, daemon=True).start()

    def _applications_loaded(self, apps: list[AppRecord], error: str | None) -> bool:
        self.busy = False
        self.refresh_button.set_sensitive(True)
        self.scan_spinner.stop()
        if error:
            self.scan_status_label.set_text(f"Einlesen fehlgeschlagen: {error}")
            return False
        self.apps = apps
        _clear_box(self.app_list)
        for app in apps:
            self.app_list.append(ApplicationRow(app))
        self.scan_status_label.set_text(f"{len(apps)} Anwendungen erkannt")
        self.app_list.invalidate_filter()
        return False

    def _filter_application(self, row: Gtk.ListBoxRow) -> bool:
        if not isinstance(row, ApplicationRow):
            return True
        query = self.search.get_text().strip().casefold()
        app = row.record
        selected = self.source_filter.get_selected_item()
        source_name = selected.get_string() if isinstance(selected, Gtk.StringObject) else "Alle Quellen"
        source_matches = source_name == "Alle Quellen" or app.source.value == source_name
        query_matches = not query or query in f"{app.name} {app.package_id} {app.source.value}".casefold()
        return source_matches and query_matches

    def _on_search_changed(self, _entry: Gtk.SearchEntry) -> None:
        self.app_list.invalidate_filter()

    def _choose_folder(self, _button: Gtk.Button) -> None:
        if hasattr(Gtk, "FileDialog"):
            dialog = Gtk.FileDialog(title="Programm- oder Spieleordner auswählen")
            dialog.select_folder(self, None, self._folder_selected)
            return
        dialog = Gtk.FileChooserNative(
            title="Programm- oder Spieleordner auswählen",
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            accept_label="Auswählen",
            cancel_label="Abbrechen",
        )
        self._legacy_folder_dialog = dialog
        dialog.connect("response", self._legacy_folder_selected)
        dialog.show()

    def _folder_selected(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        path_value = folder.get_path()
        if not path_value:
            self.scan_status_label.set_text("Dieser Ordner ist nicht als lokaler Pfad verfügbar.")
            return
        self._add_manual_folder(Path(path_value).absolute())

    def _legacy_folder_selected(self, dialog: Gtk.FileChooserNative, response: int) -> None:
        file = dialog.get_file() if response == Gtk.ResponseType.ACCEPT else None
        dialog.destroy()
        self._legacy_folder_dialog = None
        if file is None or not file.get_path():
            return
        self._add_manual_folder(Path(file.get_path()).absolute())

    def _add_manual_folder(self, path: Path) -> None:
        owned = json.dumps(
            [{"path": str(path), "reason": "Manuell gewählter Programm-/Datenordner"}],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        trusted = json.dumps([str(path)], ensure_ascii=False, separators=(",", ":"))
        app = AppRecord(
            key=f"portable:{path}",
            name=path.name or str(path),
            source=SourceKind.PORTABLE,
            package_id=path.name or "manueller-ordner",
            description="Manuell ausgewählter Ordner; Inhalt und Größe werden vor dem Entfernen angezeigt",
            icon="folder-symbolic",
            scope="Manuelle Auswahl",
            metadata={
                "manager": "portable",
                "owned_paths": owned,
                "trusted_paths": trusted,
                "install_root": str(path),
            },
        )
        existing = next((item for item in self.apps if item.key == app.key), None)
        if existing is not None:
            app = existing
        else:
            self.apps.append(app)
            self.app_list.append(ApplicationRow(app))
            self.scan_status_label.set_text(f"{len(self.apps)} Anwendungen erkannt · manueller Ordner hinzugefügt")
        self.search.set_text("")
        self.source_filter.set_selected(0)
        self.app_list.invalidate_filter()
        child = self.app_list.get_first_child()
        while child is not None:
            if isinstance(child, ApplicationRow) and child.record.key == app.key:
                self.app_list.select_row(child)
                break
            child = child.get_next_sibling()

    def _on_app_selected(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if not isinstance(row, ApplicationRow) or self.busy:
            return
        self.current_app = row.record
        self._show_app_header(row.record)
        self._analyze_current()

    def _show_app_header(self, app: AppRecord) -> None:
        _clear_box(self.detail_icon_box)
        self.detail_icon_box.append(_icon_widget(app.icon, 64))
        self.detail_name.set_text(app.name)
        self.detail_description.set_text(app.description or "Keine Beschreibung verfügbar")
        self.detail_source.set_text(f"{app.source.value} · {app.scope}")
        self.detail_id.set_text(app.package_id)
        self.detail_stack.set_visible_child_name("detail")

    def _analyze_current(self) -> None:
        if self.current_app is None or self.busy:
            return
        self.busy = True
        self.analyze_button.set_sensitive(False)
        self.remove_button.set_sensitive(False)
        self.plan_summary.set_text("Analyse läuft …")
        app = self.current_app

        def worker() -> None:
            try:
                plan = RemovalAnalyzer().analyze(app)
                GLib.idle_add(self._analysis_loaded, plan, None)
            except Exception as error:
                GLib.idle_add(self._analysis_loaded, None, str(error))

        threading.Thread(target=worker, daemon=True).start()

    def _analysis_loaded(self, plan: RemovalPlan | None, error: str | None) -> bool:
        self.busy = False
        self.analyze_button.set_sensitive(True)
        if error or plan is None:
            self.plan_summary.set_text(f"Analyse fehlgeschlagen: {error or 'unbekannter Fehler'}")
            return False
        if self.current_app is None or plan.app.key != self.current_app.key:
            return False
        self.current_plan = plan
        _clear_box(self.action_card)
        _clear_box(self.target_list)
        _clear_box(self.warning_box)

        if plan.actions:
            action_title = Gtk.Label(label="Paketverwaltung", xalign=0)
            action_title.add_css_class("section-title")
            self.action_card.append(action_title)
            for action in plan.actions:
                line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                icon = Gtk.Image.new_from_icon_name("system-software-install-symbolic")
                line.append(icon)
                label = Gtk.Label(label=action.label, xalign=0)
                label.set_wrap(True)
                line.append(label)
                self.action_card.append(line)
            self.action_card.set_visible(True)
        else:
            self.action_card.set_visible(False)

        for target in plan.targets:
            self.target_list.append(TargetRow(target, self._update_plan_summary))
        if not plan.targets:
            label = Gtk.Label(label="Keine zusätzlichen Benutzerdaten gefunden")
            label.set_margin_top(18)
            label.set_margin_bottom(18)
            label.add_css_class("muted")
            self.target_list.append(label)

        for warning in plan.warnings:
            line = Gtk.Label(label=f"⚠ {warning}", xalign=0)
            line.set_wrap(True)
            self.warning_box.append(line)
        self.warning_box.set_visible(bool(plan.warnings))
        self._update_plan_summary()
        return False

    def _update_plan_summary(self) -> None:
        if self.current_plan is None:
            return
        count = len(self.current_plan.selected_targets)
        action_count = len(self.current_plan.actions)
        self.plan_summary.set_text(
            f"{action_count} Paketaktion(en) · {count} Pfad(e) · {format_size(self.current_plan.total_size)}"
        )
        self.remove_button.set_sensitive(bool(action_count or count) and not self.busy)

    def _confirm_removal(self, _button: Gtk.Button) -> None:
        plan = self.current_plan
        if plan is None or self.busy:
            return
        permanent = self.permanent_check.get_active()
        processes = RemovalExecutor().related_processes(plan)
        process_note = ""
        if processes:
            names = ", ".join(f"{name} (PID {pid})" for pid, name in processes[:5])
            process_note = f"\n\nLaufende Prozesse: {names}"
        mode = "dauerhaft gelöscht" if permanent else "in den Papierkorb verschoben"
        secondary = (
            f"{len(plan.actions)} Paketaktion(en) und {len(plan.selected_targets)} ausgewählte Pfade "
            f"mit {format_size(plan.total_size)} werden verarbeitet. Benutzerdaten werden {mode}."
            f"{process_note}"
        )
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text=f"„{plan.app.name}“ wirklich restlos entfernen?",
            secondary_text=secondary,
        )
        dialog.add_button("Abbrechen", Gtk.ResponseType.CANCEL)
        confirm = dialog.add_button("Endgültig entfernen" if permanent else "Entfernen", Gtk.ResponseType.ACCEPT)
        confirm.add_css_class("destructive-action")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        dialog.connect("response", self._on_confirm_response)
        dialog.present()

    def _on_confirm_response(self, dialog: Gtk.MessageDialog, response: int) -> None:
        dialog.destroy()
        if response != Gtk.ResponseType.ACCEPT or self.current_plan is None:
            return
        self._start_removal(self.current_plan)

    def _start_removal(self, plan: RemovalPlan) -> None:
        self.busy = True
        permanent = self.permanent_check.get_active()
        stop_processes = self.process_check.get_active()
        self.detail_stack.set_visible_child_name("progress")
        self.progress_spinner.start()
        self.progress_bar.set_fraction(0.0)
        self.progress_title.set_text(f"„{plan.app.name}“ wird entfernt …")

        def update(message: str, fraction: float) -> None:
            GLib.idle_add(self._set_progress, message, fraction)

        def worker() -> None:
            executor = RemovalExecutor()
            result = executor.execute(
                plan,
                permanent=permanent,
                stop_processes=stop_processes,
                progress=update,
            )
            GLib.idle_add(self._removal_finished, plan, result)

        threading.Thread(target=worker, daemon=True).start()

    def _set_progress(self, message: str, fraction: float) -> bool:
        self.progress_title.set_text(message)
        self.progress_bar.set_fraction(max(0.0, min(fraction, 1.0)))
        return False

    def _removal_finished(self, plan: RemovalPlan, result: RemovalResult) -> bool:
        self.busy = False
        self.progress_spinner.stop()
        self.progress_bar.set_fraction(1.0)
        if result.success:
            title = f"„{plan.app.name}“ wurde entfernt"
            details = (
                f"{len(result.removed_paths)} Pfade wurden entfernt. "
                f"Das Ergebnis wurde unter {result.receipt_path or 'keinem Protokollpfad'} dokumentiert."
            )
            message_type = Gtk.MessageType.INFO
        else:
            title = "Entfernung nicht vollständig"
            details = "\n".join(result.errors[:8]) or "Ein unbekannter Fehler ist aufgetreten."
            message_type = Gtk.MessageType.ERROR
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=message_type,
            buttons=Gtk.ButtonsType.CLOSE,
            text=title,
            secondary_text=details,
        )
        dialog.connect("response", self._after_result_dialog, result.success)
        dialog.present()
        return False

    def _after_result_dialog(self, dialog: Gtk.MessageDialog, _response: int, success: bool) -> None:
        dialog.destroy()
        if success:
            self.current_app = None
            self.current_plan = None
            self.detail_stack.set_visible_child_name("empty")
            self._load_applications()
        else:
            self.detail_stack.set_visible_child_name("detail")
            self._update_plan_summary()


class RestlosApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.connect("activate", self._activate)
        self._add_actions()

    def _activate(self, _application: Gtk.Application) -> None:
        window = self.props.active_window
        if window is None:
            window = MainWindow(self)
        window.present()

    def _add_actions(self) -> None:
        for name, callback in (
            ("about", self._show_about),
            ("open-history", self._open_history),
            ("update-help", self._show_update_help),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def _show_about(self, _action, _parameter) -> None:
        dialog = Gtk.AboutDialog(
            transient_for=self.props.active_window,
            modal=True,
            program_name=APP_NAME,
            version=__version__,
            comments="Sicherer vollständiger App-Deinstaller für große Linux-Distributionsfamilien.",
            copyright="2026 – lokale Open-Source-Ausgabe",
            license_type=Gtk.License.MIT_X11,
        )
        dialog.set_website(PROJECT_URL)
        dialog.set_website_label("Projektseite auf GitHub")
        dialog.present()

    def _open_history(self, _action, _parameter) -> None:
        path = Path.home() / ".local/state/restlos/history"
        path.mkdir(parents=True, exist_ok=True)
        Gio.AppInfo.launch_default_for_uri(path.as_uri(), None)

    def _show_update_help(self, _action, _parameter) -> None:
        window = self.props.active_window
        dialog = Gtk.MessageDialog(
            transient_for=window,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.CLOSE,
            text="Restlos aktualisieren",
            secondary_text=(
                "Eine neue Ausgabe kann mit dem enthaltenen update.sh installiert werden. "
                "Einstellungen und Entfernungshistorie bleiben erhalten; Programmdateien werden atomar ersetzt."
            ),
        )
        dialog.connect("response", lambda item, _response: item.destroy())
        dialog.present()


def run_gui() -> int:
    Gtk.init()
    display = Gdk.Display.get_default()
    if display is None:
        print("Keine grafische Sitzung gefunden. Verwende `restlos list` oder `restlos analyze NAME`.")
        return 1
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_display(
        display,
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    return RestlosApplication().run(None)
