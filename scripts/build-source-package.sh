#!/usr/bin/env bash

set -euo pipefail

RESTLOS_PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
RESTLOS_SERIES="${1:-noble}"
RESTLOS_OUTPUT_ROOT="${2:-${RESTLOS_PROJECT_ROOT}/dist/source/${RESTLOS_SERIES}}"
RESTLOS_SIGNING_MODE="${3:---unsigned}"
RESTLOS_PYTHON="${RESTLOS_PYTHON:-python3}"
RESTLOS_PPA_REVISION="${RESTLOS_PPA_REVISION:-1}"

case "$RESTLOS_SERIES" in
    noble | jammy) ;;
    *)
        printf 'Nicht unterstützte Ubuntu-Serie: %s (erlaubt: noble, jammy)\n' "$RESTLOS_SERIES" >&2
        exit 2
        ;;
esac

case "$RESTLOS_SIGNING_MODE" in
    --unsigned) RESTLOS_SIGNING_OPTIONS=(-us -uc) ;;
    --sign)
        RESTLOS_SIGNING_OPTIONS=()
        ;;
    --key=*)
        RESTLOS_SIGNING_OPTIONS=(-k"${RESTLOS_SIGNING_MODE#--key=}")
        ;;
    *)
        printf 'Ungültiger Signaturmodus: %s (erlaubt: --unsigned, --sign, --key=KEYID)\n' \
            "$RESTLOS_SIGNING_MODE" >&2
        exit 2
        ;;
esac

for command in dpkg-buildpackage git gzip sed tar
do
    if ! command -v "$command" >/dev/null 2>&1
    then
        printf 'Benötigter Befehl fehlt: %s\n' "$command" >&2
        exit 1
    fi
done

if [[ ! "$RESTLOS_PPA_REVISION" =~ ^[1-9][0-9]*$ ]]
then
    printf '%s\n' 'RESTLOS_PPA_REVISION muss eine positive Ganzzahl sein.' >&2
    exit 2
fi

RESTLOS_VERSION="$($RESTLOS_PYTHON -I -B -c \
    'import pathlib,re,sys; text=pathlib.Path(sys.argv[1]).read_text(); match=re.search(r"^__version__ = \"([^\"]+)\"", text, re.M); print(match.group(1) if match else "")' \
    "${RESTLOS_PROJECT_ROOT}/restlos/__init__.py")"
if [[ ! "$RESTLOS_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
then
    printf '%s\n' 'Ungültige Restlos-Version.' >&2
    exit 1
fi

RESTLOS_DEBIAN_VERSION="${RESTLOS_VERSION}-1ppa${RESTLOS_PPA_REVISION}~${RESTLOS_SERIES}1"
RESTLOS_TEMP_ROOT="$(mktemp -d -t restlos-source.XXXXXXXX)"
cleanup()
{
    case "$RESTLOS_TEMP_ROOT" in
        /tmp/restlos-source.*) rm -rf -- "$RESTLOS_TEMP_ROOT" ;;
    esac
}
trap cleanup EXIT

RESTLOS_SOURCE_ROOT="${RESTLOS_TEMP_ROOT}/restlos-uninstaller-${RESTLOS_VERSION}"
install -d -m 0755 "$RESTLOS_SOURCE_ROOT" "$RESTLOS_OUTPUT_ROOT"

if git -C "$RESTLOS_PROJECT_ROOT" rev-parse --verify --quiet "refs/tags/v${RESTLOS_VERSION}" >/dev/null
then
    RESTLOS_UPSTREAM_REF="v${RESTLOS_VERSION}"
else
    RESTLOS_UPSTREAM_REF="HEAD"
fi

git -C "$RESTLOS_PROJECT_ROOT" archive "$RESTLOS_UPSTREAM_REF" | tar -x -C "$RESTLOS_SOURCE_ROOT"
rm -rf -- "$RESTLOS_SOURCE_ROOT/debian"
cp -a -- "$RESTLOS_PROJECT_ROOT/debian" "$RESTLOS_SOURCE_ROOT/debian"

sed -i \
    "1s|^restlos-uninstaller ([^)]*) [^;]*;|restlos-uninstaller (${RESTLOS_DEBIAN_VERSION}) ${RESTLOS_SERIES};|" \
    "$RESTLOS_SOURCE_ROOT/debian/changelog"

RESTLOS_SOURCE_DATE_EPOCH="$(git -C "$RESTLOS_PROJECT_ROOT" log -1 --format=%ct "$RESTLOS_UPSTREAM_REF")"
RESTLOS_ORIG_ARCHIVE="${RESTLOS_TEMP_ROOT}/restlos-uninstaller_${RESTLOS_VERSION}.orig.tar.gz"
tar \
    --sort=name \
    --mtime="@${RESTLOS_SOURCE_DATE_EPOCH}" \
    --owner=0 \
    --group=0 \
    --numeric-owner \
    --exclude="restlos-uninstaller-${RESTLOS_VERSION}/debian" \
    -C "$RESTLOS_TEMP_ROOT" \
    -cf - \
    "restlos-uninstaller-${RESTLOS_VERSION}" | gzip -n > "$RESTLOS_ORIG_ARCHIVE"

(
    cd -- "$RESTLOS_SOURCE_ROOT"
    dpkg-buildpackage -S -sa -d -nc "${RESTLOS_SIGNING_OPTIONS[@]}"
)

for artifact in \
    "$RESTLOS_TEMP_ROOT"/restlos-uninstaller_"${RESTLOS_VERSION}".orig.tar.gz \
    "$RESTLOS_TEMP_ROOT"/restlos-uninstaller_"${RESTLOS_DEBIAN_VERSION}".debian.tar.* \
    "$RESTLOS_TEMP_ROOT"/restlos-uninstaller_"${RESTLOS_DEBIAN_VERSION}".dsc \
    "$RESTLOS_TEMP_ROOT"/restlos-uninstaller_"${RESTLOS_DEBIAN_VERSION}"_source.buildinfo \
    "$RESTLOS_TEMP_ROOT"/restlos-uninstaller_"${RESTLOS_DEBIAN_VERSION}"_source.changes
do
    if [[ -f "$artifact" ]]
    then
        cp -a -- "$artifact" "$RESTLOS_OUTPUT_ROOT/"
    fi
done

printf '%s\n' \
    "Launchpad-Quellpaket für ${RESTLOS_SERIES} erstellt:" \
    "  ${RESTLOS_OUTPUT_ROOT}/restlos-uninstaller_${RESTLOS_DEBIAN_VERSION}_source.changes"
