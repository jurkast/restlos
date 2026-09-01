"""Sichere Update-Prüfung und Installation offizieller Restlos-Releases."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


REPOSITORIES = ("jurkast/restlos", "jurkastl/restlos")
REPOSITORY = REPOSITORIES[0]
RELEASES_APIS = tuple(f"https://api.github.com/repos/{repository}/releases?per_page=10" for repository in REPOSITORIES)
RELEASES_API = RELEASES_APIS[0]
CHECK_INTERVAL_SECONDS = 24 * 60 * 60
RETRY_INTERVAL_SECONDS = 4 * 60 * 60
NETWORK_TIMEOUT_SECONDS = 10.0
INSTALL_TIMEOUT_SECONDS = 180.0
MAX_METADATA_BYTES = 1_000_000
MAX_CHECKSUM_BYTES = 4096
MAX_ARCHIVE_BYTES = 250 * 1024 * 1024
MAX_EXTRACTED_BYTES = 500 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 5000

_VERSION_PATTERN = re.compile(r"^(?:v)?([0-9]+)\.([0-9]+)\.([0-9]+)$")
_DIGEST_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")
SYSTEM_UPDATE_CHANNELS = frozenset({"apt", "deb", "snap", "system"})


class UpdateError(RuntimeError):
    """Ein erwartbarer Fehler während Prüfung oder Installation."""


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    version: str
    title: str
    notes: str
    page_url: str
    archive_url: str
    checksum_url: str
    archive_digest: str
    archive_size: int
    prerelease: bool


@dataclass(frozen=True, slots=True)
class InstallResult:
    version: str
    output: str


ProgressCallback = Callable[[str, float], None]


def is_system_managed_install(environ: dict[str, str] | None = None) -> bool:
    """Return whether updates must be installed by a system package manager."""
    environment = os.environ if environ is None else environ
    channel = environment.get("RESTLOS_UPDATE_CHANNEL", "").strip().casefold()
    return channel in SYSTEM_UPDATE_CHANNELS


def parse_version(value: str) -> tuple[int, int, int]:
    match = _VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"Ungültige Versionsnummer: {value}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def select_update(
    releases: Iterable[object],
    current_version: str,
    *,
    include_prereleases: bool = True,
) -> ReleaseInfo | None:
    current = parse_version(current_version)
    candidates: list[tuple[tuple[int, int, int], ReleaseInfo]] = []
    for raw_release in releases:
        if not isinstance(raw_release, dict) or raw_release.get("draft") is True:
            continue
        prerelease = raw_release.get("prerelease") is True
        if prerelease and not include_prereleases:
            continue
        tag = raw_release.get("tag_name")
        if not isinstance(tag, str):
            continue
        try:
            parsed = parse_version(tag)
        except ValueError:
            continue
        version = ".".join(str(part) for part in parsed)
        if tag != f"v{version}" or parsed <= current:
            continue

        archive_name = f"Restlos-{version}.tar.gz"
        checksum_name = f"Restlos-{version}.sha256"
        archive = _asset_by_name(raw_release.get("assets"), archive_name)
        checksum = _asset_by_name(raw_release.get("assets"), checksum_name)
        if archive is None or checksum is None:
            continue

        archive_url = archive.get("browser_download_url")
        checksum_url = checksum.get("browser_download_url")
        repository = _release_repository(version, archive_name, checksum_name, archive_url, checksum_url)
        digest_value = archive.get("digest")
        archive_size = archive.get("size")
        if (
            repository is None
            or not isinstance(digest_value, str)
            or not digest_value.startswith("sha256:")
            or not _DIGEST_PATTERN.fullmatch(digest_value.removeprefix("sha256:"))
            or not isinstance(archive_size, int)
            or archive_size <= 0
            or archive_size > MAX_ARCHIVE_BYTES
        ):
            continue

        title = raw_release.get("name")
        notes = raw_release.get("body")
        release = ReleaseInfo(
            version=version,
            title=title.strip()[:200] if isinstance(title, str) and title.strip() else f"Restlos {version}",
            notes=notes.strip()[:20_000] if isinstance(notes, str) else "",
            page_url=f"https://github.com/{repository}/releases/tag/v{version}",
            archive_url=archive_url,
            checksum_url=checksum_url,
            archive_digest=digest_value.removeprefix("sha256:").lower(),
            archive_size=archive_size,
            prerelease=prerelease,
        )
        candidates.append((parsed, release))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _asset_by_name(raw_assets: object, name: str) -> dict[str, object] | None:
    if not isinstance(raw_assets, list):
        return None
    matches = [
        asset
        for asset in raw_assets
        if isinstance(asset, dict) and asset.get("name") == name and asset.get("state") == "uploaded"
    ]
    return matches[0] if len(matches) == 1 else None


def _release_repository(
    version: str,
    archive_name: str,
    checksum_name: str,
    archive_url: object,
    checksum_url: object,
) -> str | None:
    for repository in REPOSITORIES:
        prefix = f"https://github.com/{repository}/releases/download/v{version}/"
        if archive_url == f"{prefix}{archive_name}" and checksum_url == f"{prefix}{checksum_name}":
            return repository
    return None


def checksum_from_file(content: bytes, archive_name: str) -> str:
    try:
        text = content.decode("ascii")
    except UnicodeDecodeError as error:
        raise UpdateError("Die Prüfsummendatei ist nicht gültig.") from error
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise UpdateError("Die Prüfsummendatei muss genau einen Eintrag enthalten.")
    match = re.fullmatch(r"([a-fA-F0-9]{64})[ \t]+\*?([^/\\]+)", lines[0])
    if match is None or match.group(2) != archive_name:
        raise UpdateError("Die Prüfsumme gehört nicht zum erwarteten Restlos-Archiv.")
    return match.group(1).lower()


class UpdateState:
    def __init__(self, path: Path | None = None, home: Path | None = None) -> None:
        if path is not None:
            self.path = path
        elif home is not None:
            self.path = home / ".local/state/restlos/update.json"
        else:
            state_home = os.environ.get("XDG_STATE_HOME")
            base = Path(state_home) if state_home else Path.home() / ".local/state"
            self.path = base / "restlos/update.json"

    def automatic_checks_enabled(self) -> bool:
        return self._read().get("automatic_checks", True) is not False

    def set_automatic_checks(self, enabled: bool) -> None:
        state = self._read()
        state["automatic_checks"] = bool(enabled)
        self._write(state)

    def is_due(self, now: float | None = None) -> bool:
        if not self.automatic_checks_enabled():
            return False
        state = self._read()
        current = time.time() if now is None else now
        last_attempt = _finite_number(state.get("last_attempt"))
        if last_attempt is None or current < last_attempt:
            return True
        interval = CHECK_INTERVAL_SECONDS if state.get("last_attempt_succeeded") is True else RETRY_INTERVAL_SECONDS
        return current - last_attempt >= interval

    def record_attempt(self, succeeded: bool, now: float | None = None) -> None:
        state = self._read()
        current = time.time() if now is None else now
        state["last_attempt"] = current
        state["last_attempt_succeeded"] = bool(succeeded)
        if succeeded:
            state["last_success"] = current
        self._write(state)

    def _read(self) -> dict[str, object]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write(self, state: dict[str, object]) -> None:
        try:
            self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                delete=False,
            ) as temporary:
                json.dump(state, temporary, ensure_ascii=False, sort_keys=True)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            temporary_path.chmod(0o600)
            os.replace(temporary_path, self.path)
        except OSError:
            try:
                temporary_path.unlink(missing_ok=True)
            except (OSError, UnboundLocalError):
                pass


def _finite_number(value: object) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


class UpdateClient:
    def __init__(
        self,
        current_version: str,
        *,
        opener: Callable[..., object] = urlopen,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        parse_version(current_version)
        self.current_version = current_version
        self._opener = opener
        self._runner = runner

    def check(self) -> ReleaseInfo | None:
        failures: list[UpdateError] = []
        had_valid_response = False
        for releases_api in RELEASES_APIS:
            try:
                content = self._read_bytes(releases_api, MAX_METADATA_BYTES)
                releases = json.loads(content.decode("utf-8"))
                if not isinstance(releases, list):
                    raise UpdateError("GitHub hat ein unerwartetes Release-Format geliefert.")
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                failures.append(UpdateError("GitHub hat keine gültigen Release-Daten geliefert."))
                continue
            except UpdateError as error:
                failures.append(error)
                continue
            had_valid_response = True
            selected = select_update(releases, self.current_version, include_prereleases=True)
            if selected is not None:
                return selected
        if had_valid_response:
            return None
        raise failures[-1] if failures else UpdateError("GitHub hat keine Release-Daten geliefert.")

    def install(
        self,
        release: ReleaseInfo,
        *,
        home: Path | None = None,
        progress: ProgressCallback | None = None,
    ) -> InstallResult:
        if parse_version(release.version) <= parse_version(self.current_version):
            raise UpdateError("Die ausgewählte Ausgabe ist nicht neuer als die installierte Version.")
        report = progress or (lambda _message, _fraction: None)
        archive_name = f"Restlos-{release.version}.tar.gz"
        with tempfile.TemporaryDirectory(prefix="restlos-update-") as temporary_name:
            temporary = Path(temporary_name)
            report("Prüfsumme wird geladen …", 0.08)
            checksum_content = self._read_bytes(release.checksum_url, MAX_CHECKSUM_BYTES)
            expected = checksum_from_file(checksum_content, archive_name)
            if expected != release.archive_digest:
                raise UpdateError("GitHub-Digest und veröffentlichte Prüfsumme stimmen nicht überein.")

            archive_path = temporary / archive_name
            self._download_archive(release, archive_path, report)
            report("SHA-256-Prüfsumme wird kontrolliert …", 0.76)
            actual = _sha256(archive_path)
            if actual != expected:
                raise UpdateError("Die SHA-256-Prüfung des Updates ist fehlgeschlagen.")

            report("Update wird sicher entpackt …", 0.84)
            extract_home = temporary / "extract"
            release_home = extract_release_archive(archive_path, extract_home, release.version)
            installer = release_home / "install.sh"
            if not installer.is_file():
                raise UpdateError("Das Update enthält keinen Installer.")
            installer.chmod(0o755)

            report("Neue Version wird installiert …", 0.92)
            try:
                completed = self._runner(
                    [str(installer)],
                    cwd=str(release_home),
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=INSTALL_TIMEOUT_SECONDS,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise UpdateError(f"Der Installer konnte nicht ausgeführt werden: {error}") from error
            output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
            if completed.returncode != 0:
                details = output[-2000:] or f"Exit-Code {completed.returncode}"
                raise UpdateError(f"Die Installation ist fehlgeschlagen:\n{details}")

            user_home = Path.home() if home is None else home
            command = user_home / ".local/bin/restlos"
            try:
                verification = self._runner(
                    [str(command), "--version"],
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=20.0,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise UpdateError(f"Die installierte Version konnte nicht geprüft werden: {error}") from error
            if verification.returncode != 0 or verification.stdout.strip() != f"Restlos {release.version}":
                raise UpdateError("Die installierte Version hat die abschließende Selbstprüfung nicht bestanden.")
            report("Update abgeschlossen.", 1.0)
            return InstallResult(release.version, output)

    def _read_bytes(self, url: str, maximum: int) -> bytes:
        response = self._open(url)
        try:
            content = response.read(maximum + 1)
        except OSError as error:
            raise UpdateError(f"Der Download ist fehlgeschlagen: {error}") from error
        finally:
            response.close()
        if len(content) > maximum:
            raise UpdateError("Die heruntergeladene Datei überschreitet das Größenlimit.")
        return content

    def _download_archive(self, release: ReleaseInfo, target: Path, report: ProgressCallback) -> None:
        response = self._open(release.archive_url)
        downloaded = 0
        digest = hashlib.sha256()
        try:
            with target.open("xb") as output:
                while True:
                    block = response.read(128 * 1024)
                    if not block:
                        break
                    downloaded += len(block)
                    if downloaded > MAX_ARCHIVE_BYTES:
                        raise UpdateError("Das Update-Archiv überschreitet das Größenlimit.")
                    digest.update(block)
                    output.write(block)
                    fraction = min(downloaded / max(release.archive_size, 1), 1.0)
                    report("Update wird heruntergeladen …", 0.14 + fraction * 0.58)
        except OSError as error:
            raise UpdateError(f"Das Update-Archiv konnte nicht gespeichert werden: {error}") from error
        finally:
            response.close()
        if downloaded != release.archive_size:
            raise UpdateError("Die Größe des geladenen Update-Archivs ist unerwartet.")
        if digest.hexdigest() != release.archive_digest:
            raise UpdateError("Der GitHub-Digest des Update-Archivs stimmt nicht überein.")

    def _open(self, url: str):
        if not _trusted_https_url(url):
            raise UpdateError("Eine nicht vertrauenswürdige Update-Adresse wurde abgelehnt.")
        request = Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"Restlos/{self.current_version}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="GET",
        )
        try:
            response = self._opener(request, timeout=NETWORK_TIMEOUT_SECONDS)
        except (HTTPError, URLError, OSError, TimeoutError) as error:
            raise UpdateError(f"GitHub ist derzeit nicht erreichbar: {error}") from error
        final_url = response.geturl()
        if not _trusted_https_url(final_url):
            response.close()
            raise UpdateError("GitHub hat auf eine nicht vertrauenswürdige Adresse weitergeleitet.")
        return response


def _trusted_https_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    hostname = (parsed.hostname or "").casefold()
    return (
        parsed.scheme == "https"
        and parsed.username is None
        and parsed.password is None
        and (hostname in {"api.github.com", "github.com"} or hostname.endswith(".githubusercontent.com"))
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_release_archive(archive_path: Path, destination: Path, version: str) -> Path:
    expected_root = f"Restlos-{version}"
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    seen: set[str] = set()
    total_size = 0
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = archive.getmembers()
            if not members or len(members) > MAX_ARCHIVE_MEMBERS:
                raise UpdateError("Das Update-Archiv enthält unerwartet viele Einträge.")
            for member in members:
                path = PurePosixPath(member.name)
                if (
                    path.is_absolute()
                    or not path.parts
                    or path.parts[0] != expected_root
                    or any(part in {"", ".", ".."} for part in path.parts)
                    or "\\" in member.name
                    or member.name in seen
                ):
                    raise UpdateError("Das Update-Archiv enthält einen unsicheren Pfad.")
                seen.add(member.name)
                if not (member.isdir() or member.isfile()):
                    raise UpdateError("Links oder Spezialdateien im Update-Archiv wurden abgelehnt.")
                total_size += max(member.size, 0)
                if total_size > MAX_EXTRACTED_BYTES:
                    raise UpdateError("Der entpackte Inhalt überschreitet das Größenlimit.")

                output_path = destination.joinpath(*path.parts)
                if member.isdir():
                    output_path.mkdir(parents=True, mode=0o755, exist_ok=True)
                    continue
                output_path.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise UpdateError("Eine Datei im Update-Archiv konnte nicht gelesen werden.")
                with source, output_path.open("xb") as output:
                    shutil.copyfileobj(source, output, length=128 * 1024)
                output_path.chmod(0o755 if member.mode & 0o111 else 0o644)
    except (OSError, tarfile.TarError) as error:
        raise UpdateError(f"Das Update-Archiv konnte nicht entpackt werden: {error}") from error
    release_home = destination / expected_root
    if not release_home.is_dir():
        raise UpdateError("Das Update-Archiv besitzt keine gültige Wurzel.")
    return release_home
