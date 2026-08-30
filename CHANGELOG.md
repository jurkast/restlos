# Änderungsprotokoll

## 1.1.0 – 2026-08-30

- öffentliche Projektidentität `io.github.jurkastl.Restlos` und GitHub-Projektmetadaten
- Unterstützung ab Python 3.10 sowie Ordnerauswahl-Fallback für ältere GTK-4-Versionen
- reproduzierbarer Releasebau, automatisierte Tests für Ubuntu 22.04/24.04 und tagbasierte GitHub-Releases
- deutsch- und englischsprachige Projektdokumentation, Beitragsregeln, Datenschutz- und Sicherheitsrichtlinie
- direkte Bibliothekserkennung für Lutris, Steam und Heroic
- vollständige Bottles-Umgebungen und PlayOnLinux-Präfixe als eigene Einträge
- Erkennung nicht verwalteter portabler Spieleordner und Wine-Präfixe
- zugeordnete Spielordner, Präfixe, lokale Spielstände, Caches, Workshop-Daten, Bilder, Starter und Manifeste im Löschplan
- sichere Aktualisierung der Lutris-Datenbank und Heroic-Installationsdatei erst nach erfolgreicher Dateilöschung
- Unterstützung externer, vom Launcher registrierter Spielebibliotheken bei weiterhin gesperrten gemeinsamen Managerverzeichnissen
- Quellenfilter und manuelle Funktion „Ordner prüfen …“
- zusätzliche Regressionstests mit künstlichen Lutris-, Steam-, Heroic-, Bottles- und PlayOnLinux-Bibliotheken

## 1.0.0 – 2026-08-30

- erste GTK-4-Oberfläche mit Suche, Löschvorschau und Fortschrittsanzeige
- Erkennung für APT/DEB, Flatpak, Snap, AppImage, Wine und manuelle Installationen
- kontrollierte Suche nach Einstellungen, Cache, Anwendungsdaten, Startern, Symbolen und Installern
- separates Wine-Präfix kann vollständig entfernt werden; gemeinsame Präfixe bleiben geschützt
- laufende Prozesse innerhalb ausgewählter Programmordner werden erkannt
- dauerhafte Löschung und Papierkorbmodus
- Terminalbefehle für Liste, Analyse und Entfernung
- versionsbasierter Installer, geprüfter Updater und eigener Uninstaller
- Sicherheitsregeln und automatisierte Regressionstests
