from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .safety import PlanSnapshot


class SourceKind(str, Enum):
    APT = "APT/DEB"
    DNF = "DNF/RPM"
    PACMAN = "pacman"
    ZYPPER = "Zypper/RPM"
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
class SharedUse:
    app_key: str
    app_name: str
    source: str
    reference_path: str
    evidence: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class RemovalTarget:
    path: Path
    reason: str
    size: int
    confidence: Confidence
    selected: bool = True
    shared_with: list[SharedUse] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "reason": self.reason,
            "size": self.size,
            "confidence": self.confidence.value,
            "selected": self.selected,
            "shared_with": [use.to_dict() for use in self.shared_with],
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
    safety_error: str = ""
    package_preview: tuple[str, ...] = ()
    snapshot: PlanSnapshot | None = field(default=None, repr=False)

    @property
    def selected_targets(self) -> list[RemovalTarget]:
        return [target for target in self.targets if target.selected and not target.shared_with]

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
            "safety_error": self.safety_error,
            "review_checked": self.snapshot is not None and not self.safety_error,
            "package_preview": list(self.package_preview),
        }


@dataclass(slots=True)
class RecoveryItem:
    original_path: str
    trash_uri: str
    size: int = 0
    restored_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BackupItem:
    original_path: str
    archive_member: str
    size: int = 0
    restored_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RemovalResult:
    success: bool
    removed_paths: list[str] = field(default_factory=list)
    action_output: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    recovery_items: list[RecoveryItem] = field(default_factory=list)
    backup_items: list[BackupItem] = field(default_factory=list)
    backup_path: str = ""
    residual_paths: list[str] = field(default_factory=list)
    kept_paths: list[str] = field(default_factory=list)
    verification_error: str = ""
    recovery_id: str = ""
    receipt_path: str = ""
    review_required: bool = False


@dataclass(slots=True)
class RecoveryRecord:
    recovery_id: str
    receipt_path: str
    timestamp: str
    app_name: str
    package_id: str
    source: str
    success: bool
    items: list[RecoveryItem] = field(default_factory=list)
    backup_items: list[BackupItem] = field(default_factory=list)
    backup_path: str = ""
    actions: list[str] = field(default_factory=list)
    residual_paths: list[str] = field(default_factory=list)

    @property
    def available_trash_items(self) -> list[RecoveryItem]:
        return [item for item in self.items if item.trash_uri and not item.restored_at]

    @property
    def available_backup_items(self) -> list[BackupItem]:
        return [item for item in self.backup_items if item.archive_member and not item.restored_at]

    @property
    def available_items(self) -> list[RecoveryItem | BackupItem]:
        return [*self.available_trash_items, *self.available_backup_items]

    @property
    def available_size(self) -> int:
        return sum(item.size for item in self.available_items)


@dataclass(slots=True)
class RestoreResult:
    success: bool
    recovery_id: str
    restored_paths: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
