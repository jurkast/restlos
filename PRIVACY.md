# Datenschutz

Restlos besitzt keine Telemetrie, Werbung oder Benutzerkonten. Die Erkennung und Entfernung von Anwendungen arbeitet vollständig lokal.

Wenn die standardmäßig aktivierte automatische Update-Suche eingeschaltet ist, fragt Restlos beim Programmstart höchstens einmal täglich die öffentlichen Release-Metadaten von `api.github.com` ab. Dabei werden keine lokalen Paketlisten, Dateipfade, Einstellungen oder Entfernungsergebnisse übertragen. GitHub erhält technisch bedingt die IP-Adresse und die üblichen Verbindungsdaten. Die automatische Prüfung kann jederzeit im Anwendungsmenü abgeschaltet werden.

Ein Update-Archiv wird erst nach ausdrücklicher Bestätigung heruntergeladen. Restlos akzeptiert dabei ausschließlich die festgelegten Release-Adressen des Projekts, prüft Dateiname, Version, Größe und SHA-256-Digest und installiert das Update erst nach erfolgreicher Prüfung.

Beim Einlesen werden lokale Paketinformationen, Desktop-Dateien, Spielebibliotheken und eindeutig zuordenbare Benutzerpfade verarbeitet. Ergebnisprotokolle liegen lokal unter `~/.local/state/restlos/history` und werden nicht automatisch übertragen. Bei einer wiederherstellbaren Entfernung enthalten sie außerdem die ursprünglichen Pfade und die zugehörigen lokalen Papierkorb-URIs. Diese Angaben benötigt das Wiederherstellungszentrum und sie verlassen den Rechner nicht.

Wenn vor einer endgültigen Löschung das optionale **Safety Backup** aktiviert ist, legt Restlos eine lokale Kopie geeigneter Einstellungen, Anwendungsdaten und Spielstände unter `~/.local/state/restlos/backups` an. Archive und Protokolle sind nur für das Benutzerkonto lesbar, werden nicht hochgeladen und sind nicht zusätzlich verschlüsselt. Wer das Benutzerkonto oder die unverschlüsselte Festplatte lesen kann, kann daher auch diese Sicherungen lesen. `./uninstall.sh --purge` entfernt Einstellungen, Protokolle und Safety Backups gemeinsam.

Wenn Nutzer Protokolle in einem GitHub-Issue teilen, sollten Benutzernamen, Home-Pfade und andere persönliche Informationen vorher entfernt werden.
