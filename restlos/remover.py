from __future__ import annotations

import json
import os
import shutil
import signal
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import __version__
from .analyzer import PathGuard, RemovalAnalyzer, UnsafeTargetError
from .backup import BackupError, BackupManager
from .models import RecoveryItem, RemovalAction, RemovalPlan, RemovalResult, SourceKind
from .recovery import TrashBackend
from .i18n import translate as _
from .safety import ReviewRequired, optional_fingerprint
from .scanners import ApplicationScanner


ProgressCallback = Callable[[str, float], None]


class RemovalExecutor:
    def __init__(
        self,
        home: Path | None = None,
        *,
        trash: TrashBackend | None = None,
        backup: BackupManager | None = None,
        inventory_provider: Callable[[], list] | None = None,
    ) -> None:
        self.home = (home or Path.home()).absolute()
        self.guard = PathGuard(self.home)
        if home is not None:
            self.state_home = self.home / ".local/state"
        else:
            configured = os.environ.get("XDG_STATE_HOME")
            self.state_home = Path(configured).absolute() if configured else self.home / ".local/state"
        self.trash = trash or TrashBackend()
        self.backup = backup or BackupManager(self.home, state_home=self.state_home)
        self.inventory_provider = inventory_provider or (lambda: ApplicationScanner(self.home).scan())

    def related_processes(self, plan: RemovalPlan) -> list[tuple[int, str]]:
        roots = [target.path.absolute() for target in plan.selected_targets]
        own_pids = {os.getpid(), os.getppid()}
        matches: list[tuple[int, str]] = []
        proc = Path("/proc")
        if not proc.is_dir():
            return matches
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            if pid in own_pids:
                continue
            try:
                exe = (entry / "exe").resolve(strict=True)
            except OSError:
                exe = None
            try:
                cwd = (entry / "cwd").resolve(strict=True)
            except OSError:
                cwd = None
            try:
                cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            except OSError:
                cmdline = ""
            try:
                command = (entry / "comm").read_text(errors="replace").strip()
            except OSError:
                command = "unbekannter Prozess"
            related = False
            for root in roots:
                if root.is_dir():
                    related = related or (exe is not None and self._is_within(exe, root))
                    related = related or (cwd is not None and self._is_within(cwd, root))
                elif exe is not None:
                    related = related or exe == root
            manager_tokens = {
                SourceKind.LUTRIS: ("lutris",),
                SourceKind.STEAM: ("steam", "steamwebhelper"),
                SourceKind.HEROIC: ("heroic",),
                SourceKind.BOTTLES: ("bottles",),
                SourceKind.PLAYONLINUX: ("playonlinux",),
            }.get(plan.app.source, ())
            process_text = f"{command} {cmdline}".casefold()
            if manager_tokens and any(token in process_text for token in manager_tokens):
                related = True
            if not related:
                continue
            matches.append((pid, command))
        return matches

    def stop_processes(self, processes: list[tuple[int, str]]) -> None:
        for pid, _ in processes:
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                continue
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            remaining = [pid for pid, _ in processes if Path(f"/proc/{pid}").exists()]
            if not remaining:
                return
            time.sleep(0.1)
        for pid, _ in processes:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                continue

    def execute(
        self,
        plan: RemovalPlan,
        *,
        permanent: bool = True,
        stop_processes: bool = True,
        create_backup: bool = False,
        progress: ProgressCallback | None = None,
    ) -> RemovalResult:
        result = RemovalResult(success=False)
        callback = progress or (lambda _message, _fraction: None)
        if create_backup and not permanent:
            result.errors.append("Safety Backup und Papierkorbmodus können nicht gleichzeitig verwendet werden.")
            return self._finish(plan, result, permanent)
        callback(_("Löschplan und bekannte Datenzuordnungen werden erneut geprüft …"), 0.01)
        try:
            if plan.snapshot is None or plan.safety_error:
                raise ReviewRequired(plan.safety_error or _("Für diesen Löschplan fehlt die Sicherheitsprüfung. Bitte erneut analysieren."))
            plan.snapshot.validate_environment(plan, self.inventory_provider())
            for target in plan.selected_targets:
                self.guard.validate(target.path, self._trusted_paths(plan))
            plan.snapshot.validate_files(plan)
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
            return self._review_failed(plan, result, permanent, error)
        processes = self.related_processes(plan)
        if processes and stop_processes:
            callback("Laufende Prozesse werden beendet …", 0.02)
            self.stop_processes(processes)
        elif processes:
            result.errors.append("Die Anwendung läuft noch und wurde nicht beendet.")
            return self._finish(plan, result, permanent)
        try:
            # Shutdown can write saves/settings: never silently approve them.
            plan.snapshot.validate_files(plan)
        except (OSError, ValueError, RuntimeError) as error:
            return self._review_failed(plan, result, permanent, error)
        if create_backup:
            callback("Safety Backup wird erstellt …", 0.03)
            try:
                result.backup_path, result.backup_items = self.backup.create(
                    plan.selected_targets,
                    progress=lambda message, fraction: callback(message, 0.03 + fraction * 0.08),
                )
            except BackupError as error:
                result.errors.append(f"Safety Backup fehlgeschlagen; es wurde nichts entfernt: {error}")
                return self._finish(plan, result, permanent)

        try:
            # Backups may take time. Recheck before starting the first package
            # operation, without refreshing the approved baseline. Authentication
            # happens inside that operation and is not atomic with this check.
            plan.snapshot.validate_environment(plan, self.inventory_provider())
            plan.snapshot.validate_files(plan)
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
            return self._review_failed(plan, result, permanent, error)

        total_steps = max(len(plan.actions) + len(plan.selected_targets), 1)
        completed_steps = 0
        external_actions = [action for action in plan.actions if not action.internal_kind]
        internal_actions = [action for action in plan.actions if action.internal_kind]
        for action in external_actions:
            callback(action.label, completed_steps / total_steps)
            try:
                plan.snapshot.validate_definition(plan)
            except ReviewRequired as error:
                return self._review_failed(plan, result, permanent, error)
            try:
                process = subprocess.run(
                    list(action.command),
                    capture_output=True,
                    text=True,
                    errors="replace",
                    check=False,
                    timeout=900,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                result.errors.append(f"{action.label}: {error}")
                if action.required:
                    return self._finish(plan, result, permanent)
                continue
            output = "\n".join(part for part in (process.stdout.strip(), process.stderr.strip()) if part)
            if output:
                result.action_output.append(f"{action.label}\n{output}")
            if process.returncode != 0:
                result.errors.append(f"{action.label} ist mit Code {process.returncode} fehlgeschlagen.")
                if action.required:
                    return self._finish(plan, result, permanent)
            completed_steps += 1

        for target in sorted(plan.selected_targets, key=lambda item: len(item.path.parts), reverse=True):
            callback(f"Entferne {target.path}", completed_steps / total_steps)
            try:
                plan.snapshot.validate_definition(plan)
                plan.snapshot.validate_target(target.path, allow_missing=bool(external_actions))
                self.guard.validate(target.path, self._trusted_paths(plan))
            except (OSError, ValueError, RuntimeError) as error:
                return self._review_failed(plan, result, permanent, error)
            try:
                if external_actions and not os.path.lexists(target.path):
                    result.removed_paths.append(str(target.path))
                    completed_steps += 1
                    continue
                if permanent:
                    self._delete_permanently(target.path)
                else:
                    result.recovery_items.append(self._move_to_trash(target.path, target.size))
                if target.path.exists() or target.path.is_symlink():
                    raise OSError("Pfad ist nach dem Entfernen noch vorhanden")
                result.removed_paths.append(str(target.path))
            except (OSError, UnsafeTargetError) as error:
                result.errors.append(f"{target.path}: {error}")
            completed_steps += 1

        if not result.errors:
            for action in internal_actions:
                callback(action.label, completed_steps / total_steps)
                try:
                    plan.snapshot.validate_definition(plan)
                    for key in ("database", "path", "cache"):
                        value = action.parameters.get(key)
                        if not value:
                            continue
                        controls = [value, value + "-wal"] if value.endswith(".db") else [value]
                        for path in controls:
                            if plan.snapshot.controls.get(path) != optional_fingerprint(Path(path)):
                                raise ReviewRequired(_("Programm- oder Bibliotheksinformationen wurden verändert: {path}", path=path))
                except (OSError, ValueError, RuntimeError) as error:
                    return self._review_failed(plan, result, permanent, error)
                try:
                    output = self._execute_internal_action(action)
                    if output:
                        result.action_output.append(f"{action.label}\n{output}")
                except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as error:
                    result.errors.append(f"{action.label}: {error}")
                    if action.required:
                        return self._finish(plan, result, permanent)
                completed_steps += 1

        callback("Kontrollscan nach verbliebenen Daten …", 0.98)
        self._control_scan(plan, result)
        result.success = not result.errors
        return self._finish(plan, result, permanent)

    def _review_failed(self, plan: RemovalPlan, result: RemovalResult, permanent: bool, error: Exception) -> RemovalResult:
        result.review_required = True
        result.errors.append(str(error))
        result.errors.append(_("Abgebrochen. Bitte erneut analysieren und den neuen Löschplan bestätigen. Bereits ausgeführte Schritte werden nicht automatisch rückgängig gemacht."))
        return self._finish(plan, result, permanent)

    def _trusted_paths(self, plan: RemovalPlan) -> tuple[Path, ...]:
        try:
            values = json.loads(plan.app.metadata.get("trusted_paths", "[]"))
        except (TypeError, json.JSONDecodeError):
            return ()
        if not isinstance(values, list):
            return ()
        return tuple(Path(value).absolute() for value in values if isinstance(value, str) and Path(value).is_absolute())

    def _execute_internal_action(self, action: RemovalAction) -> str:
        if action.internal_kind == "lutris-database":
            return self._update_lutris_database(action.parameters)
        if action.internal_kind == "json-remove-key":
            return self._remove_json_key(action.parameters)
        raise ValueError(f"unbekannte interne Aktion: {action.internal_kind}")

    def _update_lutris_database(self, parameters: dict[str, str]) -> str:
        database = Path(parameters.get("database", "")).absolute()
        game_id = parameters.get("game_id", "")
        allowed_databases = {
            (self.home / ".local/share/lutris/pga.db").absolute(),
            (self.home / ".var/app/net.lutris.Lutris/data/lutris/pga.db").absolute(),
        }
        if database not in allowed_databases or database.is_symlink() or not database.is_file():
            raise ValueError("Lutris-Datenbankpfad ist nicht zulässig")
        if not game_id.isdigit():
            raise ValueError("Lutris-Spielkennung ist ungültig")
        with sqlite3.connect(database, timeout=10) as connection:
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "games_categories" in tables:
                connection.execute("DELETE FROM games_categories WHERE game_id=?", (int(game_id),))
            connection.execute("DELETE FROM games WHERE id=?", (int(game_id),))

        cache_value = parameters.get("cache", "")
        if cache_value:
            cache = Path(cache_value).absolute()
            allowed_caches = {
                (self.home / ".cache/lutris/game-paths.json").absolute(),
                (self.home / ".var/app/net.lutris.Lutris/cache/lutris/game-paths.json").absolute(),
            }
            if cache in allowed_caches and cache.is_file() and not cache.is_symlink():
                try:
                    payload = json.loads(cache.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    payload = None
                if isinstance(payload, dict) and game_id in payload:
                    payload.pop(game_id, None)
                    self._atomic_json_write(cache, payload)
        return f"Lutris-Eintrag {game_id} entfernt"

    def _remove_json_key(self, parameters: dict[str, str]) -> str:
        path = Path(parameters.get("path", "")).absolute()
        key = parameters.get("key", "")
        allowed_roots = (
            self.home / ".config/heroic",
            self.home / ".config/legendary",
            self.home / ".var/app/com.heroicgameslauncher.hgl/config",
        )
        if not any(self._is_within(path, root.absolute()) for root in allowed_roots):
            raise ValueError("JSON-Verwaltungsdatei liegt außerhalb der Heroic-Konfiguration")
        if path.name != "installed.json" or path.is_symlink() or not path.is_file() or not key:
            raise ValueError("JSON-Verwaltungsaktion ist nicht zulässig")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Heroic-Installationsdatei hat ein unbekanntes Format")
        payload.pop(key, None)
        self._atomic_json_write(path, payload)
        return f"Heroic-Eintrag {key} entfernt"

    @staticmethod
    def _atomic_json_write(path: Path, payload: object) -> None:
        mode = path.stat().st_mode & 0o777
        temporary_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_name = handle.name
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_name, mode)
            os.replace(temporary_name, path)
        finally:
            if temporary_name and Path(temporary_name).exists():
                Path(temporary_name).unlink()

    def _delete_permanently(self, path: Path) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    def _move_to_trash(self, path: Path, size: int) -> RecoveryItem:
        return self.trash.move(path, size)

    def _control_scan(self, plan: RemovalPlan, result: RemovalResult) -> None:
        try:
            discovered = RemovalAnalyzer(self.home).discover_targets(plan.app)
        except Exception as error:  # Kontrollscan darf ein korrektes Entfernen nicht rückgängig machen.
            result.verification_error = str(error)
            return
        kept = {str(target.path.absolute()) for target in plan.targets if not target.selected}
        result.kept_paths = sorted(
            str(target.path.absolute())
            for target in discovered
            if str(target.path.absolute()) in kept
        )
        result.residual_paths = sorted(
            str(target.path.absolute())
            for target in discovered
            if str(target.path.absolute()) not in kept
        )

    def _finish(self, plan: RemovalPlan, result: RemovalResult, permanent: bool) -> RemovalResult:
        result.receipt_path = self._write_receipt(plan, result, permanent)
        if result.receipt_path:
            result.recovery_id = Path(result.receipt_path).stem
        return result

    def _write_receipt(self, plan: RemovalPlan, result: RemovalResult, permanent: bool) -> str:
        state_directory = self.state_home / "restlos/history"
        try:
            state_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
            filename_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            safe_id = "".join(character if character.isalnum() else "-" for character in plan.app.package_id)[:80]
            receipt = state_directory / f"{filename_timestamp}-{safe_id}.json"
            payload = {
                "schema": 3,
                "restlos_version": __version__,
                "timestamp": timestamp,
                "application": plan.app.to_dict(),
                "mode": "permanent" if permanent else "trash",
                "success": result.success,
                "removed_paths": result.removed_paths,
                "recovery_items": [item.to_dict() for item in result.recovery_items],
                "safety_backup": {
                    "archive_path": result.backup_path,
                    "items": [item.to_dict() for item in result.backup_items],
                },
                "actions": [action.label for action in plan.actions],
                "residual_paths": result.residual_paths,
                "kept_paths": result.kept_paths,
                "verification_error": result.verification_error,
                "errors": result.errors,
                "review_required": result.review_required,
                "shared_paths": [target.to_dict() for target in plan.targets if target.shared_with],
            }
            temporary_name = ""
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=state_directory,
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
            return str(receipt)
        except OSError:
            return ""

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False
