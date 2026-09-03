"""Fail-closed review snapshots. No persistent monitoring and no file contents."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from .i18n import translate as _
from .models import AppRecord, RemovalPlan, SourceKind
from .package_managers import NATIVE_PACKAGE_SOURCES, _trusted_binary, adapter_for_source
from .utils import run_command


class ReviewRequired(ValueError):
    pass


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def inventory_digest(apps: list[AppRecord]) -> str:
    return digest(sorted((app.to_dict() for app in apps), key=lambda app: app["key"]))


def plan_digest(plan: RemovalPlan) -> str:
    targets = [target.to_dict() for target in plan.targets]
    for target in targets:
        target.pop("selected")  # This is the only editable part of a reviewed plan.
    return digest((plan.app.to_dict(), targets, [action.to_dict() for action in plan.actions], plan.package_preview))


def package_state(app: AppRecord) -> str:
    commands = {
        SourceKind.APT: ("dpkg-query", "--show", "--showformat=${binary:Package}\t${Version}\t${db:Status-Abbrev}\n"),
        SourceKind.DNF: ("rpm", "-qa"),
        SourceKind.ZYPPER: ("rpm", "-qa"),
        SourceKind.PACMAN: ("pacman", "-Q"),
        SourceKind.FLATPAK: ("flatpak", "list", "--columns=application,ref,installation,active"),
        SourceKind.SNAP: ("snap", "list", "--all"),
    }
    command = commands.get(app.source)
    if command is None:
        return ""
    result = run_command((_trusted_binary(command[0]), *command[1:]), timeout=20)
    if result.returncode != 0 or not result.stdout.strip():
        raise ReviewRequired(_("Der Paketbestand konnte nicht zuverlässig geprüft werden."))
    return digest(sorted(result.stdout.splitlines()))


def _identity(path: Path) -> tuple:
    info = path.lstat()
    return (info.st_dev, info.st_ino, info.st_mode, os.readlink(path) if stat.S_ISLNK(info.st_mode) else "")


def _mount_points() -> set[Path]:
    # ismount alone misses same-device bind mounts. Linux exposes these here.
    # A missing/unreadable mount table is a failed check, never an empty result.
    lines = Path("/proc/self/mountinfo").read_text().splitlines()
    points: set[Path] = set()
    for line in lines:
        fields = line.split()
        if len(fields) < 6:
            raise ReviewRequired(_("Die Einhängepunkte konnten nicht zuverlässig geprüft werden."))
        value = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), fields[4])
        points.add(Path(value))
    if not points:
        raise ReviewRequired(_("Die Einhängepunkte konnten nicht zuverlässig geprüft werden."))
    return points


def path_fingerprint(path: Path, *, max_entries: int = 250_000, timeout: float = 30) -> str:
    """Fingerprint lstat metadata, links and ancestor identities, never follow links.

    Limits/errors abort the check instead of approving a partially scanned tree.
    This detects ordinary changes, not all malicious races or offline edits.
    """
    if not path.is_absolute() or ".." in path.parts or "\0" in str(path):
        raise ReviewRequired(_("Ungültiger Pfad im Löschplan."))
    start = time.monotonic()
    mounts = _mount_points()
    ancestors = [(str(parent), _identity(parent)) for parent in path.parents]
    effective = path.parent.resolve() / path.name
    if not path.is_symlink() and any(mount == effective or effective in mount.parents for mount in mounts):
        raise ReviewRequired(_("Eingehängte Laufwerke im Löschziel werden nicht entfernt."))
    root_device = path.lstat().st_dev
    result = hashlib.sha256()
    stack = [(path, False, None)]
    count = 0
    while stack:
        current, after, previous = stack.pop()
        info = current.lstat()
        signature = (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if after:
            if signature != previous:
                raise ReviewRequired(_("Dateien wurden während der Sicherheitsprüfung verändert."))
            continue
        count += 1
        if count > max_entries or time.monotonic() - start > timeout:
            raise ReviewRequired(_("Die Sicherheitsprüfung ist zu groß oder dauert zu lange; es wurde keine Freigabe erteilt."))
        mode = info.st_mode
        if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
            raise ReviewRequired(_("Spezialdateien im Löschziel können nicht sicher geprüft werden."))
        if info.st_dev != root_device or (stat.S_ISDIR(mode) and os.path.ismount(current)):
            raise ReviewRequired(_("Eingehängte Laufwerke im Löschziel werden nicht entfernt."))
        link = os.readlink(current) if stat.S_ISLNK(mode) else ""
        result.update(digest((str(current.relative_to(path)), signature, link)).encode())
        if stat.S_ISDIR(mode):
            with os.scandir(current) as entries:
                children = []
                for entry in entries:
                    children.append(Path(entry.path))
                    if len(children) + count + len(stack) > max_entries or time.monotonic() - start > timeout:
                        raise ReviewRequired(_("Die Sicherheitsprüfung ist zu groß oder dauert zu lange; es wurde keine Freigabe erteilt."))
                children.sort(reverse=True)
            stack.append((current, True, signature))
            stack.extend((child, False, None) for child in children)
    if ancestors != [(str(parent), _identity(parent)) for parent in path.parents]:
        raise ReviewRequired(_("Ein übergeordneter Ordner wurde während der Prüfung verändert."))
    if mounts != _mount_points():
        raise ReviewRequired(_("Die Einhängepunkte wurden während der Prüfung verändert."))
    result.update(digest(ancestors).encode())
    return result.hexdigest()


def control_paths(plan: RemovalPlan) -> list[Path]:
    values = list(plan.app.desktop_files)
    for action in plan.actions:
        if action.internal_kind:
            values.extend(action.parameters[key] for key in ("database", "path", "cache") if action.parameters.get(key))
    # SQLite changes can reside in WAL before being checkpointed to the database.
    values += [value + "-wal" for value in values if value.endswith(".db")]
    return sorted({Path(value) for value in values if Path(value).is_absolute()})


def optional_fingerprint(path: Path) -> str:
    try:
        return path_fingerprint(path)
    except FileNotFoundError:
        if os.path.lexists(path):
            raise  # A vanished child is not the same as a missing root.
        ancestors = []
        for parent in path.parents:
            try:
                ancestors.append((str(parent), _identity(parent)))
            except FileNotFoundError:
                ancestors.append((str(parent), "missing"))
        return digest(("missing", str(path), str(path.parent.resolve()), ancestors))


@dataclass(frozen=True)
class PlanSnapshot:
    home: Path
    plan: str
    inventory: str
    packages: str
    paths: dict[str, str]
    controls: dict[str, str]

    def validate_definition(self, plan: RemovalPlan) -> None:
        if plan.safety_error or self.plan != plan_digest(plan):
            raise ReviewRequired(_("Der Löschplan wurde verändert. Bitte erneut analysieren und bestätigen."))
        if any(target.selected and target.shared_with for target in plan.targets):
            raise ReviewRequired(_("Ein gemeinsam genutzter Pfad darf nicht zur Löschung ausgewählt werden."))

    def validate_files(self, plan: RemovalPlan, *, controls: bool = True, allow_missing: bool = False) -> None:
        self.validate_definition(plan)
        for target in plan.selected_targets:
            self.validate_target(target.path, allow_missing=allow_missing)
        if controls:
            for path, before in self.controls.items():
                if optional_fingerprint(Path(path)) != before:
                    raise ReviewRequired(_("Programm- oder Bibliotheksinformationen wurden verändert: {path}", path=path))

    def validate_target(self, path: Path, *, allow_missing: bool = False) -> None:
        try:
            fingerprint = path_fingerprint(path)
        except FileNotFoundError:
            if allow_missing and not os.path.lexists(path):
                return
            raise ReviewRequired(_("Ein Löschziel ist nicht mehr vorhanden: {path}", path=path))
        if self.paths.get(str(path)) != fingerprint:
            raise ReviewRequired(_("Seit der Vorschau verändert: {path}", path=path))

    def validate_environment(self, plan: RemovalPlan, applications: list[AppRecord]) -> None:
        self.validate_definition(plan)
        if self.inventory != inventory_digest(applications):
            raise ReviewRequired(_("Die Programmliste oder eine bekannte Datenzuordnung hat sich geändert. Bitte erneut analysieren."))
        # An unchanged launcher record can point through a retargeted symlink.
        from .sharing import protect_shared_targets
        checked = deepcopy(plan)
        protect_shared_targets(checked, applications, self.home)
        if any(old.shared_with != new.shared_with for old, new in zip(plan.targets, checked.targets)):
            raise ReviewRequired(_("Die Programmliste oder eine bekannte Datenzuordnung hat sich geändert. Bitte erneut analysieren."))
        if self.packages != package_state(plan.app):
            raise ReviewRequired(_("Der Paketbestand hat sich seit der Vorschau geändert. Bitte erneut analysieren."))
        if plan.app.source in NATIVE_PACKAGE_SOURCES and plan.actions:
            adapter = adapter_for_source(plan.app.source)
            preview = adapter.preview_removal(plan.app.package_id, plan.app.metadata.get("package_manager", ""))
            if (preview.error or tuple(sorted(set(preview.removed_packages))) != plan.package_preview
                    or any(adapter.is_protected(package) for package in preview.removed_packages)):
                raise ReviewRequired(_("Die erneute Paketsimulation stimmt nicht mit der bestätigten Vorschau überein."))


def seal_plan(plan: RemovalPlan, applications: list[AppRecord], *, home: Path | None = None) -> None:
    """Called at review time, never silently during execution of an old plan."""
    plan.snapshot = None
    paths = {str(target.path): path_fingerprint(target.path) for target in plan.targets if not target.shared_with}
    controls = {str(path): optional_fingerprint(path) for path in control_paths(plan)}
    plan.snapshot = PlanSnapshot((home or Path.home()).absolute(), plan_digest(plan), inventory_digest(applications), package_state(plan.app), paths, controls)
