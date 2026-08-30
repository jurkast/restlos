#!/usr/bin/env bash

set -euo pipefail

usage()
{
    printf '%s\n' \
        "Restlos aus einer neuen Quellkopie oder einem Release-Archiv aktualisieren." \
        "" \
        "Lokal:  ./update.sh /pfad/zu/restlos-1.4.0.tar.gz [SHA256]" \
        "Ordner: ./update.sh /pfad/zu/restlos-1.4.0" \
        "Web:    ./update.sh https://server/restlos-1.4.0.tar.gz SHA256" \
        "" \
        "Bei Web-Downloads ist die erwartete SHA-256-Prüfsumme Pflicht."
}

if (( $# < 1 || $# > 2 ))
then
    usage >&2
    exit 2
fi

RESTLOS_UPDATE_SOURCE="$1"
RESTLOS_EXPECTED_SHA="${2:-}"

if [[ -d "$RESTLOS_UPDATE_SOURCE" ]]
then
    if [[ ! -x "${RESTLOS_UPDATE_SOURCE}/install.sh" ]]
    then
        printf '%s\n' "Im angegebenen Ordner fehlt install.sh." >&2
        exit 1
    fi
    exec "${RESTLOS_UPDATE_SOURCE}/install.sh"
fi

RESTLOS_UPDATE_TEMP="$(mktemp -d -t restlos-update.XXXXXXXX)"
cleanup()
{
    case "$RESTLOS_UPDATE_TEMP" in
        /tmp/restlos-update.*)
            rm -rf -- "$RESTLOS_UPDATE_TEMP"
            ;;
    esac
}
trap cleanup EXIT

RESTLOS_ARCHIVE="$RESTLOS_UPDATE_SOURCE"
case "$RESTLOS_UPDATE_SOURCE" in
    https://*|http://*)
        if [[ ! "$RESTLOS_EXPECTED_SHA" =~ ^[a-fA-F0-9]{64}$ ]]
        then
            printf '%s\n' "Web-Updates benötigen eine gültige SHA-256-Prüfsumme." >&2
            exit 1
        fi
        if ! command -v curl >/dev/null 2>&1
        then
            printf '%s\n' "curl wird für Web-Updates benötigt." >&2
            exit 1
        fi
        RESTLOS_ARCHIVE="${RESTLOS_UPDATE_TEMP}/release.archive"
        curl --fail --location --proto '=https' --tlsv1.2 \
            --output "$RESTLOS_ARCHIVE" "$RESTLOS_UPDATE_SOURCE"
        ;;
esac

if [[ ! -f "$RESTLOS_ARCHIVE" ]]
then
    printf 'Release-Archiv nicht gefunden: %s\n' "$RESTLOS_ARCHIVE" >&2
    exit 1
fi
if [[ -n "$RESTLOS_EXPECTED_SHA" ]]
then
    if [[ ! "$RESTLOS_EXPECTED_SHA" =~ ^[a-fA-F0-9]{64}$ ]]
    then
        printf '%s\n' "Ungültige SHA-256-Prüfsumme." >&2
        exit 1
    fi
    printf '%s  %s\n' "$RESTLOS_EXPECTED_SHA" "$RESTLOS_ARCHIVE" | sha256sum --check --status
    printf '%s\n' "SHA-256-Prüfung erfolgreich."
fi

RESTLOS_EXTRACT_HOME="${RESTLOS_UPDATE_TEMP}/extract"
mkdir -p "$RESTLOS_EXTRACT_HOME"
if tar -tf "$RESTLOS_ARCHIVE" >/dev/null 2>&1
then
    if tar -tf "$RESTLOS_ARCHIVE" | grep -Eq '(^/|(^|/)\.\.(/|$))'
    then
        printf '%s\n' "Unsichere Pfade im Release-Archiv erkannt." >&2
        exit 1
    fi
    tar -xf "$RESTLOS_ARCHIVE" -C "$RESTLOS_EXTRACT_HOME"
elif command -v unzip >/dev/null 2>&1 && unzip -tq "$RESTLOS_ARCHIVE" >/dev/null 2>&1
then
    if unzip -Z1 "$RESTLOS_ARCHIVE" | grep -Eq '(^/|(^|/)\.\.(/|$))'
    then
        printf '%s\n' "Unsichere Pfade im Release-Archiv erkannt." >&2
        exit 1
    fi
    unzip -q "$RESTLOS_ARCHIVE" -d "$RESTLOS_EXTRACT_HOME"
else
    printf '%s\n' "Unbekanntes oder beschädigtes Release-Archiv." >&2
    exit 1
fi

RESTLOS_INSTALLER="$(find "$RESTLOS_EXTRACT_HOME" -maxdepth 3 -type f -name install.sh -print -quit)"
if [[ -z "$RESTLOS_INSTALLER" ]]
then
    printf '%s\n' "Das Release enthält keinen Installer." >&2
    exit 1
fi
chmod 0755 "$RESTLOS_INSTALLER"
"$RESTLOS_INSTALLER"
