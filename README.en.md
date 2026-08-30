# Restlos

[![Tests](https://github.com/jurkastl/restlos/actions/workflows/ci.yml/badge.svg)](https://github.com/jurkastl/restlos/actions/workflows/ci.yml)
[![GitHub Release](https://img.shields.io/github/v/release/jurkastl/restlos?include_prereleases)](https://github.com/jurkastl/restlos/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[Deutsch](README.md) · [Downloads](https://github.com/jurkastl/restlos/releases) · [Report a bug](https://github.com/jurkastl/restlos/issues)

Restlos is a graphical application remover for the major Linux distribution families. It combines applications and games from multiple installation systems in one interface and creates a visible, selectable removal plan before making any changes.

> **Public beta:** Restlos can permanently delete data. Carefully review the removal plan and back up important files and save games first. The application interface is currently German; contributions for full localisation are welcome.

## Detected sources

- APT/DEB, DNF/RPM, pacman, Zypper/RPM, Flatpak and Snap applications
- AppImages, Wine menu entries and manually installed applications
- Lutris, Steam and Heroic games
- complete Bottles environments and PlayOnLinux prefixes
- portable applications and unassigned Wine prefixes in `Games` and `Applications`
- launcher-managed game libraries on additional drives

For supported games, Restlos can include game folders, dedicated prefixes, manifests, workshop content, shader caches, local saves, screenshots, cover art, launchers and settings. Shared launcher directories and the default Wine prefix remain protected.

## Requirements

- Debian, Ubuntu and Zorin OS families using APT/DEB
- Fedora and RHEL families using DNF/RPM
- Arch Linux and Manjaro families using pacman
- openSUSE Leap and Tumbleweed using Zypper/RPM
- Python 3.10 or newer
- GTK 4 and PyGObject

Flatpak, Snap, AppImage, Wine and game-platform detection are independent of the native package manager. Distributions using other managers, including Alpine/APK, Gentoo/Portage, NixOS, Solus/eopkg and Void/xbps, are not yet declared fully supported.

## Install

Download the latest package from [GitHub Releases](https://github.com/jurkastl/restlos/releases). For version 1.2.0:

```bash
curl -LO https://github.com/jurkastl/restlos/releases/download/v1.2.0/Restlos-1.2.0.tar.gz
curl -LO https://github.com/jurkastl/restlos/releases/download/v1.2.0/Restlos-1.2.0.sha256
sha256sum --check Restlos-1.2.0.sha256
tar -xzf Restlos-1.2.0.tar.gz
cd Restlos-1.2.0
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

Restlos is then available from the application menu or as `~/.local/bin/restlos`.

## Safety model

Restlos never executes a launcher while inspecting an application. Package identifiers are validated and commands are executed as argument lists rather than shell text. APT, DNF, pacman and Zypper must first calculate the complete removal without changing the system. The package action is blocked if that preview fails or contains protected system packages. Broad or shared locations—including the home directory, shared Flatpak, Steam and Lutris storage, and the default Wine prefix—are blocked. Symbolic links are deleted without following their targets.

No third-party uninstaller can reliably assign every neutrally named legacy file to an application. Restlos therefore prefers missing an uncertain match over deleting unrelated data and always shows the plan first.

See [CONTRIBUTING.md](CONTRIBUTING.md) to contribute and [SECURITY.md](SECURITY.md) to report security-sensitive issues. Restlos is distributed under the [MIT License](LICENSE).
