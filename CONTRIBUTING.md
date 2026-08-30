# Zu Restlos beitragen

Danke für dein Interesse an Restlos. Wegen der dauerhaften Löschfunktionen haben Sicherheit und nachvollziehbare Tests Vorrang vor einer möglichst großen Trefferzahl.

## Entwicklungsablauf

1. Repository forken oder einen neuen Branch erstellen.
2. Eine kleine, klar abgegrenzte Änderung umsetzen.
3. Tests ergänzen, besonders bei neuen Scannern oder Löschzielen.
4. Die vollständige Prüfung lokal ausführen.
5. Einen Pull Request mit Problem, Lösung und Testnachweis öffnen.

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q restlos tests
bash -n install.sh update.sh uninstall.sh scripts/build-release.sh
./install.sh --dry-run
```

## Sicherheitsregeln für Änderungen

- Keine Anwendung oder fremde Installationsroutine während der Analyse starten.
- Niemals Shelltext aus Anwendungsnamen, Paketkennungen oder Dateipfaden zusammensetzen.
- Gemeinsame Verzeichnisse und Präfixe nicht als Ziel eines einzelnen Programms markieren.
- Neue externe Pfade nur aus verifizierbaren Manager-Metadaten übernehmen.
- Unsichere Treffer standardmäßig abwählen.
- Interne Verwaltungsdaten erst ändern, nachdem zugehörige Dateien erfolgreich entfernt wurden.
- Für jeden neuen Manager mindestens einen realistischen Testdatensatz und einen Schutztest ergänzen.

## Versionen und Releases

Restlos verwendet semantische Versionen `MAJOR.MINOR.PATCH`. Die Versionen in `restlos/__init__.py`, `pyproject.toml`, `manifest.json` und `CHANGELOG.md` müssen übereinstimmen. Release-Archive werden ausschließlich mit `scripts/build-release.sh` oder der GitHub-Release-Automatisierung erzeugt.

## Sprache

Benutzertexte sind derzeit überwiegend Deutsch. Neue Oberflächentexte sollten klar formuliert sein; englische Dokumentation ist ebenfalls willkommen. Vollständige Lokalisierung ist als eigene Erweiterung vorgesehen.

Mit einem Beitrag erklärst du dich damit einverstanden, ihn unter der MIT-Lizenz des Projekts zu veröffentlichen.
