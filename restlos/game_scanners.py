from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .models import AppRecord, SourceKind
from .utils import extract_home_paths, normalize_key


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _existing_owned(entries: Iterable[tuple[Path, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for path, reason in entries:
        absolute = path.absolute()
        key = str(absolute)
        if key in seen or not (absolute.exists() or absolute.is_symlink()):
            continue
        seen.add(key)
        result.append({"path": key, "reason": reason})
    return result


def _metadata(manager: str, owned: list[dict[str, str]], **values: str) -> dict[str, str]:
    result = {
        "manager": manager,
        "owned_paths": _json_text(owned),
        "trusted_paths": _json_text([item["path"] for item in owned]),
    }
    result.update({key: str(value) for key, value in values.items() if value is not None})
    return result


def _first_image(paths: Iterable[Path], fallback: str) -> str:
    for path in paths:
        if path.is_file():
            return str(path)
    return fallback


def _literal_yaml_path(text: str, key: str) -> str:
    """Read only simple path scalars; never evaluate YAML tags or shell text."""
    match = re.search(r"^\s*" + re.escape(key) + r":\s*(.+)$", text, re.MULTILINE)
    if match is None:
        return ""
    value = match[1].strip()
    if value.startswith("'") and value.endswith("'"):
        value = value[1:-1].replace("''", "'")
    elif value.startswith('"'):
        try:
            value = json.loads(value)
        except ValueError:
            return ""
    else:
        value = value.split(" #", 1)[0].strip()
    if not isinstance(value, str) or "\0" in value:
        return ""
    value = os.path.expanduser(os.path.expandvars(value))
    path = Path(value)
    return str(path) if path.is_absolute() and ".." not in path.parts else ""


class GamePlatformScanner:
    """Read launcher libraries directly, without starting any launcher."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = (home or Path.home()).absolute()

    def scan(self) -> list[AppRecord]:
        records: list[AppRecord] = []
        records.extend(self._scan_lutris())
        records.extend(self._scan_steam())
        records.extend(self._scan_heroic())
        records.extend(self._scan_bottles())
        records.extend(self._scan_playonlinux())
        return records

    def scan_unmanaged_game_folders(self, known: Iterable[AppRecord]) -> list[AppRecord]:
        referenced: set[str] = set()
        for app in known:
            try:
                owned = json.loads(app.metadata.get("owned_paths", "[]"))
            except (TypeError, json.JSONDecodeError):
                continue
            for item in owned:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    continue
                path = Path(item["path"])
                if path.is_dir():
                    try:
                        referenced.add(str(path.resolve()))
                    except OSError:
                        referenced.add(str(path.absolute()))

        records: list[AppRecord] = []
        for parent in (self.home / "Games", self.home / "Applications"):
            if not parent.is_dir():
                continue
            try:
                children = list(parent.iterdir())
            except OSError:
                continue
            for path in children:
                if not path.is_dir() or path.is_symlink():
                    continue
                try:
                    resolved = str(path.resolve())
                except OSError:
                    resolved = str(path.absolute())
                if resolved in referenced:
                    continue
                if (path / "steamapps").is_dir() or path.name.casefold() in {"prefixes", "steamlibrary"}:
                    continue
                is_prefix = (path / "drive_c").is_dir() and (
                    (path / "dosdevices").exists() or (path / "system.reg").exists()
                )
                owned = _existing_owned(((path, "Nicht zugeordneter Wine-Präfix" if is_prefix else "Portabler Programmordner"),))
                records.append(
                    AppRecord(
                        key=f"portable:{path}",
                        name=(f"Wine-Präfix: {path.name}" if is_prefix else path.name),
                        source=SourceKind.PORTABLE,
                        package_id=path.name,
                        description=(
                            "Nicht von einer Spielebibliothek zugeordneter Wine-Präfix"
                            if is_prefix
                            else "Nicht von einem Paketmanager verwalteter Ordner"
                        ),
                        icon="folder-games-symbolic" if is_prefix else "folder-symbolic",
                        scope="Benutzer",
                        metadata=_metadata("portable", owned, install_root=str(path)),
                    )
                )
        return records

    def _scan_lutris(self) -> list[AppRecord]:
        data_roots = (
            self.home / ".local/share/lutris",
            self.home / ".var/app/net.lutris.Lutris/data/lutris",
        )
        records: list[AppRecord] = []
        seen_databases: set[str] = set()
        for data_root in data_roots:
            database = data_root / "pga.db"
            if not database.is_file():
                continue
            try:
                database_key = str(database.resolve())
            except OSError:
                database_key = str(database.absolute())
            if database_key in seen_databases:
                continue
            seen_databases.add(database_key)
            try:
                connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=2)
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    "SELECT id, name, slug, platform, runner, directory, configpath, service, service_id "
                    "FROM games WHERE installed=1 ORDER BY name"
                ).fetchall()
                connection.close()
            except sqlite3.Error:
                continue

            flatpak = "/.var/app/net.lutris.Lutris/" in str(data_root)
            cache_root = (
                self.home / ".var/app/net.lutris.Lutris/cache/lutris"
                if flatpak
                else self.home / ".cache/lutris"
            )
            icon_roots = (
                self.home / ".local/share/icons/hicolor",
                self.home / ".var/app/net.lutris.Lutris/data/icons/hicolor",
            )
            for row in rows:
                game_id = str(row["id"])
                name = str(row["name"] or row["slug"] or f"Lutris-Spiel {game_id}")
                slug = str(row["slug"] or normalize_key(name))
                directory = Path(os.path.expanduser(str(row["directory"] or "")))
                config_id = str(row["configpath"] or "")
                owned_entries: list[tuple[Path, str]] = []
                if directory.is_absolute():
                    owned_entries.append((directory, "Lutris-Spielordner und eigener Präfix"))
                config_file = data_root / "games" / f"{config_id}.yml" if config_id else Path()
                if config_id:
                    owned_entries.append((config_file, "Lutris-Spielkonfiguration"))
                for media_root, reason in (
                    (data_root / "banners", "Lutris-Banner"),
                    (data_root / "coverart", "Lutris-Cover"),
                ):
                    for extension in ("png", "jpg", "jpeg", "webp"):
                        owned_entries.append((media_root / f"{slug}.{extension}", reason))
                for icon_root in icon_roots:
                    if not icon_root.is_dir():
                        continue
                    for icon in icon_root.glob(f"*/apps/lutris_{slug}.*"):
                        owned_entries.append((icon, "Lutris-Spielsymbol"))
                for desktop_root in (
                    self.home / "Desktop",
                    self.home / "Schreibtisch",
                    self.home / ".local/share/applications",
                ):
                    for filename in (
                        f"net.lutris.{slug}-{game_id}.desktop",
                        f"{slug}-{game_id}.desktop",
                        f"{slug}.desktop",
                    ):
                        owned_entries.append((desktop_root / filename, "Lutris-Starter"))

                prefix = ""
                executable = ""
                if config_file.is_file():
                    try:
                        config_text = config_file.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        config_text = ""
                    prefix = _literal_yaml_path(config_text, "prefix")
                    executable = _literal_yaml_path(config_text, "exe")
                    if prefix and (Path(prefix) / "drive_c").is_dir() and (Path(prefix) / "system.reg").is_file():
                        owned_entries.append((Path(prefix), "Lutris-Wine-Präfix laut Spielkonfiguration"))
                    game_aliases = {normalize_key(name), normalize_key(slug)}
                    for referenced in extract_home_paths(config_text, self.home):
                        if referenced.is_file() and referenced.parent == self.home / "Downloads":
                            normalized = normalize_key(referenced.name)
                            if any(alias and alias in normalized for alias in game_aliases):
                                owned_entries.append((referenced, "Von Lutris verwendeter Installer"))

                owned = _existing_owned(owned_entries)
                image_candidates = [Path(item["path"]) for item in owned if "Cover" in item["reason"]]
                image_candidates += [Path(item["path"]) for item in owned if "Symbol" in item["reason"]]
                actions = [
                    {
                        "kind": "lutris-database",
                        "label": "Spiel aus der Lutris-Bibliothek entfernen",
                        "parameters": {
                            "database": str(database),
                            "game_id": game_id,
                            "cache": str(cache_root / "game-paths.json"),
                        },
                    }
                ]
                records.append(
                    AppRecord(
                        key=f"lutris:{database_key}:{game_id}",
                        name=name,
                        source=SourceKind.LUTRIS,
                        package_id=f"lutris-{game_id}-{slug}",
                        description=f"Lutris-Spiel · {row['platform'] or 'unbekannte Plattform'} · {row['runner'] or 'unbekannter Runner'}",
                        icon=_first_image(image_candidates, "lutris"),
                        exec_line=f"lutris lutris:rungameid/{game_id}",
                        scope="Lutris Flatpak" if flatpak else "Lutris",
                        metadata={
                            **_metadata(
                                "lutris",
                                owned,
                                manager_actions=_json_text(actions),
                                install_root=str(directory) if directory.is_absolute() else "",
                                manager_id=game_id,
                                slug=slug,
                                wine_prefix=prefix,
                                executable=executable,
                            ),
                        },
                    )
                )
        return records

    def _steam_roots(self) -> list[Path]:
        candidates = [
            self.home / ".steam/debian-installation",
            self.home / ".steam/steam",
            self.home / ".steam/root",
            self.home / ".local/share/Steam",
            self.home / ".var/app/com.valvesoftware.Steam/.steam/steam",
            self.home / ".var/app/com.valvesoftware.Steam/data/Steam",
        ]
        roots: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not (candidate / "steamapps").is_dir():
                continue
            try:
                key = str(candidate.resolve())
            except OSError:
                key = str(candidate.absolute())
            if key not in seen:
                seen.add(key)
                roots.append(candidate)
        return roots

    def _steam_libraries(self, steam_root: Path) -> list[Path]:
        libraries = [steam_root]
        for config in (
            steam_root / "steamapps/libraryfolders.vdf",
            steam_root / "config/libraryfolders.vdf",
        ):
            if not config.is_file():
                continue
            try:
                text = config.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in re.finditer(r'"path"\s+"([^"]+)"', text):
                raw = match.group(1).replace("\\\\", "\\")
                path = Path(raw)
                if (path / "steamapps").is_dir():
                    libraries.append(path)
        result: list[Path] = []
        seen: set[str] = set()
        for library in libraries:
            try:
                key = str(library.resolve())
            except OSError:
                key = str(library.absolute())
            if key not in seen:
                seen.add(key)
                result.append(library)
        return result

    def _scan_steam(self) -> list[AppRecord]:
        records: list[AppRecord] = []
        seen_manifests: set[str] = set()
        for steam_root in self._steam_roots():
            flatpak = "/.var/app/com.valvesoftware.Steam/" in str(steam_root)
            for library in self._steam_libraries(steam_root):
                steamapps = library / "steamapps"
                for manifest in sorted(steamapps.glob("appmanifest_*.acf")):
                    try:
                        manifest_key = str(manifest.resolve())
                        text = manifest.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    if manifest_key in seen_manifests:
                        continue
                    seen_manifests.add(manifest_key)
                    values = {
                        key: (match.group(1) if (match := re.search(rf'"{key}"\s+"([^"]*)"', text, re.I)) else "")
                        for key in ("appid", "name", "installdir", "SizeOnDisk")
                    }
                    app_id = values["appid"]
                    name = values["name"] or f"Steam-App {app_id}"
                    install_dir = values["installdir"]
                    if not app_id.isdigit() or not install_dir:
                        continue
                    lowered = name.casefold()
                    if any(token in lowered for token in ("steam linux runtime", "proton", "redistributables")):
                        continue
                    owned_entries: list[tuple[Path, str]] = [
                        (manifest, "Steam-App-Manifest"),
                        (steamapps / "common" / install_dir, "Steam-Spielordner"),
                        (steamapps / "compatdata" / app_id, "Proton-Präfix und Windows-Benutzerdaten"),
                        (steamapps / "shadercache" / app_id, "Steam-Shadercache"),
                        (steamapps / "workshop/content" / app_id, "Steam-Workshop-Inhalte"),
                        (steamapps / "downloading" / app_id, "Unvollständige Steam-Downloads"),
                        (steamapps / "temp" / app_id, "Temporäre Steam-Daten"),
                        (steam_root / "appcache/librarycache" / app_id, "Steam-Bibliotheksbilder und Cache"),
                    ]
                    userdata = steam_root / "userdata"
                    if userdata.is_dir():
                        for user in userdata.iterdir():
                            if not user.is_dir() or not user.name.isdigit():
                                continue
                            owned_entries.extend(
                                (
                                    (user / app_id, "Lokale Steam-Benutzerdaten und Spielstände"),
                                    (user / "760/remote" / app_id, "Lokale Steam-Screenshots"),
                                    (user / "config/librarycache" / f"{app_id}.json", "Steam-Spielmetadaten"),
                                )
                            )
                            shader_hit_root = user / "config/shaderhitcache"
                            if shader_hit_root.is_dir():
                                for cache_file in shader_hit_root.rglob(f"{app_id}_pbuf"):
                                    owned_entries.append((cache_file, "Steam-Pipelinecache"))
                    for desktop_root in (
                        self.home / "Desktop",
                        self.home / "Schreibtisch",
                        self.home / ".local/share/applications",
                    ):
                        owned_entries.append((desktop_root / f"steam_app_{app_id}.desktop", "Steam-Starter"))
                    owned = _existing_owned(owned_entries)
                    artwork = steam_root / "appcache/librarycache" / app_id / "library_capsule.jpg"
                    if not artwork.is_file():
                        artwork = steam_root / "appcache/librarycache" / app_id / "library_header.jpg"
                    records.append(
                        AppRecord(
                            key=f"steam:{manifest_key}",
                            name=name,
                            source=SourceKind.STEAM,
                            package_id=f"steam-{app_id}",
                            description=f"Steam-Spiel · App-ID {app_id}",
                            icon=str(artwork) if artwork.is_file() else "steam",
                            exec_line=f"steam steam://rungameid/{app_id}",
                            scope="Steam Flatpak" if flatpak else "Steam",
                            metadata=_metadata(
                                "steam",
                                owned,
                                install_root=str(steamapps / "common" / install_dir),
                                manager_id=app_id,
                                steam_root=str(steam_root),
                            ),
                        )
                    )
        return records

    def _heroic_bases(self) -> list[Path]:
        candidates = [
            self.home / ".config/heroic",
            self.home / ".var/app/com.heroicgameslauncher.hgl/config/heroic",
        ]
        return [path for path in candidates if path.is_dir()]

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _install_path(data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        for key in ("install_path", "installPath", "path"):
            value = data.get(key)
            if isinstance(value, str) and Path(os.path.expanduser(value)).is_absolute():
                return value
        install = data.get("install")
        if isinstance(install, dict):
            return GamePlatformScanner._install_path(install)
        return ""

    def _scan_heroic(self) -> list[AppRecord]:
        records: list[AppRecord] = []
        seen: set[tuple[str, str]] = set()
        for base in self._heroic_bases():
            flatpak = "/.var/app/com.heroicgameslauncher.hgl/" in str(base)
            installed_files = [
                base / "legendaryConfig/legendary/installed.json",
                base / "legendary/installed.json",
                base.parent / "legendary/installed.json",
                base / "gogdlConfig/heroic_gogdl/installed.json",
                base / "nile_config/nile/installed.json",
            ]
            if not flatpak:
                installed_files.append(self.home / ".config/legendary/installed.json")
            for installed_file in installed_files:
                payload = self._read_json(installed_file)
                if not isinstance(payload, dict):
                    continue
                for app_id, data in payload.items():
                    if not isinstance(data, dict):
                        continue
                    raw_install = self._install_path(data)
                    if not raw_install:
                        continue
                    install_path = Path(os.path.expanduser(raw_install))
                    identity = (str(installed_file), str(app_id))
                    if identity in seen:
                        continue
                    seen.add(identity)
                    name = str(data.get("title") or data.get("app_title") or data.get("name") or app_id)
                    settings_candidates = [
                        base / "GamesConfig" / f"{app_id}.json",
                        base / "GameConfig" / f"{app_id}.json",
                    ]
                    prefix: Path | None = None
                    settings_file: Path | None = None
                    for candidate in settings_candidates:
                        settings = self._read_json(candidate)
                        if not isinstance(settings, dict):
                            continue
                        raw_prefix = settings.get("winePrefix") or settings.get("wine_prefix") or settings.get("WINEPREFIX")
                        if isinstance(raw_prefix, str) and Path(os.path.expanduser(raw_prefix)).is_absolute():
                            prefix = Path(os.path.expanduser(raw_prefix))
                        settings_file = candidate
                        break
                    owned_entries: list[tuple[Path, str]] = [
                        (install_path, "Heroic-Spielordner"),
                    ]
                    if prefix is not None and prefix.is_absolute() and prefix != install_path:
                        owned_entries.append((prefix, "Eigener Heroic-Wine-/Proton-Präfix"))
                    if settings_file is not None:
                        owned_entries.append((settings_file, "Heroic-Spieleinstellungen"))
                    for desktop_root in (
                        self.home / "Desktop",
                        self.home / "Schreibtisch",
                        self.home / ".local/share/applications",
                    ):
                        for stem in (f"heroic-{app_id}", f"heroic_{app_id}", str(app_id)):
                            owned_entries.append((desktop_root / f"{stem}.desktop", "Heroic-Starter"))
                    owned = _existing_owned(owned_entries)
                    actions = [
                        {
                            "kind": "json-remove-key",
                            "label": "Installationsstatus aus Heroic entfernen",
                            "parameters": {"path": str(installed_file), "key": str(app_id)},
                        }
                    ]
                    records.append(
                        AppRecord(
                            key=f"heroic:{installed_file}:{app_id}",
                            name=name,
                            source=SourceKind.HEROIC,
                            package_id=f"heroic-{app_id}",
                            description=f"Heroic-Spiel · {data.get('platform') or 'Epic/GOG/Amazon'}",
                            icon="com.heroicgameslauncher.hgl",
                            exec_line=f"heroic launch {app_id}",
                            scope="Heroic Flatpak" if flatpak else "Heroic",
                            metadata=_metadata(
                                "heroic",
                                owned,
                                manager_actions=_json_text(actions),
                                install_root=str(install_path),
                                manager_id=str(app_id),
                            ),
                        )
                    )
        return records

    def _scan_bottles(self) -> list[AppRecord]:
        roots = (
            self.home / ".local/share/bottles/bottles",
            self.home / ".var/app/com.usebottles.bottles/data/bottles/bottles",
        )
        records: list[AppRecord] = []
        for root in roots:
            if not root.is_dir():
                continue
            for bottle in sorted(root.iterdir()):
                config = bottle / "bottle.yml"
                if not bottle.is_dir() or not config.is_file():
                    continue
                try:
                    text = config.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    text = ""
                match = re.search(r"^(?:Name|name):\s*['\"]?([^'\"\n]+)", text, re.MULTILINE)
                name = match.group(1).strip() if match else bottle.name
                owned = _existing_owned(((bottle, "Gesamte Bottles-Umgebung mit Präfix und Programmen"),))
                records.append(
                    AppRecord(
                        key=f"bottles:{bottle}",
                        name=f"Bottle: {name}",
                        source=SourceKind.BOTTLES,
                        package_id=f"bottle-{bottle.name}",
                        description="Vollständige Bottles-Umgebung; alle darin enthaltenen Windows-Programme werden entfernt",
                        icon="com.usebottles.bottles",
                        scope="Bottles",
                        metadata=_metadata("bottles", owned, install_root=str(bottle)),
                    )
                )
        return records

    def _scan_playonlinux(self) -> list[AppRecord]:
        root = self.home / ".PlayOnLinux"
        prefix_root = root / "wineprefix"
        if not prefix_root.is_dir():
            return []
        records: list[AppRecord] = []
        for prefix in sorted(prefix_root.iterdir()):
            if not prefix.is_dir() or prefix.is_symlink():
                continue
            name = prefix.name
            owned_entries: list[tuple[Path, str]] = [
                (prefix, "PlayOnLinux-Präfix und Programmdateien"),
                (root / "shortcuts" / name, "PlayOnLinux-Starter"),
                (root / "configurations/installed" / name, "PlayOnLinux-Konfiguration"),
                (root / "icons/full_size" / f"{name}.png", "PlayOnLinux-Symbol"),
                (root / "icons/32" / f"{name}.png", "PlayOnLinux-Symbol"),
            ]
            for desktop in (self.home / ".local/share/applications").glob(f"*{name}*.desktop"):
                owned_entries.append((desktop, "PlayOnLinux-Menüeintrag"))
            owned = _existing_owned(owned_entries)
            records.append(
                AppRecord(
                    key=f"playonlinux:{prefix}",
                    name=name,
                    source=SourceKind.PLAYONLINUX,
                    package_id=f"playonlinux-{name}",
                    description="PlayOnLinux-Programm mit eigenem Wine-Präfix",
                    icon="playonlinux",
                    scope="PlayOnLinux",
                    metadata=_metadata("playonlinux", owned, install_root=str(prefix)),
                )
            )
        return records
