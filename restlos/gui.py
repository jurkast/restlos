from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from . import APP_ID, APP_NAME, APP_TAGLINE, PROJECT_URL, __version__
from .analyzer import RemovalAnalyzer
from .backup import BackupManager
from .i18n import LanguageSettings, display_text, translate as _
from .locations import LocationResolver, LocationResult, folder_for_path
from .models import AppRecord, Confidence, RecoveryRecord, RemovalPlan, RemovalResult, RestoreResult, SourceKind
from .recovery import RecoveryManager
from .remover import RemovalExecutor
from .scanners import ApplicationScanner
from .updater import ReleaseInfo, UpdateClient, UpdateError, UpdateState, is_system_managed_install
from .utils import format_size


CSS = b"""
window.restlos-root { background: @window_bg_color; }
window.restlos-root.restlos-light { color: #202128; background: #f7f7fa; }
window.restlos-root.restlos-dark { color: #f4f2f7; background: #1d1c21; }
.brand-mark {
  min-width: 32px;
  min-height: 32px;
  border-radius: 10px;
  background: @accent_bg_color;
  color: @accent_fg_color;
  font-size: 17px;
  font-weight: 900;
}
.brand-name { font-size: 15px; font-weight: 800; }
.header-tagline { color: alpha(@window_fg_color, 0.62); font-size: 0.86em; }
.sidebar {
  background: alpha(@view_bg_color, 0.76);
  border-right: 1px solid alpha(@borders, 0.62);
}
.sidebar-heading, .eyebrow, .stat-heading {
  color: alpha(@window_fg_color, 0.58);
  font-size: 0.78em;
  font-weight: 800;
  letter-spacing: 1.1px;
}
.scan-card {
  padding: 9px 11px;
  border-radius: 12px;
  background: alpha(@accent_bg_color, 0.10);
}
.app-list { background: transparent; }
.app-list row { border-radius: 12px; margin: 3px 0; }
.app-list row:hover { background: alpha(@window_fg_color, 0.055); }
.app-list row:selected {
  background: alpha(@accent_bg_color, 0.18);
  color: @window_fg_color;
}
.app-name { font-weight: 750; }
.app-source { color: alpha(@window_fg_color, 0.58); font-size: 0.88em; }
.muted { color: alpha(@window_fg_color, 0.62); }
.source-badge {
  border-radius: 999px;
  padding: 3px 9px;
  background: alpha(@accent_bg_color, 0.14);
  color: @accent_color;
  font-size: 0.86em;
  font-weight: 700;
}
.hero-card, .card, .safety-card, .stat-tile {
  background: @card_bg_color;
  border: 1px solid alpha(@borders, 0.62);
}
.hero-card { border-radius: 18px; padding: 18px; }
.hero-title { font-size: 1.8em; font-weight: 800; }
.section-title { font-size: 1.15em; font-weight: 800; }
.card { border-radius: 16px; padding: 15px; }
.stat-tile { border-radius: 14px; padding: 13px; }
.stat-value { font-size: 1.15em; font-weight: 800; }
.safety-card { border-radius: 16px; padding: 14px; }
.action-bar {
  padding-top: 12px;
  border-top: 1px solid alpha(@borders, 0.45);
}
.warning-card {
  background: alpha(#f6d32d, 0.12);
  border: 1px solid alpha(#e5a50a, 0.48);
  border-radius: 14px;
  padding: 12px;
}
.target-row { border-bottom: 1px solid alpha(@borders, 0.35); padding: 9px 4px; }
.confidence-certain { color: #2ec27e; }
.confidence-high { color: #3584e4; }
.confidence-possible { color: #e5a50a; }
.danger-note { color: #c01c28; font-weight: 650; }
.empty-title { font-size: 1.5em; font-weight: 800; }
.restlos-light .sidebar { background: #f0eff5; border-color: #d9d7e0; }
.restlos-dark .sidebar { background: #242329; border-color: #3b3942; }
.restlos-light .hero-card,
.restlos-light .card,
.restlos-light .safety-card,
.restlos-light .stat-tile { background: #ffffff; border-color: #dedce5; }
.restlos-dark .hero-card,
.restlos-dark .card,
.restlos-dark .safety-card,
.restlos-dark .stat-tile { background: #29282e; border-color: #403e46; }
.restlos-light .muted,
.restlos-light .app-source,
.restlos-light .header-tagline,
.restlos-light .sidebar-heading,
.restlos-light .eyebrow,
.restlos-light .stat-heading { color: #68788e; }
.restlos-dark .muted,
.restlos-dark .app-source,
.restlos-dark .header-tagline,
.restlos-dark .sidebar-heading,
.restlos-dark .eyebrow,
.restlos-dark .stat-heading { color: #b9b6c1; }
.restlos-light .scan-card { background: #e2f2fb; }
.restlos-dark .scan-card { background: #253540; }
.restlos-light .warning-card { color: #594000; background: #fff7e8; border-color: #e7c788; }
.restlos-dark .warning-card { color: #f4d38a; background: #3a3020; border-color: #75603b; }
.restlos-light .target-row:hover { color: #202128; background: #f3f2f6; }
.restlos-dark .target-row:hover { color: #f4f2f7; background: #35333b; }
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
        source = Gtk.Label(label=f"{display_text(record.source.value)} · {record.package_id}", xalign=0)
        source.set_ellipsize(Pango.EllipsizeMode.END)
        source.add_css_class("app-source")
        labels.append(source)
        box.append(labels)
        self.set_child(box)


class TargetRow(Gtk.ListBoxRow):
    def __init__(self, target, changed_callback, open_callback) -> None:
        super().__init__()
        self.target = target
        self.set_selectable(False)
        self.add_css_class("target-row")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        check = Gtk.CheckButton()
        check.set_active(target.selected and not target.shared_with)
        check.set_sensitive(not target.shared_with)
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
        reason = Gtk.Label(label=display_text(target.reason), xalign=0)
        reason.set_wrap(True)
        reason.add_css_class("muted")
        labels.append(reason)
        if target.shared_with:
            shared = Gtk.Expander(label=_("Geschützt – wer braucht diese Daten noch?"))
            references = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            for use in target.shared_with:
                note = Gtk.Label(
                    label=_("{name} ({source})\n{evidence}: {path}", name=use.app_name,
                            source=display_text(use.source), evidence=display_text(use.evidence), path=use.reference_path),
                    xalign=0,
                )
                note.set_wrap(True)
                note.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                note.set_max_width_chars(45)
                note.set_selectable(True)
                references.append(note)
            shared.set_child(references)
            labels.append(shared)
        box.append(labels)

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        side.set_valign(Gtk.Align.CENTER)
        size = Gtk.Label(label=format_size(target.size), xalign=1)
        side.append(size)
        confidence = Gtk.Label(label=_("Geschützt") if target.shared_with else display_text(target.confidence.value), xalign=1)
        confidence.add_css_class(
            {
                Confidence.CERTAIN: "confidence-certain",
                Confidence.HIGH: "confidence-high",
                Confidence.POSSIBLE: "confidence-possible",
            }[target.confidence]
        )
        side.append(confidence)
        box.append(side)
        open_button = Gtk.Button.new_from_icon_name("folder-open-symbolic")
        open_button.set_valign(Gtk.Align.CENTER)
        open_button.set_tooltip_text(_("Ordner öffnen: {path}", path=target.path))
        open_button.connect("clicked", lambda _button: open_callback(target.path))
        box.append(open_button)
        self.set_child(box)

    def _on_toggled(self, check: Gtk.CheckButton, callback) -> None:
        self.target.selected = check.get_active() and not self.target.shared_with
        if self.target.shared_with and check.get_active():
            check.set_active(False)
        callback()


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application, title=APP_NAME)
        self.set_default_size(1120, 760)
        self.set_size_request(840, 560)
        self.add_css_class("restlos-root")
        self._gtk_settings = Gtk.Settings.get_default()
        if self._gtk_settings is not None:
            self._gtk_settings.connect("notify::gtk-theme-name", self._sync_theme)
            self._gtk_settings.connect("notify::gtk-application-prefer-dark-theme", self._sync_theme)
        self._sync_theme()
        self.apps: list[AppRecord] = []
        self.current_app: AppRecord | None = None
        self.current_plan: RemovalPlan | None = None
        self._legacy_folder_dialog: Gtk.FileChooserNative | None = None
        self._recovery_dialog: Gtk.Dialog | None = None
        self._locations_dialog: Gtk.Dialog | None = None
        self.busy = False

        self._build_header()
        self._build_content()
        self._load_applications()

    def _sync_theme(self, *_args) -> None:
        self.remove_css_class("restlos-light")
        self.remove_css_class("restlos-dark")
        theme_name = ""
        prefer_dark = False
        if self._gtk_settings is not None:
            theme_name = str(self._gtk_settings.get_property("gtk-theme-name") or "")
            prefer_dark = bool(self._gtk_settings.get_property("gtk-application-prefer-dark-theme"))
        environment_theme = os.environ.get("GTK_THEME", "")
        dark = prefer_dark or "dark" in theme_name.casefold() or "dark" in environment_theme.casefold()
        self.add_css_class("restlos-dark" if dark else "restlos-light")

    def _build_header(self) -> None:
        header = Gtk.HeaderBar()

        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        mark = Gtk.Label(label="R", xalign=0.5, yalign=0.5)
        mark.add_css_class("brand-mark")
        mark.set_valign(Gtk.Align.CENTER)
        name = Gtk.Label(label=APP_NAME, xalign=0)
        name.add_css_class("brand-name")
        brand.append(mark)
        brand.append(name)
        header.pack_start(brand)

        tagline = Gtk.Label(label=APP_TAGLINE)
        tagline.add_css_class("header-tagline")
        tagline.set_ellipsize(Pango.EllipsizeMode.END)
        header.set_title_widget(tagline)

        self.refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self.refresh_button.set_tooltip_text(_("Programmliste neu einlesen"))
        self.refresh_button.connect("clicked", lambda _button: self._load_applications())
        header.pack_end(self.refresh_button)

        menu = Gio.Menu()
        menu.append(_("Wiederherstellungszentrum …"), "app.recovery")
        menu.append(_("Protokollordner öffnen"), "app.open-history")
        menu.append(_("Nach Updates suchen …"), "app.check-updates")
        menu.append(_("Automatisch nach Updates suchen"), "app.automatic-updates")
        language_menu = Gio.Menu()
        for label, language in (
            (_("Systemsprache"), "system"),
            (_("Deutsch"), "de"),
            (_("Englisch"), "en"),
        ):
            item = Gio.MenuItem.new(label, None)
            item.set_action_and_target_value("app.language", GLib.Variant.new_string(language))
            language_menu.append_item(item)
        menu.append_submenu(_("Sprache"), language_menu)
        menu.append(_("Über Restlos Uninstaller"), "app.about")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        header.pack_end(menu_button)
        self.set_titlebar(header)

    def _build_content(self) -> None:
        paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        paned.set_position(370)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        self.set_child(paned)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        sidebar.add_css_class("sidebar")
        sidebar.set_size_request(320, -1)
        sidebar.set_margin_top(18)
        sidebar.set_margin_bottom(16)
        sidebar.set_margin_start(14)
        sidebar.set_margin_end(14)

        sidebar_heading = Gtk.Label(label=_("INSTALLIERTE APPS & SPIELE"), xalign=0)
        sidebar_heading.add_css_class("sidebar-heading")
        sidebar.append(sidebar_heading)

        self.search = Gtk.SearchEntry()
        # The property predates the setter method, which requires GTK 4.10.
        self.search.set_property("placeholder-text", _("Programme durchsuchen …"))
        self.search.connect("search-changed", self._on_search_changed)
        sidebar.append(self.search)

        filter_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        sources = [_("Alle Quellen"), *(display_text(source.value) for source in SourceKind)]
        self.source_filter = Gtk.DropDown.new_from_strings(sources)
        self.source_filter.set_hexpand(True)
        self.source_filter.set_tooltip_text(_("Nach Installationsquelle filtern"))
        self.source_filter.connect("notify::selected", lambda *_args: self.app_list.invalidate_filter())
        filter_bar.append(self.source_filter)
        folder_button = Gtk.Button(label=_("Ordner prüfen …"))
        folder_button.set_tooltip_text(_("Einen nicht erkannten Programm- oder Spieleordner manuell analysieren"))
        folder_button.connect("clicked", self._choose_folder)
        filter_bar.append(folder_button)
        sidebar.append(filter_bar)

        self.scan_status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.scan_spinner = Gtk.Spinner()
        self.scan_status_label = Gtk.Label(label=_("Programme werden eingelesen …"), xalign=0)
        self.scan_status_label.set_hexpand(True)
        self.scan_status_label.add_css_class("muted")
        self.scan_status.append(self.scan_spinner)
        self.scan_status.append(self.scan_status_label)
        self.scan_status.add_css_class("scan-card")
        sidebar.append(self.scan_status)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self.app_list = Gtk.ListBox()
        self.app_list.add_css_class("app-list")
        self.app_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.app_list.set_filter_func(self._filter_application)
        self.app_list.connect("row-selected", self._on_app_selected)
        placeholder = Gtk.Label(label=_("Keine passenden Programme gefunden"))
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
        title = Gtk.Label(label=_("Programm auswählen"))
        title.add_css_class("empty-title")
        box.append(title)
        note = Gtk.Label(label=_("Restlos erstellt zuerst einen überprüfbaren Löschplan."))
        note.add_css_class("muted")
        box.append(note)
        return box

    def _detail_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page_scroll = Gtk.ScrolledWindow()
        page_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        page_scroll.set_vexpand(True)
        page.append(page_scroll)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        outer.set_margin_top(28)
        outer.set_margin_bottom(18)
        outer.set_margin_start(28)
        outer.set_margin_end(28)
        page_scroll.set_child(outer)

        eyebrow = Gtk.Label(label=_("AUSGEWÄHLTE ANWENDUNG"), xalign=0)
        eyebrow.add_css_class("eyebrow")
        outer.append(eyebrow)

        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        hero.add_css_class("hero-card")
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
        hero_actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        hero_actions.set_valign(Gtk.Align.START)
        self.locations_button = Gtk.Button(label=_("Speicherorte …"))
        self.locations_button.set_tooltip_text(_("Programmdateien und zugehörige Daten vor dem Löschen ansehen"))
        self.locations_button.connect("clicked", self._show_locations)
        hero_actions.append(self.locations_button)
        self.analyze_button = Gtk.Button(label=_("Erneut analysieren"))
        self.analyze_button.connect("clicked", lambda _button: self._analyze_current())
        hero_actions.append(self.analyze_button)
        hero.append(hero_actions)
        outer.append(hero)

        self.warning_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.warning_box.add_css_class("warning-card")
        self.warning_box.set_visible(False)
        outer.append(self.warning_box)

        section = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        section_title = Gtk.Label(label=_("Löschplan"), xalign=0)
        section_title.add_css_class("section-title")
        section_title.set_hexpand(True)
        section.append(section_title)
        self.plan_summary = Gtk.Label(xalign=1)
        self.plan_summary.add_css_class("muted")
        section.append(self.plan_summary)
        outer.append(section)

        stats = Gtk.Grid(column_spacing=12, row_spacing=12)
        stats.set_column_homogeneous(True)
        self.action_stat_value = self._summary_tile(stats, 0, _("PAKETAKTIONEN"))
        self.path_stat_value = self._summary_tile(stats, 1, _("AUSGEWÄHLTE PFADE"))
        self.size_stat_value = self._summary_tile(stats, 2, _("FREIGEGEBENER SPEICHER"))
        outer.append(stats)

        plan_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.action_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.action_card.add_css_class("card")
        plan_box.append(self.action_card)
        self.target_list = Gtk.ListBox()
        self.target_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.target_list.add_css_class("card")
        plan_box.append(self.target_list)
        outer.append(plan_box)

        safety_heading = Gtk.Label(label=_("SICHERHEIT & WIEDERHERSTELLUNG"), xalign=0)
        safety_heading.add_css_class("eyebrow")
        outer.append(safety_heading)

        options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        options.add_css_class("safety-card")
        self.permanent_check = Gtk.CheckButton(label=_("Benutzerdaten endgültig löschen (keine Papierkorb-Wiederherstellung)"))
        self.permanent_check.set_active(False)
        self.permanent_check.connect("toggled", self._permanent_mode_changed)
        options.append(self.permanent_check)
        self.backup_check = Gtk.CheckButton(label=_("Safety Backup vor endgültigem Löschen erstellen"))
        self.backup_check.set_active(True)
        self.backup_check.set_sensitive(False)
        self.backup_check.set_tooltip_text(
            _("Sichert Einstellungen und Spielstände; Cache und Programmdateien werden ausgelassen.")
        )
        options.append(self.backup_check)
        self.process_check = Gtk.CheckButton(label=_("Zugehörige laufende Prozesse automatisch beenden"))
        self.process_check.set_active(True)
        options.append(self.process_check)
        outer.append(options)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bottom.add_css_class("action-bar")
        bottom.set_margin_start(28)
        bottom.set_margin_end(28)
        bottom.set_margin_bottom(14)
        self.delete_note = Gtk.Label(label=_("Vor dem Löschen erscheint eine letzte Zusammenfassung."), xalign=0)
        self.delete_note.set_hexpand(True)
        self.delete_note.add_css_class("muted")
        bottom.append(self.delete_note)
        self.remove_button = Gtk.Button(label=_("Restlos entfernen"))
        self.remove_button.add_css_class("destructive-action")
        self.remove_button.connect("clicked", self._confirm_removal)
        bottom.append(self.remove_button)
        page.append(bottom)
        return page

    @staticmethod
    def _summary_tile(grid: Gtk.Grid, column: int, heading: str) -> Gtk.Label:
        tile = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        tile.add_css_class("stat-tile")
        title = Gtk.Label(label=heading, xalign=0)
        title.add_css_class("stat-heading")
        title.set_wrap(True)
        title.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        title.set_max_width_chars(18)
        tile.append(title)
        value = Gtk.Label(label="—", xalign=0)
        value.add_css_class("stat-value")
        tile.append(value)
        grid.attach(tile, column, 0, 1, 1)
        return value

    def _progress_page(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_size_request(500, -1)
        self.progress_spinner = Gtk.Spinner()
        self.progress_spinner.set_size_request(48, 48)
        box.append(self.progress_spinner)
        self.progress_title = Gtk.Label(label=_("Entfernung wird vorbereitet …"))
        self.progress_title.add_css_class("empty-title")
        self.progress_title.set_wrap(True)
        self.progress_title.set_max_width_chars(58)
        box.append(self.progress_title)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_size_request(480, -1)
        box.append(self.progress_bar)
        note = Gtk.Label(label=_("Dieses Fenster nicht schließen, solange Paketaktionen laufen."))
        note.add_css_class("muted")
        box.append(note)
        return box

    def _load_applications(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.refresh_button.set_sensitive(False)
        self.scan_spinner.start()
        self.scan_status_label.set_text(_("Pakete, Spielebibliotheken, Wine und portable Ordner werden eingelesen …"))

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
            self.scan_status_label.set_text(_("Einlesen fehlgeschlagen: {error}", error=error))
            return False
        self.apps = apps
        _clear_box(self.app_list)
        for app in apps:
            self.app_list.append(ApplicationRow(app))
        self.scan_status_label.set_text(_("{count} Anwendungen erkannt", count=len(apps)))
        self.app_list.invalidate_filter()
        return False

    def _filter_application(self, row: Gtk.ListBoxRow) -> bool:
        if not isinstance(row, ApplicationRow):
            return True
        query = self.search.get_text().strip().casefold()
        app = row.record
        selected_index = self.source_filter.get_selected()
        source_matches = (
            selected_index == 0
            or selected_index > len(SourceKind)
            or app.source == list(SourceKind)[selected_index - 1]
        )
        query_matches = not query or query in f"{app.name} {app.package_id} {app.source.value}".casefold()
        return source_matches and query_matches

    def _on_search_changed(self, _entry: Gtk.SearchEntry) -> None:
        self.app_list.invalidate_filter()

    def _choose_folder(self, _button: Gtk.Button) -> None:
        if hasattr(Gtk, "FileDialog"):
            dialog = Gtk.FileDialog(title=_("Programm- oder Spieleordner auswählen"))
            dialog.select_folder(self, None, self._folder_selected)
            return
        dialog = Gtk.FileChooserNative(
            title=_("Programm- oder Spieleordner auswählen"),
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            accept_label=_("Auswählen"),
            cancel_label=_("Abbrechen"),
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
            self.scan_status_label.set_text(_("Dieser Ordner ist nicht als lokaler Pfad verfügbar."))
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
            description=_("Manuell ausgewählter Ordner; Inhalt und Größe werden vor dem Entfernen angezeigt"),
            icon="folder-symbolic",
            scope=_("Manuelle Auswahl"),
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
            self.scan_status_label.set_text(
                _("{count} Anwendungen erkannt · manueller Ordner hinzugefügt", count=len(self.apps))
            )
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
        self.detail_description.set_text(display_text(app.description) or _("Keine Beschreibung verfügbar"))
        self.detail_source.set_text(f"{display_text(app.source.value)} · {display_text(app.scope)}")
        self.detail_id.set_text(app.package_id)
        self.detail_stack.set_visible_child_name("detail")

    def _analyze_current(self) -> None:
        if self.current_app is None or self.busy:
            return
        self.busy = True
        self.analyze_button.set_sensitive(False)
        self.locations_button.set_sensitive(False)
        self.remove_button.set_sensitive(False)
        self.current_plan = None
        _clear_box(self.target_list)
        _clear_box(self.action_card)
        self.warning_box.set_visible(False)
        self.plan_summary.set_text(_("Analyse läuft …"))
        self.action_stat_value.set_text("—")
        self.path_stat_value.set_text("—")
        self.size_stat_value.set_text("—")
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
        self.locations_button.set_sensitive(True)
        if error or plan is None:
            self.plan_summary.set_text(
                _("Analyse fehlgeschlagen: {error}", error=error or _("unbekannter Fehler"))
            )
            return False
        if self.current_app is None or plan.app.key != self.current_app.key:
            return False
        self.current_plan = plan
        self.current_app = plan.app
        self._show_app_header(plan.app)
        _clear_box(self.action_card)
        _clear_box(self.target_list)
        _clear_box(self.warning_box)

        if plan.actions:
            action_title = Gtk.Label(label=_("Paketverwaltung"), xalign=0)
            action_title.add_css_class("section-title")
            self.action_card.append(action_title)
            for action in plan.actions:
                line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                icon = Gtk.Image.new_from_icon_name("system-software-install-symbolic")
                line.append(icon)
                label = Gtk.Label(label=display_text(action.label), xalign=0)
                label.set_wrap(True)
                line.append(label)
                self.action_card.append(line)
            self.action_card.set_visible(True)
        else:
            self.action_card.set_visible(False)

        for target in plan.targets:
            self.target_list.append(TargetRow(target, self._update_plan_summary, self._open_folder))
        if not plan.targets:
            label = Gtk.Label(label=_("Keine zusätzlichen Benutzerdaten gefunden"))
            label.set_margin_top(18)
            label.set_margin_bottom(18)
            label.add_css_class("muted")
            self.target_list.append(label)

        warnings = [*plan.warnings, *([plan.safety_error] if plan.safety_error else [])]
        for warning in warnings:
            line = Gtk.Label(label=f"⚠ {display_text(warning)}", xalign=0)
            line.set_wrap(True)
            self.warning_box.append(line)
        self.warning_box.set_visible(bool(warnings))
        self._update_plan_summary()
        return False

    def _open_folder(self, path: Path, parent: Gtk.Window | None = None) -> None:
        try:
            folder = folder_for_path(path)
            # Select a directory handler explicitly. Never launch the target
            # file's MIME handler (it might be an executable or .desktop file).
            manager = Gio.AppInfo.get_default_for_type("inode/directory", False)
            if manager is None:
                raise OSError(_("Es ist kein Dateimanager für Ordner eingerichtet."))
            if not manager.launch([Gio.File.new_for_path(str(folder))], None):
                raise OSError(_("Der Dateimanager konnte nicht gestartet werden."))
        except (OSError, ValueError, RuntimeError, GLib.Error) as error:
            dialog = Gtk.MessageDialog(
                transient_for=parent or self,
                modal=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CLOSE,
                text=_("Ordner konnte nicht geöffnet werden"),
            )
            dialog.set_property("secondary-text", _("Pfad: {path}\n\n{error}", path=path, error=error))
            dialog.connect("response", lambda item, _response: item.destroy())
            dialog.present()

    def _show_locations(self, _button: Gtk.Button) -> None:
        if self.current_app is None or self.busy:
            return
        if self._locations_dialog is not None:
            self._locations_dialog.present()
            return
        app = self.current_app
        plan = self.current_plan
        dialog = Gtk.Dialog(title=_("Speicherorte – {name}", name=app.name), transient_for=self, modal=True)
        dialog.set_default_size(800, 560)
        dialog.add_button(_("Schließen"), Gtk.ResponseType.CLOSE)
        dialog.connect("response", self._close_locations)
        dialog.connect("close-request", self._locations_close_requested)
        self._locations_dialog = dialog
        content = dialog.get_content_area()
        content.set_spacing(12)
        for edge in ("top", "bottom", "start", "end"):
            getattr(content, f"set_margin_{edge}")(16)
        note = Gtk.Label(
            label=_("Programme können mehrere Speicherorte haben. Geöffnet wird nur der Ordner, niemals die Programmdatei. Die Lösch-Auswahl bleibt unverändert. Gemeinsame Systemordner können auch Dateien anderer Programme enthalten."),
            xalign=0,
        )
        note.set_wrap(True)
        content.append(note)
        status = Gtk.Label(label=_("Speicherorte werden ermittelt …"), xalign=0)
        status.set_wrap(True)
        status.add_css_class("muted")
        content.append(status)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        locations = Gtk.ListBox()
        locations.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.set_child(locations)
        content.append(scroll)
        dialog.present()

        def worker() -> None:
            try:
                result = LocationResolver().inspect(app, plan)
                GLib.idle_add(self._locations_loaded, dialog, locations, status, result, None)
            except Exception as error:
                GLib.idle_add(self._locations_loaded, dialog, locations, status, None, str(error))

        threading.Thread(target=worker, daemon=True).start()

    def _close_locations(self, dialog: Gtk.Dialog, _response: int) -> None:
        if self._locations_dialog is dialog:
            self._locations_dialog = None
        dialog.destroy()

    def _locations_close_requested(self, dialog: Gtk.Dialog) -> bool:
        self._close_locations(dialog, Gtk.ResponseType.CLOSE)
        return True

    def _locations_loaded(
        self, dialog: Gtk.Dialog, locations: Gtk.ListBox, status: Gtk.Label,
        result: LocationResult | None, error: str | None,
    ) -> bool:
        if self._locations_dialog is not dialog:
            return False
        if error or result is None:
            status.set_text(_("Speicherorte konnten nicht ermittelt werden: {error}", error=error or _("unbekannter Fehler")))
            return False
        summary = (_("{count} Speicherort(e) gefunden", count=len(result.locations)) if result.locations
                   else _("Keine vorhandenen lokalen Speicherorte gefunden."))
        status.set_text("\n".join([summary, *result.warnings]))
        for location in result.locations:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.add_css_class("target-row")
            labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            labels.set_hexpand(True)
            path = Gtk.Label(label=str(location.path), xalign=0)
            path.set_selectable(True)
            path.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            path.set_tooltip_text(str(location.path))
            labels.append(path)
            reason = Gtk.Label(label=display_text(location.reason), xalign=0)
            reason.set_wrap(True)
            reason.add_css_class("muted")
            labels.append(reason)
            row.append(labels)
            button = Gtk.Button(label=_("Ordner öffnen"))
            button.set_valign(Gtk.Align.CENTER)
            button.connect("clicked", lambda _button, value=location.path: self._open_folder(value, dialog))
            row.append(button)
            locations.append(row)
        return False

    def _update_plan_summary(self) -> None:
        if self.current_plan is None:
            self.remove_button.set_sensitive(False)
            return
        count = len(self.current_plan.selected_targets)
        action_count = len(self.current_plan.actions)
        self.plan_summary.set_text(_("Auswahl vor dem Entfernen prüfen"))
        self.action_stat_value.set_text(str(action_count))
        self.path_stat_value.set_text(str(count))
        self.size_stat_value.set_text(format_size(self.current_plan.total_size))
        self.remove_button.set_sensitive(
            bool(action_count or count) and not self.busy
            and self.current_plan.snapshot is not None and not self.current_plan.safety_error
        )

    def _permanent_mode_changed(self, check: Gtk.CheckButton) -> None:
        self.backup_check.set_sensitive(check.get_active())

    def _confirm_removal(self, _button: Gtk.Button) -> None:
        plan = self.current_plan
        if plan is None or self.busy or plan.safety_error or plan.snapshot is None:
            return
        permanent = self.permanent_check.get_active()
        create_backup = permanent and self.backup_check.get_active()
        backup_targets = BackupManager().candidates(plan.selected_targets) if create_backup else []
        processes = RemovalExecutor().related_processes(plan)
        process_note = ""
        if processes:
            names = ", ".join(f"{name} (PID {pid})" for pid, name in processes[:5])
            process_note = _("\n\nLaufende Prozesse: {names}", names=names)
        mode = _("dauerhaft gelöscht") if permanent else _("wiederherstellbar in den Papierkorb verschoben")
        recovery_note = ""
        if not permanent and plan.actions:
            recovery_note = (
                "\n\n" + _(
                    "Hinweis: Paket-Deinstallationen und Änderungen an Launcher-Bibliotheken sind nicht automatisch "
                    "wiederherstellbar; nur die ausgewählten Dateipfade werden in den Papierkorb verschoben."
                )
            )
        backup_note = ""
        if create_backup:
            backup_note = _(
                "\n\nSafety Backup: {count} geeignete Datenpfade mit {size} werden vor der Entfernung gesichert.",
                count=len(backup_targets),
                size=format_size(sum(target.size for target in backup_targets)),
            )
        secondary = (
            _(
                "{actions} Paketaktion(en) und {paths} ausgewählte Pfade mit {size} werden verarbeitet. "
                "Benutzerdaten werden {mode}.",
                actions=len(plan.actions),
                paths=len(plan.selected_targets),
                size=format_size(plan.total_size),
                mode=mode,
            )
            + backup_note + recovery_note + process_note
        )
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text=_("„{name}“ wirklich restlos entfernen?", name=plan.app.name),
            secondary_text=secondary,
        )
        dialog.add_button(_("Abbrechen"), Gtk.ResponseType.CANCEL)
        confirm = dialog.add_button(_("Endgültig entfernen") if permanent else _("Entfernen"), Gtk.ResponseType.ACCEPT)
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
        create_backup = permanent and self.backup_check.get_active()
        self.detail_stack.set_visible_child_name("progress")
        self.progress_spinner.start()
        self.progress_bar.set_fraction(0.0)
        self.progress_title.set_text(_("„{name}“ wird entfernt …", name=plan.app.name))

        def update(message: str, fraction: float) -> None:
            GLib.idle_add(self._set_progress, message, fraction)

        def worker() -> None:
            executor = RemovalExecutor()
            result = executor.execute(
                plan,
                permanent=permanent,
                stop_processes=stop_processes,
                create_backup=create_backup,
                progress=update,
            )
            GLib.idle_add(self._removal_finished, plan, result)

        threading.Thread(target=worker, daemon=True).start()

    def _set_progress(self, message: str, fraction: float) -> bool:
        self.progress_title.set_text(display_text(message))
        self.progress_bar.set_fraction(max(0.0, min(fraction, 1.0)))
        return False

    def _removal_finished(self, plan: RemovalPlan, result: RemovalResult) -> bool:
        self.busy = False
        self.progress_spinner.stop()
        self.progress_bar.set_fraction(1.0)
        if result.success:
            title = (
                _("„{name}“ wurde entfernt", name=plan.app.name)
                if not result.residual_paths
                else _("„{name}“ wurde entfernt – Restdaten gefunden", name=plan.app.name)
            )
            detail_parts = [_('{count} Pfade wurden verarbeitet.', count=len(result.removed_paths))]
            if result.recovery_items:
                detail_parts.append(
                    _(
                        "{count} Pfade können im Wiederherstellungszentrum zurückgeholt werden.",
                        count=len(result.recovery_items),
                    )
                )
            if result.backup_items:
                detail_parts.append(
                    _(
                        "Safety Backup: {count} Datenpfade wurden vor dem Löschen gesichert.",
                        count=len(result.backup_items),
                    )
                )
            if result.residual_paths:
                preview = "\n".join(result.residual_paths[:6])
                suffix = "\n…" if len(result.residual_paths) > 6 else ""
                detail_parts.append(
                    _(
                        "Der Kontrollscan fand {count} weitere mögliche Restpfade:\n{preview}{suffix}",
                        count=len(result.residual_paths),
                        preview=preview,
                        suffix=suffix,
                    )
                )
            elif result.verification_error:
                detail_parts.append(
                    _(
                        "Der Kontrollscan konnte nicht abgeschlossen werden: {error}",
                        error=result.verification_error,
                    )
                )
            else:
                detail_parts.append(_("Kontrollscan: keine weiteren zuordenbaren Restpfade gefunden."))
            if result.kept_paths:
                detail_parts.append(
                    _(
                        "{count} nicht ausgewählte Pfade wurden wie gewünscht beibehalten.",
                        count=len(result.kept_paths),
                    )
                )
            detail_parts.append(
                _(
                    "Protokoll: {path}",
                    path=result.receipt_path or _("konnte nicht geschrieben werden"),
                )
            )
            details = "\n\n".join(detail_parts)
            message_type = Gtk.MessageType.WARNING if result.residual_paths else Gtk.MessageType.INFO
        else:
            title = _("Neue Analyse erforderlich") if result.review_required else _("Entfernung nicht vollständig")
            detail_parts = [
                "\n".join(display_text(error) for error in result.errors[:8])
                or _("Ein unbekannter Fehler ist aufgetreten.")
            ]
            if result.recovery_items:
                detail_parts.append(
                    _(
                        "{count} bereits verschobene Pfade sind im Wiederherstellungszentrum verfügbar.",
                        count=len(result.recovery_items),
                    )
                )
            if result.backup_items:
                detail_parts.append(
                    _(
                        "Das Safety Backup mit {count} Datenpfaden ist im Wiederherstellungszentrum verfügbar.",
                        count=len(result.backup_items),
                    )
                )
            details = "\n\n".join(detail_parts)
            message_type = Gtk.MessageType.ERROR
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=message_type,
            buttons=Gtk.ButtonsType.NONE,
            text=title,
            secondary_text=details,
        )
        dialog.add_button(_("Schließen"), Gtk.ResponseType.CLOSE)
        if result.review_required:
            self.current_plan = None
            self.remove_button.set_sensitive(False)
            self.plan_summary.set_text(_("Löschplan ungültig – bitte erneut analysieren"))
            dialog.add_button(_("Erneut analysieren"), Gtk.ResponseType.APPLY)
        if result.recovery_items or result.backup_items:
            dialog.add_button(_("Wiederherstellungszentrum"), Gtk.ResponseType.HELP)
        dialog.connect("response", self._after_result_dialog, result)
        dialog.present()
        return False

    def _after_result_dialog(self, dialog: Gtk.MessageDialog, response: int, result: RemovalResult) -> None:
        dialog.destroy()
        if result.success:
            self.current_app = None
            self.current_plan = None
            self.detail_stack.set_visible_child_name("empty")
            self._load_applications()
        else:
            self.detail_stack.set_visible_child_name("detail")
            self._update_plan_summary()
            if result.review_required and response == Gtk.ResponseType.APPLY:
                self._analyze_current()
        if response == Gtk.ResponseType.HELP:
            self.show_recovery_center()

    def show_recovery_center(self) -> None:
        if self._recovery_dialog is not None:
            self._recovery_dialog.present()
            return
        dialog = Gtk.Dialog(
            transient_for=self,
            modal=True,
            title=_("Restlos-Wiederherstellungszentrum"),
        )
        dialog.set_default_size(760, 520)
        dialog.add_button(_("Schließen"), Gtk.ResponseType.CLOSE)
        dialog.connect("response", self._close_recovery_center)
        content = dialog.get_content_area()
        content.set_spacing(14)
        content.set_margin_top(20)
        content.set_margin_bottom(16)
        content.set_margin_start(20)
        content.set_margin_end(20)

        title = Gtk.Label(label=_("Wiederherstellbare Benutzerdaten und Safety Backups"), xalign=0)
        title.add_css_class("hero-title")
        content.append(title)
        note = Gtk.Label(
            label=_(
                "Hier kannst du Papierkorbdaten und Safety Backups an ihren ursprünglichen Ort zurückholen. "
                "Paket-Deinstallationen und Änderungen an Spielebibliotheken werden dabei nicht rückgängig gemacht."
            ),
            xalign=0,
        )
        note.set_wrap(True)
        note.add_css_class("muted")
        content.append(note)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        record_list = Gtk.ListBox()
        record_list.set_selection_mode(Gtk.SelectionMode.NONE)
        record_list.add_css_class("card")
        loading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        loading.set_halign(Gtk.Align.CENTER)
        loading.set_margin_top(36)
        loading.set_margin_bottom(36)
        spinner = Gtk.Spinner()
        spinner.start()
        loading.append(spinner)
        loading.append(Gtk.Label(label=_("Papierkorb, Safety Backups und Restlos-Protokolle werden geprüft …")))
        record_list.append(loading)
        scroll.set_child(record_list)
        content.append(scroll)
        self._recovery_dialog = dialog
        dialog.present()

        def worker() -> None:
            try:
                records = RecoveryManager().list_records()
                GLib.idle_add(self._recovery_records_loaded, dialog, record_list, records, None)
            except Exception as error:  # defensive boundary for the GUI worker
                GLib.idle_add(self._recovery_records_loaded, dialog, record_list, [], str(error))

        threading.Thread(target=worker, daemon=True).start()

    def _recovery_records_loaded(
        self,
        dialog: Gtk.Dialog,
        record_list: Gtk.ListBox,
        records: list[RecoveryRecord],
        error: str | None,
    ) -> bool:
        if self._recovery_dialog is not dialog:
            return False
        _clear_box(record_list)
        if error:
            empty_text = _("Wiederherstellungsdaten konnten nicht gelesen werden: {error}", error=error)
        elif not records:
            empty_text = _("Keine wiederherstellbaren Restlos-Vorgänge gefunden.")
        else:
            empty_text = ""
            for record in records:
                record_list.append(self._recovery_row(record, dialog))
        if empty_text:
            empty = Gtk.Label(label=empty_text)
            empty.set_wrap(True)
            empty.set_margin_top(36)
            empty.set_margin_bottom(36)
            empty.set_margin_start(12)
            empty.set_margin_end(12)
            empty.add_css_class("muted")
            record_list.append(empty)
        return False

    def _recovery_row(self, record: RecoveryRecord, parent: Gtk.Dialog) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.add_css_class("target-row")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(8)
        box.set_margin_end(8)

        icon = Gtk.Image.new_from_icon_name("edit-undo-symbolic")
        icon.set_pixel_size(34)
        box.append(icon)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        labels.set_hexpand(True)
        name = Gtk.Label(label=record.app_name, xalign=0)
        name.add_css_class("app-name")
        labels.append(name)
        timestamp = record.timestamp.replace("T", " ").replace("Z", " UTC")
        details = Gtk.Label(
            label=(
                _(
                    "{timestamp} · {count} Pfad(e) · {size} · {source}",
                    timestamp=timestamp,
                    count=len(record.available_items),
                    size=format_size(record.available_size),
                    source=display_text(record.source),
                )
            ),
            xalign=0,
        )
        details.add_css_class("muted")
        labels.append(details)
        if record.actions:
            action_note = Gtk.Label(
                label=_("Paket- oder Bibliotheksaktionen müssen bei Bedarf separat rückgängig gemacht werden."),
                xalign=0,
            )
            action_note.set_wrap(True)
            action_note.add_css_class("muted")
            labels.append(action_note)
        box.append(labels)
        restore = Gtk.Button(label=_("Wiederherstellen"))
        restore.set_valign(Gtk.Align.CENTER)
        restore.add_css_class("suggested-action")
        restore.connect("clicked", self._confirm_restore, record, parent)
        box.append(restore)
        row.set_child(box)
        return row

    def _close_recovery_center(self, dialog: Gtk.Dialog, _response: int) -> None:
        dialog.destroy()
        if self._recovery_dialog is dialog:
            self._recovery_dialog = None

    def _confirm_restore(
        self,
        _button: Gtk.Button,
        record: RecoveryRecord,
        center: Gtk.Dialog,
    ) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=center,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=_("Daten von „{name}“ wiederherstellen?", name=record.app_name),
            secondary_text=_(
                "{count} Pfad(e) mit {size} werden an ihre ursprünglichen Orte zurückgeholt. Vorhandene Dateien "
                "werden nicht überschrieben. Ein deinstalliertes Programmpaket wird dadurch nicht erneut installiert.",
                count=len(record.available_items),
                size=format_size(record.available_size),
            ),
        )
        dialog.add_button(_("Abbrechen"), Gtk.ResponseType.CANCEL)
        confirm = dialog.add_button(_("Wiederherstellen"), Gtk.ResponseType.ACCEPT)
        confirm.add_css_class("suggested-action")
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        dialog.connect("response", self._on_restore_confirmed, record.recovery_id, center)
        dialog.present()

    def _on_restore_confirmed(
        self,
        dialog: Gtk.MessageDialog,
        response: int,
        recovery_id: str,
        center: Gtk.Dialog,
    ) -> None:
        dialog.destroy()
        if response != Gtk.ResponseType.ACCEPT:
            return
        self._close_recovery_center(center, Gtk.ResponseType.CLOSE)
        progress = Gtk.Dialog(
            transient_for=self,
            modal=True,
            title=_("Daten wiederherstellen"),
        )
        progress.set_deletable(False)
        area = progress.get_content_area()
        area.set_spacing(14)
        area.set_margin_top(24)
        area.set_margin_bottom(24)
        area.set_margin_start(28)
        area.set_margin_end(28)
        spinner = Gtk.Spinner()
        spinner.set_size_request(42, 42)
        spinner.set_halign(Gtk.Align.CENTER)
        spinner.start()
        area.append(spinner)
        status = Gtk.Label(label=_("Daten werden an ihre ursprünglichen Orte zurückgeholt …"))
        status.set_wrap(True)
        area.append(status)
        progress.present()

        def worker() -> None:
            result = RecoveryManager().restore(recovery_id)
            GLib.idle_add(self._restore_finished, progress, result)

        threading.Thread(target=worker, daemon=True).start()

    def _restore_finished(self, progress: Gtk.Dialog, result: RestoreResult) -> bool:
        progress.destroy()
        if result.success:
            title = _("Wiederherstellung abgeschlossen")
            details = (
                _(
                    "{count} Pfad(e) wurden zurückgeholt. Falls das Programmpaket entfernt wurde, muss es separat "
                    "neu installiert werden.",
                    count=len(result.restored_paths),
                )
            )
            message_type = Gtk.MessageType.INFO
        else:
            title = _("Wiederherstellung nicht vollständig")
            restored = (
                _(
                    "{count} Pfad(e) wurden bereits wiederhergestellt.\n\n",
                    count=len(result.restored_paths),
                )
                if result.restored_paths
                else ""
            )
            details = restored + (
                "\n".join(display_text(error) for error in result.errors[:8])
                or _("Ein unbekannter Fehler ist aufgetreten.")
            )
            message_type = Gtk.MessageType.ERROR
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=message_type,
            buttons=Gtk.ButtonsType.CLOSE,
            text=title,
            secondary_text=details,
        )
        dialog.connect("response", lambda item, _response: item.destroy())
        dialog.present()
        if not self.busy:
            self._load_applications()
        return False


class RestlosApplication(Gtk.Application):
    def __init__(self) -> None:
        # DEFAULT_FLAGS was only named in GLib 2.74; zero also supports 2.72.
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags(0))
        self.update_state = UpdateState()
        self._update_check_running = False
        self._update_install_running = False
        self._update_progress_dialog: Gtk.Dialog | None = None
        self._update_progress_label: Gtk.Label | None = None
        self._update_progress_bar: Gtk.ProgressBar | None = None
        self.connect("activate", self._activate)
        self._add_actions()

    def _activate(self, _application: Gtk.Application) -> None:
        window = self.props.active_window
        if window is None:
            window = MainWindow(self)
        window.present()
        self._start_update_check(automatic=True)

    def _add_actions(self) -> None:
        for name, callback in (
            ("about", self._show_about),
            ("recovery", self._show_recovery_center),
            ("open-history", self._open_history),
            ("check-updates", self._check_updates_manually),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        automatic = Gio.SimpleAction.new_stateful(
            "automatic-updates",
            None,
            GLib.Variant.new_boolean(self.update_state.automatic_checks_enabled()),
        )
        automatic.connect("change-state", self._change_automatic_updates)
        self.add_action(automatic)
        language = Gio.SimpleAction.new_stateful(
            "language",
            GLib.VariantType.new("s"),
            GLib.Variant.new_string(LanguageSettings().selected()),
        )
        language.connect("change-state", self._change_language)
        self.add_action(language)

    def _show_about(self, _action, _parameter) -> None:
        dialog = Gtk.AboutDialog(
            transient_for=self.props.active_window,
            modal=True,
            program_name=APP_NAME,
            version=__version__,
            comments=APP_TAGLINE,
            copyright=_("2026 – lokale Open-Source-Ausgabe"),
            license_type=Gtk.License.MIT_X11,
        )
        dialog.set_website(PROJECT_URL)
        dialog.set_website_label(_("Projektseite auf GitHub"))
        dialog.present()

    def _show_recovery_center(self, _action, _parameter) -> None:
        window = self.props.active_window
        if isinstance(window, MainWindow):
            window.show_recovery_center()

    def _open_history(self, _action, _parameter) -> None:
        path = Path.home() / ".local/state/restlos/history"
        path.mkdir(parents=True, exist_ok=True)
        Gio.AppInfo.launch_default_for_uri(path.as_uri(), None)

    def _check_updates_manually(self, _action, _parameter) -> None:
        self._start_update_check(automatic=False)

    def _change_automatic_updates(self, action: Gio.SimpleAction, value: GLib.Variant) -> None:
        enabled = value.get_boolean()
        self.update_state.set_automatic_checks(enabled)
        action.set_state(value)
        if enabled:
            self._start_update_check(automatic=False)

    def _change_language(self, action: Gio.SimpleAction, value: GLib.Variant) -> None:
        selected = value.get_string()
        try:
            LanguageSettings().set(selected)
        except (OSError, ValueError) as error:
            self._show_message(_("Sprache konnte nicht gespeichert werden"), str(error), Gtk.MessageType.ERROR)
            return
        action.set_state(value)
        self._show_message(
            _("Sprache gespeichert"),
            _("Starte Restlos Uninstaller neu, damit die neue Sprache vollständig verwendet wird."),
            Gtk.MessageType.INFO,
        )

    def _start_update_check(self, *, automatic: bool) -> None:
        if self._update_check_running or self._update_install_running:
            return
        if automatic and not self.update_state.is_due():
            return
        self._update_check_running = True
        action = self.lookup_action("check-updates")
        if action is not None:
            action.set_enabled(False)

        def worker() -> None:
            try:
                release = UpdateClient(__version__).check()
                self.update_state.record_attempt(True)
                GLib.idle_add(self._update_check_finished, release, None, automatic)
            except UpdateError as error:
                self.update_state.record_attempt(False)
                GLib.idle_add(self._update_check_finished, None, str(error), automatic)
            except Exception as error:  # defensive boundary for the background worker
                self.update_state.record_attempt(False)
                GLib.idle_add(self._update_check_finished, None, str(error), automatic)

        threading.Thread(target=worker, daemon=True).start()

    def _update_check_finished(
        self,
        release: ReleaseInfo | None,
        error: str | None,
        automatic: bool,
    ) -> bool:
        self._update_check_running = False
        action = self.lookup_action("check-updates")
        if action is not None:
            action.set_enabled(True)
        if error:
            if not automatic:
                self._show_message(
                    _("Update-Suche fehlgeschlagen"),
                    display_text(error),
                    Gtk.MessageType.ERROR,
                )
            return False
        if release is None:
            if not automatic:
                self._show_message(
                    _("Restlos Uninstaller ist aktuell"),
                    _("Version {version} ist die neueste verfügbare Ausgabe.", version=__version__),
                    Gtk.MessageType.INFO,
                )
            return False
        self._show_update_available(release)
        return False

    def _show_update_available(self, release: ReleaseInfo) -> None:
        notes = release.notes.strip()
        if len(notes) > 1400:
            notes = notes[:1397].rstrip() + " …"
        system_managed = is_system_managed_install()
        update_note = (
            _(
                "Diese Installation wird vom Linux-Paketmanager verwaltet. Öffne die Release-Seite, "
                "um das neue Systempaket zu beziehen."
            )
            if system_managed
            else _(
                "Das Update wird nur nach deiner Bestätigung geladen, per SHA-256 geprüft und atomar installiert."
            )
        )
        details = (
            _("Installiert: {version}", version=__version__) + "\n"
            + _("Verfügbar: {version}", version=release.version) + "\n\n"
            + (notes or _("Änderungen stehen auf der Release-Seite.")) + "\n\n"
            + update_note
        )
        dialog = Gtk.MessageDialog(
            transient_for=self.props.active_window,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.NONE,
            text=_("Restlos Uninstaller {version} ist verfügbar", version=release.version),
            secondary_text=details,
        )
        dialog.add_button(_("Später"), Gtk.ResponseType.CANCEL)
        release_page = dialog.add_button(_("Release-Seite"), Gtk.ResponseType.HELP)
        if system_managed:
            release_page.add_css_class("suggested-action")
            dialog.set_default_response(Gtk.ResponseType.HELP)
        else:
            install = dialog.add_button(_("Herunterladen und installieren"), Gtk.ResponseType.ACCEPT)
            install.add_css_class("suggested-action")
            dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        dialog.connect("response", self._on_update_response, release)
        dialog.present()

    def _on_update_response(self, dialog: Gtk.MessageDialog, response: int, release: ReleaseInfo) -> None:
        dialog.destroy()
        if response == Gtk.ResponseType.HELP:
            Gio.AppInfo.launch_default_for_uri(release.page_url, None)
        elif response == Gtk.ResponseType.ACCEPT:
            self._install_update(release)

    def _install_update(self, release: ReleaseInfo) -> None:
        if self._update_install_running:
            return
        self._update_install_running = True
        action = self.lookup_action("check-updates")
        if action is not None:
            action.set_enabled(False)

        dialog = Gtk.Dialog(
            transient_for=self.props.active_window,
            modal=True,
            title=_("Restlos Uninstaller {version} installieren", version=release.version),
        )
        dialog.set_deletable(False)
        content = dialog.get_content_area()
        content.set_spacing(14)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(26)
        content.set_margin_end(26)
        spinner = Gtk.Spinner()
        spinner.set_size_request(42, 42)
        spinner.set_halign(Gtk.Align.CENTER)
        spinner.start()
        content.append(spinner)
        label = Gtk.Label(label=_("Update wird vorbereitet …"))
        label.set_wrap(True)
        label.set_max_width_chars(58)
        content.append(label)
        progress_bar = Gtk.ProgressBar()
        progress_bar.set_size_request(460, -1)
        content.append(progress_bar)
        note = Gtk.Label(label=_("Der aktuelle Restlos Uninstaller bleibt bei einem Fehler weiterhin startfähig."))
        note.add_css_class("muted")
        content.append(note)
        self._update_progress_dialog = dialog
        self._update_progress_label = label
        self._update_progress_bar = progress_bar
        self.hold()
        dialog.present()

        def progress(message: str, fraction: float) -> None:
            GLib.idle_add(self._set_update_progress, message, fraction)

        def worker() -> None:
            try:
                result = UpdateClient(__version__).install(release, progress=progress)
                GLib.idle_add(self._update_install_finished, result.version, None)
            except UpdateError as error:
                GLib.idle_add(self._update_install_finished, None, str(error))
            except Exception as error:  # defensive boundary for the background worker
                GLib.idle_add(self._update_install_finished, None, str(error))

        threading.Thread(target=worker, daemon=True).start()

    def _set_update_progress(self, message: str, fraction: float) -> bool:
        if self._update_progress_label is not None:
            self._update_progress_label.set_text(display_text(message))
        if self._update_progress_bar is not None:
            self._update_progress_bar.set_fraction(max(0.0, min(fraction, 1.0)))
        return False

    def _update_install_finished(self, version: str | None, error: str | None) -> bool:
        self._update_install_running = False
        action = self.lookup_action("check-updates")
        if action is not None:
            action.set_enabled(True)
        if self._update_progress_dialog is not None:
            self._update_progress_dialog.destroy()
        self._update_progress_dialog = None
        self._update_progress_label = None
        self._update_progress_bar = None
        self.release()
        if error or version is None:
            self._show_message(
                _("Update nicht installiert"),
                display_text(error) if error else _("Ein unbekannter Fehler ist aufgetreten."),
                Gtk.MessageType.ERROR,
            )
            return False

        dialog = Gtk.MessageDialog(
            transient_for=self.props.active_window,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.NONE,
            text=_("Restlos Uninstaller {version} wurde installiert", version=version),
            secondary_text=_(
                "Einstellungen und Entfernungshistorie wurden beibehalten. Starte Restlos Uninstaller jetzt neu, "
                "damit die neue Version aktiv wird."
            ),
        )
        dialog.add_button(_("Später neu starten"), Gtk.ResponseType.CLOSE)
        restart = dialog.add_button(_("Jetzt neu starten"), Gtk.ResponseType.ACCEPT)
        restart.add_css_class("suggested-action")
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        dialog.connect("response", self._on_restart_response)
        dialog.present()
        return False

    def _on_restart_response(self, dialog: Gtk.MessageDialog, response: int) -> None:
        dialog.destroy()
        if response != Gtk.ResponseType.ACCEPT:
            return
        command = Path.home() / ".local/bin/restlos"
        try:
            os.execv(str(command), (str(command),))
        except OSError as error:
            self._show_message(
                _("Neustart fehlgeschlagen"),
                _("Starte Restlos Uninstaller manuell neu. Technisches Detail: {error}", error=error),
                Gtk.MessageType.ERROR,
            )

    def _show_message(self, title: str, details: str, message_type: Gtk.MessageType) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self.props.active_window,
            modal=True,
            message_type=message_type,
            buttons=Gtk.ButtonsType.CLOSE,
            text=title,
            secondary_text=details,
        )
        dialog.connect("response", lambda item, _response: item.destroy())
        dialog.present()


def run_gui() -> int:
    Gtk.init()
    display = Gdk.Display.get_default()
    if display is None:
        print(_("Keine grafische Sitzung gefunden. Verwende `restlos list` oder `restlos analyze NAME`."))
        return 1
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_display(
        display,
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    return RestlosApplication().run(None)
