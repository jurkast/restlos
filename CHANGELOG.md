# Änderungsprotokoll

## 1.4.3 – 2026-08-30

- GitHub-Projekt und öffentliche Autorenkennung vollständig von `jurkastl` auf `jurkast` migriert
- neue App-ID `io.github.jurkast.Restlos` für Desktop-Eintrag, Symbol und GTK-Anwendung
- Installer entfernt nach erfolgreichem Update alte Starter und Symbole mit `io.github.jurkastl.Restlos`
- Scanner und Uninstaller erkennen weiterhin die bisherige sowie die provisorische App-ID
- Projekt-, Download-, Fehler- und Sicherheitslinks zeigen auf `github.com/jurkast/restlos`

## 1.4.2 – 2026-08-30

- sicherer Übergang für die geplante Änderung des GitHub-Benutzernamens von `jurkastl` zu `jurkast`
- Update-Suche akzeptiert Releases aus dem bisherigen und dem neuen Repository-Namensraum
- automatischer Fallback auf den bisherigen Namensraum, solange der neue GitHub-Benutzername noch nicht aktiv ist
- strikte Prüfung von Release-Dateinamen, Versionen, Digests und beiden ausdrücklich erlaubten Projektpfaden bleibt erhalten

## 1.4.1 – 2026-08-30

- international verständlicher sichtbarer Name **Restlos Uninstaller**
- neuer Untertitel **Safe Linux App & Game Uninstaller** in Programmfenster, Desktop-Eintrag und Projektbeschreibung
- zusätzliche englische und deutsche Suchbegriffe für Anwendungsmenüs
- technische App-ID, Terminalbefehl, Installationspfade und Benutzerdaten bleiben für störungsfreie Updates unverändert

## 1.4.0 – 2026-08-30

- neues grafisches Wiederherstellungszentrum für von Restlos in den Desktop-Papierkorb verschobene Benutzerdaten
- eindeutige Zuordnung jedes verschobenen Pfads über seine GIO-Papierkorb-URI und den gespeicherten Ursprungsort
- sichere Rücksicherung ohne Überschreiben bereits vorhandener Dateien oder Ordner
- lokale, atomar geschriebene Protokolle im neuen Schema 2 mit Löschmodus, Wiederherstellungsdaten und Kontrollergebnis
- dateibasierter Kontrollscan nach jedem Löschvorgang, ohne eine erneute Paketaktion auszulösen
- getrennte Anzeige unerwarteter Restpfade und bewusst nicht ausgewählter, beibehaltener Pfade
- wiederherstellbarer Modus ist in der grafischen Oberfläche nun die sichere Voreinstellung
- neue Terminalbefehle `restlos recovery list` und `restlos recovery restore ID --yes`
- klare Begrenzung: Paket-Deinstallationen und Änderungen an Launcher-Bibliotheken werden nicht automatisch rückgängig gemacht

## 1.3.0 – 2026-08-30

- automatische, standardmäßig höchstens einmal täglich ausgeführte Suche nach neuen GitHub-Releases beim Programmstart
- abschaltbare automatische Suche und jederzeit ausführbare manuelle Prüfung im Anwendungsmenü
- grafische Update-Meldung mit installierter und verfügbarer Version sowie den veröffentlichten Änderungshinweisen
- ausdrücklich bestätigter Download mit sichtbarer Fortschrittsanzeige und anschließendem Neustartangebot
- strikte Prüfung von Release-Tag, Asset-Namen, Download-Adressen, Dateigröße, GitHub-Digest und veröffentlichter SHA-256-Prüfsumme
- sichere Archivextraktion mit Pfad-, Größen- und Dateitypgrenzen; Links und Spezialdateien werden abgelehnt
- atomare Installation in ein neues Versionsverzeichnis, sodass die bisherige Ausgabe bei Fehlern startfähig bleibt
- transparente Datenschutzangabe für die sparsame GitHub-Abfrage; keine Telemetrie oder Übertragung lokaler Anwendungsdaten

## 1.2.0 – 2026-08-30

- native Paketmanager-Adapter für DNF/RPM auf Fedora-/RHEL-Systemen, pacman auf Arch-basierten Systemen und Zypper/RPM auf openSUSE
- automatische Auswahl des zur Betriebssystemfamilie passenden Paketmanagers über `/etc/os-release`
- grafische Paketerkennung anhand der Besitzer von Desktop-Dateien in der jeweiligen Paketdatenbank
- verpflichtende Entfernungsvorschau für alle nativen Paketmanager; bei Simulationsfehlern wird die Paketaktion blockiert
- distributionsspezifische Schutzlisten für Kernel, Bootloader, Paketmanager, Desktop und andere kritische Systemkomponenten
- Anzeige zusätzlich entfernter, nicht mehr benötigter Abhängigkeiten vor der Bestätigung
- distributionsabhängige Installationshinweise für GTK 4, PyGObject und PolicyKit
- zusätzliche CI-Prüfungen in Fedora-, Arch-Linux- und openSUSE-Containern
- alte Restlos-App-IDs werden zuverlässig ausgeblendet und beim Installieren bereinigt

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
