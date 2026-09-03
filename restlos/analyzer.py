from __future__ import annotations

import json
import os
import re
from pathlib import Path
from copy import deepcopy

from .models import AppRecord, Confidence, RemovalAction, RemovalPlan, RemovalTarget, SourceKind
from .package_managers import (
    NATIVE_PACKAGE_SOURCES,
    PACKAGE_ID_PATTERN,
    PackageManagerAdapter,
    adapter_for_source,
)
from .utils import command_executable, extract_home_paths, is_within, normalize_key, path_size
from .i18n import translate as _
from .safety import seal_plan
from .sharing import protect_shared_targets


class UnsafeTargetError(ValueError):
    pass


class PathGuard:
    def __init__(self, home: Path) -> None:
        self.home = home.absolute()
        self.allowed_roots = (
            self.home / ".config",
            self.home / ".cache",
            self.home / ".local/share",
            self.home / ".local/state",
            self.home / ".local/bin",
            self.home / ".var/app",
            self.home / ".wine/drive_c/Program Files",
            self.home / ".wine/drive_c/Program Files (x86)",
            self.home / "snap",
            self.home / "Applications",
            self.home / "Games",
            self.home / "Downloads",
            self.home / "Desktop",
            self.home / "Schreibtisch",
        )
        self.protected = {
            Path("/"),
            self.home,
            self.home / ".config",
            self.home / ".cache",
            self.home / ".local",
            self.home / ".local/share",
            self.home / ".local/state",
            self.home / ".local/bin",
            self.home / ".local/share/flatpak",
            self.home / ".local/share/lutris",
            self.home / ".cache/lutris",
            self.home / ".local/share/Steam",
            self.home / ".steam/debian-installation",
            self.home / ".config/heroic",
            self.home / ".config/legendary",
            self.home / ".PlayOnLinux",
            self.home / ".cache/flatpak",
            self.home / ".config/flatpak",
            self.home / ".var",
            self.home / ".var/app",
            self.home / ".wine",
            self.home / "snap",
            self.home / "Applications",
            self.home / "Games",
            self.home / "Downloads",
            self.home / "Desktop",
            self.home / "Schreibtisch",
            self.home / "Documents",
            self.home / "Dokumente",
            self.home / "Pictures",
            self.home / "Bilder",
            self.home / "Music",
            self.home / "Musik",
            self.home / "Videos",
            Path("/usr"),
            Path("/usr/local"),
            Path("/opt"),
            Path("/var"),
        }

    def validate(self, path: Path, trusted_roots: tuple[Path, ...] = ()) -> None:
        if not path.is_absolute() or ".." in path.parts or "\0" in str(path):
            raise UnsafeTargetError("Pfad ist nicht absolut oder enthält unsichere Bestandteile")
        absolute = path.absolute()
        if absolute in self.protected:
            raise UnsafeTargetError(f"geschützter Pfad: {absolute}")
        safe_trusted = tuple(
            root.absolute()
            for root in trusted_roots
            if root.is_absolute() and root.absolute() not in self.protected and len(root.absolute().parts) >= 4
        )
        if not any(is_within(absolute, root) for root in (*self.allowed_roots, *safe_trusted)):
            raise UnsafeTargetError(f"Pfad liegt außerhalb sicherer Benutzerbereiche: {absolute}")
        if len(absolute.parts) < 4:
            raise UnsafeTargetError(f"Pfad ist zu breit: {absolute}")
        # Follow ancestors only: deleting the final symlink is safe, traversing
        # a link into an unrelated directory is not. Standard library symlinks
        # (e.g. ~/.steam) and explicitly registered external roots still work.
        effective = absolute.parent.resolve() / absolute.name
        effective_roots = tuple(root.resolve() for root in self.allowed_roots)
        effective_trusted = tuple(root.parent.resolve() / root.name for root in safe_trusted)
        if effective in {root.resolve() for root in self.protected} and not absolute.is_symlink():
            raise UnsafeTargetError(f"geschützter aufgelöster Pfad: {effective}")
        if not any(is_within(effective, root) for root in (*effective_roots, *effective_trusted)):
            raise UnsafeTargetError(f"übergeordneter Symlink verlässt den erlaubten Bereich: {absolute}")


class RemovalAnalyzer:
    def __init__(self, home: Path | None = None) -> None:
        self.home = (home or Path.home()).absolute()
        self.guard = PathGuard(self.home)

    def analyze(self, app: AppRecord, *, applications: list[AppRecord] | None = None) -> RemovalPlan:
        if applications is None:
            from .scanners import ApplicationScanner
            applications = ApplicationScanner(self.home).scan()
        # Refresh stale GUI entries from the same inventory used for sharing.
        app = deepcopy(next((item for item in applications if item.key == app.key), app))
        plan = RemovalPlan(app=app)

        if self._add_managed_action(plan, app):
            return plan
        self._add_manager_actions(plan, app)
        plan.targets = self.discover_targets(app)

        if app.source == SourceKind.WINE and app.metadata.get("wine_prefix") in {"", str(self.home / ".wine")}:
            plan.warnings.append(
                "Die Anwendung verwendet möglicherweise das gemeinsame Standard-Wine-Präfix. "
                "Restlos löscht dieses Präfix nicht, weil darin weitere Windows-Programme liegen können."
            )
        if app.source in {SourceKind.MANUAL, SourceKind.WINE, SourceKind.APPIMAGE, SourceKind.PORTABLE}:
            plan.warnings.append(
                "Manuelle Installationen besitzen kein vollständiges Systemmanifest. Prüfe deshalb die vorgeschlagenen Pfade vor dem Löschen."
            )
        if app.source == SourceKind.BOTTLES:
            plan.warnings.append(
                "Diese Auswahl ist eine vollständige Bottle. Alle Programme und Windows-Daten innerhalb dieser Umgebung werden gemeinsam entfernt."
            )
        if app.source == SourceKind.STEAM:
            plan.warnings.append(
                "Lokale Steam-Daten werden entfernt. Bereits mit Steam Cloud synchronisierte Spielstände können bei einer Neuinstallation erneut geladen werden."
            )
        if not plan.actions and not plan.targets:
            plan.warnings.append("Es wurden keine sicher zuordenbaren Löschziele gefunden.")
        protect_shared_targets(plan, applications, self.home)
        plan.warnings.append(_("Die Schutzprüfung berücksichtigt bekannte Programmeinträge, keine unbekannten oder nicht lesbaren Installationen."))
        if not plan.safety_error:
            try:
                seal_plan(plan, applications, home=self.home)
            except (OSError, ValueError, RuntimeError) as error:
                plan.safety_error = _("Sicherheitsprüfung nicht abgeschlossen: {error}", error=error)
        return plan

    def discover_targets(self, app: AppRecord) -> list[RemovalTarget]:
        """Findet aktuell vorhandene Dateiziele ohne Paketaktionen auszuführen oder zu simulieren."""

        aliases = self._aliases(app)
        candidates: list[tuple[Path, str, Confidence]] = []
        candidates.extend(self._manager_targets(app))
        candidates.extend(self._explicit_targets(app))
        candidates.extend(self._known_data_targets(app, aliases))
        candidates.extend(self._launcher_references(app, aliases))
        candidates.extend(self._default_wine_targets(app, aliases))

        for desktop_file in app.desktop_files:
            path = Path(desktop_file)
            if is_within(path, self.home):
                candidates.append((path, "Menüeintrag", Confidence.CERTAIN))

        icon_path = Path(os.path.expanduser(app.icon))
        if icon_path.is_absolute() and is_within(icon_path, self.home):
            candidates.append((icon_path, "Anwendungssymbol", Confidence.CERTAIN))

        return self._safe_targets(candidates, self._trusted_paths(app))

    @staticmethod
    def _metadata_list(app: AppRecord, key: str) -> list[object]:
        try:
            value = json.loads(app.metadata.get(key, "[]"))
        except (TypeError, json.JSONDecodeError):
            return []
        return value if isinstance(value, list) else []

    def _trusted_paths(self, app: AppRecord) -> tuple[Path, ...]:
        result: list[Path] = []
        for raw in self._metadata_list(app, "trusted_paths"):
            if not isinstance(raw, str):
                continue
            path = Path(os.path.expandvars(os.path.expanduser(raw)))
            if path.is_absolute():
                result.append(path.absolute())
        return tuple(result)

    def _manager_targets(self, app: AppRecord) -> list[tuple[Path, str, Confidence]]:
        result: list[tuple[Path, str, Confidence]] = []
        for item in self._metadata_list(app, "owned_paths"):
            if not isinstance(item, dict):
                continue
            raw_path = item.get("path")
            reason = item.get("reason")
            if not isinstance(raw_path, str) or not isinstance(reason, str):
                continue
            path = Path(os.path.expandvars(os.path.expanduser(raw_path)))
            if path.is_absolute():
                result.append((path, reason, Confidence.CERTAIN))
        return result

    def _add_manager_actions(self, plan: RemovalPlan, app: AppRecord) -> None:
        supported = {"lutris-database", "json-remove-key"}
        for item in self._metadata_list(app, "manager_actions"):
            if not isinstance(item, dict):
                continue
            kind = item.get("kind")
            label = item.get("label")
            parameters = item.get("parameters")
            if kind not in supported or not isinstance(label, str) or not isinstance(parameters, dict):
                continue
            clean_parameters = {
                str(key): str(value)
                for key, value in parameters.items()
                if isinstance(key, str) and isinstance(value, (str, int))
            }
            plan.actions.append(
                RemovalAction(label=label, internal_kind=str(kind), parameters=clean_parameters)
            )

    def _add_managed_action(self, plan: RemovalPlan, app: AppRecord) -> bool:
        package = app.package_id
        if not PACKAGE_ID_PATTERN.fullmatch(package):
            if app.source in {*NATIVE_PACKAGE_SOURCES, SourceKind.FLATPAK, SourceKind.SNAP}:
                plan.warnings.append("Die Paketkennung enthält unerlaubte Zeichen; die Paketaktion wurde blockiert.")
                return True
            return False
        adapter = adapter_for_source(app.source)
        if adapter is not None:
            manager_name = app.metadata.get("package_manager", "")
            if self._native_action_is_unsafe(plan, adapter, package, manager_name):
                return True
            plan.actions.append(
                RemovalAction(
                    label=adapter.removal_label(package),
                    command=adapter.removal_command(package, manager_name),
                    privileged=True,
                )
            )
        elif app.source == SourceKind.FLATPAK:
            command = ["/usr/bin/flatpak", "uninstall", "--delete-data", "-y"]
            if app.metadata.get("installation") == "system":
                command.insert(0, "/usr/bin/pkexec")
                command.insert(2, "--system")
            else:
                command.insert(1, "--user")
            command.append(package)
            plan.actions.append(
                RemovalAction(
                    label=f"Flatpak „{package}“ samt App-Daten entfernen",
                    command=tuple(command),
                    privileged=app.metadata.get("installation") == "system",
                )
            )
        elif app.source == SourceKind.SNAP:
            plan.actions.append(
                RemovalAction(
                    label=f"Snap „{package}“ ohne gespeicherten Snapshot entfernen",
                    command=("/usr/bin/pkexec", "/usr/bin/snap", "remove", "--purge", package),
                    privileged=True,
                )
            )
        return False

    def _native_action_is_unsafe(
        self,
        plan: RemovalPlan,
        adapter: PackageManagerAdapter,
        package: str,
        manager_name: str,
    ) -> bool:
        preview = adapter.preview_removal(package, manager_name)
        if preview.error:
            plan.warnings.append(
                f"{preview.error} Die Paketaktion wurde vorsorglich blockiert."
            )
            return True
        removed = preview.removed_packages
        plan.package_preview = tuple(sorted(set(removed)))
        critical = sorted({name for name in removed if adapter.is_protected(name)})
        if critical:
            plan.warnings.append(
                f"Entfernung blockiert: Die {adapter.source.value}-Simulation würde wichtige Systemkomponenten entfernen: "
                + ", ".join(critical)
            )
            return True
        additional = sorted({name for name in removed if name != package})
        if additional:
            additional_preview = ", ".join(additional[:8])
            suffix = " …" if len(additional) > 8 else ""
            plan.warnings.append(
                f"{adapter.source.value} wird zusätzlich {len(additional)} abhängige(s) Paket(e) entfernen: "
                f"{additional_preview}{suffix}"
            )
        return False

    def _aliases(self, app: AppRecord) -> set[str]:
        values = {app.name, app.package_id}
        if app.source in {SourceKind.MANUAL, SourceKind.WINE, SourceKind.APPIMAGE}:
            values.add(Path(command_executable(app.exec_line)).stem)
        values.update(re.split(r"[.\s_:/\\-]+", app.package_id))
        for desktop in app.desktop_files:
            values.add(Path(desktop).stem)
        ignored = {
            "app", "application", "desktop", "linux", "launcher", "client", "program",
            "com", "org", "net", "io", "eu", "de", "gtk", "qt", "bin", "x8664",
            "gnome", "kde", "canonical", "ubuntu", "zorin", "microsoft", "google", "mozilla",
            "wine", "flatpak", "snap", "browser", "player", "viewer", "editor", "manager",
            "lutris", "steam", "heroic", "bottles", "playonlinux", "epic", "gog",
            "utility", "utilities", "tools", "setup", "installer",
        }
        aliases = {normalize_key(value) for value in values}
        aliases = {alias for alias in aliases if len(alias) >= 4 and alias not in ignored}
        full_name = normalize_key(app.name)
        if len(full_name) >= 4:
            aliases.add(full_name)
        return aliases

    def _match_confidence(self, name: str, aliases: set[str]) -> Confidence | None:
        normalized = normalize_key(name)
        if not normalized:
            return None
        if normalized in aliases:
            return Confidence.CERTAIN
        reduced = normalized
        removable_suffixes = (
            "appimage", "targz", "tarxz", "zip", "deb", "exe", "msi",
            "linuxinstaller", "installer", "linuxsetup", "setup", "launcher", "client",
        )
        changed = True
        while changed:
            changed = False
            for suffix in removable_suffixes:
                if reduced.endswith(suffix) and len(reduced) > len(suffix) + 3:
                    reduced = reduced[: -len(suffix)]
                    changed = True
                    break
        if len(reduced) >= 4 and reduced in aliases:
            return Confidence.HIGH
        for alias in aliases:
            if len(alias) < 6:
                continue
            shorter, longer = sorted((alias, normalized), key=len)
            if shorter and longer.startswith(shorter) and len(shorter) / len(longer) >= 0.62:
                return Confidence.HIGH
            if shorter and shorter in longer and len(shorter) / len(longer) >= 0.72:
                return Confidence.POSSIBLE
        return None

    def _explicit_targets(self, app: AppRecord) -> list[tuple[Path, str, Confidence]]:
        result: list[tuple[Path, str, Confidence]] = []
        executable = app.metadata.get("executable") or command_executable(app.exec_line)
        if executable:
            path = Path(os.path.expandvars(os.path.expanduser(executable)))
            if path.is_absolute() and is_within(path, self.home):
                reason = "AppImage-Datei" if app.source == SourceKind.APPIMAGE else "Programmstarter"
                result.append((path, reason, Confidence.CERTAIN))
        prefix = app.metadata.get("wine_prefix", "")
        if prefix:
            path = Path(os.path.expandvars(os.path.expanduser(prefix))).absolute()
            # A literal Lutris path is useful evidence of sharing, but alone
            # must not turn an arbitrary folder into a new deletion target.
            prefix_confirmed = app.source != SourceKind.LUTRIS or (
                (path / "drive_c").is_dir() and (path / "system.reg").is_file()
            )
            if prefix_confirmed and path != self.home / ".wine" and is_within(path, self.home):
                result.append((path, "Eigenes Wine-Präfix mit allen Windows-Daten", Confidence.CERTAIN))
        return result

    def _known_data_targets(self, app: AppRecord, aliases: set[str]) -> list[tuple[Path, str, Confidence]]:
        roots = (
            (self.home / ".config", "Einstellungen"),
            (self.home / ".cache", "Zwischenspeicher"),
            (self.home / ".local/share", "Anwendungsdaten"),
            (self.home / ".local/state", "Status- und Protokolldaten"),
            (self.home / ".local/bin", "Programmstarter"),
            (self.home / ".var/app", "Sandbox-Daten"),
            (self.home / "snap", "Snap-Benutzerdaten"),
            (self.home / "Applications", "Manuelle Installation"),
            (self.home / "Games", "Spielinstallation"),
            (self.home / "Downloads", "Heruntergeladener Installer"),
            (self.home / "Desktop", "Desktop-Datei"),
            (self.home / "Schreibtisch", "Desktop-Datei"),
        )
        result: list[tuple[Path, str, Confidence]] = []
        for root, reason in roots:
            if not root.is_dir():
                continue
            try:
                for path in root.iterdir():
                    confidence = self._match_confidence(path.name, aliases)
                    if confidence:
                        result.append((path, reason, confidence))
            except OSError:
                continue

        # A number of applications store profiles below a vendor directory,
        # for example ~/.config/BraveSoftware/Brave-Browser.  Only the matching
        # second-level entry is proposed; the shared vendor directory is kept.
        for root, reason in roots[:4]:
            if not root.is_dir():
                continue
            try:
                for vendor in root.iterdir():
                    if not vendor.is_dir() or vendor.is_symlink():
                        continue
                    for path in vendor.iterdir():
                        confidence = self._match_confidence(path.name, aliases)
                        if confidence:
                            result.append((path, reason, confidence))
            except OSError:
                continue

        app_id = app.package_id
        explicit = (
            self.home / ".var/app" / app_id,
            self.home / ".config" / app_id,
            self.home / ".cache" / app_id,
            self.home / ".local/share" / app_id,
            self.home / ".local/state" / app_id,
            self.home / "snap" / app_id,
        )
        for path in explicit:
            if path.exists() or path.is_symlink():
                result.append((path, "Paketkennung stimmt exakt überein", Confidence.CERTAIN))

        nested_roots = (
            self.home / ".local/share/applications",
            self.home / ".local/share/icons",
            self.home / ".local/share/pixmaps",
        )
        for root in nested_roots:
            if not root.is_dir():
                continue
            try:
                for current, directories, files in os.walk(root):
                    depth = len(Path(current).relative_to(root).parts)
                    if depth >= 4:
                        directories.clear()
                    for filename in files:
                        confidence = self._match_confidence(filename, aliases)
                        if confidence:
                            result.append((Path(current) / filename, "Menüeintrag oder Symbol", confidence))
            except OSError:
                continue
        return result

    def _launcher_references(self, app: AppRecord, aliases: set[str]) -> list[tuple[Path, str, Confidence]]:
        executable = app.metadata.get("executable") or command_executable(app.exec_line)
        if not executable:
            return []
        launcher = Path(os.path.expandvars(os.path.expanduser(executable)))
        if not launcher.is_file() or not is_within(launcher, self.home):
            return []
        try:
            if launcher.stat().st_size > 512 * 1024:
                return []
            text = launcher.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []
        result: list[tuple[Path, str, Confidence]] = []
        for referenced in extract_home_paths(text, self.home):
            candidate = referenced
            if not (candidate.exists() or candidate.is_symlink()):
                continue
            confidence = self._match_confidence(candidate.name, aliases)
            if confidence:
                result.append((candidate, "Vom Programmstarter referenzierter Installationspfad", confidence))
        return result

    def _default_wine_targets(self, app: AppRecord, aliases: set[str]) -> list[tuple[Path, str, Confidence]]:
        if app.source != SourceKind.WINE:
            return []
        result: list[tuple[Path, str, Confidence]] = []
        for program_root in (
            self.home / ".wine/drive_c/Program Files",
            self.home / ".wine/drive_c/Program Files (x86)",
        ):
            if not program_root.is_dir():
                continue
            try:
                for path in program_root.iterdir():
                    confidence = self._match_confidence(path.name, aliases)
                    if confidence:
                        result.append((path, "Programmdateien im gemeinsamen Wine-Präfix", confidence))
            except OSError:
                continue
        return result

    def _safe_targets(
        self,
        candidates: list[tuple[Path, str, Confidence]],
        trusted_roots: tuple[Path, ...] = (),
    ) -> list[RemovalTarget]:
        best: dict[str, tuple[Path, str, Confidence]] = {}
        rank = {Confidence.POSSIBLE: 1, Confidence.HIGH: 2, Confidence.CERTAIN: 3}
        for path, reason, confidence in candidates:
            if not (path.exists() or path.is_symlink()):
                continue
            try:
                self.guard.validate(path, trusted_roots)
            except UnsafeTargetError:
                continue
            key = str(path.absolute())
            previous = best.get(key)
            if previous is None or rank[confidence] > rank[previous[2]]:
                best[key] = (path.absolute(), reason, confidence)

        ordered = sorted(best.values(), key=lambda item: len(item[0].parts))
        collapsed: list[tuple[Path, str, Confidence]] = []
        for item in ordered:
            path = item[0]
            if any(parent.is_dir() and is_within(path, parent) for parent, _, _ in collapsed):
                continue
            collapsed.append(item)
        return [
            RemovalTarget(
                path=path,
                reason=reason,
                size=path_size(path),
                confidence=confidence,
                selected=confidence != Confidence.POSSIBLE,
            )
            for path, reason, confidence in collapsed
        ]
