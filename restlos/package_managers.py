from __future__ import annotations

import re
import shutil
from abc import ABC, abstractmethod
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .models import AppRecord, SourceKind
from .utils import DesktopEntry, run_command


PACKAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@+._:-]*$")
_ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
_TRUSTED_BINARY_DIRECTORIES = (Path("/usr/bin"), Path("/bin"), Path("/usr/sbin"), Path("/sbin"))


@dataclass(frozen=True, slots=True)
class RemovalPreview:
    removed_packages: tuple[str, ...] = ()
    error: str = ""


class PackageManagerAdapter(ABC):
    source: SourceKind
    key_prefix: str
    description: str
    manager_names: tuple[str, ...]
    protected_packages: tuple[str, ...]

    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def scan(self, entries: Sequence[DesktopEntry]) -> list[AppRecord]:
        raise NotImplementedError

    @abstractmethod
    def preview_removal(self, package: str, manager_name: str = "") -> RemovalPreview:
        raise NotImplementedError

    @abstractmethod
    def removal_command(self, package: str, manager_name: str = "") -> tuple[str, ...]:
        raise NotImplementedError

    @abstractmethod
    def removal_label(self, package: str) -> str:
        raise NotImplementedError

    def manager_name(self, requested: str = "") -> str:
        if requested in self.manager_names:
            return requested
        for name in self.manager_names:
            if shutil.which(name):
                return name
        return self.manager_names[0]

    def manager_path(self, requested: str = "") -> str:
        return _trusted_binary(self.manager_name(requested))

    def is_protected(self, package: str) -> bool:
        normalized = _canonical_package_name(package).casefold()
        return any(
            normalized == protected.casefold()
            or normalized.startswith(f"{protected.casefold()}-")
            for protected in self.protected_packages
        )

    def _records(
        self,
        entries: Sequence[DesktopEntry],
        owners: dict[str, str],
        manager_name: str,
    ) -> list[AppRecord]:
        by_package: dict[str, list[DesktopEntry]] = defaultdict(list)
        for entry in entries:
            package = owners.get(str(entry.path))
            if package and PACKAGE_ID_PATTERN.fullmatch(package):
                by_package[package].append(entry)

        records: list[AppRecord] = []
        for package, package_entries in by_package.items():
            visible = sorted(
                package_entries,
                key=lambda item: ("settings" in item.app_id.casefold(), len(item.name)),
            )
            entry = visible[0]
            records.append(
                AppRecord(
                    key=f"{self.key_prefix}:{package}",
                    name=entry.name,
                    source=self.source,
                    package_id=package,
                    description=entry.comment or entry.generic_name or self.description,
                    icon=entry.icon,
                    exec_line=entry.exec_line,
                    desktop_files=tuple(str(item.path) for item in package_entries),
                    scope="System",
                    metadata={"package_manager": manager_name},
                )
            )
        return records


class AptAdapter(PackageManagerAdapter):
    source = SourceKind.APT
    key_prefix = "apt"
    description = "APT/DEB-Anwendung"
    manager_names = ("apt-get",)
    protected_packages = (
        "zorin-os",
        "ubuntu-desktop",
        "ubuntu-minimal",
        "gnome-shell",
        "systemd",
        "libc6",
        "linux-image",
        "linux-generic",
        "grub",
        "initramfs-tools",
        "network-manager",
        "python3-minimal",
        "apt",
        "dpkg",
        "sudo",
        "policykit",
        "polkit",
        "xorg",
    )

    def available(self) -> bool:
        return bool(shutil.which("dpkg-query") and shutil.which("apt-get"))

    def scan(self, entries: Sequence[DesktopEntry]) -> list[AppRecord]:
        if not entries:
            return []
        paths = [str(entry.path) for entry in entries]
        result = run_command((_trusted_binary("dpkg-query"), "-S", *paths), timeout=15)
        owners: dict[str, str] = {}
        for line in result.stdout.splitlines():
            try:
                package_part, owned_path = line.split(": ", 1)
            except ValueError:
                continue
            package = package_part.split(",", 1)[0].split(":", 1)[0]
            if PACKAGE_ID_PATTERN.fullmatch(package):
                owners[owned_path] = package
        return self._records(entries, owners, "apt-get")

    def preview_removal(self, package: str, manager_name: str = "") -> RemovalPreview:
        result = run_command((self.manager_path(manager_name), "-s", "purge", package), timeout=20)
        if result.returncode != 0:
            return RemovalPreview(error="Die APT-Entfernung konnte nicht sicher simuliert werden.")
        removed = re.findall(r"^(?:Remv|Purg)\s+([^\s:]+)", result.stdout, flags=re.MULTILINE)
        if package not in removed:
            return RemovalPreview(error="Die APT-Simulation enthielt das ausgewählte Paket nicht.")
        return RemovalPreview(tuple(dict.fromkeys(removed)))

    def removal_command(self, package: str, manager_name: str = "") -> tuple[str, ...]:
        return ("/usr/bin/pkexec", self.manager_path(manager_name), "purge", "-y", package)

    def removal_label(self, package: str) -> str:
        return f"APT-Paket „{package}“ vollständig entfernen (purge)"


class RpmAdapter(PackageManagerAdapter, ABC):
    def available(self) -> bool:
        return bool(shutil.which("rpm") and any(shutil.which(name) for name in self.manager_names))

    def scan(self, entries: Sequence[DesktopEntry]) -> list[AppRecord]:
        if not entries:
            return []
        rpm_path = _trusted_binary("rpm")

        def find_owner(entry: DesktopEntry) -> tuple[str, str]:
            result = run_command(
                (rpm_path, "-q", "--file", str(entry.path), "--queryformat", "%{NAME}\\n"),
                timeout=5,
            )
            if result.returncode != 0:
                return str(entry.path), ""
            package = result.stdout.splitlines()[0].strip() if result.stdout.splitlines() else ""
            return str(entry.path), package if PACKAGE_ID_PATTERN.fullmatch(package) else ""

        workers = min(8, max(1, len(entries)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="restlos-rpm") as executor:
            owners = dict(executor.map(find_owner, entries))
        return self._records(entries, owners, self.manager_name())


class DnfAdapter(RpmAdapter):
    source = SourceKind.DNF
    key_prefix = "dnf"
    description = "DNF/RPM-Anwendung"
    manager_names = ("dnf5", "dnf")
    protected_packages = (
        "filesystem",
        "basesystem",
        "fedora-release",
        "fedora-workstation",
        "dnf",
        "dnf5",
        "rpm",
        "glibc",
        "systemd",
        "kernel",
        "grub2",
        "dracut",
        "networkmanager",
        "sudo",
        "polkit",
        "gnome-shell",
        "plasma-desktop",
    )

    def preview_removal(self, package: str, manager_name: str = "") -> RemovalPreview:
        result = run_command(
            (self.manager_path(manager_name), "--assumeno", "--cacheonly", "remove", package),
            timeout=30,
        )
        output = f"{result.stdout}\n{result.stderr}"
        aborted_normally = result.returncode == 1 and "operation aborted" in output.casefold()
        if result.returncode != 0 and not aborted_normally:
            return RemovalPreview(error="Die DNF-Entfernung konnte nicht sicher simuliert werden.")
        removed = _parse_dnf_removed(output)
        if package not in removed:
            return RemovalPreview(error="Die DNF-Simulation enthielt das ausgewählte Paket nicht.")
        return RemovalPreview(tuple(dict.fromkeys(removed)))

    def removal_command(self, package: str, manager_name: str = "") -> tuple[str, ...]:
        return ("/usr/bin/pkexec", self.manager_path(manager_name), "-y", "remove", package)

    def removal_label(self, package: str) -> str:
        return f"DNF/RPM-Paket „{package}“ samt unbenötigten Abhängigkeiten entfernen"


class ZypperAdapter(RpmAdapter):
    source = SourceKind.ZYPPER
    key_prefix = "zypper"
    description = "Zypper/RPM-Anwendung"
    manager_names = ("zypper",)
    protected_packages = (
        "filesystem",
        "patterns-base",
        "patterns-desktop",
        "rpm",
        "zypper",
        "libzypp",
        "glibc",
        "systemd",
        "kernel-default",
        "grub2",
        "dracut",
        "networkmanager",
        "sudo",
        "polkit",
        "gnome-shell",
        "plasma5-desktop",
        "plasma6-desktop",
    )

    def preview_removal(self, package: str, manager_name: str = "") -> RemovalPreview:
        result = run_command(
            (
                self.manager_path(manager_name),
                "--non-interactive",
                "remove",
                "--dry-run",
                "--clean-deps",
                package,
            ),
            timeout=30,
        )
        if result.returncode != 0:
            return RemovalPreview(error="Die Zypper-Entfernung konnte nicht sicher simuliert werden.")
        removed = _parse_zypper_removed(result.stdout)
        if package not in removed:
            return RemovalPreview(error="Die Zypper-Simulation enthielt das ausgewählte Paket nicht.")
        return RemovalPreview(tuple(dict.fromkeys(removed)))

    def removal_command(self, package: str, manager_name: str = "") -> tuple[str, ...]:
        return (
            "/usr/bin/pkexec",
            self.manager_path(manager_name),
            "--non-interactive",
            "remove",
            "--clean-deps",
            package,
        )

    def removal_label(self, package: str) -> str:
        return f"Zypper/RPM-Paket „{package}“ samt unbenötigten Abhängigkeiten entfernen"


class PacmanAdapter(PackageManagerAdapter):
    source = SourceKind.PACMAN
    key_prefix = "pacman"
    description = "pacman-Anwendung"
    manager_names = ("pacman",)
    protected_packages = (
        "base",
        "base-devel",
        "filesystem",
        "glibc",
        "linux",
        "linux-lts",
        "systemd",
        "pacman",
        "bash",
        "sudo",
        "polkit",
        "networkmanager",
        "grub",
        "mkinitcpio",
        "xorg-server",
        "gnome-shell",
        "plasma-desktop",
    )

    def available(self) -> bool:
        return bool(shutil.which("pacman"))

    def scan(self, entries: Sequence[DesktopEntry]) -> list[AppRecord]:
        owners: dict[str, str] = {}
        pacman_path = self.manager_path()
        for start in range(0, len(entries), 100):
            chunk = entries[start : start + 100]
            result = run_command((pacman_path, "-Qo", *(str(entry.path) for entry in chunk)), timeout=20)
            for line in result.stdout.splitlines():
                try:
                    owned_path, package_part = line.rsplit(" is owned by ", 1)
                except ValueError:
                    continue
                package = package_part.split(maxsplit=1)[0]
                if PACKAGE_ID_PATTERN.fullmatch(package):
                    owners[owned_path] = package
        return self._records(entries, owners, "pacman")

    def preview_removal(self, package: str, manager_name: str = "") -> RemovalPreview:
        result = run_command(
            (self.manager_path(manager_name), "-Rns", "--print", "--print-format", "%n", package),
            timeout=20,
        )
        if result.returncode != 0:
            return RemovalPreview(error="Die pacman-Entfernung konnte nicht sicher simuliert werden.")
        removed = [
            line.strip()
            for line in result.stdout.splitlines()
            if PACKAGE_ID_PATTERN.fullmatch(line.strip())
        ]
        if package not in removed:
            return RemovalPreview(error="Die pacman-Simulation enthielt das ausgewählte Paket nicht.")
        return RemovalPreview(tuple(dict.fromkeys(removed)))

    def removal_command(self, package: str, manager_name: str = "") -> tuple[str, ...]:
        return (
            "/usr/bin/pkexec",
            self.manager_path(manager_name),
            "-Rns",
            "--noconfirm",
            package,
        )

    def removal_label(self, package: str) -> str:
        return f"pacman-Paket „{package}“ samt unbenötigten Abhängigkeiten entfernen"


ADAPTERS: tuple[PackageManagerAdapter, ...] = (
    AptAdapter(),
    PacmanAdapter(),
    ZypperAdapter(),
    DnfAdapter(),
)
NATIVE_PACKAGE_SOURCES = frozenset(adapter.source for adapter in ADAPTERS)


def native_package_adapter(os_release_path: Path = Path("/etc/os-release")) -> PackageManagerAdapter | None:
    available = [adapter for adapter in ADAPTERS if adapter.available()]
    if not available:
        return None
    family = _os_release_family(os_release_path)
    family_sources = (
        ({"debian", "ubuntu"}, SourceKind.APT),
        ({"arch", "manjaro"}, SourceKind.PACMAN),
        ({"suse", "opensuse"}, SourceKind.ZYPPER),
        ({"fedora", "rhel", "centos"}, SourceKind.DNF),
    )
    for identifiers, source in family_sources:
        if identifiers & family:
            match = next((adapter for adapter in available if adapter.source == source), None)
            if match is not None:
                return match
    return available[0]


def adapter_for_source(source: SourceKind) -> PackageManagerAdapter | None:
    return next((adapter for adapter in ADAPTERS if adapter.source == source), None)


def _trusted_binary(name: str) -> str:
    candidate = shutil.which(name)
    if candidate:
        path = Path(candidate).absolute()
        if path.parent in _TRUSTED_BINARY_DIRECTORIES:
            return str(path)
    return str(Path("/usr/bin") / name)


def _os_release_family(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    values: set[str] = set()
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key not in {"ID", "ID_LIKE"}:
            continue
        values.update(value.strip().strip("'\"").casefold().split())
    return values


def _canonical_package_name(package: str) -> str:
    return re.sub(
        r"\.(?:x86_64|noarch|i[3-6]86|aarch64|ppc64le|s390x)$",
        "",
        package,
        flags=re.IGNORECASE,
    )


def _parse_dnf_removed(output: str) -> list[str]:
    removed: list[str] = []
    collecting = False
    for raw_line in output.splitlines():
        line = _ANSI_PATTERN.sub("", raw_line).strip()
        if re.match(r"^Removing(?: .*)?:$", line, re.IGNORECASE):
            collecting = True
            continue
        if not collecting:
            continue
        if line.startswith(("Transaction Summary", "Installing:", "Upgrading:", "Downgrading:")):
            collecting = False
            continue
        if not line or set(line) <= {"-", "="}:
            continue
        columns = line.split()
        if len(columns) < 3 or columns[0].casefold() in {"package", "name"}:
            continue
        package = _canonical_package_name(columns[0])
        if PACKAGE_ID_PATTERN.fullmatch(package):
            removed.append(package)
    return removed


def _parse_zypper_removed(output: str) -> list[str]:
    removed: list[str] = []
    collecting = False
    for raw_line in output.splitlines():
        line = _ANSI_PATTERN.sub("", raw_line).strip()
        if re.match(
            r"^The following (?:\d+ )?packages? (?:is|are) going to be REMOVED:",
            line,
            re.IGNORECASE,
        ):
            collecting = True
            continue
        if not collecting:
            continue
        if re.match(r"^\d+ packages? to remove", line, re.IGNORECASE):
            break
        for package in line.split():
            if PACKAGE_ID_PATTERN.fullmatch(package):
                removed.append(package)
    return removed
