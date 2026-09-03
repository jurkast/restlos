# Restlos Uninstaller

> **Safe Linux App & Game Uninstaller**

[![Tests](https://github.com/jurkast/restlos/actions/workflows/ci.yml/badge.svg)](https://github.com/jurkast/restlos/actions/workflows/ci.yml)
[![GitHub Release](https://img.shields.io/github/v/release/jurkast/restlos?include_prereleases)](https://github.com/jurkast/restlos/releases)
[![Lizenz: MIT](https://img.shields.io/badge/Lizenz-MIT-blue.svg)](LICENSE)

[English](README.en.md) · [Downloads](https://github.com/jurkast/restlos/releases) · [Fehler melden](https://github.com/jurkast/restlos/issues)

**Restlos Uninstaller** ist ein sicherer grafischer App- und Spiele-Deinstaller für die großen Linux-Distributionsfamilien. Die Anwendung führt Programme und Spiele aus mehreren Installationssystemen in einer Oberfläche zusammen und erstellt vor jeder Entfernung einen sichtbaren, abwählbaren Löschplan.

> **Öffentliche Beta:** Restlos kann Daten dauerhaft löschen. Prüfe den angezeigten Löschplan aufmerksam. Für geeignete Einstellungen und Spielstände kann Restlos vorab ein lokales Safety Backup erstellen.

## Funktionen

- erkennt grafische APT/DEB-, DNF/RPM-, pacman-, Zypper/RPM-, Flatpak- und Snap-Anwendungen
- erkennt AppImages, Wine-Menüeinträge und manuell installierte Programme
- liest installierte Spiele direkt aus Lutris-, Steam- und Heroic-Bibliotheken
- erkennt vollständige Bottles-Umgebungen und PlayOnLinux-Präfixe
- findet nicht zugeordnete portable Programme und Wine-Präfixe in `Games` und `Applications`
- folgt Steam-Bibliotheken auf weiteren Laufwerken und von Launchern verwalteten externen Installationspfaden
- entfernt je Spiel zugeordnete Präfixe, Manifeste, Workshop-Inhalte, Shadercache, lokale Spielstände, Screenshots, Cover, Starter und Einstellungen
- bereinigt nach erfolgreicher Dateilöschung auch die Lutris- beziehungsweise Heroic-Bibliotheksdaten
- bietet Quellenfilter und **Ordner prüfen …** für nicht automatisch erkannte Installationen
- sucht app-spezifische Daten in `.config`, `.cache`, `.local/share`, `.local/state`, `.var/app`, `snap`, `Applications`, `Games`, `Downloads` und auf dem Desktop
- liest bei manuellen Startern referenzierte Installationspfade aus, ohne den Starter auszuführen
- zeigt Pfade, Begründung, Trefferqualität und Größe vor dem Löschen
- zeigt unter **Geschützt – wer braucht diese Daten noch?** bekannte andere Anwendungen mit konkretem Referenzpfad; gemeinsam referenzierte Löschziele sind gesperrt
- prüft vor dem Entfernen erneut auf geänderte Dateien, Paketstände und bekannte Datenzuordnungen und verlangt bei Änderungen eine neue Bestätigung nach erneuter Analyse
- entfernt native Pakete über APT, DNF, pacman oder Zypper sowie Flatpaks mit `--delete-data` und Snaps mit `--purge`
- simuliert jede native Paketentfernung und blockiert sie, falls kritische Systemkomponenten betroffen wären
- erkennt laufende Prozesse innerhalb der ausgewählten Programmordner
- unterstützt dauerhafte Löschung oder eine wiederherstellbare Entfernung über den Desktop-Papierkorb
- erstellt auf Wunsch vor endgültigem Löschen ein Safety Backup geeigneter Einstellungen, Anwendungsdaten und Spielstände
- bietet ein Wiederherstellungszentrum für Papierkorbdaten und Safety Backups, das vorhandene Dateien niemals überschreibt
- kontrolliert nach der Entfernung erneut auf zuordenbare Restpfade und trennt diese von bewusst beibehaltenen Daten
- schreibt ein lokales Ergebnis- und Wiederherstellungsprotokoll nach `~/.local/state/restlos/history`
- bietet zusätzlich eine Terminaloberfläche für Listen und Löschpläne
- besitzt eine vollständige deutsche und englische Oberfläche mit Sprachwahl im Menü
- sucht beim Start höchstens einmal täglich nach neuen Releases und bietet geprüfte Updates nach Bestätigung direkt an

Restlos zeigt bewusst **Anwendungen, Spiele und eigenständige Programmumgebungen** und keine Tausenden Bibliotheks- oder Kernelpakete an.

## Unterstützte Systeme

- Debian, Ubuntu, Zorin OS und darauf basierende Systeme mit APT/DEB
- Fedora, RHEL und verwandte Systeme mit DNF/RPM
- Arch Linux, Manjaro und verwandte Systeme mit pacman
- openSUSE Leap/Tumbleweed und verwandte Systeme mit Zypper/RPM
- Python 3.10 oder neuer
- GTK 4 und PyGObject

Flatpak, Snap, AppImage, Wine sowie die Spieleplattformen funktionieren unabhängig vom nativen Paketmanager. Distributionen mit anderen Paketmanagern – etwa Alpine/APK, Gentoo/Portage, NixOS, Solus/eopkg oder Void/xbps – werden noch nicht als vollständig unterstützt bezeichnet.

## Installation

Die aktuelle Ausgabe von der [Release-Seite](https://github.com/jurkast/restlos/releases) herunterladen.

### Zorin OS, Ubuntu und Debian

Das native Debian-Paket wird über die grafische Softwareverwaltung oder vollständig im Terminal installiert. APT installiert dabei die benötigten GTK- und Python-Abhängigkeiten automatisch:

```bash
curl -LO https://github.com/jurkast/restlos/releases/download/v1.8.0/restlos-uninstaller_1.8.0-1_all.deb
curl -LO https://github.com/jurkast/restlos/releases/download/v1.8.0/restlos-uninstaller_1.8.0-1_all.deb.sha256
sha256sum --check restlos-uninstaller_1.8.0-1_all.deb.sha256
sudo apt install ./restlos-uninstaller_1.8.0-1_all.deb
```

Der Menüeintrag startet ausdrücklich die systemweite Paketversion. Falls daneben eine ältere Benutzerinstallation unter `~/.local/bin/restlos` liegt, lautet der eindeutige Terminalpfad `/usr/bin/restlos`.

### Universelles Archiv

Für Fedora, Arch Linux, openSUSE oder eine benutzerbezogene Installation:

```bash
curl -LO https://github.com/jurkast/restlos/releases/download/v1.8.0/Restlos-1.8.0.tar.gz
curl -LO https://github.com/jurkast/restlos/releases/download/v1.8.0/Restlos-1.8.0.sha256
sha256sum --check Restlos-1.8.0.sha256
tar -xzf Restlos-1.8.0.tar.gz
cd Restlos-1.8.0
./install.sh
```

Alternativ das Release grafisch entpacken, im entpackten Ordner ein Terminal öffnen und ausführen:

```bash
./install.sh
```

Danach erscheint **Restlos Uninstaller** im Anwendungsmenü. Beim universellen Archiv bleibt der updatekompatible Terminalbefehl `~/.local/bin/restlos`.

Falls GTK/PyGObject fehlt, gilt je nach Distribution einer dieser Befehle:

```bash
# Debian / Ubuntu / Zorin OS
sudo apt install python3-gi gir1.2-gtk-4.0 policykit-1

# Fedora / RHEL
sudo dnf install python3-gobject gtk4 polkit

# Arch Linux / Manjaro
sudo pacman -S python-gobject gtk4 polkit

# openSUSE
sudo zypper install python3-gobject typelib-1_0-Gtk-4_0 polkit
```

## Dateien vor dem Löschen ansehen

Ab Version 1.7.0 öffnet **Speicherorte …** beim
ausgewählten Programm eine Übersicht der bekannten Programm- und Datenpfade.
**Ordner öffnen** zeigt den jeweiligen Ordner im Standard-Dateimanager.
Direkt neben jedem Pfad im Löschplan gibt es dafür ebenfalls einen Ordnerknopf.
Dateien, AppImages, Programmstarter und symbolische Links werden nicht gestartet;
stattdessen öffnet sich ihr übergeordneter Ordner. Die Lösch-Auswahl ändert sich nicht.

Linux-Pakete können auf mehrere, teilweise gemeinsam genutzte Systemordner
verteilt sein. Diese werden nur zum Ansehen aufgelistet, nicht als zusätzliche
Löschziele ausgewählt. Fehlende Dateien, Paketabfragen und Dateimanager werden
abgefangen; bei sehr großen Paketen weist die Übersicht auf ihre Grenze von
250 Speicherorten hin. In Dateien können weitere Änderungen durch den Benutzer
im Dateimanager erfolgen; Restlos nimmt beim Öffnen selbst keine Löschung vor.

## Terminalbefehle

```bash
restlos list
restlos analyze "Programmname"
restlos analyze "Programmname" --json
restlos remove "Programmname" --yes
restlos remove "Programmname" --yes --backup
restlos remove "Programmname" --yes --trash
restlos recovery list
restlos recovery restore WIEDERHERSTELLUNGS-ID --yes
restlos --language en list
```

`remove --yes` löscht die im Plan ausgewählten Benutzerdaten dauerhaft. `--backup` sichert vorher geeignete Einstellungen und Spielstände; `--trash` verwendet stattdessen den Papierkorb. Ohne `--yes` wird nichts verändert. `--backup` und `--trash` können nicht kombiniert werden.

## Safety Backup, Wiederherstellung und Kontrollscan

In der grafischen Oberfläche ist die wiederherstellbare Entfernung die sichere Voreinstellung. Restlos verschiebt ausgewählte Benutzerdaten mit GIO in den Desktop-Papierkorb und protokolliert die genaue Papierkorb-URI zusammen mit dem ursprünglichen Pfad. Wird die endgültige Löschung ausgewählt, kann zusätzlich das standardmäßig angebotene **Safety Backup** aktiviert werden. Nach dem Beenden zugehöriger Prozesse sichert es geeignete Einstellungen, Anwendungsdaten und Spielstände vor der ersten Lösch- oder Paketaktion. Cache, Installer, Cover, Starter und eigentliche Programm- beziehungsweise Spieleordner werden nicht unnötig kopiert. Schlägt das Backup fehl, beginnt die Entfernung nicht.

Unter **Menü → Wiederherstellungszentrum …** können noch vorhandene Papierkorbdaten und Safety Backups zurückgeholt werden. Existiert am ursprünglichen Ort bereits eine Datei oder ein Ordner, verweigert Restlos das Überschreiben. Die privaten Archive liegen unter `~/.local/state/restlos/backups` und werden nicht in eine Cloud übertragen.

Nach jeder Entfernung durchsucht Restlos die bekannten Dateiquellen erneut, ohne die Paketaktion nochmals aufzurufen. Zusätzliche Treffer werden im Ergebnis als mögliche Restpfade angezeigt. Pfade, die im Löschplan bewusst abgewählt wurden, erscheinen getrennt als beibehaltene Daten.

Die Wiederherstellung betrifft ausschließlich in den Papierkorb verschobene oder im Safety Backup gesicherte Dateien und Ordner. Native Pakete, Flatpaks, Snaps sowie entfernte Einträge in Lutris- oder Heroic-Bibliotheken werden nicht automatisch erneut installiert beziehungsweise angelegt. Wird der Papierkorb außerhalb von Restlos geleert, sind die betreffenden Papierkorbdaten nicht mehr wiederherstellbar.

## Sprache

Restlos verwendet standardmäßig die Systemsprache und unterstützt Deutsch und Englisch. Unter **Menü → Sprache** kann eine Sprache dauerhaft ausgewählt werden; nach einem Neustart ist die gesamte Oberfläche umgestellt. Im Terminal gilt die Auswahl ebenfalls, kann aber für einen einzelnen Aufruf überschrieben werden, etwa mit `restlos --language en list`.

## Updates

Restlos fragt beim Programmstart standardmäßig höchstens einmal täglich die öffentlichen GitHub-Release-Metadaten ab. Ist eine neue Ausgabe vorhanden, erscheint eine Meldung mit Änderungshinweisen. Erst nach einem Klick auf **Herunterladen und installieren** wird das Archiv geladen, anhand des GitHub-Digests und der veröffentlichten SHA-256-Prüfsumme kontrolliert und in ein neues Versionsverzeichnis installiert. Die bisherige Version bleibt bei einem Fehler startfähig.

Unter **Menü → Automatisch nach Updates suchen** lässt sich die Startprüfung abschalten. **Menü → Nach Updates suchen …** prüft unabhängig vom Zeitintervall sofort. Restlos installiert keine Aktualisierung ohne ausdrückliche Bestätigung.

Der Installer ist weiterhin versionsbasiert und kann auch manuell ausgeführt werden. Eine neue lokale Ausgabe wird so installiert:

```bash
./update.sh /pfad/zu/Restlos-1.8.0.tar.gz
```

Für ein über HTTPS geladenes Release ist eine bekannte SHA-256-Prüfsumme Pflicht:

```bash
./update.sh 'https://github.com/jurkast/restlos/releases/download/v1.8.0/Restlos-1.8.0.tar.gz' '64-stellige-sha256-prüfsumme'
```

Updates werden zuerst in ein neues Versionsverzeichnis kopiert und geprüft. Erst danach wird der `current`-Symlink atomar umgeschaltet. Einstellungen und Entfernungshistorie bleiben erhalten.

## Restlos selbst entfernen

```bash
./uninstall.sh
```

Mit Einstellungen und Historie:

```bash
./uninstall.sh --purge
```

## Sicherheitsmodell

### Neue Schutzprüfung (ab Version 1.8.0)

Restlos vergleicht explizite Installationspfade, Programmstarter, App-Kennungen und Spielebibliotheksdaten mit anderen erkannten Anwendungen. Bei Überschneidungen bleibt der betroffene Pfad erhalten. Der ausklappbare Nachweis nennt Anwendung, Quelle und Referenzpfad; **Ordner öffnen** bleibt verfügbar. Ähnliche Namen allein sind kein Beleg für gemeinsame Nutzung. Unbekannte oder nicht lesbare Installationen kann diese Prüfung nicht berücksichtigen. Kein angezeigter Mitnutzer bedeutet daher nicht garantiert exklusive Nutzung.

Die Vorschau hält einen nur im Arbeitsspeicher gespeicherten Prüfstand fest. Vor dem Beenden von Prozessen, nach deren Beendigung, nach einem optionalen Backup und unmittelbar vor der jeweiligen Dateientfernung werden relevante Zustände erneut geprüft. Vor Paketaktionen werden zusätzlich der erkannte Programmbestand, Paketversionen und bei nativen Paketen die Entfernungssimulation verglichen. Bei Änderungen wird die Ausführung angehalten: **Erneut analysieren** erstellt eine neue Vorschau, löscht aber nicht automatisch weiter. Das kann auch nötig sein, wenn ein Spiel beim Beenden neue Spielstände schreibt. Ein bereits erstelltes Backup bleibt erhalten; vorher erfolgreich ausgeführte Schritte werden nicht automatisch zurückgenommen.

Die Dateiprüfung erfasst Pfad- und Verzeichnisidentität, Dateigröße, Änderungszeiten und Symlinkziele, nicht Dateiinhalte. Sie folgt keinen Symlinks innerhalb eines Löschziels. Unlesbare Bereiche, Spezialdateien, Mountpoints/Bind-Mounts und überschrittene Prüfgrenzen (höchstens 250.000 Einträge und 30 Sekunden je Pfadprüfung) sperren die Freigabe. Große Ziele können deshalb eine manuelle Prüfung außerhalb von Restlos erfordern. Es gibt keinen dauerhaften Hintergrundwächter und keine Garantie gegen jede zeitgleiche oder absichtlich manipulierte Änderung. Insbesondere Passwortabfrage und Ausführung eines externen Paketmanagers sind keine atomare Transaktion mit Restlos' vorheriger Prüfung.

### Bestehende Schutzregeln

Restlos führt niemals den Starter einer zu untersuchenden Anwendung aus. Paketkennungen werden validiert und Befehle werden als Argumentlisten statt als Shelltext gestartet. APT, DNF, pacman und Zypper müssen den vollständigen Entfernungsvorgang zuerst ohne Änderungen berechnen. Schlägt diese Vorschau fehl oder enthält sie geschützte Systempakete, wird die Paketaktion blockiert. Breite oder gemeinsam verwendete Pfade wie das Home-Verzeichnis, `.config`, `.local/share`, der gesamte Flatpak-, Steam- oder Lutris-Speicher und das Standard-Wine-Präfix sind gesperrt. Symlinks werden selbst gelöscht und nicht bis zu ihrem Ziel verfolgt. Externe Spielebibliotheken werden nur über die konkreten, vom jeweiligen Launcher registrierten Spielpfade freigegeben.

Treffer mit der Einstufung **prüfen** sind standardmäßig abgewählt. Gemeinsame Wine-Präfixe werden nicht als Ganzes gelöscht; darin wird nur ein eindeutig passender Programmordner vorgeschlagen. Für Systempakete erscheint bei Bedarf die normale PolicyKit-Passwortabfrage.

Die Wiederherstellung prüft, ob Papierkorb-URI und gespeicherter Ursprungsort weiterhin zusammengehören. Safety Backups folgen beim Erstellen keinen Symlinks, nehmen keine Spezialdateien auf, prüfen beim Wiederherstellen Archivmanifest und Pfade und bleiben innerhalb des ursprünglichen Benutzerpfads. Bereits neu angelegte Dateien und Ordner werden nicht überschrieben. Archive und Protokolle werden mit nur für den Benutzer lesbaren Rechten geschrieben.

## Technische Grenze

Kein nachträglich installierter Uninstaller kann für beliebige alte, manuell installierte Software garantiert wissen, ob eine neutral benannte Datei wie `data.bin` zu einem Programm gehört. Paketmanager, Spielebibliotheken und separate Wine-Präfixe liefern weitgehend eindeutige Zuordnungen; manuelle Alt-Installationen müssen dagegen kontrolliert zugeordnet werden. Dafür gibt es **Ordner prüfen …**. Restlos bevorzugt fehlende Treffer gegenüber dem Risiko, fremde Daten zu löschen, und zeigt den Plan immer vorab an.

Für zukünftige Erweiterungen ist die Erkennung in Scanner, Analyse und Ausführung getrennt. Weitere Paketquellen können als zusätzliche Scanner ergänzt werden.

Sicherheitsrelevante Probleme bitte nicht als öffentliches Issue mit Löschpfaden oder privaten Daten einstellen. Hinweise stehen in [SECURITY.md](SECURITY.md).

## Entwicklung und Tests

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
python3 -m compileall -q restlos
./install.sh --dry-run
```

Die Desktop-Vorlage enthält vor der Installation die Platzhalter `@EXEC@` und `@ICON@`; der Installer ersetzt beide durch absolute Pfade und validiert anschließend den erzeugten Menüeintrag.

Beiträge sind willkommen. Der Ablauf und die Qualitätsanforderungen stehen in [CONTRIBUTING.md](CONTRIBUTING.md). Mitwirkung erfolgt unter der [MIT-Lizenz](LICENSE).
