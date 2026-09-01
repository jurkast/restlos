#!/usr/bin/env bash

set -euo pipefail

RESTLOS_PURGE=0
if [[ "${1:-}" == "--purge" ]]
then
    RESTLOS_PURGE=1
elif (( $# > 0 ))
then
    printf '%s\n' "Aufruf: ./uninstall.sh [--purge]" >&2
    exit 2
fi

RESTLOS_USER_HOME="${RESTLOS_TEST_HOME:-${HOME}}"
if [[ -n "${RESTLOS_TEST_HOME:-}" ]]
then
    RESTLOS_DATA_HOME="${RESTLOS_USER_HOME}/.local/share"
    RESTLOS_STATE_HOME="${RESTLOS_USER_HOME}/.local/state"
    RESTLOS_CONFIG_HOME="${RESTLOS_USER_HOME}/.config"
else
    RESTLOS_DATA_HOME="${XDG_DATA_HOME:-${RESTLOS_USER_HOME}/.local/share}"
    RESTLOS_STATE_HOME="${XDG_STATE_HOME:-${RESTLOS_USER_HOME}/.local/state}"
    RESTLOS_CONFIG_HOME="${XDG_CONFIG_HOME:-${RESTLOS_USER_HOME}/.config}"
fi
RESTLOS_APP_HOME="${RESTLOS_DATA_HOME}/restlos"
RESTLOS_COMMAND_PATH="${RESTLOS_USER_HOME}/.local/bin/restlos"
RESTLOS_DESKTOP_PATH="${RESTLOS_DATA_HOME}/applications/io.github.jurkast.Restlos.desktop"
RESTLOS_ICON_PATH="${RESTLOS_DATA_HOME}/pixmaps/io.github.jurkast.Restlos.svg"

case "$RESTLOS_APP_HOME" in
    ""|"/"|"${RESTLOS_USER_HOME}"|"${RESTLOS_DATA_HOME}")
        printf 'Unsicheres Deinstallationsziel abgelehnt: %s\n' "$RESTLOS_APP_HOME" >&2
        exit 1
        ;;
esac

case "$RESTLOS_STATE_HOME" in
    ""|"/"|"${RESTLOS_USER_HOME}")
        printf 'Unsicheres Statusdatenziel abgelehnt: %s\n' "$RESTLOS_STATE_HOME" >&2
        exit 1
        ;;
esac

rm -rf -- \
    "$RESTLOS_APP_HOME" \
    "$RESTLOS_COMMAND_PATH" \
    "$RESTLOS_DESKTOP_PATH" \
    "$RESTLOS_ICON_PATH" \
    "${RESTLOS_DATA_HOME}/applications/io.github.jurkastl.Restlos.desktop" \
    "${RESTLOS_DATA_HOME}/pixmaps/io.github.jurkastl.Restlos.svg" \
    "${RESTLOS_DATA_HOME}/applications/io.github.local.Restlos.desktop" \
    "${RESTLOS_DATA_HOME}/pixmaps/io.github.local.Restlos.svg"

if (( RESTLOS_PURGE == 1 ))
then
    rm -rf -- \
        "${RESTLOS_CONFIG_HOME}/restlos" \
        "${RESTLOS_USER_HOME}/.cache/restlos" \
        "${RESTLOS_STATE_HOME}/restlos"
    printf '%s\n' "Restlos Uninstaller einschließlich Einstellungen und Historie wurde entfernt."
else
    printf '%s\n' \
        "Restlos Uninstaller wurde entfernt." \
        "Die Entfernungshistorie bleibt erhalten. Für vollständiges Löschen: ./uninstall.sh --purge"
fi

if command -v update-desktop-database >/dev/null 2>&1
then
    update-desktop-database "${RESTLOS_DATA_HOME}/applications" >/dev/null 2>&1 || true
fi
