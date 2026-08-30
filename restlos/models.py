from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SourceKind(str, Enum):
    APT = "APT/DEB"
    FLATPAK = "Flatpak"
    SNAP = "Snap"
    APPIMAGE = "AppImage"
    WINE = "Wine"
    MANUAL = "Manuell"
    LUTRIS = "Lutris-Spiel"
    STEAM = "Steam-Spiel"
    HEROIC = "Heroic-Spiel"
    BOTTLES = "Bottles-Umgebung"
    PLAYONLINUX = "PlayOnLinux"
    PORTABLE = "Ordner/Portable"


class Confidence(str, Enum):
    CERTAIN = "sicher"
    HIGH = "hoch"
    POSSIBLE = "prüfen"


@dataclass(slots=True)
class AppRecord:
    key: str
    name: str
    source: SourceKind
    package_id: str
    description: str = ""
    icon: str = "application-x-executable"
    exec_line: str = ""
    desktop_files: tuple[str, ...] = ()
    scope: str = "Benutzer"
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source"] = self.source.value
        return data


@dataclass(slots=True)
class RemovalTarget:
    path: Path
    reason: str
    size: int
    confidence: Confidence
    selected: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "reason": self.reason,
            "size": self.size,
            "confidence": self.confidence.value,
            "selected": self.selected,
        }


@dataclass(slots=True)
class RemovalAction:
    label: str
    command: tuple[str, ...] = ()
    privileged: bool = False
    required: bool = True
    internal_kind: str = ""
    parameters: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "command": list(self.command),
            "privileged": self.privileged,
            "required": self.required,
            "internal_kind": self.internal_kind,
            "parameters": dict(self.parameters),
        }


@dataclass(slots=True)
class RemovalPlan:
    app: AppRecord
    targets: list[RemovalTarget] = field(default_factory=list)
    actions: list[RemovalAction] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def selected_targets(self) -> list[RemovalTarget]:
        return [target for target in self.targets if target.selected]

    @property
    def total_size(self) -> int:
        return sum(target.size for target in self.selected_targets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "app": self.app.to_dict(),
            "targets": [target.to_dict() for target in self.targets],
            "actions": [action.to_dict() for action in self.actions],
            "warnings": list(self.warnings),
            "total_size": self.total_size,
        }


@dataclass(slots=True)
class RemovalResult:
    success: bool
    removed_paths: list[str] = field(default_factory=list)
    action_output: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    receipt_path: str = ""
