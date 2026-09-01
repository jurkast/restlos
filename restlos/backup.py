"""Create and safely restore local Safety Backups for selected user data."""

from __future__ import annotations

import json
import os
import shutil
import stat
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

from .models import BackupItem, RemovalTarget
from .utils import is_within


ProgressCallback = Callable[[str, float], None]


class BackupError(OSError):
    """Raised when a Safety Backup cannot be created or safely restored."""


class BackupManager:
    """Stores private, traversal-safe archives below the Restlos state directory."""

    _INCLUDE_TOKENS = (
        "einstellung",
        "konfiguration",
        "spielstand",
        "benutzerdaten",
        "anwendungsdaten",
        "sandbox-daten",
        "wine-präfix",
        "proton-präfix",
        "bottles-umgebung",
    )
    _EXCLUDE_TOKENS = (
        "cache",
        "temporär",
        "download",
        "installer",
        "cover",
        "banner",
        "symbol",
        "starter",
        "menüeintrag",
        "manifest",
        "spielordner",
        "spielinstallation",
        "programmdateien",
        "workshop",
        "screenshot",
        "metadaten",
    )

    def __init__(self, home: Path | None = None, *, state_home: Path | None = None) -> None:
        self.home = (home or Path.home()).absolute()
        if state_home is not None:
            base = state_home.absolute()
        elif home is not None:
            base = self.home / ".local/state"
        else:
            configured = os.environ.get("XDG_STATE_HOME")
            base = Path(configured).absolute() if configured else self.home / ".local/state"
        self.backup_directory = base / "restlos/backups"

    def candidates(self, targets: Iterable[RemovalTarget]) -> list[RemovalTarget]:
        candidates: list[RemovalTarget] = []
        for target in targets:
            path = target.path.absolute()
            reason = target.reason.casefold()
            if (
                path.is_symlink()
                or not self._is_safe_home_path(path)
                or path == self.home
                or is_within(self.backup_directory.absolute(), path)
                or is_within(path, self.backup_directory.absolute())
            ):
                continue
            if any(token in reason for token in self._EXCLUDE_TOKENS):
                continue
            standard_data = any(
                is_within(path, root)
                for root in (
                    self.home / ".config",
                    self.home / ".local/share",
                    self.home / ".local/state",
                    self.home / ".var/app",
                    self.home / "snap",
                )
            )
            if standard_data or any(token in reason for token in self._INCLUDE_TOKENS):
                candidates.append(target)

        ordered = sorted(candidates, key=lambda target: len(target.path.parts))
        collapsed: list[RemovalTarget] = []
        for target in ordered:
            if any(is_within(target.path.absolute(), parent.path.absolute()) for parent in collapsed):
                continue
            collapsed.append(target)
        return collapsed

    def create(
        self,
        targets: Iterable[RemovalTarget],
        *,
        progress: ProgressCallback | None = None,
    ) -> tuple[str, list[BackupItem]]:
        selected = self.candidates(targets)
        if not selected:
            return "", []
        callback = progress or (lambda _message, _fraction: None)
        self.backup_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.backup_directory, 0o700)
        backup_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        final_path = self.backup_directory / f"{backup_id}.tar.gz"
        temporary_name = ""
        items: list[BackupItem] = []
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.backup_directory,
                prefix=f".{backup_id}.",
                suffix=".tar.gz",
                delete=False,
            ) as handle:
                temporary_name = handle.name
            os.chmod(temporary_name, 0o600)
            with tarfile.open(temporary_name, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
                for index, target in enumerate(selected):
                    path = target.path.absolute()
                    if not (path.exists() or path.is_symlink()) or path.is_symlink():
                        raise BackupError(f"Backup-Quelle ist nicht mehr sicher verfügbar: {path}")
                    member = f"items/{index:04d}"
                    callback(f"Safety Backup: {path}", index / max(len(selected), 1))
                    self._add_path(archive, path, member)
                    items.append(BackupItem(str(path), member, max(target.size, 0)))
                manifest = {
                    "schema": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "items": [item.to_dict() for item in items],
                }
                encoded = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
                info = tarfile.TarInfo("manifest.json")
                info.size = len(encoded)
                info.mode = 0o600
                info.mtime = int(datetime.now(timezone.utc).timestamp())
                import io

                archive.addfile(info, io.BytesIO(encoded))
            os.replace(temporary_name, final_path)
            temporary_name = ""
            return str(final_path), items
        except (OSError, tarfile.TarError) as error:
            raise BackupError(str(error)) from error
        finally:
            if temporary_name and Path(temporary_name).exists():
                Path(temporary_name).unlink()

    def restore_item(self, archive_path: Path, item: BackupItem) -> None:
        archive_path = archive_path.absolute()
        if not self._valid_archive_path(archive_path):
            raise BackupError("Backup-Archiv liegt außerhalb des geschützten Restlos-Bereichs")
        original = Path(item.original_path)
        if not original.is_absolute() or original == self.home or not self._is_safe_home_path(original):
            raise BackupError("Ursprünglicher Backup-Pfad ist nicht zulässig")
        if original.exists() or original.is_symlink():
            raise FileExistsError(f"Am ursprünglichen Ort existiert bereits etwas: {original}")
        base = PurePosixPath(item.archive_member)
        if base.is_absolute() or ".." in base.parts or not base.parts:
            raise BackupError("Backup-Eintrag ist ungültig")

        created_root = False
        directory_modes: list[tuple[Path, int]] = []
        try:
            with tarfile.open(archive_path, mode="r:gz") as archive:
                manifest_items = self._manifest_items(archive)
                if not any(
                    value.original_path == item.original_path and value.archive_member == item.archive_member
                    for value in manifest_items
                ):
                    raise BackupError("Backup-Eintrag stimmt nicht mit dem Archivmanifest überein")
                members = [member for member in archive.getmembers() if self._is_member_of(member.name, base)]
                if not members:
                    raise BackupError("Backup-Eintrag fehlt im Archiv")
                for member in sorted(members, key=lambda value: len(PurePosixPath(value.name).parts)):
                    if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                        raise BackupError("Backup enthält einen nicht zulässigen Dateityp")
                    member_path = PurePosixPath(member.name)
                    relative = member_path.relative_to(base)
                    destination = original.joinpath(*relative.parts) if relative.parts else original
                    if not is_within(destination, original):
                        raise BackupError("Backup-Pfad verlässt sein Wiederherstellungsziel")
                    if member.isdir():
                        destination.mkdir(parents=True, exist_ok=False)
                        created_root = True
                        os.chmod(destination, 0o700)
                        directory_modes.append((destination, member.mode & 0o777))
                    elif member.isfile():
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        source = archive.extractfile(member)
                        if source is None:
                            raise BackupError(f"Datei konnte nicht aus dem Backup gelesen werden: {member.name}")
                        with source, destination.open("xb") as output:
                            shutil.copyfileobj(source, output)
                        os.chmod(destination, member.mode & 0o777)
                        created_root = True
                    else:
                        raise BackupError("Backup enthält einen unbekannten Dateityp")
                for destination, mode in reversed(directory_modes):
                    os.chmod(destination, mode)
        except (OSError, tarfile.TarError, ValueError) as error:
            if created_root and (original.exists() or original.is_symlink()):
                if original.is_dir() and not original.is_symlink():
                    shutil.rmtree(original)
                else:
                    original.unlink()
            if isinstance(error, BackupError):
                raise
            raise BackupError(str(error)) from error

    def _add_path(self, archive: tarfile.TarFile, path: Path, member: str) -> None:
        info = archive.gettarinfo(str(path), arcname=member)
        if info.issym() or info.islnk() or info.isdev() or info.isfifo():
            raise BackupError(f"Nicht zulässiger Dateityp im Backup: {path}")
        if info.isdir():
            archive.addfile(info)
            try:
                children = sorted(path.iterdir(), key=lambda child: child.name)
            except OSError as error:
                raise BackupError(f"Backup-Ordner konnte nicht gelesen werden: {path}: {error}") from error
            for child in children:
                if child.is_symlink():
                    continue
                self._add_path(archive, child, f"{member}/{child.name}")
        elif info.isfile() and stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
            with path.open("rb") as source:
                archive.addfile(info, source)
        else:
            raise BackupError(f"Nicht zulässiger Dateityp im Backup: {path}")

    def _manifest_items(self, archive: tarfile.TarFile) -> list[BackupItem]:
        try:
            member = archive.getmember("manifest.json")
            if member.size > 2_000_000 or not member.isfile():
                raise BackupError("Backup-Manifest ist ungültig")
            source = archive.extractfile(member)
            if source is None:
                raise BackupError("Backup-Manifest fehlt")
            payload = json.loads(source.read().decode("utf-8"))
        except (KeyError, UnicodeError, json.JSONDecodeError) as error:
            raise BackupError("Backup-Manifest konnte nicht gelesen werden") from error
        if not isinstance(payload, dict) or payload.get("schema") != 1 or not isinstance(payload.get("items"), list):
            raise BackupError("Backup-Manifest hat ein unbekanntes Format")
        items: list[BackupItem] = []
        for raw in payload["items"]:
            if not isinstance(raw, dict):
                continue
            original = raw.get("original_path")
            archive_member = raw.get("archive_member")
            size = raw.get("size", 0)
            if isinstance(original, str) and isinstance(archive_member, str) and isinstance(size, int):
                items.append(BackupItem(original, archive_member, max(size, 0)))
        return items

    def _valid_archive_path(self, path: Path) -> bool:
        return (
            is_within(path, self.backup_directory.absolute())
            and path.suffixes[-2:] == [".tar", ".gz"]
            and path.is_file()
            and not path.is_symlink()
        )

    def _is_safe_home_path(self, path: Path) -> bool:
        if not is_within(path.absolute(), self.home):
            return False
        try:
            resolved_home = self.home.resolve(strict=True)
            resolved = path.resolve(strict=False)
        except OSError:
            return False
        return is_within(resolved, resolved_home) and resolved != resolved_home

    @staticmethod
    def _is_member_of(name: str, base: PurePosixPath) -> bool:
        member = PurePosixPath(name)
        if member.is_absolute() or ".." in member.parts:
            return False
        return member == base or base in member.parents
