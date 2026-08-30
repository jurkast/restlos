# Restlos

[![Tests](https://github.com/jurkastl/restlos/actions/workflows/ci.yml/badge.svg)](https://github.com/jurkastl/restlos/actions/workflows/ci.yml)
[![GitHub Release](https://img.shields.io/github/v/release/jurkastl/restlos?include_prereleases)](https://github.com/jurkastl/restlos/releases)
[![Lizenz: MIT](https://img.shields.io/badge/Lizenz-MIT-blue.svg)](LICENSE)

[English](README.en.md) · [Downloads](https://github.com/jurkastl/restlos/releases) · [Fehler melden](https://github.com/jurkastl/restlos/issues)

Restlos ist ein grafischer App-Deinstaller für die großen Linux-Distributionsfamilien. Die Anwendung führt Programme aus mehreren Installationssystemen in einer Oberfläche zusammen und erstellt vor jeder Entfernung einen sichtbaren, abwählbaren Löschplan.

> **Öffentliche Beta:** Restlos kann Daten dauerhaft löschen. Prüfe den angezeigten Löschplan aufmerksam und sichere wichtige Spielstände und Dateien vorher.

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
- entfernt native Pakete über APT, DNF, pacman oder Zypper sowie Flatpaks mit `--delete-data` und Snaps mit `--purge`
- simuliert jede native Paketentfernung und blockiert sie, falls kritische Systemkomponenten betroffen wären
- erkennt laufende Prozesse innerhalb der ausgewählten Programmordner
- unterstützt dauerhafte Löschung oder den Papierkorb
- schreibt ein minimales Ergebnisprotokoll nach `~/.local/state/restlos/history`
- bietet zusätzlich eine Terminaloberfläche für Listen und Löschpläne

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

Die aktuelle Ausgabe von der [Release-Seite](https://github.com/jurkastl/restlos/releases) herunterladen. Für Version 1.2.0 geht es auch vollständig im Terminal:

```bash
curl -LO https://github.com/jurkastl/restlos/releases/download/v1.2.0/Restlos-1.2.0.tar.gz
curl -LO https://github.com/jurkastl/restlos/releases/download/v1.2.0/Restlos-1.2.0.sha256
sha256sum --check Restlos-1.2.0.sha256
tar -xzf Restlos-1.2.0.tar.gz
cd Restlos-1.2.0
./install.sh
```

Alternativ das Release grafisch entpacken, im entpackten Ordner ein Terminal öffnen und ausführen:

```bash
./install.sh
```

Danach erscheint **Restlos** im Anwendungsmenü. Alternativ lässt es sich mit `~/.local/bin/restlos` starten.

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

## Terminalbefehle

```bash
restlos list
restlos analyze "Programmname"
restlos analyze "Programmname" --json
restlos remove "Programmname" --yes
restlos remove "Programmname" --yes --trash
```

`remove --yes` löscht die im Plan ausgewählten Benutzerdaten dauerhaft. Ohne `--yes` wird nichts verändert.

## Updates

Der Installer ist versionsbasiert und kann jederzeit erneut ausgeführt werden. Eine neue lokale Ausgabe wird so installiert:

```bash
./update.sh /pfad/zu/Restlos-1.2.0.tar.gz
```

Für ein über HTTPS geladenes Release ist eine bekannte SHA-256-Prüfsumme Pflicht:

```bash
./update.sh 'https://github.com/jurkastl/restlos/releases/download/v1.2.0/Restlos-1.2.0.tar.gz' '64-stellige-sha256-prüfsumme'
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

Restlos führt niemals den Starter einer zu untersuchenden Anwendung aus. Paketkennungen werden validiert und Befehle werden als Argumentlisten statt als Shelltext gestartet. APT, DNF, pacman und Zypper müssen den vollständigen Entfernungsvorgang zuerst ohne Änderungen berechnen. Schlägt diese Vorschau fehl oder enthält sie geschützte Systempakete, wird die Paketaktion blockiert. Breite oder gemeinsam verwendete Pfade wie das Home-Verzeichnis, `.config`, `.local/share`, der gesamte Flatpak-, Steam- oder Lutris-Speicher und das Standard-Wine-Präfix sind gesperrt. Symlinks werden selbst gelöscht und nicht bis zu ihrem Ziel verfolgt. Externe Spielebibliotheken werden nur über die konkreten, vom jeweiligen Launcher registrierten Spielpfade freigegeben.

Treffer mit der Einstufung **prüfen** sind standardmäßig abgewählt. Gemeinsame Wine-Präfixe werden nicht als Ganzes gelöscht; darin wird nur ein eindeutig passender Programmordner vorgeschlagen. Für Systempakete erscheint bei Bedarf die normale PolicyKit-Passwortabfrage.

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
