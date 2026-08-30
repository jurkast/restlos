"""Wiederherstellung von durch Restlos in den Desktop-Papierkorb verschobenen Daten."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .models import RecoveryItem, RecoveryRecord, RestoreResult


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
_RECOVERY_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,180}$")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class TrashBackend:
    """Kleine, überprüfbare Schnittstelle zur GIO-Papierkorbimplementierung."""

    def __init__(
        self,
        *,
        gio_path: str = "/usr/bin/gio",
        runner: CommandRunner = subprocess.run,
    ) -> None:
        self.gio_path = gio_path
        self.runner = runner

    def list_entries(self) -> dict[str, str]:
        process = self.runner(
            (self.gio_path, "trash", "--list"),
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
            timeout=30,
        )
        if process.returncode != 0:
            raise OSError(process.stderr.strip() or "Papierkorb konnte nicht gelesen werden")
        entries: dict[str, str] = {}
        for line in process.stdout.splitlines():
            uri, separator, original = line.partition("\t")
            if separator and uri.startswith("trash:///") and Path(original).is_absolute():
                entries[uri] = original
        return entries

    def move(self, path: Path, size: int = 0) -> RecoveryItem:
        absolute = path.absolute()
        before = self.list_entries()
        process = self.runner(
            (self.gio_path, "trash", str(absolute)),
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
            timeout=120,
        )
        if process.returncode != 0:
            raise OSError(process.stderr.strip() or "Verschieben in den Papierkorb fehlgeschlagen")
        after = self.list_entries()
        matches = [
            uri
            for uri, original in after.items()
            if original == str(absolute) and uri not in before
        ]
        if len(matches) != 1:
            raise OSError("Der neue Papierkorbeintrag konnte nicht eindeutig zugeordnet werden")
        return RecoveryItem(original_path=str(absolute), trash_uri=matches[0], size=max(size, 0))

    def restore(self, item: RecoveryItem) -> None:
        entries = self.list_entries()
        if entries.get(item.trash_uri) != item.original_path:
            raise OSError("Papierkorbeintrag und ursprünglicher Pfad stimmen nicht überein")
        original = Path(item.original_path)
        if original.exists() or original.is_symlink():
            raise FileExistsError(f"Am ursprünglichen Ort existiert bereits etwas: {original}")
        process = self.runner(
            (self.gio_path, "trash", "--restore", item.trash_uri),
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
            timeout=300,
        )
        if process.returncode != 0:
            raise OSError(process.stderr.strip() or "Wiederherstellung aus dem Papierkorb fehlgeschlagen")
        if not (original.exists() or original.is_symlink()):
            raise OSError("Der ursprüngliche Pfad fehlt nach der Wiederherstellung")


class RecoveryManager:
    """Liest Restlos-Protokolle und stellt deren noch vorhandene Papierkorbdaten wieder her."""

    def __init__(
        self,
        home: Path | None = None,
        *,
        state_home: Path | None = None,
        trash: TrashBackend | None = None,
    ) -> None:
        self.home = (home or Path.home()).absolute()
        if state_home is not None:
            base = state_home.absolute()
        elif home is not None:
            base = self.home / ".local/state"
        else:
            configured = os.environ.get("XDG_STATE_HOME")
            base = Path(configured).absolute() if configured else self.home / ".local/state"
        self.history_directory = base / "restlos/history"
        self.trash = trash or TrashBackend()

    def list_records(self, *, include_finished: bool = False) -> list[RecoveryRecord]:
        try:
            entries = self.trash.list_entries()
        except OSError:
            entries = {}
        records: list[RecoveryRecord] = []
        if not self.history_directory.is_dir():
            return records
        for receipt in sorted(self.history_directory.glob("*.json"), reverse=True):
            record = self._read_record(receipt, entries)
            if record is None:
                continue
            if include_finished or record.available_items:
                records.append(record)
        return records

    def restore(self, recovery_id: str) -> RestoreResult:
        result = RestoreResult(success=False, recovery_id=recovery_id)
        receipt = self._receipt_path(recovery_id)
        if receipt is None:
            result.errors.append("Ungültige Wiederherstellungskennung.")
            return result
        try:
            payload = self._read_payload(receipt)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            result.errors.append(f"Protokoll konnte nicht gelesen werden: {error}")
            return result
        raw_items = payload.get("recovery_items")
        if not isinstance(raw_items, list):
            result.errors.append("Dieses Protokoll enthält keine wiederherstellbaren Daten.")
            return result

        changed = False
        for raw_item in raw_items:
            item = self._item_from_payload(raw_item)
            if item is None or item.restored_at:
                continue
            try:
                self.trash.restore(item)
                restored_at = _utc_timestamp()
                raw_item["restored_at"] = restored_at
                item.restored_at = restored_at
                result.restored_paths.append(item.original_path)
                changed = True
                self._write_payload(receipt, payload)
            except OSError as error:
                result.errors.append(f"{item.original_path}: {error}")

        if not changed and not result.errors:
            result.errors.append("Es sind keine noch verfügbaren Daten in diesem Vorgang enthalten.")
        result.success = bool(result.restored_paths) and not result.errors
        return result

    def _receipt_path(self, recovery_id: str) -> Path | None:
        if not _RECOVERY_ID_PATTERN.fullmatch(recovery_id):
            return None
        path = self.history_directory / f"{recovery_id}.json"
        if path.is_symlink() or not path.is_file():
            return None
        return path

    def _read_record(self, receipt: Path, entries: dict[str, str]) -> RecoveryRecord | None:
        try:
            payload = self._read_payload(receipt)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return None
        if payload.get("schema") != 2 or payload.get("mode") != "trash":
            return None
        application = payload.get("application")
        raw_items = payload.get("recovery_items")
        if not isinstance(application, dict) or not isinstance(raw_items, list):
            return None
        items: list[RecoveryItem] = []
        for raw_item in raw_items:
            item = self._item_from_payload(raw_item)
            if item is None:
                continue
            if not item.restored_at and entries.get(item.trash_uri) != item.original_path:
                continue
            items.append(item)
        actions = payload.get("actions")
        residual_paths = payload.get("residual_paths")
        return RecoveryRecord(
            recovery_id=receipt.stem,
            receipt_path=str(receipt),
            timestamp=str(payload.get("timestamp", "")),
            app_name=str(application.get("name", "Unbekannte Anwendung")),
            package_id=str(application.get("package_id", "")),
            source=str(application.get("source", "")),
            success=payload.get("success") is True,
            items=items,
            actions=[value for value in actions if isinstance(value, str)] if isinstance(actions, list) else [],
            residual_paths=[value for value in residual_paths if isinstance(value, str)]
            if isinstance(residual_paths, list)
            else [],
        )

    @staticmethod
    def _item_from_payload(raw_item: object) -> RecoveryItem | None:
        if not isinstance(raw_item, dict):
            return None
        original = raw_item.get("original_path")
        uri = raw_item.get("trash_uri")
        size = raw_item.get("size", 0)
        restored_at = raw_item.get("restored_at", "")
        if (
            not isinstance(original, str)
            or not Path(original).is_absolute()
            or not isinstance(uri, str)
            or not uri.startswith("trash:///")
            or not isinstance(size, int)
            or size < 0
            or not isinstance(restored_at, str)
        ):
            return None
        return RecoveryItem(original, uri, size, restored_at)

    @staticmethod
    def _read_payload(receipt: Path) -> dict[str, object]:
        if receipt.stat().st_size > 2_000_000:
            raise ValueError("Protokoll ist ungewöhnlich groß")
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Protokoll hat ein ungültiges Format")
        return payload

    @staticmethod
    def _write_payload(receipt: Path, payload: dict[str, object]) -> None:
        receipt.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=receipt.parent,
                prefix=f".{receipt.name}.",
                delete=False,
            ) as handle:
                temporary_name = handle.name
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, receipt)
        finally:
            if temporary_name and Path(temporary_name).exists():
                Path(temporary_name).unlink()
