#!/usr/bin/env bash

set -euo pipefail

RESTLOS_SOURCE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RESTLOS_PYTHON="${RESTLOS_PYTHON:-python3}"
RESTLOS_DRY_RUN=0

usage()
{
    printf '%s\n' \
        "Restlos Uninstaller für den aktuellen Benutzer installieren oder aktualisieren." \
        "" \
        "Aufruf: ./install.sh [--dry-run]"
}

while (( $# > 0 ))
do
    case "$1" in
        --dry-run)
            RESTLOS_DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Unbekannte Option: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if ! command -v "$RESTLOS_PYTHON" >/dev/null 2>&1
then
    printf '%s\n' "Python 3 wurde nicht gefunden." >&2
    exit 1
fi

RESTLOS_VERSION="$($RESTLOS_PYTHON -I -B -c \
    'import pathlib,re,sys; text=pathlib.Path(sys.argv[1]).read_text(); match=re.search(r"^__version__ = \"([^\"]+)\"", text, re.M); print(match.group(1) if match else "")' \
    "${RESTLOS_SOURCE_ROOT}/restlos/__init__.py")"
if [[ ! "$RESTLOS_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
then
    printf '%s\n' "Die Restlos-Version konnte nicht gelesen werden." >&2
    exit 1
fi

RESTLOS_USER_HOME="${RESTLOS_TEST_HOME:-${HOME}}"
if [[ -n "${RESTLOS_TEST_HOME:-}" ]]
then
    RESTLOS_DATA_HOME="${RESTLOS_USER_HOME}/.local/share"
else
    RESTLOS_DATA_HOME="${XDG_DATA_HOME:-${RESTLOS_USER_HOME}/.local/share}"
fi
RESTLOS_BIN_HOME="${RESTLOS_USER_HOME}/.local/bin"
RESTLOS_APP_HOME="${RESTLOS_DATA_HOME}/restlos"
RESTLOS_RELEASES_HOME="${RESTLOS_APP_HOME}/releases"
RESTLOS_RELEASE_HOME="${RESTLOS_RELEASES_HOME}/${RESTLOS_VERSION}"
RESTLOS_APPLICATIONS_HOME="${RESTLOS_DATA_HOME}/applications"
RESTLOS_PIXMAPS_HOME="${RESTLOS_DATA_HOME}/pixmaps"
RESTLOS_DESKTOP_PATH="${RESTLOS_APPLICATIONS_HOME}/io.github.jurkast.Restlos.desktop"
RESTLOS_ICON_PATH="${RESTLOS_PIXMAPS_HOME}/io.github.jurkast.Restlos.svg"
RESTLOS_COMMAND_PATH="${RESTLOS_BIN_HOME}/restlos"

case "$RESTLOS_APP_HOME" in
    ""|"/"|"${RESTLOS_USER_HOME}"|"${RESTLOS_DATA_HOME}")
        printf 'Unsicheres Installationsziel abgelehnt: %s\n' "$RESTLOS_APP_HOME" >&2
        exit 1
        ;;
esac

for required in \
    "restlos/__init__.py" \
    "restlos/gui.py" \
    "restlos/analyzer.py" \
    "restlos/package_managers.py" \
    "restlos/recovery.py" \
    "restlos/updater.py" \
    "restlos/game_scanners.py" \
    "run_restlos.py" \
    "assets/restlos-wrapper" \
    "assets/io.github.jurkast.Restlos.desktop.in" \
    "assets/io.github.jurkast.Restlos.svg"
do
    if [[ ! -f "${RESTLOS_SOURCE_ROOT}/${required}" ]]
    then
        printf 'Installationsquelle ist unvollständig: %s\n' "$required" >&2
        exit 1
    fi
done

if ! "$RESTLOS_PYTHON" -c \
    'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
then
    printf '%s\n' "Restlos benötigt Python 3.10 oder neuer." >&2
    exit 1
fi

if ! "$RESTLOS_PYTHON" -c \
    'import gi; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk' >/dev/null 2>&1
then
    if command -v apt-get >/dev/null 2>&1
    then
        RESTLOS_DEPENDENCY_COMMAND="sudo apt install python3-gi gir1.2-gtk-4.0 policykit-1"
    elif command -v dnf5 >/dev/null 2>&1
    then
        RESTLOS_DEPENDENCY_COMMAND="sudo dnf5 install python3-gobject gtk4 polkit"
    elif command -v dnf >/dev/null 2>&1
    then
        RESTLOS_DEPENDENCY_COMMAND="sudo dnf install python3-gobject gtk4 polkit"
    elif command -v pacman >/dev/null 2>&1
    then
        RESTLOS_DEPENDENCY_COMMAND="sudo pacman -S python-gobject gtk4 polkit"
    elif command -v zypper >/dev/null 2>&1
    then
        RESTLOS_DEPENDENCY_COMMAND="sudo zypper install python3-gobject typelib-1_0-Gtk-4_0 polkit"
    else
        RESTLOS_DEPENDENCY_COMMAND="Installiere Python-PyGObject, GTK 4 und PolicyKit mit dem Paketmanager deiner Distribution."
    fi
    printf '%s\n' \
        "GTK 4/PyGObject fehlt. Passender Installationshinweis:" \
        "  ${RESTLOS_DEPENDENCY_COMMAND}" >&2
    exit 1
fi

printf '%s\n' \
    "Restlos Uninstaller ${RESTLOS_VERSION} wird für den aktuellen Benutzer installiert." \
    "  Programm: ${RESTLOS_APP_HOME}" \
    "  Befehl:   ${RESTLOS_COMMAND_PATH}" \
    "  Menü:     ${RESTLOS_DESKTOP_PATH}"

if (( RESTLOS_DRY_RUN == 1 ))
then
    exit 0
fi

install -d -m 0755 \
    "$RESTLOS_RELEASES_HOME" \
    "$RESTLOS_BIN_HOME" \
    "$RESTLOS_APPLICATIONS_HOME" \
    "$RESTLOS_PIXMAPS_HOME"

RESTLOS_STAGING_HOME="${RESTLOS_RELEASES_HOME}/.${RESTLOS_VERSION}.$$.staging"
RESTLOS_REPLACED_HOME="${RESTLOS_RELEASES_HOME}/.${RESTLOS_VERSION}.$$.replaced"
if [[ -e "$RESTLOS_STAGING_HOME" || -L "$RESTLOS_STAGING_HOME" ]]
then
    printf 'Temporäres Installationsziel existiert bereits: %s\n' "$RESTLOS_STAGING_HOME" >&2
    exit 1
fi
install -d -m 0755 "$RESTLOS_STAGING_HOME"
cp -a -- "${RESTLOS_SOURCE_ROOT}/restlos" "$RESTLOS_STAGING_HOME/restlos"
install -m 0755 "${RESTLOS_SOURCE_ROOT}/run_restlos.py" "$RESTLOS_STAGING_HOME/run_restlos.py"
find "$RESTLOS_STAGING_HOME/restlos" -type d -name __pycache__ -prune -exec rm -r -- {} +
find "$RESTLOS_STAGING_HOME/restlos" -type f -name '*.py' -exec chmod 0644 {} +

if ! "$RESTLOS_PYTHON" -I -B -c \
    'import sys; sys.path.insert(0, sys.argv[1]); import restlos, restlos.cli, restlos.gui; raise SystemExit(0 if restlos.__version__ == sys.argv[2] else 1)' \
    "$RESTLOS_STAGING_HOME" "$RESTLOS_VERSION"
then
    rm -r -- "$RESTLOS_STAGING_HOME"
    printf '%s\n' "Die installierte Kopie hat die Selbstprüfung nicht bestanden." >&2
    exit 1
fi

if [[ -e "$RESTLOS_RELEASE_HOME" || -L "$RESTLOS_RELEASE_HOME" ]]
then
    mv -- "$RESTLOS_RELEASE_HOME" "$RESTLOS_REPLACED_HOME"
fi
if ! mv -- "$RESTLOS_STAGING_HOME" "$RESTLOS_RELEASE_HOME"
then
    if [[ -d "$RESTLOS_REPLACED_HOME" ]]
    then
        mv -- "$RESTLOS_REPLACED_HOME" "$RESTLOS_RELEASE_HOME"
    fi
    exit 1
fi
if [[ -d "$RESTLOS_REPLACED_HOME" ]]
then
    rm -r -- "$RESTLOS_REPLACED_HOME"
fi

RESTLOS_CURRENT_LINK="${RESTLOS_APP_HOME}/.current.$$.tmp"
ln -s -- "releases/${RESTLOS_VERSION}" "$RESTLOS_CURRENT_LINK"
mv -Tf -- "$RESTLOS_CURRENT_LINK" "${RESTLOS_APP_HOME}/current"

install -m 0755 "${RESTLOS_SOURCE_ROOT}/assets/restlos-wrapper" "$RESTLOS_COMMAND_PATH"
install -m 0644 "${RESTLOS_SOURCE_ROOT}/assets/io.github.jurkast.Restlos.svg" "$RESTLOS_ICON_PATH"

RESTLOS_EXEC_SED="$(printf '%s' "$RESTLOS_COMMAND_PATH" | sed 's/[|&]/\\&/g')"
RESTLOS_ICON_SED="$(printf '%s' "$RESTLOS_ICON_PATH" | sed 's/[|&]/\\&/g')"
RESTLOS_DESKTOP_TEMP="${RESTLOS_APPLICATIONS_HOME}/.io.github.jurkast.Restlos.$$.desktop"
sed \
    -e "s|@EXEC@|${RESTLOS_EXEC_SED}|g" \
    -e "s|@ICON@|${RESTLOS_ICON_SED}|g" \
    "${RESTLOS_SOURCE_ROOT}/assets/io.github.jurkast.Restlos.desktop.in" > "$RESTLOS_DESKTOP_TEMP"
chmod 0644 "$RESTLOS_DESKTOP_TEMP"
mv -f -- "$RESTLOS_DESKTOP_TEMP" "$RESTLOS_DESKTOP_PATH"

# Frühere Ausgaben verwendeten die alte GitHub-Kennung oder eine provisorische App-ID.
rm -f -- \
    "${RESTLOS_APPLICATIONS_HOME}/io.github.jurkastl.Restlos.desktop" \
    "${RESTLOS_PIXMAPS_HOME}/io.github.jurkastl.Restlos.svg" \
    "${RESTLOS_APPLICATIONS_HOME}/io.github.local.Restlos.desktop" \
    "${RESTLOS_PIXMAPS_HOME}/io.github.local.Restlos.svg"

if command -v desktop-file-validate >/dev/null 2>&1
then
    desktop-file-validate "$RESTLOS_DESKTOP_PATH"
fi
if command -v update-desktop-database >/dev/null 2>&1
then
    update-desktop-database "$RESTLOS_APPLICATIONS_HOME" >/dev/null 2>&1 || true
fi

printf '%s\n' \
    "Installation abgeschlossen." \
    "Starte Restlos Uninstaller über das Anwendungsmenü oder mit: ${RESTLOS_COMMAND_PATH}"
