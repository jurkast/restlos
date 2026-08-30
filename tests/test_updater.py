from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from restlos.updater import (
    CHECK_INTERVAL_SECONDS,
    RETRY_INTERVAL_SECONDS,
    ReleaseInfo,
    UpdateClient,
    UpdateError,
    UpdateState,
    checksum_from_file,
    extract_release_archive,
    parse_version,
    select_update,
)


def release_payload(version: str, *, draft: bool = False, prerelease: bool = True) -> dict[str, object]:
    archive_name = f"Restlos-{version}.tar.gz"
    prefix = f"https://github.com/jurkastl/restlos/releases/download/v{version}"
    return {
        "tag_name": f"v{version}",
        "name": f"Restlos {version} (Beta)",
        "body": "Neue Funktionen",
        "draft": draft,
        "prerelease": prerelease,
        "assets": [
            {
                "name": archive_name,
                "state": "uploaded",
                "size": 1234,
                "digest": "sha256:" + "a" * 64,
                "browser_download_url": f"{prefix}/{archive_name}",
            },
            {
                "name": f"Restlos-{version}.sha256",
                "state": "uploaded",
                "size": 87,
                "browser_download_url": f"{prefix}/Restlos-{version}.sha256",
            },
        ],
    }


class FakeResponse:
    def __init__(self, content: bytes, url: str) -> None:
        self.stream = io.BytesIO(content)
        self.url = url

    def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)

    def geturl(self) -> str:
        return self.url

    def close(self) -> None:
        self.stream.close()


class UpdaterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_version_parser_is_strict(self) -> None:
        self.assertEqual(parse_version("v1.2.3"), (1, 2, 3))
        with self.assertRaises(ValueError):
            parse_version("1.2")
        with self.assertRaises(ValueError):
            parse_version("1.2.3-beta")

    def test_highest_complete_release_is_selected(self) -> None:
        incomplete = release_payload("1.5.0")
        incomplete["assets"] = []
        selected = select_update(
            [release_payload("1.3.0"), incomplete, release_payload("1.4.0"), release_payload("9.0.0", draft=True)],
            "1.2.0",
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected.version, "1.4.0")
        self.assertEqual(selected.archive_digest, "a" * 64)

    def test_no_downgrade_or_same_version(self) -> None:
        self.assertIsNone(select_update([release_payload("1.2.0"), release_payload("1.1.0")], "1.2.0"))

    def test_checksum_must_name_exact_archive(self) -> None:
        content = ("b" * 64 + "  Restlos-1.3.0.tar.gz\n").encode("ascii")
        self.assertEqual(checksum_from_file(content, "Restlos-1.3.0.tar.gz"), "b" * 64)
        with self.assertRaises(UpdateError):
            checksum_from_file(content, "Restlos-1.4.0.tar.gz")

    def test_state_uses_daily_success_and_shorter_failure_retry(self) -> None:
        state = UpdateState(self.root / "update.json")
        self.assertTrue(state.automatic_checks_enabled())
        self.assertTrue(state.is_due(now=1000))
        state.record_attempt(True, now=1000)
        self.assertFalse(state.is_due(now=1000 + CHECK_INTERVAL_SECONDS - 1))
        self.assertTrue(state.is_due(now=1000 + CHECK_INTERVAL_SECONDS))
        state.record_attempt(False, now=200_000)
        self.assertFalse(state.is_due(now=200_000 + RETRY_INTERVAL_SECONDS - 1))
        self.assertTrue(state.is_due(now=200_000 + RETRY_INTERVAL_SECONDS))

    def test_automatic_checks_can_be_disabled(self) -> None:
        state = UpdateState(self.root / "update.json")
        state.set_automatic_checks(False)
        self.assertFalse(state.automatic_checks_enabled())
        self.assertFalse(state.is_due(now=1000))

    def test_client_reads_public_release_metadata(self) -> None:
        content = json.dumps([release_payload("1.3.0")]).encode("utf-8")

        def opener(request, **_kwargs):
            return FakeResponse(content, request.full_url)

        selected = UpdateClient("1.2.0", opener=opener).check()
        self.assertIsNotNone(selected)
        self.assertEqual(selected.version, "1.3.0")

    def test_untrusted_redirect_is_rejected(self) -> None:
        def opener(_request, **_kwargs):
            return FakeResponse(b"[]", "https://example.invalid/releases")

        with self.assertRaises(UpdateError):
            UpdateClient("1.2.0", opener=opener).check()

    def test_safe_archive_is_extracted(self) -> None:
        archive = self.root / "release.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            data = b"#!/bin/sh\n"
            info = tarfile.TarInfo("Restlos-1.3.0/install.sh")
            info.mode = 0o755
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
        release_home = extract_release_archive(archive, self.root / "extract", "1.3.0")
        self.assertTrue((release_home / "install.sh").is_file())
        self.assertTrue((release_home / "install.sh").stat().st_mode & 0o111)

    def test_archive_path_traversal_is_rejected(self) -> None:
        archive = self.root / "unsafe.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            data = b"bad"
            info = tarfile.TarInfo("Restlos-1.3.0/../../outside")
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
        with self.assertRaises(UpdateError):
            extract_release_archive(archive, self.root / "unsafe-extract", "1.3.0")
        self.assertFalse((self.root / "outside").exists())

    def test_archive_links_are_rejected(self) -> None:
        archive = self.root / "link.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            info = tarfile.TarInfo("Restlos-1.3.0/link")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            bundle.addfile(info)
        with self.assertRaises(UpdateError):
            extract_release_archive(archive, self.root / "link-extract", "1.3.0")

    def test_install_rejects_mismatching_github_and_checksum_digests(self) -> None:
        checksum = ("b" * 64 + "  Restlos-1.3.0.tar.gz\n").encode("ascii")

        def opener(request, **_kwargs):
            return FakeResponse(checksum, request.full_url)

        release = ReleaseInfo(
            version="1.3.0",
            title="Restlos 1.3.0",
            notes="",
            page_url="https://github.com/jurkastl/restlos/releases/tag/v1.3.0",
            archive_url="https://github.com/jurkastl/restlos/releases/download/v1.3.0/Restlos-1.3.0.tar.gz",
            checksum_url="https://github.com/jurkastl/restlos/releases/download/v1.3.0/Restlos-1.3.0.sha256",
            archive_digest="a" * 64,
            archive_size=1,
            prerelease=True,
        )
        with self.assertRaises(UpdateError):
            UpdateClient("1.2.0", opener=opener).install(release)

    def test_verified_archive_runs_installer_and_final_version_check(self) -> None:
        archive_buffer = io.BytesIO()
        with tarfile.open(fileobj=archive_buffer, mode="w:gz") as bundle:
            data = b"#!/bin/sh\nexit 0\n"
            info = tarfile.TarInfo("Restlos-1.3.0/install.sh")
            info.mode = 0o755
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
        archive = archive_buffer.getvalue()
        digest = hashlib.sha256(archive).hexdigest()
        checksum = f"{digest}  Restlos-1.3.0.tar.gz\n".encode("ascii")
        archive_url = "https://github.com/jurkastl/restlos/releases/download/v1.3.0/Restlos-1.3.0.tar.gz"
        checksum_url = "https://github.com/jurkastl/restlos/releases/download/v1.3.0/Restlos-1.3.0.sha256"

        def opener(request, **_kwargs):
            content = checksum if request.full_url == checksum_url else archive
            return FakeResponse(content, request.full_url)

        commands: list[list[str]] = []

        def runner(command, **_kwargs):
            commands.append(command)
            if command[-1] == "--version":
                return subprocess.CompletedProcess(command, 0, "Restlos 1.3.0\n", "")
            return subprocess.CompletedProcess(command, 0, "Installation abgeschlossen.\n", "")

        release = ReleaseInfo(
            version="1.3.0",
            title="Restlos 1.3.0",
            notes="",
            page_url="https://github.com/jurkastl/restlos/releases/tag/v1.3.0",
            archive_url=archive_url,
            checksum_url=checksum_url,
            archive_digest=digest,
            archive_size=len(archive),
            prerelease=True,
        )
        result = UpdateClient("1.2.0", opener=opener, runner=runner).install(release, home=self.root)
        self.assertEqual(result.version, "1.3.0")
        self.assertTrue(commands[0][0].endswith("/Restlos-1.3.0/install.sh"))
        self.assertEqual(commands[1], [str(self.root / ".local/bin/restlos"), "--version"])


if __name__ == "__main__":
    unittest.main()
