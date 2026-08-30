from __future__ import annotations

import configparser
import locale
import os
import re
import shlex
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(slots=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class DesktopEntry:
    path: Path
    name: str
    generic_name: str
    comment: str
    exec_line: str
    icon: str
    app_id: str
    hidden: bool
    no_display: bool


def run_command(command: Sequence[str], timeout: float = 12.0) -> CommandResult:
    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
            env={**os.environ, "LC_ALL": "C.UTF-8"},
        )
        return CommandResult(tuple(command), completed.returncode, completed.stdout, completed.stderr)
    except (OSError, subprocess.TimeoutExpired) as error:
        return CommandResult(tuple(command), 127, "", str(error))


def normalize_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    return "".join(character for character in value if character.isalnum())


def format_size(size: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(max(size, 0))
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{size} B"


def path_size(path: Path) -> int:
    try:
        if path.is_symlink():
            return path.lstat().st_size
        if path.is_file():
            return path.stat().st_size
        if not path.is_dir():
            return 0
    except OSError:
        return 0

    total = 0
    try:
        for root, directories, files in os.walk(path, followlinks=False):
            root_path = Path(root)
            for name in files:
                try:
                    total += (root_path / name).lstat().st_size
                except OSError:
                    continue
            for name in list(directories):
                candidate = root_path / name
                if candidate.is_symlink():
                    try:
                        total += candidate.lstat().st_size
                    except OSError:
                        pass
                    directories.remove(name)
    except OSError:
        return total
    return total


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.absolute().relative_to(parent.absolute())
        return True
    except ValueError:
        return False


def _locale_candidates() -> list[str]:
    language = locale.getlocale()[0] or os.environ.get("LANG", "").split(".", 1)[0]
    candidates: list[str] = []
    if language:
        candidates.append(language)
        if "_" in language:
            candidates.append(language.split("_", 1)[0])
    return candidates


def parse_desktop_file(path: Path) -> DesktopEntry | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read(path, encoding="utf-8")
        section = parser["Desktop Entry"]
    except (OSError, UnicodeError, KeyError, configparser.Error):
        return None
    if section.get("Type", "Application") != "Application":
        return None

    name = section.get("Name", path.stem)
    comment = section.get("Comment", "")
    generic_name = section.get("GenericName", "")
    for language in _locale_candidates():
        name = section.get(f"Name[{language}]", name)
        comment = section.get(f"Comment[{language}]", comment)
        generic_name = section.get(f"GenericName[{language}]", generic_name)

    return DesktopEntry(
        path=path,
        name=name.strip() or path.stem,
        generic_name=generic_name.strip(),
        comment=comment.strip(),
        exec_line=section.get("Exec", "").strip(),
        icon=section.get("Icon", "application-x-executable").strip(),
        app_id=path.stem,
        hidden=section.getboolean("Hidden", fallback=False),
        no_display=section.getboolean("NoDisplay", fallback=False),
    )


def command_executable(exec_line: str) -> str:
    if not exec_line:
        return ""
    cleaned = re.sub(r"\s%[fFuUdDnNickvm]", "", exec_line)
    try:
        parts = shlex.split(cleaned)
    except ValueError:
        return ""
    if not parts:
        return ""
    index = 0
    if Path(parts[0]).name == "env":
        index = 1
        while index < len(parts) and "=" in parts[index] and not parts[index].startswith("/"):
            index += 1
    while index < len(parts) and Path(parts[index]).name in {"sh", "bash", "python", "python3", "wine", "wine64"}:
        if Path(parts[index]).name in {"sh", "bash", "python", "python3"} and index + 1 < len(parts):
            index += 1
            break
        index += 1
    return parts[index] if index < len(parts) else parts[0]


def extract_home_paths(text: str, home: Path) -> set[Path]:
    escaped_home = re.escape(str(home))
    expression = re.compile(rf"(?P<quote>['\"]?)({escaped_home}/[^\n\r'\"]+)(?P=quote)")
    paths: set[Path] = set()
    for match in expression.finditer(text):
        raw = match.group(2).rstrip(" ,;:)")
        if raw:
            paths.add(Path(raw))
    return paths


def unique_existing_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path.absolute())
        if key in seen:
            continue
        seen.add(key)
        if path.exists() or path.is_symlink():
            result.append(path)
    return result

