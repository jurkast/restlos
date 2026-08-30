#!/usr/bin/env bash

set -euo pipefail

RESTLOS_PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
RESTLOS_OUTPUT_ROOT="${1:-${RESTLOS_PROJECT_ROOT}/dist}"
RESTLOS_PYTHON="${RESTLOS_PYTHON:-python3}"

RESTLOS_VERSION="$($RESTLOS_PYTHON -I -B -c \
    'import pathlib,re,sys; text=pathlib.Path(sys.argv[1]).read_text(); match=re.search(r"^__version__ = \"([^\"]+)\"", text, re.M); print(match.group(1) if match else "")' \
    "${RESTLOS_PROJECT_ROOT}/restlos/__init__.py")"
if [[ ! "$RESTLOS_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
then
    printf '%s\n' "Ungültige Restlos-Version." >&2
    exit 1
fi

RESTLOS_MANIFEST_VERSION="$($RESTLOS_PYTHON -I -B -c \
    'import json,pathlib,sys; print(json.loads(pathlib.Path(sys.argv[1]).read_text())["version"])' \
    "${RESTLOS_PROJECT_ROOT}/manifest.json")"
RESTLOS_PROJECT_VERSION="$($RESTLOS_PYTHON -I -B -c \
    'import pathlib,re,sys; text=pathlib.Path(sys.argv[1]).read_text(); print(re.search(r"^version = \"([^\"]+)\"", text, re.M).group(1))' \
    "${RESTLOS_PROJECT_ROOT}/pyproject.toml")"
if [[ "$RESTLOS_VERSION" != "$RESTLOS_MANIFEST_VERSION" || "$RESTLOS_VERSION" != "$RESTLOS_PROJECT_VERSION" ]]
then
    printf '%s\n' "Versionsangaben stimmen nicht überein." >&2
    exit 1
fi

RESTLOS_TEMP_ROOT="$(mktemp -d -t restlos-release.XXXXXXXX)"
cleanup()
{
    case "$RESTLOS_TEMP_ROOT" in
        /tmp/restlos-release.*)
            rm -rf -- "$RESTLOS_TEMP_ROOT"
            ;;
    esac
}
trap cleanup EXIT

RESTLOS_RELEASE_NAME="Restlos-${RESTLOS_VERSION}"
RESTLOS_STAGING_ROOT="${RESTLOS_TEMP_ROOT}/${RESTLOS_RELEASE_NAME}"
install -d -m 0755 "$RESTLOS_STAGING_ROOT" "$RESTLOS_OUTPUT_ROOT"

for item in \
    CHANGELOG.md \
    CONTRIBUTING.md \
    LICENSE \
    PRIVACY.md \
    README.md \
    README.en.md \
    SECURITY.md \
    assets \
    install.sh \
    manifest.json \
    pyproject.toml \
    restlos \
    run_restlos.py \
    scripts \
    tests \
    uninstall.sh \
    update.sh
do
    cp -a -- "${RESTLOS_PROJECT_ROOT}/${item}" "$RESTLOS_STAGING_ROOT/"
done

find "$RESTLOS_STAGING_ROOT" -type d -name __pycache__ -prune -exec rm -r -- {} +
find "$RESTLOS_STAGING_ROOT" -type f -name '*.pyc' -delete
chmod 0755 \
    "$RESTLOS_STAGING_ROOT/install.sh" \
    "$RESTLOS_STAGING_ROOT/update.sh" \
    "$RESTLOS_STAGING_ROOT/uninstall.sh" \
    "$RESTLOS_STAGING_ROOT/run_restlos.py" \
    "$RESTLOS_STAGING_ROOT/scripts/build-release.sh"

RESTLOS_ARCHIVE="${RESTLOS_OUTPUT_ROOT}/${RESTLOS_RELEASE_NAME}.tar.gz"
RESTLOS_CHECKSUM="${RESTLOS_OUTPUT_ROOT}/${RESTLOS_RELEASE_NAME}.sha256"
rm -f -- "$RESTLOS_ARCHIVE" "$RESTLOS_CHECKSUM"

RESTLOS_SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-0}"
tar \
    --sort=name \
    --mtime="@${RESTLOS_SOURCE_DATE_EPOCH}" \
    --owner=0 \
    --group=0 \
    --numeric-owner \
    -C "$RESTLOS_TEMP_ROOT" \
    -cf - \
    "$RESTLOS_RELEASE_NAME" | gzip -n > "$RESTLOS_ARCHIVE"

(
    cd -- "$RESTLOS_OUTPUT_ROOT"
    sha256sum "${RESTLOS_RELEASE_NAME}.tar.gz" > "${RESTLOS_RELEASE_NAME}.sha256"
)

printf '%s\n' \
    "Release erstellt:" \
    "  ${RESTLOS_ARCHIVE}" \
    "  ${RESTLOS_CHECKSUM}"
