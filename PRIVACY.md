# Datenschutz

Restlos besitzt keine Telemetrie, Werbung oder Benutzerkonten. Die Erkennung und Entfernung von Anwendungen arbeitet vollständig lokal.

Wenn die standardmäßig aktivierte automatische Update-Suche eingeschaltet ist, fragt Restlos beim Programmstart höchstens einmal täglich die öffentlichen Release-Metadaten von `api.github.com` ab. Dabei werden keine lokalen Paketlisten, Dateipfade, Einstellungen oder Entfernungsergebnisse übertragen. GitHub erhält technisch bedingt die IP-Adresse und die üblichen Verbindungsdaten. Die automatische Prüfung kann jederzeit im Anwendungsmenü abgeschaltet werden.

Ein Update-Archiv wird erst nach ausdrücklicher Bestätigung heruntergeladen. Restlos akzeptiert dabei ausschließlich die festgelegten Release-Adressen des Projekts, prüft Dateiname, Version, Größe und SHA-256-Digest und installiert das Update erst nach erfolgreicher Prüfung.

Beim Einlesen werden lokale Paketinformationen, Desktop-Dateien, Spielebibliotheken und eindeutig zuordenbare Benutzerpfade verarbeitet. Ergebnisprotokolle liegen lokal unter `~/.local/state/restlos/history` und werden nicht automatisch übertragen.

Wenn Nutzer Protokolle in einem GitHub-Issue teilen, sollten Benutzernamen, Home-Pfade und andere persönliche Informationen vorher entfernt werden.
