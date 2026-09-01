# Distribution packages

## Debian, Ubuntu, and Zorin OS

Build the native, architecture-independent package from the repository root:

```bash
SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)" ./scripts/build-deb.sh dist
```

The package installs the application below `/usr/lib/restlos`, the command as
`/usr/bin/restlos`, the desktop entry below `/usr/share/applications`, the SVG
icon below the hicolor theme, and AppStream metadata below `/usr/share/metainfo`.
The wrapper sets `RESTLOS_UPDATE_CHANNEL=deb`, so updates remain under the
control of the system package manager.

Validate a built package without installing it:

```bash
dpkg-deb --info dist/restlos-uninstaller_*_all.deb
dpkg-deb --contents dist/restlos-uninstaller_*_all.deb
cd dist && sha256sum --check restlos-uninstaller_*_all.deb.sha256
```

Install and remove it on a Debian-family test system:

```bash
sudo apt install ./dist/restlos-uninstaller_*_all.deb
/usr/bin/restlos --version
sudo apt remove restlos-uninstaller
```

## Snap Store preparation

`snap/snapcraft.yaml` is a development manifest for a future official Snap.
Restlos needs to inspect host package databases, processes, and application
data, and therefore declares `confinement: classic`. A classically confined
Snap must receive manual approval from the Snap Store before publication.

The reserved application name should be `restlos-uninstaller`. Before the
first upload, build the Snap in a dedicated test environment, verify all native
package-manager previews on the host, request classic-confinement approval,
and only then promote it from an edge or beta channel.

Do not publish this manifest with strict confinement: a partially functional
uninstaller that cannot see host data or package-manager state would be
misleading and unsafe.
