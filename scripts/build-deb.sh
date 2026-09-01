#!/usr/bin/env bash

set -euo pipefail

RESTLOS_PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
RESTLOS_OUTPUT_ROOT="${1:-${RESTLOS_PROJECT_ROOT}/dist}"
RESTLOS_PYTHON="${RESTLOS_PYTHON:-python3}"
RESTLOS_DEBIAN_REVISION="${RESTLOS_DEBIAN_REVISION:-1}"

for command in dpkg-deb gzip sed
do
    if ! command -v "$command" >/dev/null 2>&1
    then
        printf 'Benötigter Befehl fehlt: %s\n' "$command" >&2
        exit 1
    fi
done

RESTLOS_VERSION="$($RESTLOS_PYTHON -I -B -c \
    'import pathlib,re,sys; text=pathlib.Path(sys.argv[1]).read_text(); match=re.search(r"^__version__ = \"([^\"]+)\"", text, re.M); print(match.group(1) if match else "")' \
    "${RESTLOS_PROJECT_ROOT}/restlos/__init__.py")"
if [[ ! "$RESTLOS_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ || ! "$RESTLOS_DEBIAN_REVISION" =~ ^[1-9][0-9]*$ ]]
then
    printf '%s\n' "Ungültige Debian-Paketversion." >&2
    exit 1
fi

RESTLOS_SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-}"
if [[ -z "$RESTLOS_SOURCE_DATE_EPOCH" ]] && command -v git >/dev/null 2>&1
then
    RESTLOS_SOURCE_DATE_EPOCH="$(git -C "$RESTLOS_PROJECT_ROOT" log -1 --format=%ct 2>/dev/null || true)"
fi
RESTLOS_SOURCE_DATE_EPOCH="${RESTLOS_SOURCE_DATE_EPOCH:-0}"
if [[ ! "$RESTLOS_SOURCE_DATE_EPOCH" =~ ^[0-9]+$ ]]
then
    printf '%s\n' "SOURCE_DATE_EPOCH ist ungültig." >&2
    exit 1
fi

RESTLOS_DEBIAN_VERSION="${RESTLOS_VERSION}-${RESTLOS_DEBIAN_REVISION}"
RESTLOS_RELEASE_DATE="$(date --utc --date="@${RESTLOS_SOURCE_DATE_EPOCH}" +%F)"
RESTLOS_TEMP_ROOT="$(mktemp -d -t restlos-deb.XXXXXXXX)"
cleanup()
{
    case "$RESTLOS_TEMP_ROOT" in
        /tmp/restlos-deb.*)
            rm -rf -- "$RESTLOS_TEMP_ROOT"
            ;;
    esac
}
trap cleanup EXIT

RESTLOS_PACKAGE_ROOT="${RESTLOS_TEMP_ROOT}/root"
RESTLOS_DOC_ROOT="${RESTLOS_PACKAGE_ROOT}/usr/share/doc/restlos-uninstaller"
install -d -m 0755 \
    "${RESTLOS_PACKAGE_ROOT}/DEBIAN" \
    "${RESTLOS_PACKAGE_ROOT}/usr/bin" \
    "${RESTLOS_PACKAGE_ROOT}/usr/lib/restlos" \
    "${RESTLOS_PACKAGE_ROOT}/usr/share/applications" \
    "${RESTLOS_PACKAGE_ROOT}/usr/share/icons/hicolor/scalable/apps" \
    "${RESTLOS_PACKAGE_ROOT}/usr/share/metainfo" \
    "$RESTLOS_DOC_ROOT" \
    "$RESTLOS_OUTPUT_ROOT"

cp -a -- "${RESTLOS_PROJECT_ROOT}/restlos" "${RESTLOS_PACKAGE_ROOT}/usr/lib/restlos/restlos"
install -m 0755 "${RESTLOS_PROJECT_ROOT}/run_restlos.py" "${RESTLOS_PACKAGE_ROOT}/usr/lib/restlos/run_restlos.py"
install -m 0755 "${RESTLOS_PROJECT_ROOT}/packaging/debian/restlos-wrapper" "${RESTLOS_PACKAGE_ROOT}/usr/bin/restlos"
install -m 0644 "${RESTLOS_PROJECT_ROOT}/assets/io.github.jurkast.Restlos.svg" \
    "${RESTLOS_PACKAGE_ROOT}/usr/share/icons/hicolor/scalable/apps/io.github.jurkast.Restlos.svg"

sed \
    -e 's|@EXEC@|/usr/bin/restlos|g' \
    -e 's|@ICON@|io.github.jurkast.Restlos|g' \
    "${RESTLOS_PROJECT_ROOT}/assets/io.github.jurkast.Restlos.desktop.in" \
    > "${RESTLOS_PACKAGE_ROOT}/usr/share/applications/io.github.jurkast.Restlos.desktop"
chmod 0644 "${RESTLOS_PACKAGE_ROOT}/usr/share/applications/io.github.jurkast.Restlos.desktop"

sed \
    -e "s|@VERSION@|${RESTLOS_VERSION}|g" \
    -e "s|@DATE@|${RESTLOS_RELEASE_DATE}|g" \
    "${RESTLOS_PROJECT_ROOT}/assets/io.github.jurkast.Restlos.metainfo.xml.in" \
    > "${RESTLOS_PACKAGE_ROOT}/usr/share/metainfo/io.github.jurkast.Restlos.metainfo.xml"
chmod 0644 "${RESTLOS_PACKAGE_ROOT}/usr/share/metainfo/io.github.jurkast.Restlos.metainfo.xml"

install -m 0644 "${RESTLOS_PROJECT_ROOT}/README.md" "$RESTLOS_DOC_ROOT/README.md"
install -m 0644 "${RESTLOS_PROJECT_ROOT}/README.en.md" "$RESTLOS_DOC_ROOT/README.en.md"
install -m 0644 "${RESTLOS_PROJECT_ROOT}/packaging/debian/copyright" "$RESTLOS_DOC_ROOT/copyright"
gzip -9 -n -c "${RESTLOS_PROJECT_ROOT}/CHANGELOG.md" > "$RESTLOS_DOC_ROOT/changelog.gz"

find "$RESTLOS_PACKAGE_ROOT" -type d -exec chmod 0755 {} +
find "${RESTLOS_PACKAGE_ROOT}/usr/lib/restlos" -type d -name __pycache__ -prune -exec rm -r -- {} +
find "${RESTLOS_PACKAGE_ROOT}/usr/lib/restlos" -type f -name '*.pyc' -delete
find "${RESTLOS_PACKAGE_ROOT}/usr/lib/restlos/restlos" -type f -name '*.py' -exec chmod 0644 {} +
chmod 0644 "$RESTLOS_DOC_ROOT/changelog.gz"

RESTLOS_INSTALLED_SIZE="$(du -sk "${RESTLOS_PACKAGE_ROOT}/usr" | awk '{print $1}')"
sed \
    -e "s|@DEBIAN_VERSION@|${RESTLOS_DEBIAN_VERSION}|g" \
    -e "s|@INSTALLED_SIZE@|${RESTLOS_INSTALLED_SIZE}|g" \
    "${RESTLOS_PROJECT_ROOT}/packaging/debian/control.in" \
    > "${RESTLOS_PACKAGE_ROOT}/DEBIAN/control"
chmod 0644 "${RESTLOS_PACKAGE_ROOT}/DEBIAN/control"

if command -v desktop-file-validate >/dev/null 2>&1
then
    desktop-file-validate "${RESTLOS_PACKAGE_ROOT}/usr/share/applications/io.github.jurkast.Restlos.desktop"
fi
if command -v appstreamcli >/dev/null 2>&1
then
    appstreamcli validate --no-net "${RESTLOS_PACKAGE_ROOT}/usr/share/metainfo/io.github.jurkast.Restlos.metainfo.xml"
fi

RESTLOS_PACKAGE_PATH="${RESTLOS_OUTPUT_ROOT}/restlos-uninstaller_${RESTLOS_DEBIAN_VERSION}_all.deb"
RESTLOS_CHECKSUM_PATH="${RESTLOS_PACKAGE_PATH}.sha256"
rm -f -- "$RESTLOS_PACKAGE_PATH" "$RESTLOS_CHECKSUM_PATH"
SOURCE_DATE_EPOCH="$RESTLOS_SOURCE_DATE_EPOCH" dpkg-deb \
    --build \
    --root-owner-group \
    -Zxz \
    -z9 \
    "$RESTLOS_PACKAGE_ROOT" \
    "$RESTLOS_PACKAGE_PATH"
(
    cd -- "$RESTLOS_OUTPUT_ROOT"
    sha256sum "$(basename -- "$RESTLOS_PACKAGE_PATH")" > "$(basename -- "$RESTLOS_CHECKSUM_PATH")"
)

printf '%s\n' \
    "Debian-Paket erstellt:" \
    "  ${RESTLOS_PACKAGE_PATH}" \
    "  ${RESTLOS_CHECKSUM_PATH}"
