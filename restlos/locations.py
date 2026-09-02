"""Read-only discovery of places to inspect, independent of deletion targets."""
from __future__ import annotations

import json
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import translate as _
from .models import AppRecord, RemovalPlan, SourceKind
from .package_managers import NATIVE_PACKAGE_SOURCES, PACKAGE_ID_PATTERN, _trusted_binary
from .utils import run_command


SNAP_MOUNT_ROOTS = (Path("/snap"), Path("/var/lib/snapd/snap"))


@dataclass(frozen=True, slots=True)
class AppLocation:
    path: Path
    reason: str


@dataclass(slots=True)
class LocationResult:
    locations: list[AppLocation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def folder_for_path(path: Path) -> Path:
    """Open directories themselves, but show files/links in their parent folder.

    In particular, never pass an executable or a .desktop file to a URI handler.
    Do not follow the final symlink: users should inspect the link being removed,
    not mistake its target for the selected deletion target.
    """
    if not path.is_absolute() or "\0" in str(path):
        raise ValueError(_("Nur absolute lokale Dateipfade können geöffnet werden."))
    mode = path.lstat().st_mode  # Also accepts broken links; missing paths raise.
    if stat.S_ISDIR(mode):
        folder = path
    elif stat.S_ISREG(mode) or stat.S_ISLNK(mode):
        folder = path.parent
    else:
        raise ValueError(_("Dieser Pfad ist keine normale Datei und kein Ordner."))
    folder = folder.resolve(strict=True)
    if not folder.is_dir():
        raise NotADirectoryError(str(folder))
    return folder


class LocationResolver:
    """Inspect metadata and package file lists, never execute launchers or remove.

    Returned locations may be shared system directories. They must never be
    added to a RemovalPlan merely because they appear in this inspection list.
    """

    def __init__(self, *, limit: int = 250) -> None:
        self.limit = max(1, limit)

    def inspect(self, app: AppRecord, plan: RemovalPlan | None = None) -> LocationResult:
        result = LocationResult()
        seen: set[Path] = set()
        truncated = False

        def add(value: str | Path, reason: str) -> None:
            nonlocal truncated
            if not value or "\0" in str(value):
                return
            path = Path(value)
            if not path.is_absolute() or path in seen:
                return
            try:
                folder_for_path(path)
            except (OSError, ValueError, RuntimeError):
                return
            seen.add(path)
            if len(result.locations) >= self.limit:
                truncated = True
                return
            result.locations.append(AppLocation(path, reason))

        for key, label in (
            ("install_root", _("Programm-/Spieleordner")),
            ("executable", _("Programmdatei (öffnet den übergeordneten Ordner)")),
            ("wine_prefix", _("Wine-Präfix (kann gemeinsam genutzt sein)")),
        ):
            add(app.metadata.get(key, ""), label)

        # Include deselected data too: inspection must not change or depend on
        # what the user intends to delete. Never mix a previous app's plan in.
        if plan is not None and plan.app.key == app.key:
            for target in plan.targets:
                add(target.path, target.reason)
        try:
            owned = json.loads(app.metadata.get("owned_paths", "[]"))
        except (ValueError, TypeError):
            owned = []
        if isinstance(owned, list):
            for entry in owned:
                if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                    add(entry["path"], _("Vom Spiele-Launcher zugeordneter Pfad"))
        for path in app.desktop_files:
            add(path, _("Menüeintrag"))

        if app.source in NATIVE_PACKAGE_SOURCES or app.source in {SourceKind.FLATPAK, SourceKind.SNAP}:
            if not PACKAGE_ID_PATTERN.fullmatch(app.package_id):
                result.warnings.append(_("Ungültige Paketkennung; Paketdateien wurden nicht abgefragt."))
            elif app.source == SourceKind.SNAP:
                found = False
                # Snap mount roots vary across distributions. Resolve this known
                # current-revision link so the mounted program directory opens.
                for root in SNAP_MOUNT_ROOTS:
                    try:
                        folder = (root / app.package_id / "current").resolve(strict=True)
                        if folder.is_dir():
                            add(folder, _("Snap-Programmdateien (schreibgeschützt)"))
                            found = True
                            break
                    except (OSError, RuntimeError):
                        continue
                if not found:
                    result.warnings.append(_("Der Snap-Installationsordner ist nicht verfügbar."))
            else:
                self._package_locations(app, add, result)
        if truncated:
            result.warnings.append(_("Die Speicherortliste ist auf {count} Einträge begrenzt.", count=self.limit))
        return result

    def _package_locations(
        self, app: AppRecord, add: Callable[[str | Path, str], None], result: LocationResult,
    ) -> None:
        package = app.package_id
        if app.source == SourceKind.APT:
            command = (_trusted_binary("dpkg-query"), "--listfiles", package)
        elif app.source in {SourceKind.DNF, SourceKind.ZYPPER}:
            command = (_trusted_binary("rpm"), "-ql", package)
        elif app.source == SourceKind.PACMAN:
            command = (_trusted_binary("pacman"), "-Qql", package)
        else:
            installation = app.metadata.get("installation", "user")
            if installation in {"user", "system"}:
                scope = f"--{installation}"
            elif re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", installation):
                scope = f"--installation={installation}"
            else:
                result.warnings.append(_("Ungültige Flatpak-Installation; Programmdateien wurden nicht abgefragt."))
                return
            command = (_trusted_binary("flatpak"), "info", scope, "--show-location", package)

        response = run_command(command, timeout=15)
        if response.returncode != 0:
            result.warnings.append(_("Paketdateien konnten nicht abgefragt werden. Andere bekannte Speicherorte werden trotzdem angezeigt."))
            return
        if app.source == SourceKind.FLATPAK:
            # --show-location returns one absolute deployment path, not a URI.
            value = response.stdout.strip()
            if value and "\n" not in value:
                add(value, _("Flatpak-Programmdateien (paketverwaltet)"))
            return

        for line in response.stdout.splitlines():
            path = Path(line)
            if not line or not path.is_absolute():
                continue
            try:
                # Package lists include broad ancestors such as / and /usr.
                # Only derive folders from actual files, never list ancestors.
                mode = path.lstat().st_mode
                if stat.S_ISREG(mode) or stat.S_ISLNK(mode):
                    add(path.parent, _("Paketdateien (Ordner kann gemeinsam genutzt sein)"))
            except (OSError, ValueError):
                continue
