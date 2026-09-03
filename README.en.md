# Restlos Uninstaller

> **Safe Linux App & Game Uninstaller**

[![Tests](https://github.com/jurkast/restlos/actions/workflows/ci.yml/badge.svg)](https://github.com/jurkast/restlos/actions/workflows/ci.yml)
[![GitHub Release](https://img.shields.io/github/v/release/jurkast/restlos?include_prereleases)](https://github.com/jurkast/restlos/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[Deutsch](README.md) · [Downloads](https://github.com/jurkast/restlos/releases) · [Report a bug](https://github.com/jurkast/restlos/issues)

**Restlos Uninstaller** is a safe graphical app and game uninstaller for the major Linux distribution families. It combines software from multiple installation systems in one interface and creates a visible, selectable removal plan before making any changes.

> **Public beta:** Restlos can permanently delete data. Carefully review the removal plan. Restlos can create a local Safety Backup of eligible settings and save data first.

## Detected sources

- APT/DEB, DNF/RPM, pacman, Zypper/RPM, Flatpak and Snap applications
- AppImages, Wine menu entries and manually installed applications
- Lutris, Steam and Heroic games
- complete Bottles environments and PlayOnLinux prefixes
- portable applications and unassigned Wine prefixes in `Games` and `Applications`
- launcher-managed game libraries on additional drives
- recoverable removal through the desktop trash and a graphical recovery centre
- optional Safety Backups of eligible settings, application data and save games before permanent deletion
- a complete German and English interface with an in-app language selector
- a post-removal scan that reports additional residual paths separately from intentionally retained data
- locked shared paths with an expandable list of known other applications and the specific references linking them
- a pre-removal recheck of file metadata, known application associations, package state and native removal simulations
- automatic daily release checks with an explicitly confirmed, verified in-app update

For supported games, Restlos can include game folders, dedicated prefixes, manifests, workshop content, shader caches, local saves, screenshots, cover art, launchers and settings. Shared launcher directories and the default Wine prefix remain protected.

## New safety checks (starting with version 1.8.0)

**Protected – who else needs this data?** shows other detected applications that explicitly reference the same path, a parent directory or something inside the removal target. Shared targets cannot be selected; their folder button remains available. Lutris Wine prefixes are included even when game directories differ. Similar names alone are not evidence of sharing. Unknown or unreadable installations are outside this check; no listed user is not proof of exclusive ownership. Flatpak/Snap purge actions are blocked when they could bypass shared-data protection.

An in-memory review snapshot is compared before process termination, after shutdown and optional backup, and directly before deleting each target. Application inventory, package versions and native removal simulations are also rechecked before package actions. Changes stop execution and require a fresh analysis and confirmation, including saves written during shutdown. **Analyze again** never retries deletion automatically. Completed actions are not automatically rolled back; any backup already created is retained.

File checks use directory/file identity, sizes, timestamps and link targets, not file contents. Links inside targets are not followed. Unreadable data, special files, mount points including bind mounts, or scan limits (at most 250,000 entries and 30 seconds per path check) prevent approval. Very large targets may require manual inspection outside Restlos. These checks are not continuous monitoring or a guarantee against every concurrent or malicious change. Authentication and execution in an external package manager are not atomic with Restlos' previous check.

## Requirements

- Debian, Ubuntu and Zorin OS families using APT/DEB
- Fedora and RHEL families using DNF/RPM
- Arch Linux and Manjaro families using pacman
- openSUSE Leap and Tumbleweed using Zypper/RPM
- Python 3.10 or newer
- GTK 4 and PyGObject

Flatpak, Snap, AppImage, Wine and game-platform detection are independent of the native package manager. Distributions using other managers, including Alpine/APK, Gentoo/Portage, NixOS, Solus/eopkg and Void/xbps, are not yet declared fully supported.

## Install

Download the latest package from [GitHub Releases](https://github.com/jurkast/restlos/releases).

### Zorin OS, Ubuntu, and Debian

Install the native Debian package through the graphical software manager or with APT. APT resolves the required GTK and Python dependencies automatically:

```bash
curl -LO https://github.com/jurkast/restlos/releases/download/v1.8.0/restlos-uninstaller_1.8.0-1_all.deb
curl -LO https://github.com/jurkast/restlos/releases/download/v1.8.0/restlos-uninstaller_1.8.0-1_all.deb.sha256
sha256sum --check restlos-uninstaller_1.8.0-1_all.deb.sha256
sudo apt install ./restlos-uninstaller_1.8.0-1_all.deb
```

The application-menu entry explicitly starts the system package. If an older per-user installation still exists at `~/.local/bin/restlos`, use `/usr/bin/restlos` to address the package version unambiguously.

### Universal archive

For Fedora, Arch Linux, openSUSE, or a per-user installation:

```bash
curl -LO https://github.com/jurkast/restlos/releases/download/v1.8.0/Restlos-1.8.0.tar.gz
curl -LO https://github.com/jurkast/restlos/releases/download/v1.8.0/Restlos-1.8.0.sha256
sha256sum --check Restlos-1.8.0.sha256
tar -xzf Restlos-1.8.0.tar.gz
cd Restlos-1.8.0
./install.sh
```

If GTK/PyGObject is missing, use the command for your distribution:

```bash
# Debian / Ubuntu / Zorin OS
sudo apt install python3-gi gir1.2-gtk-4.0 policykit-1

# Fedora / RHEL
sudo dnf install python3-gobject gtk4 polkit

# Arch Linux / Manjaro
sudo pacman -S python-gobject gtk4 polkit

# openSUSE
sudo zypper install python3-gobject typelib-1_0-Gtk-4_0 polkit
```

Restlos Uninstaller is then available from the application menu. For the universal archive, the update-compatible terminal command remains `~/.local/bin/restlos`.

## Inspect files before removal

Starting with version 1.7.0, **File locations…** shows known
program and data paths for the selected application. **Open folder** opens a
location in the default file manager. Each path in the removal plan also has a
folder button. Files, AppImages, desktop launchers and symbolic links are never
executed: their containing folder opens instead. The removal selection stays
unchanged, including deliberately deselected data.

Native packages may span multiple shared system folders. These are listed only
for inspection, not added as deletion targets. Missing paths, failed package
queries and missing file managers are handled; a warning appears when the list
reaches its limit of 250 locations. Restlos does not delete anything when opening
a folder; you can still make changes yourself in the file manager.

## Safety Backup, recovery and post-removal verification

Recoverable removal is the safe default in the graphical interface. Restlos moves selected user data through GIO to the desktop trash and records both the exact trash URI and original path. When permanent deletion is selected, the offered Safety Backup can copy eligible settings, application data and save games after related processes have stopped and before the first deletion or package action. Cache, installers, artwork, launchers, and application or game installation folders are excluded. If the requested backup fails, removal does not begin.

The application menu opens a recovery centre for restoring available Trash data and Safety Backups. Existing files or directories at an original location are never overwritten. Private archives are stored below `~/.local/state/restlos/backups` and are never uploaded.

After every removal, Restlos scans its known file sources again without repeating package-manager actions. Additional matches are reported as possible residual paths; paths deliberately deselected in the plan are reported separately as retained data.

Recovery only covers files and directories moved to Trash or stored in a Safety Backup. It does not reinstall native packages, Flatpaks or Snaps, and it does not recreate removed Lutris or Heroic library entries. Emptying the desktop trash outside Restlos also makes those Trash entries unavailable to the recovery centre.

Terminal users can inspect and restore transactions with:

```bash
restlos recovery list
restlos recovery restore RECOVERY-ID --yes
restlos remove "Application name" --yes --backup
restlos --language de list
```

Restlos uses the system language by default. Choose German or English from **Menu → Language** and restart the application, or override the language for one terminal invocation with `--language`.

## Updates

By default, Restlos checks the public GitHub release metadata no more than once per day when it starts. When a newer version is available, it shows the release notes and waits for explicit confirmation. The archive is accepted only after its version, asset names, trusted URLs, size, GitHub digest and published SHA-256 checksum have been validated. Installation uses a new version directory, leaving the previous version startable if anything fails.

Automatic checks can be disabled from the application menu, and a manual check can be started there at any time. No update is installed silently.

## Safety model

Restlos never executes a launcher while inspecting an application. Package identifiers are validated and commands are executed as argument lists rather than shell text. APT, DNF, pacman and Zypper must first calculate the complete removal without changing the system. The package action is blocked if that preview fails or contains protected system packages. Broad or shared locations—including the home directory, shared Flatpak, Steam and Lutris storage, and the default Wine prefix—are blocked. Symbolic links are deleted without following their targets.

Recovery verifies that the recorded Trash URI still belongs to the recorded original path and refuses to overwrite anything recreated at that location. Safety Backup creation does not follow symlinks or include special files; restoration validates the archive manifest and paths and stays inside the original user path. Archives and receipts use user-only permissions.

No third-party uninstaller can reliably assign every neutrally named legacy file to an application. Restlos therefore prefers missing an uncertain match over deleting unrelated data and always shows the plan first.

See [CONTRIBUTING.md](CONTRIBUTING.md) to contribute and [SECURITY.md](SECURITY.md) to report security-sensitive issues. Restlos is distributed under the [MIT License](LICENSE).
