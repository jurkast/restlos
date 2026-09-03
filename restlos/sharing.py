"""Conservative, read-only cross-application references, not proof of ownership."""
from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path

from .i18n import translate as _
from .models import AppRecord, RemovalPlan, SharedUse, SourceKind
from .package_managers import PACKAGE_ID_PATTERN
from .utils import command_executable, is_within


def references(app: AppRecord, home: Path) -> Iterable[tuple[Path, str]]:
    """Only explicit metadata/IDs; similar names alone do not establish sharing."""
    values = [(value, _("Programmstarter")) for value in app.desktop_files]
    for key, evidence in (
        ("install_root", _("Installationsordner laut Programmeintrag")),
        ("wine_prefix", _("Wine-Präfix laut Programmeintrag")),
        ("executable", _("Programmdatei laut Programmeintrag")),
    ):
        values.append((app.metadata.get(key, ""), evidence))
    values.append((command_executable(app.exec_line), _("Programmstarter")))
    values.append((app.icon, _("Anwendungssymbol")))
    if app.source == SourceKind.WINE and not app.metadata.get("wine_prefix"):
        values.append((str(home / ".wine"), _("Gemeinsames Standard-Wine-Präfix")))
    try:
        owned = json.loads(app.metadata.get("owned_paths", "[]"))
    except (ValueError, TypeError):
        owned = []
    if isinstance(owned, list):
        for item in owned:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                values.append((item["path"], _("Pfad laut Spielebibliothek")))
    if PACKAGE_ID_PATTERN.fullmatch(app.package_id):
        for directory in (".config", ".cache", ".local/share", ".local/state", ".var/app", "snap"):
            values.append((str(home / directory / app.package_id), _("Datenpfad mit identischer Paketkennung")))
    seen: set[Path] = set()
    for raw, evidence in values:
        if not raw or "\0" in raw:
            continue
        path = Path(os.path.expandvars(os.path.expanduser(raw)))
        if not path.is_absolute() or ".." in path.parts:
            continue
        try:
            if not (path.exists() or path.is_symlink()):
                continue
            # Keep the link itself as a reference, and also its destination.
            variants = (path.parent.resolve() / path.name, path.resolve())
        except (OSError, RuntimeError):
            continue
        for reference in variants:
            if reference not in seen:
                seen.add(reference)
                yield reference, evidence


def protect_shared_targets(plan: RemovalPlan, applications: Iterable[AppRecord], home: Path) -> None:
    indexed = [
        (app, path, evidence)
        for app in applications if app.key != plan.app.key
        for path, evidence in references(app, home)
    ]
    for target in plan.targets:
        target.shared_with.clear()
        # Removing a symlink removes the entry, not its destination.
        candidate = target.path.parent.resolve() / target.path.name
        candidate_directory = not target.path.is_symlink() and target.path.is_dir()
        seen: set[tuple[str, str]] = set()
        for app, reference, evidence in indexed:
            overlaps = (
                candidate == reference
                or (candidate_directory and is_within(reference, candidate))
                or (reference.is_dir() and is_within(candidate, reference))
            )
            identity = (app.key, str(reference))
            if overlaps and identity not in seen:
                seen.add(identity)
                target.shared_with.append(SharedUse(app.key, app.name, app.source.value, str(reference), evidence))
        if target.shared_with:
            target.selected = False
    if any(target.shared_with for target in plan.targets):
        plan.warnings.append(_("Gemeinsam referenzierte Pfade sind gesperrt. Die betroffenen Anwendungen und Nachweise stehen am jeweiligen Pfad."))
        # --delete-data and --purge bypass our individual target selections.
        # Do not execute a manager action which could remove protected data.
        if plan.app.source in {SourceKind.FLATPAK, SourceKind.SNAP}:
            plan.safety_error = _("Die Paketaktion könnte gemeinsam genutzte Daten mitentfernen und wurde deshalb gesperrt.")
