"""Small dependency-free German/English message catalog and language settings."""

from __future__ import annotations

import json
import locale
import os
import tempfile
from pathlib import Path
from typing import Any


SUPPORTED_LANGUAGES = {"system", "de", "en"}


ENGLISH: dict[str, str] = {
    "Die Einhängepunkte konnten nicht zuverlässig geprüft werden.": "Mount points could not be checked reliably.",
    "Die Einhängepunkte wurden während der Prüfung verändert.": "Mount points changed during the safety check.",
    "Geschützt – wer braucht diese Daten noch?": "Protected – who else needs this data?",
    "Geschützt": "Protected",
    "{name} ({source})\n{evidence}: {path}": "{name} ({source})\n{evidence}: {path}",
    "  GESCHÜTZT: {name} ({source}) – {evidence}: {path}": "  PROTECTED: {name} ({source}) – {evidence}: {path}",
    "  GESPERRT: {error}": "  BLOCKED: {error}",
    "Programmstarter": "Application launcher",
    "Installationsordner laut Programmeintrag": "Installation directory from application record",
    "Wine-Präfix laut Programmeintrag": "Wine prefix from application record",
    "Programmdatei laut Programmeintrag": "Executable from application record",
    "Gemeinsames Standard-Wine-Präfix": "Shared default Wine prefix",
    "Pfad laut Spielebibliothek": "Path from game library",
    "Datenpfad mit identischer Paketkennung": "Data path with identical package ID",
    "Lutris-Wine-Präfix laut Spielkonfiguration": "Lutris Wine prefix from game configuration",
    "Gemeinsam referenzierte Pfade sind gesperrt. Die betroffenen Anwendungen und Nachweise stehen am jeweiligen Pfad.": "Shared paths are protected. The affected applications and references are listed next to each path.",
    "Die Paketaktion könnte gemeinsam genutzte Daten mitentfernen und wurde deshalb gesperrt.": "The package operation could also remove shared data and has therefore been blocked.",
    "Die Schutzprüfung berücksichtigt bekannte Programmeinträge, keine unbekannten oder nicht lesbaren Installationen.": "The protection check covers known application records, not unknown or unreadable installations.",
    "Der Paketbestand konnte nicht zuverlässig geprüft werden.": "The installed package state could not be checked reliably.",
    "Ungültiger Pfad im Löschplan.": "Invalid path in the removal plan.",
    "Dateien wurden während der Sicherheitsprüfung verändert.": "Files changed during the safety check.",
    "Die Sicherheitsprüfung ist zu groß oder dauert zu lange; es wurde keine Freigabe erteilt.": "The safety check is too large or takes too long; removal has not been approved.",
    "Spezialdateien im Löschziel können nicht sicher geprüft werden.": "Special files in the removal target cannot be checked safely.",
    "Eingehängte Laufwerke im Löschziel werden nicht entfernt.": "Mounted filesystems inside the removal target will not be removed.",
    "Ein übergeordneter Ordner wurde während der Prüfung verändert.": "A parent directory changed during the check.",
    "Der Löschplan wurde verändert. Bitte erneut analysieren und bestätigen.": "The removal plan changed. Please analyze and confirm again.",
    "Ein gemeinsam genutzter Pfad darf nicht zur Löschung ausgewählt werden.": "A shared path cannot be selected for removal.",
    "Ein Löschziel ist nicht mehr vorhanden: {path}": "A removal target is no longer present: {path}",
    "Seit der Vorschau verändert: {path}": "Changed since the preview: {path}",
    "Programm- oder Bibliotheksinformationen wurden verändert: {path}": "Application or library information changed: {path}",
    "Die Programmliste oder eine bekannte Datenzuordnung hat sich geändert. Bitte erneut analysieren.": "The application list or a known data reference changed. Please analyze again.",
    "Der Paketbestand hat sich seit der Vorschau geändert. Bitte erneut analysieren.": "The installed package state changed since the preview. Please analyze again.",
    "Die erneute Paketsimulation stimmt nicht mit der bestätigten Vorschau überein.": "The new package simulation does not match the approved preview.",
    "Sicherheitsprüfung nicht abgeschlossen: {error}": "Safety check incomplete: {error}",
    "Löschplan und bekannte Datenzuordnungen werden erneut geprüft …": "Rechecking the removal plan and known data references…",
    "Für diesen Löschplan fehlt die Sicherheitsprüfung. Bitte erneut analysieren.": "This removal plan has no safety check. Please analyze again.",
    "Abgebrochen. Bitte erneut analysieren und den neuen Löschplan bestätigen. Bereits ausgeführte Schritte werden nicht automatisch rückgängig gemacht.": "Aborted. Please analyze again and confirm the new removal plan. Steps already completed are not automatically undone.",
    "Neue Analyse erforderlich": "New analysis required",
    "Löschplan ungültig – bitte erneut analysieren": "Removal plan invalid – please analyze again",
    "Speicherorte …": "File locations…",
    "Programmdateien und zugehörige Daten vor dem Löschen ansehen": "Inspect program files and associated data before removal",
    "Ordner öffnen": "Open folder",
    "Ordner öffnen: {path}": "Open folder: {path}",
    "Speicherorte – {name}": "File locations – {name}",
    "Programme können mehrere Speicherorte haben. Geöffnet wird nur der Ordner, niemals die Programmdatei. Die Lösch-Auswahl bleibt unverändert. Gemeinsame Systemordner können auch Dateien anderer Programme enthalten.": "Applications can have multiple file locations. Only the folder is opened, never the program file. Your removal selection stays unchanged. Shared system folders may also contain files from other applications.",
    "Speicherorte werden ermittelt …": "Finding file locations…",
    "Speicherorte konnten nicht ermittelt werden: {error}": "Could not find file locations: {error}",
    "{count} Speicherort(e) gefunden": "{count} file location(s) found",
    "Keine vorhandenen lokalen Speicherorte gefunden.": "No existing local file locations found.",
    "Es ist kein Dateimanager für Ordner eingerichtet.": "No file manager is configured for folders.",
    "Der Dateimanager konnte nicht gestartet werden.": "The file manager could not be started.",
    "Ordner konnte nicht geöffnet werden": "Could not open folder",
    "Pfad: {path}\n\n{error}": "Path: {path}\n\n{error}",
    "Nur absolute lokale Dateipfade können geöffnet werden.": "Only absolute local file paths can be opened.",
    "Dieser Pfad ist keine normale Datei und kein Ordner.": "This path is not a regular file or folder.",
    "Programm-/Spieleordner": "Application/game folder",
    "Programmdatei (öffnet den übergeordneten Ordner)": "Program file (opens its containing folder)",
    "Wine-Präfix (kann gemeinsam genutzt sein)": "Wine prefix (may be shared)",
    "Vom Spiele-Launcher zugeordneter Pfad": "Path associated by the game launcher",
    "Ungültige Paketkennung; Paketdateien wurden nicht abgefragt.": "Invalid package identifier; package files were not queried.",
    "Snap-Programmdateien (schreibgeschützt)": "Snap program files (read-only)",
    "Der Snap-Installationsordner ist nicht verfügbar.": "The Snap installation folder is unavailable.",
    "Die Speicherortliste ist auf {count} Einträge begrenzt.": "The file-location list is limited to {count} entries.",
    "Ungültige Flatpak-Installation; Programmdateien wurden nicht abgefragt.": "Invalid Flatpak installation; program files were not queried.",
    "Paketdateien konnten nicht abgefragt werden. Andere bekannte Speicherorte werden trotzdem angezeigt.": "Package files could not be queried. Other known locations are still shown.",
    "Flatpak-Programmdateien (paketverwaltet)": "Flatpak program files (package-managed)",
    "Paketdateien (Ordner kann gemeinsam genutzt sein)": "Package files (folder may be shared)",
    "Programmliste neu einlesen": "Refresh application list",
    "Wiederherstellungszentrum …": "Recovery Center…",
    "Protokollordner öffnen": "Open history folder",
    "Nach Updates suchen …": "Check for updates…",
    "Automatisch nach Updates suchen": "Automatically check for updates",
    "Sprache": "Language",
    "Systemsprache": "System language",
    "Deutsch": "German",
    "Englisch": "English",
    "Über Restlos Uninstaller": "About Restlos Uninstaller",
    "Programme durchsuchen …": "Search applications…",
    "INSTALLIERTE APPS & SPIELE": "INSTALLED APPS & GAMES",
    "AUSGEWÄHLTE ANWENDUNG": "SELECTED APPLICATION",
    "PAKETAKTIONEN": "PACKAGE ACTIONS",
    "AUSGEWÄHLTE PFADE": "SELECTED PATHS",
    "FREIGEGEBENER SPEICHER": "SPACE TO RECLAIM",
    "SICHERHEIT & WIEDERHERSTELLUNG": "SAFETY & RECOVERY",
    "Alle Quellen": "All sources",
    "Nach Installationsquelle filtern": "Filter by installation source",
    "Ordner prüfen …": "Analyze folder…",
    "Einen nicht erkannten Programm- oder Spieleordner manuell analysieren": "Manually analyze an unrecognized application or game folder",
    "Programme werden eingelesen …": "Scanning applications…",
    "Keine passenden Programme gefunden": "No matching applications found",
    "Programm auswählen": "Select an application",
    "Restlos erstellt zuerst einen überprüfbaren Löschplan.": "Restlos creates a reviewable removal plan first.",
    "Erneut analysieren": "Analyze again",
    "Löschplan": "Removal plan",
    "Auswahl vor dem Entfernen prüfen": "Review selection before removal",
    "Benutzerdaten endgültig löschen (keine Papierkorb-Wiederherstellung)": "Permanently delete user data (no Trash recovery)",
    "Safety Backup vor endgültigem Löschen erstellen": "Create a Safety Backup before permanent deletion",
    "Sichert Einstellungen und Spielstände; Cache und Programmdateien werden ausgelassen.": "Backs up settings and save data; cache and application files are excluded.",
    "Zugehörige laufende Prozesse automatisch beenden": "Automatically stop related running processes",
    "Vor dem Löschen erscheint eine letzte Zusammenfassung.": "A final summary is shown before removal.",
    "Restlos entfernen": "Remove completely",
    "Entfernung wird vorbereitet …": "Preparing removal…",
    "Dieses Fenster nicht schließen, solange Paketaktionen laufen.": "Do not close this window while package actions are running.",
    "Pakete, Spielebibliotheken, Wine und portable Ordner werden eingelesen …": "Scanning packages, game libraries, Wine, and portable folders…",
    "Programm- oder Spieleordner auswählen": "Select an application or game folder",
    "Auswählen": "Select",
    "Abbrechen": "Cancel",
    "Dieser Ordner ist nicht als lokaler Pfad verfügbar.": "This folder is not available as a local path.",
    "Manuell gewählter Programm-/Datenordner": "Manually selected application/data folder",
    "Manuell ausgewählter Ordner; Inhalt und Größe werden vor dem Entfernen angezeigt": "Manually selected folder; contents and size are shown before removal",
    "Manuelle Auswahl": "Manual selection",
    "Keine Beschreibung verfügbar": "No description available",
    "Analyse läuft …": "Analyzing…",
    "Paketverwaltung": "Package management",
    "Keine zusätzlichen Benutzerdaten gefunden": "No additional user data found",
    "Safety Backup wird erstellt …": "Creating Safety Backup…",
    "Hinweis: Paket-Deinstallationen und Änderungen an Launcher-Bibliotheken sind nicht automatisch wiederherstellbar; nur die ausgewählten Dateipfade werden in den Papierkorb verschoben.": "Note: Package removals and launcher library changes cannot be restored automatically; only selected file paths are moved to Trash.",
    "Abbrechen": "Cancel",
    "Endgültig entfernen": "Remove permanently",
    "Entfernen": "Remove",
    "Schließen": "Close",
    "Wiederherstellungszentrum": "Recovery Center",
    "Restlos-Wiederherstellungszentrum": "Restlos Recovery Center",
    "Wiederherstellbare Benutzerdaten und Safety Backups": "Recoverable user data and Safety Backups",
    "Hier kannst du Papierkorbdaten und Safety Backups an ihren ursprünglichen Ort zurückholen. Paket-Deinstallationen und Änderungen an Spielebibliotheken werden dabei nicht rückgängig gemacht.": "Restore Trash data and Safety Backups to their original locations here. Package removals and game-library changes are not reversed.",
    "Papierkorb, Safety Backups und Restlos-Protokolle werden geprüft …": "Checking Trash, Safety Backups, and Restlos history…",
    "Keine wiederherstellbaren Restlos-Vorgänge gefunden.": "No recoverable Restlos operations found.",
    "Paket- oder Bibliotheksaktionen müssen bei Bedarf separat rückgängig gemacht werden.": "Package or library actions must be reversed separately if needed.",
    "Wiederherstellen": "Restore",
    "Daten wiederherstellen": "Restore data",
    "Daten werden an ihre ursprünglichen Orte zurückgeholt …": "Restoring data to its original locations…",
    "Wiederherstellung abgeschlossen": "Recovery complete",
    "Wiederherstellung nicht vollständig": "Recovery incomplete",
    "Ein unbekannter Fehler ist aufgetreten.": "An unknown error occurred.",
    "2026 – lokale Open-Source-Ausgabe": "2026 – local open-source edition",
    "Projektseite auf GitHub": "Project page on GitHub",
    "Update-Suche fehlgeschlagen": "Update check failed",
    "Restlos Uninstaller ist aktuell": "Restlos Uninstaller is up to date",
    "Änderungen stehen auf der Release-Seite.": "Changes are listed on the release page.",
    "Später": "Later",
    "Release-Seite": "Release page",
    "Herunterladen und installieren": "Download and install",
    "Update wird vorbereitet …": "Preparing update…",
    "Der aktuelle Restlos Uninstaller bleibt bei einem Fehler weiterhin startfähig.": "The current Restlos Uninstaller remains usable if the update fails.",
    "Update nicht installiert": "Update not installed",
    "Später neu starten": "Restart later",
    "Jetzt neu starten": "Restart now",
    "Neustart fehlgeschlagen": "Restart failed",
    "Sprache gespeichert": "Language saved",
    "Starte Restlos Uninstaller neu, damit die neue Sprache vollständig verwendet wird.": "Restart Restlos Uninstaller to use the new language throughout the application.",
    "Manuell": "Manual",
    "Lutris-Spiel": "Lutris game",
    "Steam-Spiel": "Steam game",
    "Heroic-Spiel": "Heroic game",
    "Bottles-Umgebung": "Bottles environment",
    "Ordner/Portable": "Folder/portable",
    "Benutzer": "User",
    "System": "System",
    "sicher": "certain",
    "hoch": "high",
    "prüfen": "review",
    "Einstellungen": "Settings",
    "Anwendungsdaten": "Application data",
    "Sandbox-Daten": "Sandbox data",
    "Menüeintrag": "Menu entry",
    "Anwendungssymbol": "Application icon",
    "Menüeintrag oder Symbol": "Menu entry or icon",
    "Heruntergeladener Installer": "Downloaded installer",
    "Manuelle Installation": "Manual installation",
    "Spielinstallation": "Game installation",
    "Lutris-Spielordner und eigener Präfix": "Lutris game folder and dedicated prefix",
    "Lutris-Spielkonfiguration": "Lutris game configuration",
    "Lokale Steam-Benutzerdaten und Spielstände": "Local Steam user data and save games",
    "Proton-Präfix und Windows-Benutzerdaten": "Proton prefix and Windows user data",
    "Steam-Spielordner": "Steam game folder",
    "Steam-Shadercache": "Steam shader cache",
    "Steam-App-Manifest": "Steam app manifest",
    "Steam-Bibliotheksbilder und Cache": "Steam library artwork and cache",
    "Temporäre Steam-Daten": "Temporary Steam data",
    "Heroic-Spieleinstellungen": "Heroic game settings",
    "Heroic-Spielordner": "Heroic game folder",
    "Eigener Heroic-Wine-/Proton-Präfix": "Dedicated Heroic Wine/Proton prefix",
    "Gesamte Bottles-Umgebung mit Präfix und Programmen": "Entire Bottles environment with prefix and applications",
    "PlayOnLinux-Konfiguration": "PlayOnLinux configuration",
    "PlayOnLinux-Präfix und Programmdateien": "PlayOnLinux prefix and application files",
    "Programmdateien im gemeinsamen Wine-Präfix": "Application files in the shared Wine prefix",
    "Vom Programmstarter referenzierter Installationspfad": "Installation path referenced by the launcher",
    "Einlesen fehlgeschlagen: {error}": "Scan failed: {error}",
    "{count} Anwendungen erkannt": "{count} applications detected",
    "{count} Anwendungen erkannt · manueller Ordner hinzugefügt": "{count} applications detected · manual folder added",
    "Analyse fehlgeschlagen: {error}": "Analysis failed: {error}",
    "unbekannter Fehler": "unknown error",
    "{actions} Paketaktion(en) · {paths} Pfad(e) · {size}": "{actions} package action(s) · {paths} path(s) · {size}",
    "\n\nLaufende Prozesse: {names}": "\n\nRunning processes: {names}",
    "dauerhaft gelöscht": "deleted permanently",
    "wiederherstellbar in den Papierkorb verschoben": "moved to Trash for recovery",
    "\n\nSafety Backup: {count} geeignete Datenpfade mit {size} werden vor der Entfernung gesichert.": "\n\nSafety Backup: {count} eligible data path(s), totaling {size}, will be backed up before removal.",
    "{actions} Paketaktion(en) und {paths} ausgewählte Pfade mit {size} werden verarbeitet. Benutzerdaten werden {mode}.": "{actions} package action(s) and {paths} selected path(s), totaling {size}, will be processed. User data will be {mode}.",
    "„{name}“ wirklich restlos entfernen?": "Remove “{name}” completely?",
    "„{name}“ wird entfernt …": "Removing “{name}”…",
    "„{name}“ wurde entfernt": "“{name}” was removed",
    "„{name}“ wurde entfernt – Restdaten gefunden": "“{name}” was removed – residual data found",
    "{count} Pfade wurden verarbeitet.": "{count} path(s) were processed.",
    "{count} Pfade können im Wiederherstellungszentrum zurückgeholt werden.": "{count} path(s) can be restored in the Recovery Center.",
    "Safety Backup: {count} Datenpfade wurden vor dem Löschen gesichert.": "Safety Backup: {count} data path(s) were backed up before deletion.",
    "Der Kontrollscan fand {count} weitere mögliche Restpfade:\n{preview}{suffix}": "The verification scan found {count} additional possible residual path(s):\n{preview}{suffix}",
    "Der Kontrollscan konnte nicht abgeschlossen werden: {error}": "The verification scan could not be completed: {error}",
    "Kontrollscan: keine weiteren zuordenbaren Restpfade gefunden.": "Verification scan: no additional attributable residual paths found.",
    "{count} nicht ausgewählte Pfade wurden wie gewünscht beibehalten.": "{count} unselected path(s) were kept as requested.",
    "Protokoll: {path}": "History record: {path}",
    "konnte nicht geschrieben werden": "could not be written",
    "Entfernung nicht vollständig": "Removal incomplete",
    "{count} bereits verschobene Pfade sind im Wiederherstellungszentrum verfügbar.": "{count} path(s) already moved are available in the Recovery Center.",
    "Das Safety Backup mit {count} Datenpfaden ist im Wiederherstellungszentrum verfügbar.": "The Safety Backup containing {count} data path(s) is available in the Recovery Center.",
    "Wiederherstellungsdaten konnten nicht gelesen werden: {error}": "Recovery data could not be read: {error}",
    "{timestamp} · {count} Pfad(e) · {size} · {source}": "{timestamp} · {count} path(s) · {size} · {source}",
    "Daten von „{name}“ wiederherstellen?": "Restore data for “{name}”?",
    "{count} Pfad(e) mit {size} werden an ihre ursprünglichen Orte zurückgeholt. Vorhandene Dateien werden nicht überschrieben. Ein deinstalliertes Programmpaket wird dadurch nicht erneut installiert.": "{count} path(s), totaling {size}, will be restored to their original locations. Existing files will not be overwritten. This does not reinstall a removed package.",
    "{count} Pfad(e) wurden zurückgeholt. Falls das Programmpaket entfernt wurde, muss es separat neu installiert werden.": "{count} path(s) were restored. If the package was removed, it must be reinstalled separately.",
    "{count} Pfad(e) wurden bereits wiederhergestellt.\n\n": "{count} path(s) have already been restored.\n\n",
    "Sprache konnte nicht gespeichert werden": "Language could not be saved",
    "Version {version} ist die neueste verfügbare Ausgabe.": "Version {version} is the latest available release.",
    "Installiert: {version}": "Installed: {version}",
    "Verfügbar: {version}": "Available: {version}",
    "Das Update wird nur nach deiner Bestätigung geladen, per SHA-256 geprüft und atomar installiert.": "The update is downloaded only after your confirmation, verified with SHA-256, and installed atomically.",
    "Diese Installation wird vom Linux-Paketmanager verwaltet. Öffne die Release-Seite, um das neue Systempaket zu beziehen.": "This installation is managed by the Linux package manager. Open the release page to get the new system package.",
    "Restlos Uninstaller {version} ist verfügbar": "Restlos Uninstaller {version} is available",
    "Restlos Uninstaller {version} installieren": "Install Restlos Uninstaller {version}",
    "Restlos Uninstaller {version} wurde installiert": "Restlos Uninstaller {version} was installed",
    "Einstellungen und Entfernungshistorie wurden beibehalten. Starte Restlos Uninstaller jetzt neu, damit die neue Version aktiv wird.": "Settings and removal history were preserved. Restart Restlos Uninstaller now to activate the new version.",
    "Starte Restlos Uninstaller manuell neu. Technisches Detail: {error}": "Restart Restlos Uninstaller manually. Technical detail: {error}",
    "Keine grafische Sitzung gefunden. Verwende `restlos list` oder `restlos analyze NAME`.": "No graphical session found. Use `restlos list` or `restlos analyze NAME`.",
    "Lutris-Banner": "Lutris banner",
    "Lutris-Cover": "Lutris cover",
    "Lutris-Spielsymbol": "Lutris game icon",
    "Lutris-Starter": "Lutris launcher",
    "Von Lutris verwendeter Installer": "Installer used by Lutris",
    "Steam-Workshop-Inhalte": "Steam Workshop content",
    "Unvollständige Steam-Downloads": "Incomplete Steam downloads",
    "Lokale Steam-Screenshots": "Local Steam screenshots",
    "Steam-Spielmetadaten": "Steam game metadata",
    "Steam-Pipelinecache": "Steam pipeline cache",
    "Steam-Starter": "Steam launcher",
    "Heroic-Starter": "Heroic launcher",
    "PlayOnLinux-Menüeintrag": "PlayOnLinux menu entry",
    "PlayOnLinux-Starter": "PlayOnLinux launcher",
    "PlayOnLinux-Symbol": "PlayOnLinux icon",
    "Portabler Programmordner": "Portable application folder",
    "Nicht zugeordneter Wine-Präfix": "Unassigned Wine prefix",
    "Sprache für diesen Aufruf": "Language for this invocation",
    "erkannte Anwendungen auflisten": "list detected applications",
    "Löschplan anzeigen": "show removal plan",
    "Anwendung gemäß Löschplan entfernen": "remove an application according to its removal plan",
    "Entfernung bestätigen": "confirm removal",
    "Benutzerdaten in den Papierkorb verschieben": "move user data to Trash",
    "Safety Backup geeigneter Einstellungen und Spielstände vor endgültigem Löschen erstellen": "create a Safety Backup of eligible settings and save data before permanent deletion",
    "wiederherstellbare Entfernungsvorgänge verwalten": "manage recoverable removal operations",
    "verfügbare Wiederherstellungen auflisten": "list available recoveries",
    "Benutzerdaten eines Vorgangs wiederherstellen": "restore user data from an operation",
    "Wiederherstellung bestätigen": "confirm recovery",
    "Keine Anwendung für „{query}“ gefunden.": "No application found for “{query}”.",
    "Mehrdeutige Auswahl: {names}": "Ambiguous selection: {names}",
    "{id}\t{name}\t{count} Pfad(e)\t{size}": "{id}\t{name}\t{count} path(s)\t{size}",
    "Abgebrochen: Für die Wiederherstellung ist --yes erforderlich.": "Cancelled: --yes is required for recovery.",
    "{count} Pfad(e) wurden wiederhergestellt.": "{count} path(s) were restored.",
    "Paketaktionen werden nicht automatisch rückgängig gemacht.": "Package actions are not reversed automatically.",
    "Wiederherstellung nicht vollständig:": "Recovery incomplete:",
    "  Paketaktion: {label}": "  Package action: {label}",
    "  WARNUNG: {warning}": "  WARNING: {warning}",
    "Ausgewählte Benutzerdaten: {size}": "Selected user data: {size}",
    "Abgebrochen: Für die Entfernung ist --yes erforderlich.": "Cancelled: --yes is required for removal.",
    "--backup ist für endgültiges Löschen vorgesehen und kann nicht mit --trash verwendet werden.": "--backup is intended for permanent deletion and cannot be combined with --trash.",
    "{name} wurde entfernt. Protokoll: {path}": "{name} was removed. History record: {path}",
    "nicht geschrieben": "not written",
    "Wiederherstellbar: {count} Pfad(e) mit Kennung {id}.": "Recoverable: {count} path(s) with ID {id}.",
    "Safety Backup: {count} Datenpfad(e) mit Kennung {id}.": "Safety Backup: {count} data path(s) with ID {id}.",
    "Kontrollscan: {count} weitere mögliche Restpfade gefunden.": "Verification scan: {count} additional possible residual path(s) found.",
    "Kontrollscan fehlgeschlagen: {error}": "Verification scan failed: {error}",
    "Bewusst nicht ausgewählt und beibehalten: {count} Pfad(e).": "Intentionally unselected and kept: {count} path(s).",
    "Entfernung nicht vollständig:": "Removal incomplete:",
    "Laufende Prozesse werden beendet …": "Stopping running processes…",
    "Kontrollscan nach verbliebenen Daten …": "Scanning for residual data…",
    "Prüfsumme wird geladen …": "Downloading checksum…",
    "SHA-256-Prüfsumme wird kontrolliert …": "Verifying SHA-256 checksum…",
    "Update wird sicher entpackt …": "Safely extracting update…",
    "Neue Version wird installiert …": "Installing new version…",
    "Update abgeschlossen.": "Update complete.",
    "Update wird heruntergeladen …": "Downloading update…",
    "Die Anwendung läuft noch und wurde nicht beendet.": "The application is still running and was not stopped.",
    "Safety Backup und Papierkorbmodus können nicht gleichzeitig verwendet werden.": "Safety Backup and Trash mode cannot be used at the same time.",
    "Ungültige Wiederherstellungskennung.": "Invalid recovery ID.",
    "Dieses Protokoll enthält keine wiederherstellbaren Daten.": "This history record contains no recoverable data.",
    "Es sind keine noch verfügbaren Daten in diesem Vorgang enthalten.": "This operation contains no data that is still available.",
    "Papierkorb konnte nicht gelesen werden": "Trash could not be read",
    "Verschieben in den Papierkorb fehlgeschlagen": "Moving to Trash failed",
    "Der neue Papierkorbeintrag konnte nicht eindeutig zugeordnet werden": "The new Trash entry could not be identified unambiguously",
    "Papierkorbeintrag und ursprünglicher Pfad stimmen nicht überein": "Trash entry and original path do not match",
    "Wiederherstellung aus dem Papierkorb fehlgeschlagen": "Recovery from Trash failed",
    "Der ursprüngliche Pfad fehlt nach der Wiederherstellung": "The original path is missing after recovery",
    "GitHub hat keine gültigen Release-Daten geliefert.": "GitHub returned no valid release data.",
    "Die SHA-256-Prüfung des Updates ist fehlgeschlagen.": "The update failed SHA-256 verification.",
    "Das Update enthält keinen Installer.": "The update contains no installer.",
    "Das Update-Archiv überschreitet das Größenlimit.": "The update archive exceeds the size limit.",
    "Die Größe des geladenen Update-Archivs ist unerwartet.": "The downloaded update archive has an unexpected size.",
    "Der GitHub-Digest des Update-Archivs stimmt nicht überein.": "The update archive does not match its GitHub digest.",
    "Eine nicht vertrauenswürdige Update-Adresse wurde abgelehnt.": "An untrusted update address was rejected.",
    "Das Update-Archiv enthält unerwartet viele Einträge.": "The update archive contains an unexpected number of entries.",
    "Das Update-Archiv enthält einen unsicheren Pfad.": "The update archive contains an unsafe path.",
    "Links oder Spezialdateien im Update-Archiv wurden abgelehnt.": "Links or special files in the update archive were rejected.",
    "Eine Datei im Update-Archiv konnte nicht gelesen werden.": "A file in the update archive could not be read.",
    "Das Update-Archiv besitzt keine gültige Wurzel.": "The update archive has no valid root directory.",
    "Die Anwendung verwendet möglicherweise das gemeinsame Standard-Wine-Präfix. Restlos löscht dieses Präfix nicht, weil darin weitere Windows-Programme liegen können.": "This application may use the shared default Wine prefix. Restlos does not delete that prefix because it may contain other Windows applications.",
    "Manuelle Installationen besitzen kein vollständiges Systemmanifest. Prüfe deshalb die vorgeschlagenen Pfade vor dem Löschen.": "Manual installations do not have a complete system manifest. Review the suggested paths before deletion.",
    "Diese Auswahl ist eine vollständige Bottle. Alle Programme und Windows-Daten innerhalb dieser Umgebung werden gemeinsam entfernt.": "This selection is an entire Bottle. All applications and Windows data in this environment will be removed together.",
    "Lokale Steam-Daten werden entfernt. Bereits mit Steam Cloud synchronisierte Spielstände können bei einer Neuinstallation erneut geladen werden.": "Local Steam data will be removed. Save games already synchronized with Steam Cloud may be downloaded again after reinstallation.",
    "Es wurden keine sicher zuordenbaren Löschziele gefunden.": "No safely attributable removal targets were found.",
    "Die Paketkennung enthält unerlaubte Zeichen; die Paketaktion wurde blockiert.": "The package ID contains invalid characters; the package action was blocked.",
    "APT/DEB-Anwendung": "APT/DEB application",
    "DNF/RPM-Anwendung": "DNF/RPM application",
    "Zypper/RPM-Anwendung": "Zypper/RPM application",
    "pacman-Anwendung": "pacman application",
    "Flatpak-Anwendung": "Flatpak application",
    "Snap-Anwendung": "Snap application",
    "Windows-Anwendung über Wine": "Windows application through Wine",
    "Manuell installierte Anwendung": "Manually installed application",
    "Eigenständige AppImage-Anwendung": "Standalone AppImage application",
    "Vollständige Bottles-Umgebung; alle darin enthaltenen Windows-Programme werden entfernt": "Complete Bottles environment; all Windows applications inside it will be removed",
    "PlayOnLinux-Programm mit eigenem Wine-Präfix": "PlayOnLinux application with a dedicated Wine prefix",
    "Nicht von einer Spielebibliothek zugeordneter Wine-Präfix": "Wine prefix not assigned to a game library",
    "Nicht von einem Paketmanager verwalteter Ordner": "Folder not managed by a package manager",
    "Spiel aus der Lutris-Bibliothek entfernen": "Remove game from the Lutris library",
    "Installationsstatus aus Heroic entfernen": "Remove installation status from Heroic",
    "Die APT-Entfernung konnte nicht sicher simuliert werden.": "APT removal could not be simulated safely.",
    "Die APT-Simulation enthielt das ausgewählte Paket nicht.": "The APT simulation did not include the selected package.",
    "Die DNF-Entfernung konnte nicht sicher simuliert werden.": "DNF removal could not be simulated safely.",
    "Die DNF-Simulation enthielt das ausgewählte Paket nicht.": "The DNF simulation did not include the selected package.",
    "Die Zypper-Entfernung konnte nicht sicher simuliert werden.": "Zypper removal could not be simulated safely.",
    "Die Zypper-Simulation enthielt das ausgewählte Paket nicht.": "The Zypper simulation did not include the selected package.",
    "Die pacman-Entfernung konnte nicht sicher simuliert werden.": "pacman removal could not be simulated safely.",
    "Die pacman-Simulation enthielt das ausgewählte Paket nicht.": "The pacman simulation did not include the selected package.",
}


_language = "de"


def _system_language() -> str:
    value = locale.getlocale()[0] or os.environ.get("LANG", "")
    return "de" if value.casefold().startswith("de") else "en"


class LanguageSettings:
    def __init__(self, home: Path | None = None, *, config_home: Path | None = None) -> None:
        base_home = (home or Path.home()).absolute()
        if config_home is not None:
            base = config_home.absolute()
        elif home is not None:
            base = base_home / ".config"
        else:
            configured = os.environ.get("XDG_CONFIG_HOME")
            base = Path(configured).absolute() if configured else base_home / ".config"
        self.path = base / "restlos/settings.json"

    def selected(self) -> str:
        try:
            if self.path.stat().st_size > 100_000 or self.path.is_symlink():
                return "system"
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            value = payload.get("language") if isinstance(payload, dict) else None
            return value if value in SUPPORTED_LANGUAGES else "system"
        except (OSError, UnicodeError, json.JSONDecodeError):
            return "system"

    def resolved(self) -> str:
        selected = self.selected()
        return _system_language() if selected == "system" else selected

    def set(self, language: str) -> None:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")
        payload: dict[str, Any] = {}
        try:
            existing = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                payload.update(existing)
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
        payload["language"] = language
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                delete=False,
            ) as handle:
                temporary_name = handle.name
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self.path)
        finally:
            if temporary_name and Path(temporary_name).exists():
                Path(temporary_name).unlink()


def configure(language: str | None = None) -> str:
    global _language
    selected = language or LanguageSettings().resolved()
    if selected == "system":
        selected = _system_language()
    _language = selected if selected in {"de", "en"} else "en"
    return _language


def current_language() -> str:
    return _language


def translate(message: str, **values: object) -> str:
    translated = ENGLISH.get(message, message) if _language == "en" else message
    return translated.format(**values) if values else translated


def display_text(message: str) -> str:
    """Translate scanner/analyzer labels while leaving unknown technical output intact."""
    if _language != "en":
        return message
    direct = ENGLISH.get(message)
    if direct is not None:
        return direct
    prefixes = {
        "Lutris-Spiel · ": "Lutris game · ",
        "Steam-Spiel · App-ID ": "Steam game · App ID ",
        "Heroic-Spiel · ": "Heroic game · ",
        "Wine-Präfix: ": "Wine prefix: ",
        "Entferne ": "Removing ",
        "Protokoll konnte nicht gelesen werden: ": "History record could not be read: ",
        "Am ursprünglichen Ort existiert bereits etwas: ": "Something already exists at the original location: ",
        "Safety Backup fehlgeschlagen; es wurde nichts entfernt: ": "Safety Backup failed; nothing was removed: ",
        "Der Installer konnte nicht ausgeführt werden: ": "The installer could not be run: ",
        "Die installierte Version konnte nicht geprüft werden: ": "The installed version could not be verified: ",
        "Das Update-Archiv konnte nicht gespeichert werden: ": "The update archive could not be saved: ",
        "Das Update-Archiv konnte nicht entpackt werden: ": "The update archive could not be extracted: ",
    }
    for prefix, replacement in prefixes.items():
        if message.startswith(prefix):
            return replacement + message[len(prefix):]
    action_patterns = (
        ("APT-Paket „", "“ vollständig entfernen (purge)", "Completely remove APT package “{value}” (purge)"),
        ("DNF/RPM-Paket „", "“ samt unbenötigten Abhängigkeiten entfernen", "Remove DNF/RPM package “{value}” including unused dependencies"),
        ("Zypper/RPM-Paket „", "“ samt unbenötigten Abhängigkeiten entfernen", "Remove Zypper/RPM package “{value}” including unused dependencies"),
        ("pacman-Paket „", "“ samt unbenötigten Abhängigkeiten entfernen", "Remove pacman package “{value}” including unused dependencies"),
        ("Flatpak „", "“ samt App-Daten entfernen", "Remove Flatpak “{value}” including app data"),
        ("Snap „", "“ ohne gespeicherten Snapshot entfernen", "Remove Snap “{value}” without retaining a snapshot"),
    )
    for source_prefix, source_suffix, target_template in action_patterns:
        if message.startswith(source_prefix) and message.endswith(source_suffix):
            value = message[len(source_prefix):-len(source_suffix)]
            return target_template.format(value=value)
    if message.startswith("Entfernung blockiert: Die "):
        return message.replace("Entfernung blockiert: Die ", "Removal blocked: The ", 1).replace(
            "-Simulation würde wichtige Systemkomponenten entfernen: ",
            " simulation would remove important system components: ",
        )
    if " wird zusätzlich " in message and " abhängige(s) Paket(e) entfernen: " in message:
        return message.replace(" wird zusätzlich ", " will also remove ", 1).replace(
            " abhängige(s) Paket(e) entfernen: ",
            " dependent package(s): ",
            1,
        )
    return message


configure()
