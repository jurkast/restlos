from __future__ import annotations

import os
import re
import shutil
from collections import defaultdict
from pathlib import Path

from . import APP_ID
from .game_scanners import GamePlatformScanner
from .models import AppRecord, SourceKind
from .utils import DesktopEntry, command_executable, parse_desktop_file, run_command


PACKAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._:-]*$")


class ApplicationScanner:
    """Collect user-facing applications without executing their launchers."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = (home or Path.home()).absolute()
        self._desktop_entries = self._read_desktop_entries()

    def scan(self) -> list[AppRecord]:
        records: list[AppRecord] = []
        records.extend(self._scan_flatpak())
        records.extend(self._scan_snap())
        records.extend(self._scan_apt())
        game_scanner = GamePlatformScanner(self.home)
        records.extend(game_scanner.scan())
        records.extend(self._scan_wine_and_manual())
        records.extend(self._scan_appimages(records))
        records.extend(game_scanner.scan_unmanaged_game_folders(records))

        deduplicated: dict[str, AppRecord] = {}
        for record in records:
            if record.package_id == APP_ID or record.key.endswith(":restlos"):
                continue
            current = deduplicated.get(record.key)
            if current is None or len(record.description) > len(current.description):
                deduplicated[record.key] = record
        return sorted(deduplicated.values(), key=lambda app: app.name.casefold())

    def _desktop_directories(self) -> tuple[Path, ...]:
        return (
            self.home / ".local/share/applications",
            self.home / ".local/share/flatpak/exports/share/applications",
            Path("/var/lib/flatpak/exports/share/applications"),
            Path("/var/lib/snapd/desktop/applications"),
            Path("/usr/local/share/applications"),
            Path("/usr/share/applications"),
        )

    def _read_desktop_entries(self) -> list[DesktopEntry]:
        entries: list[DesktopEntry] = []
        seen: set[str] = set()
        for directory in self._desktop_directories():
            if not directory.is_dir():
                continue
            try:
                candidates = directory.rglob("*.desktop") if "wine/Programs" in str(directory) else directory.glob("*.desktop")
                for path in candidates:
                    key = str(path.absolute())
                    if key in seen:
                        continue
                    seen.add(key)
                    entry = parse_desktop_file(path)
                    if entry and not entry.hidden and not entry.no_display and entry.exec_line:
                        entries.append(entry)
            except OSError:
                continue
        wine_directory = self.home / ".local/share/applications/wine/Programs"
        if wine_directory.is_dir():
            for path in wine_directory.rglob("*.desktop"):
                key = str(path.absolute())
                if key in seen:
                    continue
                entry = parse_desktop_file(path)
                if entry and not entry.hidden and entry.exec_line:
                    entries.append(entry)
        return entries

    def _scan_flatpak(self) -> list[AppRecord]:
        if not shutil.which("flatpak"):
            return []
        result = run_command(
            ("flatpak", "list", "--app", "--columns=application,name,installation"),
            timeout=8,
        )
        if result.returncode != 0:
            return []
        by_id = {entry.app_id: entry for entry in self._desktop_entries}
        records: list[AppRecord] = []
        for line in result.stdout.splitlines():
            columns = line.split("\t")
            if len(columns) < 2:
                continue
            app_id, name = columns[0].strip(), columns[1].strip()
            if not PACKAGE_ID_PATTERN.fullmatch(app_id):
                continue
            installation = columns[2].strip() if len(columns) > 2 else "user"
            entry = by_id.get(app_id)
            records.append(
                AppRecord(
                    key=f"flatpak:{installation}:{app_id}",
                    name=(entry.name if entry else name) or app_id,
                    source=SourceKind.FLATPAK,
                    package_id=app_id,
                    description=entry.comment if entry else "Flatpak-Anwendung",
                    icon=entry.icon if entry else app_id,
                    exec_line=entry.exec_line if entry else f"flatpak run {app_id}",
                    desktop_files=(str(entry.path),) if entry else (),
                    scope="System" if installation == "system" else "Benutzer",
                    metadata={"installation": installation},
                )
            )
        return records

    def _scan_snap(self) -> list[AppRecord]:
        if not shutil.which("snap"):
            return []
        result = run_command(("snap", "list"), timeout=6)
        if result.returncode != 0:
            return []
        entries_by_snap: dict[str, list[DesktopEntry]] = defaultdict(list)
        for entry in self._desktop_entries:
            if str(entry.path).startswith("/var/lib/snapd/desktop/applications/"):
                entries_by_snap[entry.app_id.split("_", 1)[0]].append(entry)
        records: list[AppRecord] = []
        for line_number, line in enumerate(result.stdout.splitlines()):
            if line_number == 0:
                continue
            columns = line.split()
            if not columns:
                continue
            name = columns[0]
            if not PACKAGE_ID_PATTERN.fullmatch(name):
                continue
            entries = entries_by_snap.get(name, [])
            if not entries:
                continue
            entry = entries[0] if entries else None
            records.append(
                AppRecord(
                    key=f"snap:{name}",
                    name=entry.name if entry else name,
                    source=SourceKind.SNAP,
                    package_id=name,
                    description=entry.comment if entry else "Snap-Anwendung",
                    icon=entry.icon if entry else "package-x-generic",
                    exec_line=entry.exec_line if entry else f"snap run {name}",
                    desktop_files=tuple(str(item.path) for item in entries),
                    scope="System",
                )
            )
        return records

    def _scan_apt(self) -> list[AppRecord]:
        system_entries = [
            entry
            for entry in self._desktop_entries
            if str(entry.path).startswith(("/usr/share/applications/", "/usr/local/share/applications/"))
        ]
        paths = [str(entry.path) for entry in system_entries if str(entry.path).startswith("/usr/")]
        if not paths or not shutil.which("dpkg-query"):
            return []
        result = run_command(("dpkg-query", "-S", *paths), timeout=15)
        owners: dict[str, str] = {}
        for line in result.stdout.splitlines():
            try:
                package_part, owned_path = line.split(": ", 1)
            except ValueError:
                continue
            package = package_part.split(",", 1)[0].split(":", 1)[0]
            if PACKAGE_ID_PATTERN.fullmatch(package):
                owners[owned_path] = package

        by_package: dict[str, list[DesktopEntry]] = defaultdict(list)
        for entry in system_entries:
            package = owners.get(str(entry.path))
            if package:
                by_package[package].append(entry)
        records: list[AppRecord] = []
        for package, entries in by_package.items():
            visible = sorted(entries, key=lambda item: ("settings" in item.app_id.casefold(), len(item.name)))
            entry = visible[0]
            records.append(
                AppRecord(
                    key=f"apt:{package}",
                    name=entry.name,
                    source=SourceKind.APT,
                    package_id=package,
                    description=entry.comment or entry.generic_name or "APT/DEB-Anwendung",
                    icon=entry.icon,
                    exec_line=entry.exec_line,
                    desktop_files=tuple(str(item.path) for item in entries),
                    scope="System",
                )
            )
        return records

    def _scan_wine_and_manual(self) -> list[AppRecord]:
        records: list[AppRecord] = []
        for entry in self._desktop_entries:
            path_string = str(entry.path)
            if not path_string.startswith(str(self.home / ".local/share/applications")):
                continue
            if entry.app_id == APP_ID:
                continue
            executable = command_executable(entry.exec_line)
            expanded = Path(os.path.expandvars(os.path.expanduser(executable))) if executable else Path()
            looks_like_wine = (
                "/wine/Programs/" in path_string
                or re.search(r"(?:^|\s)(?:wine|wine64)(?:\s|$)", entry.exec_line) is not None
                or "WINEPREFIX=" in entry.exec_line
            )
            is_home_executable = executable.startswith((str(self.home), "~/", "$HOME/"))
            if not looks_like_wine and not is_home_executable:
                continue
            source = SourceKind.WINE if looks_like_wine else SourceKind.MANUAL
            metadata: dict[str, str] = {}
            prefix_match = re.search(r"WINEPREFIX=(?:['\"])?([^'\"\s]+)", entry.exec_line)
            if prefix_match:
                metadata["wine_prefix"] = os.path.expanduser(os.path.expandvars(prefix_match.group(1)))
            if expanded.is_absolute():
                metadata["executable"] = str(expanded)
            records.append(
                AppRecord(
                    key=f"{source.name.casefold()}:{entry.app_id}",
                    name=entry.name,
                    source=source,
                    package_id=entry.app_id,
                    description=entry.comment or ("Windows-Anwendung über Wine" if looks_like_wine else "Manuell installierte Anwendung"),
                    icon=entry.icon,
                    exec_line=entry.exec_line,
                    desktop_files=(str(entry.path),),
                    scope="Benutzer",
                    metadata=metadata,
                )
            )
        return records

    def _scan_appimages(self, existing: list[AppRecord]) -> list[AppRecord]:
        referenced = {record.metadata.get("executable", "") for record in existing}
        roots = (
            self.home / "Applications",
            self.home / "Desktop",
            self.home / "Downloads",
            self.home / ".local/bin",
            self.home / "Games",
        )
        records: list[AppRecord] = []
        seen: set[str] = set()
        for root in roots:
            if not root.is_dir():
                continue
            try:
                for current, directories, files in os.walk(root):
                    depth = len(Path(current).relative_to(root).parts)
                    if depth >= 2:
                        directories.clear()
                    for filename in files:
                        if not filename.casefold().endswith(".appimage"):
                            continue
                        path = Path(current) / filename
                        path_string = str(path)
                        if path_string in referenced or path_string in seen:
                            continue
                        seen.add(path_string)
                        name = path.stem.replace("-x86_64", "").replace("_", " ").replace("-", " ").strip()
                        records.append(
                            AppRecord(
                                key=f"appimage:{path_string}",
                                name=name or path.stem,
                                source=SourceKind.APPIMAGE,
                                package_id=path.stem,
                                description="Eigenständige AppImage-Anwendung",
                                icon="application-x-executable",
                                exec_line=path_string,
                                scope="Benutzer",
                                metadata={"executable": path_string},
                            )
                        )
            except OSError:
                continue
        return records
